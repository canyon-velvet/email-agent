"""The run trace: an append-only log of everything that happens during a run.

Each run gets its own JSON Lines file, `<run_id>.jsonl`, with one event per line.
Events are only ever appended, never edited or deleted, so the trace is the full
record of a run. Views of it, such as the context sent to a model, are derived from
it and may leave things out; the trace itself never does.
"""

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The characters a run ID may contain. start_run only makes IDs like this, and
# read_trace refuses anything else, so an ID such as '../x' can't reach a file
# outside the trace directory.
_RUN_ID = re.compile(r'[A-Za-z0-9_-]+')


class RunNotFoundError(LookupError):
    """Raised when a trace directory has no run with the requested ID."""


@dataclass(frozen=True)
class TraceEvent:
    """One recorded event.

    `seq` counts from 1 within a run; `timestamp` is an ISO 8601 UTC time with its
    offset; `type` names the kind of event, such as 'tool_call'; `payload` holds its
    details as JSON-serializable data.
    """

    seq: int
    timestamp: str
    type: str
    payload: dict[str, Any]


class Trace:
    """The writing side of a run's trace. Get one from `start_run`.

    It offers no way to edit or delete events: only `append`. Use one Trace per run:
    `seq` is counted in memory, so a second writer on the same file would repeat
    numbers. Not thread-safe.
    """

    def __init__(self, run_id: str, path: Path) -> None:
        self.run_id = run_id
        self._path = path
        self._next_seq = 1

    def append(self, type: str, payload: dict[str, Any]) -> TraceEvent:
        """Record an event and return it, numbered and timestamped.

        Raises TypeError if the payload isn't JSON-serializable; nothing is written
        then, and the sequence number isn't used up.
        """
        event = TraceEvent(
            seq=self._next_seq,
            timestamp=datetime.now(UTC).isoformat(),
            type=type,
            payload=payload,
        )
        # Serialize before touching the file, so a bad payload writes nothing.
        # ensure_ascii (the default, kept explicit) escapes every non-ASCII character,
        # so the file is pure ASCII: a write cut short by a crash can't split a
        # multi-byte character and make the whole file undecodable.
        line = json.dumps(asdict(event), ensure_ascii=True)

        # Open, write and close for every event: closing flushes Python's buffer to
        # the OS, so a process crash loses nothing already appended. (Surviving a
        # power cut too would need os.fsync, at a cost on every event.)
        with open(self._path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        self._next_seq += 1

        return event


def start_run(trace_dir: Path) -> Trace:
    """Start a run: give it a unique ID and an empty trace file in `trace_dir`.

    The directory is created if needed. A run ID is its UTC start time plus a
    random suffix, so IDs sort by time and two runs in the same second differ.
    """
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    path = trace_dir / f'{run_id}.jsonl'
    path.touch(exist_ok=False)

    return Trace(run_id, path)


def read_trace(trace_dir: Path, run_id: str) -> list[TraceEvent]:
    """Return a run's events in the order they were appended.

    Raises RunNotFoundError for an unknown or malformed run ID. A last line cut off
    by a crash mid-write is skipped; a bad line anywhere else raises.
    """
    if not _RUN_ID.fullmatch(run_id):
        raise RunNotFoundError(run_id)

    path = trace_dir / f'{run_id}.jsonl'
    if not path.is_file():
        raise RunNotFoundError(run_id)

    events = []
    # Split on '\n' only: str.splitlines() also breaks on characters such as U+2028.
    # The writer escapes those, but the reader shouldn't depend on it.
    lines = path.read_text(encoding='utf-8').split('\n')
    for i, line in enumerate(lines):
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break  # torn by a crash mid-write
            raise
        trace_event = TraceEvent(**data)
        events.append(trace_event)

    return events

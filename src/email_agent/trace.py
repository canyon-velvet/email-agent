from dataclasses import asdict, dataclass
from typing import Any
from pathlib import Path
from datetime import UTC, datetime
import uuid
import re
import json

_RUN_ID = re.compile(r'[A-Za-z0-9_-]+')

class RunNotFoundError(LookupError): ...

@dataclass(frozen=True)
class TraceEvent:
    seq: int
    timestamp: str
    type: str
    payload: dict[str, Any]

class Trace:
    def __init__(self, run_id, path):
        self.run_id = run_id
        self._path = path
        self._next_seq = 1

    def append(self, type: str, payload: dict[str, Any]) -> TraceEvent:
        event = TraceEvent(
            seq=self._next_seq,
            timestamp=datetime.now(UTC).isoformat(),
            type=type,
            payload=payload
        )

        line = json.dumps(asdict(event))
        

        with open(self._path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
        self._next_seq += 1

        return event
        

def start_run(trace_dir: Path) -> Trace:
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    path = trace_dir / f'{run_id}.jsonl'
    path.touch(exist_ok=False)

    return Trace(run_id, path)

def read_trace(trace_dir: Path, run_id: str) -> list[TraceEvent]:
    if not _RUN_ID.fullmatch(run_id):
        raise RunNotFoundError(run_id)

    path = trace_dir / f'{run_id}.jsonl'
    if not path.is_file():
        raise RunNotFoundError(run_id)

    events = []
    lines = path.read_text(encoding='utf-8').split('\n')
    for i, line in enumerate(lines):
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break
            raise
        trace_event = TraceEvent(**data)
        events.append(trace_event)

    return events



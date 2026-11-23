"""The run trace: an append-only event log, one JSON Lines file per run."""

import re
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

from email_agent.trace import RunNotFoundError, read_trace, start_run


def test_starting_a_run_gives_a_unique_id_and_an_empty_trace(tmp_path):
    trace_dir = tmp_path / 'not' / 'there' / 'yet'

    first = start_run(trace_dir)
    second = start_run(trace_dir)  # straight after: a seconds-only clock would collide

    assert first.run_id != second.run_id
    assert re.fullmatch(r'[A-Za-z0-9_-]+', first.run_id)  # safe as a file name
    assert read_trace(trace_dir, first.run_id) == []


def test_events_come_back_in_order_with_seq_timestamp_type_and_payload(tmp_path):
    trace = start_run(tmp_path)

    written = [
        trace.append('model_request', {'messages': [{'role': 'user', 'text': 'café'}]}),
        trace.append('tool_call', {'name': 'read_email', 'args': {'id': 'abc'}}),
        trace.append('tool_result', {'ok': True, 'count': 3}),
    ]

    events = read_trace(tmp_path, trace.run_id)
    assert events == written
    assert [event.seq for event in events] == [1, 2, 3]
    assert [event.type for event in events] == ['model_request', 'tool_call', 'tool_result']
    assert events[0].payload == {'messages': [{'role': 'user', 'text': 'café'}]}
    times = [datetime.fromisoformat(event.timestamp) for event in events]
    assert all(time.utcoffset() == timedelta(0) for time in times)  # UTC, offset written out
    assert times == sorted(times)


def test_any_text_in_a_payload_comes_back_exactly(tmp_path):
    # Email text can hold anything: line breaks, NUL, emoji, and U+2028, which
    # str.splitlines() counts as a line break.
    text = 'café 🚀\r\nnext\x00line separator'
    trace = start_run(tmp_path)
    trace.append('tool_result', {'text': text})
    trace.append('step', {'n': 2})

    events = read_trace(tmp_path, trace.run_id)

    assert [event.payload for event in events] == [{'text': text}, {'n': 2}]


def test_append_returns_the_event_as_recorded(tmp_path):
    # The caller may change its payload afterwards, as context pruning will, and JSON
    # has no tuples: the returned event must still equal what the trace holds.
    trace = start_run(tmp_path)
    payload = {'messages': ['hi'], 'pair': ('a', 'b')}

    event = trace.append('model_request', payload)
    payload['messages'].append('pruned later')

    assert read_trace(tmp_path, trace.run_id) == [event]


def test_appending_never_rewrites_earlier_events(tmp_path):
    trace = start_run(tmp_path)
    path = tmp_path / f'{trace.run_id}.jsonl'
    trace.append('step', {'n': 1})
    before = path.read_bytes()

    trace.append('step', {'n': 2})

    after = path.read_bytes()
    assert after.startswith(before)  # earlier bytes untouched: appended, not rewritten
    assert after.count(b'\n') == 2  # one JSON line per event


def test_a_trace_offers_no_way_to_edit_or_delete_events(tmp_path):
    trace = start_run(tmp_path)

    assert {name for name in dir(trace) if not name.startswith('_')} == {'run_id', 'append'}


def test_an_event_that_cannot_be_stored_is_rejected_whole(tmp_path):
    trace = start_run(tmp_path)

    with pytest.raises(TypeError):
        trace.append('step', {'when': object()})  # not JSON-serializable

    # Nothing half-written, and no sequence number used up.
    assert read_trace(tmp_path, trace.run_id) == []
    assert trace.append('step', {'n': 1}).seq == 1
    assert len(read_trace(tmp_path, trace.run_id)) == 1


# Appends two events, prints the run ID, then dies at once: os._exit skips all cleanup,
# including flushing Python's file buffers, as a crash would.
CRASHING_RUN = """
import os, sys
from pathlib import Path
from email_agent.trace import start_run
trace = start_run(Path(sys.argv[1]))
trace.append('step', {'n': 1})
trace.append('step', {'n': 2})
print(trace.run_id, flush=True)
os._exit(1)
"""


def test_events_written_before_a_crash_are_still_readable(tmp_path):
    result = subprocess.run(
        [sys.executable, '-c', CRASHING_RUN, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stderr

    events = read_trace(tmp_path, result.stdout.strip())

    assert [event.payload for event in events] == [{'n': 1}, {'n': 2}]


def test_a_write_torn_by_a_crash_at_any_byte_is_skipped(tmp_path):
    trace = start_run(tmp_path)
    first = trace.append('step', {'text': 'café 🚀'})
    path = tmp_path / f'{trace.run_id}.jsonl'
    before = path.read_bytes()
    trace.append('step', {'text': 'café 🚀'})
    full = path.read_bytes()

    # Cut the second write short at every byte, as a crash mid-write could. If the
    # file held raw multi-byte characters, some cuts would split one and make the
    # whole file undecodable.
    for cut in range(len(before) + 1, len(full) - 1):
        path.write_bytes(full[:cut])
        assert read_trace(tmp_path, trace.run_id) == [first], f'cut at byte {cut}'


@pytest.mark.parametrize('more_events_after', [True, False])
def test_a_bad_line_written_whole_raises(tmp_path, more_events_after):
    # Only a last line missing its newline can be a torn write. A bad line that ends
    # in a newline was written whole: that's corruption, and must not be hidden.
    trace = start_run(tmp_path)
    trace.append('step', {'n': 1})
    with open(tmp_path / f'{trace.run_id}.jsonl', 'a', encoding='utf-8') as f:
        f.write('not json\n')
    if more_events_after:
        trace.append('step', {'n': 3})

    with pytest.raises(ValueError):
        read_trace(tmp_path, trace.run_id)


@pytest.mark.parametrize('run_id', ['no-such-run', '../outside', 'sub/../../outside', ''])
def test_reading_an_unknown_run_raises(tmp_path, run_id):
    trace_dir = tmp_path / 'traces'
    (trace_dir / 'sub').mkdir(parents=True)
    (tmp_path / 'outside.jsonl').write_text('')  # a file, but outside the trace directory

    with pytest.raises(RunNotFoundError):
        read_trace(trace_dir, run_id)

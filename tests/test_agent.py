"""The agent loop, through Seam 1: a fixture mailbox and a scripted model in; the run's
result and its trace out (ticket #12)."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pytest

from email_agent.agent import RunResult, run_agent
from email_agent.mail import DataOrigin, FixtureProvider
from email_agent.model import (
    AssistantMessage,
    ModelReply,
    ScriptedModelClient,
    ScriptExhaustedError,
    StopReason,
    ToolCall,
    ToolResult,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from email_agent.router import ModelRouter, RoutingError
from email_agent.trace import TraceEvent, read_trace, start_run

SYSTEM = 'You triage email.'
TASK = 'Triage my unread email.'
LUNCH = '19a8f3c2b1d04e01'  # unread messages in the contract mailbox
BUILD = '19a80b17c3f25b02'
INVOICE = '19a84d6b9e1c7a03'
SAM = '19a83c5d7e9f1a07'


class SpyRouter(ModelRouter):
    """A real router that also records the origins of every request it routes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.routed: list[set[DataOrigin]] = []

    def route(self, origins: Iterable[DataOrigin]):
        origins = list(origins)
        self.routed.append(set(origins))
        return super().route(origins)


@dataclass
class Run:
    result: RunResult
    events: list[TraceEvent]
    model: ScriptedModelClient
    router: SpyRouter


@pytest.fixture
def mailbox(contract_mailbox) -> FixtureProvider:
    return FixtureProvider(contract_mailbox)


@pytest.fixture
def run_script(mailbox, tmp_path):
    """Run the agent on the fixture mailbox, with a cloud model that replies as scripted."""

    def run(*replies: ModelReply, max_iterations: int = 20) -> Run:
        model = ScriptedModelClient(replies)
        router = SpyRouter({'cloud': model})
        trace = start_run(tmp_path)
        result = run_agent(
            TASK,
            mailbox=mailbox,
            router=router,
            trace=trace,
            system=SYSTEM,
            max_iterations=max_iterations,
        )
        return Run(result, read_trace(tmp_path, trace.run_id), model, router)

    return run


def call(id: str, name: str, **arguments) -> ToolCall:
    return ToolCall(id=id, name=name, arguments={'reason': 'Triage.', **arguments})


def wants(*calls: ToolCall, text: str = '', provider_data: Any = None) -> ModelReply:
    return ModelReply(
        message=AssistantMessage(text=text, tool_calls=calls, provider_data=provider_data),
        stop_reason=StopReason.TOOL_USE,
        usage=Usage(input_tokens=100, output_tokens=20),
    )


def says(text: str) -> ModelReply:
    return ModelReply(
        message=AssistantMessage(text=text),
        stop_reason=StopReason.END_TURN,
        usage=Usage(input_tokens=100, output_tokens=20),
    )


def disk_on_fire(message_id: str):
    raise RuntimeError('disk on fire')


def tool_results(messages) -> list[ToolResult]:
    return [r for m in messages if isinstance(m, ToolResultMessage) for r in m.results]


def results_sent_in(run: Run, request: int) -> ToolResultMessage:
    last = run.model.requests[request].messages[-1]
    assert isinstance(last, ToolResultMessage)
    return last


def test_a_run_lists_the_inbox_reads_a_message_and_finishes(run_script):
    listing = wants(
        call('c1', 'fetch_unread_emails'),
        text='Let me look at the inbox.',
        provider_data={'thinking': 'opaque to the loop'},
    )
    reading = wants(call('c2', 'read_email', message_id=LUNCH))
    run = run_script(listing, reading, says('Alice asks about lunch on Thursday.'))

    # The result is the last reply's text, not text from along the way.
    assert run.result == RunResult(status='end_turn', text='Alice asks about lunch on Thursday.')
    # Each request carries the whole conversation so far: the task, then each reply
    # followed by its tool results.
    last = run.model.requests[2]
    assert [type(m) for m in last.messages] == [
        UserMessage,
        AssistantMessage,
        ToolResultMessage,
        AssistantMessage,
        ToolResultMessage,
    ]
    # Each reply goes back exactly as it came: an API rejects a tool result whose call
    # is missing, and provider data (Claude's thinking) must survive the round trip.
    assert (last.messages[1], last.messages[3]) == (listing.message, reading.message)
    assert last.system == SYSTEM
    assert {'fetch_unread_emails', 'read_email'} <= {tool.name for tool in last.tools}
    [inbox] = results_sent_in(run, 1).results
    assert LUNCH in [email['id'] for email in json.loads(inbox.content)['emails']]
    [result] = results_sent_in(run, 2).results
    assert (result.call_id, result.is_error) == ('c2', False)
    assert json.loads(result.content)['subject'] == 'Re: Lunch on Thursday?'


def test_every_tool_call_in_a_reply_runs_and_the_results_go_back_together(run_script):
    run = run_script(
        wants(
            call('c1', 'read_email', message_id=LUNCH), call('c2', 'read_email', message_id=BUILD)
        ),
        says('Read both.'),
    )

    results = results_sent_in(run, 1).results
    assert [r.call_id for r in results] == ['c1', 'c2']
    assert [json.loads(r.content)['id'] for r in results] == [LUNCH, BUILD]


def test_the_iteration_limit_stops_the_run_and_runs_no_unanswered_calls(run_script):
    # A model that never stops asking for tools; only two replies are scripted, so a
    # third model call would fail the test rather than hang.
    run = run_script(
        wants(call('c1', 'fetch_unread_emails')),
        wants(
            call('c2', 'fetch_unread_emails'),
            text='Still working.',
            provider_data={'thinking': 'still thinking'},
        ),
        max_iterations=2,
    )

    assert run.result == RunResult(status='max_iterations', text='Still working.')
    assert len(run.model.requests) == 2
    # The last reply's call isn't run: its result could never go back to the model.
    assert [e.payload['id'] for e in run.events if e.type == 'tool_call'] == ['c1']
    # It's still in the trace, in the reply that asked for it, with its provider data:
    # no later request carries this last reply.
    last_reply = [e.payload for e in run.events if e.type == 'model_reply'][-1]
    assert [c['id'] for c in last_reply['tool_calls']] == ['c2']
    assert last_reply['provider_data'] == {'thinking': 'still thinking'}
    assert run.events[-1].payload == {'status': 'max_iterations', 'text': 'Still working.'}


def test_a_run_that_finishes_on_its_last_allowed_call_ends_normally(run_script):
    run = run_script(wants(call('c1', 'fetch_unread_emails')), says('Done.'), max_iterations=2)

    assert run.result == RunResult(status='end_turn', text='Done.')


def test_a_limit_of_zero_makes_no_model_call(run_script):
    run = run_script(max_iterations=0)

    assert run.result == RunResult(status='max_iterations', text='')
    assert run.model.requests == []
    assert [e.type for e in run.events] == ['run_finished']


@pytest.mark.parametrize('stop_reason', [StopReason.MAX_TOKENS, StopReason.REFUSAL])
def test_a_reply_that_stops_for_another_reason_ends_the_run_and_runs_no_tools(
    run_script, stop_reason
):
    # A reply cut off mid tool call may still carry it; tools run only on tool_use.
    cut_off = ModelReply(
        message=AssistantMessage(text='', tool_calls=(call('c1', 'fetch_unread_emails'),)),
        stop_reason=stop_reason,
        usage=Usage(),
    )

    run = run_script(cut_off)

    assert run.result.status == stop_reason
    assert not [e for e in run.events if e.type == 'tool_call']


@pytest.mark.parametrize(
    ('bad_call', 'error'),
    [
        (call('c1', 'read_email', message_id='no-such-id'), 'not_found'),
        (
            ToolCall(id='c1', name='read_email', arguments={'message_id': LUNCH}),
            'invalid_arguments',
        ),
        (call('c1', 'archive_everything'), 'unknown_tool'),
        (call('c1', 'archive_email', message_id='no-such-id'), 'not_found'),
    ],
)
def test_a_tool_error_goes_back_to_the_model_and_the_run_continues(run_script, bad_call, error):
    run = run_script(wants(bad_call), says('Done, with one error.'))

    assert run.result.status == 'end_turn'
    [result] = results_sent_in(run, 1).results
    assert result.is_error
    assert json.loads(result.content)['error'] == error


def test_an_unknown_tool_error_names_the_tools_there_are(run_script):
    run = run_script(wants(call('c1', 'archive_everything')), says('Done.'))

    [result] = results_sent_in(run, 1).results
    message = json.loads(result.content)['message']
    assert 'archive_everything' in message
    assert 'fetch_unread_emails' in message and 'read_email' in message


def test_the_trace_records_each_request_reply_call_and_output_in_order(run_script):
    run = run_script(wants(call('c1', 'read_email', message_id=LUNCH)), says('Done.'))

    assert [e.type for e in run.events] == [
        'model_request',
        'model_reply',
        'tool_call',
        'tool_output',
        'model_request',
        'model_reply',
        'run_finished',
    ]
    request, reply, tool_call, tool_output, second_request = (e.payload for e in run.events[:5])
    # The request: its routing decision, and the full context sent.
    assert (request['tag'], request['destination']) == ('synthetic', 'cloud')
    assert request['reason']
    assert request['system'] == SYSTEM
    assert request['messages'] == [{'role': 'user', 'text': TASK}]
    assert {'fetch_unread_emails', 'read_email'} <= set(request['tools'])
    # The reply, with its token usage.
    assert reply['stop_reason'] == 'tool_use'
    assert reply['usage'] == {
        'input_tokens': 100,
        'output_tokens': 20,
        'cache_read_tokens': 0,
        'cache_write_tokens': 0,
    }
    # The call in full, `reason` included, and what it returned.
    assert tool_call == {
        'id': 'c1',
        'name': 'read_email',
        'arguments': {'reason': 'Triage.', 'message_id': LUNCH},
    }
    assert (tool_output['call_id'], tool_output['is_error']) == ('c1', False)
    assert tool_output['origin'] == 'synthetic'
    assert tool_output['output']['subject'] == 'Re: Lunch on Thursday?'
    # Messages are marked with their role, so the trace reads back unambiguously.
    assert [m['role'] for m in second_request['messages']] == [
        'user',
        'assistant',
        'tool_results',
    ]
    assert run.events[-1].payload == {'status': 'end_turn', 'text': 'Done.'}


@pytest.mark.parametrize(
    ('script', 'crash', 'last_event'),
    [
        # The model call fails: no second reply is scripted.
        ([wants(call('c1', 'fetch_unread_emails'))], ScriptExhaustedError, 'model_request'),
        # A tool hits a bug.
        ([wants(call('c1', 'read_email', message_id=LUNCH))], RuntimeError, 'tool_call'),
    ],
)
def test_a_crash_mid_run_still_leaves_what_was_asked_in_the_trace(
    mailbox, tmp_path, monkeypatch, script, crash, last_event
):
    # Each step is recorded before it runs, so the trace shows what failed.
    monkeypatch.setattr(mailbox, 'get_message', disk_on_fire)
    trace = start_run(tmp_path)

    with pytest.raises(crash) as raised:
        run_agent(
            TASK,
            mailbox=mailbox,
            router=ModelRouter({'cloud': ScriptedModelClient(script)}),
            trace=trace,
            system=SYSTEM,
            max_iterations=2,
        )

    # Exactly this crash: ScriptExhaustedError is also a RuntimeError.
    assert raised.type is crash
    assert read_trace(tmp_path, trace.run_id)[-1].type == last_event


def triage(run_script) -> Run:
    """A scripted triage of the four unread messages, ending in one draft."""
    return run_script(
        wants(call('c1', 'fetch_unread_emails')),
        wants(
            call('c2', 'star_email', message_id=LUNCH),
            call('c3', 'draft_reply', message_id=LUNCH, body='Noon on Thursday works.'),
            call('c4', 'apply_label', message_id=INVOICE, label_name='Finance'),
        ),
        wants(
            call('c5', 'archive_email', message_id=BUILD),
            call('c6', 'mark_as_read', message_id=SAM),
        ),
        says('Triaged 4 messages; one reply is drafted for you to review.'),
    )


def changes(
    before: dict[str, frozenset[str]], after: dict[str, frozenset[str]]
) -> dict[str, tuple[set[str], set[str]]]:
    """The labels each changed message gained and lost."""
    return {
        id: (set(after[id] - before[id]), set(before[id] - after[id]))
        for id in before
        if after[id] != before[id]
    }


def test_a_triage_run_leaves_the_mailbox_in_the_expected_state(run_script, mailbox):
    # Judged by the outcome, the labels and drafts, not by the exact calls made.
    before = mailbox.snapshot()

    run = triage(run_script)

    assert run.result.status == 'end_turn'
    assert changes(before, mailbox.snapshot()) == {
        LUNCH: ({'STARRED'}, set()),
        INVOICE: ({'Finance'}, set()),
        BUILD: (set(), {'INBOX'}),
        SAM: (set(), {'UNREAD'}),
    }
    [draft] = mailbox.list_drafts()
    assert (draft.in_reply_to, draft.body) == (LUNCH, 'Noon on Thursday works.')
    assert not [r for m in run.model.requests for r in tool_results(m.messages) if r.is_error]


def test_every_mailbox_change_is_in_the_trace_with_the_call_that_caused_it(run_script, mailbox):
    before = mailbox.snapshot()

    run = triage(run_script)

    # Replaying the trace's reported changes on the starting labels gives the final
    # labels: nothing changed the mailbox without showing up in the trace.
    calls = {e.payload['id']: e.payload for e in run.events if e.type == 'tool_call'}
    replayed = {id: set(labels) for id, labels in before.items()}
    drafts = []
    for event in run.events:
        if event.type != 'tool_output':
            continue
        output, call = event.payload['output'], calls[event.payload['call_id']]
        if 'added' in output:
            assert output['message_id'] == call['arguments']['message_id']
            replayed[output['message_id']] |= set(output['added'])
            replayed[output['message_id']] -= set(output['removed'])
        if 'draft_id' in output:
            assert output['in_reply_to'] == call['arguments']['message_id']
            drafts.append(output['draft_id'])
    assert replayed == {id: set(labels) for id, labels in mailbox.snapshot().items()}
    assert drafts == [d.id for d in mailbox.list_drafts()]


def test_the_agent_is_offered_exactly_the_mail_tools_and_none_can_send(run_script):
    # Least privilege: a new tool, such as one that sends or forwards mail, fails
    # this test until it's added here on purpose.
    run = run_script(says('Nothing to do.'))

    assert {tool.name for tool in run.model.requests[0].tools} == {
        'fetch_unread_emails',
        'read_email',
        'star_email',
        'mark_as_read',
        'archive_email',
        'apply_label',
        'report_spam',
        'trash_email',
        'draft_reply',
    }


def test_every_request_is_routed_with_the_origin_of_everything_so_far(run_script):
    # The first request has no tool output yet; it takes the mailbox's origin, so a
    # fixture run is `synthetic` from the start. An unknown-tool error holds no mail
    # data, so it is `public`; its origin is still passed on.
    run = run_script(wants(call('c1', 'archive_everything')), says('Done.'))

    assert run.router.routed == [{'synthetic'}, {'synthetic', 'public'}]
    assert [e.payload['origin'] for e in run.events if e.type == 'tool_output'] == ['public']
    assert [e.payload['tag'] for e in run.events if e.type == 'model_request'] == [
        'synthetic',
        'synthetic',
    ]


def test_real_email_with_only_a_cloud_model_is_refused_before_any_model_call(mailbox, tmp_path):
    mailbox.data_origin = 'email_content'
    model = ScriptedModelClient([says('This must never be asked.')])

    with pytest.raises(RoutingError):
        run_agent(
            TASK,
            mailbox=mailbox,
            router=ModelRouter({'cloud': model}),
            trace=start_run(tmp_path),
            system=SYSTEM,
        )

    assert model.requests == []

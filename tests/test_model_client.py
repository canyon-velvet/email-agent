"""The model-client interface and its scripted test double (ticket #9)."""

import subprocess
import sys

import pytest

from email_agent.model import (
    AssistantMessage,
    ModelReply,
    ModelRequest,
    ScriptedModelClient,
    ScriptExhaustedError,
    StopReason,
    ToolCall,
    ToolResult,
    ToolResultMessage,
    ToolSchema,
    Usage,
    UserMessage,
)

SYSTEM = 'You triage email.'
READ_EMAIL = ToolSchema(
    name='read_email',
    description='Read one email by its ID.',
    input_schema={
        'type': 'object',
        'properties': {'id': {'type': 'string'}},
        'required': ['id'],
    },
)


def text_reply(text: str) -> ModelReply:
    return ModelReply(
        message=AssistantMessage(text=text),
        stop_reason=StopReason.END_TURN,
        usage=Usage(input_tokens=100, output_tokens=10),
    )


def ask(text: str) -> ModelRequest:
    return ModelRequest(system=SYSTEM, messages=(UserMessage(text),))


def test_a_tool_round_trip_through_the_scripted_client():
    call = ToolCall(id='call_1', name='read_email', arguments={'id': '19a8f3c2b1d04e01'})
    wants_tool = ModelReply(
        # provider_data is opaque: whatever the provider needs back verbatim on the
        # next request, such as Claude's thinking blocks. The loop never reads it.
        message=AssistantMessage(
            text='Let me read it.', tool_calls=(call,), provider_data=('opaque',)
        ),
        stop_reason=StopReason.TOOL_USE,
        usage=Usage(input_tokens=120, output_tokens=30),
    )
    done = ModelReply(
        message=AssistantMessage(text='Alice asks about lunch on Thursday.'),
        stop_reason=StopReason.END_TURN,
        usage=Usage(input_tokens=40, output_tokens=12, cache_read_tokens=150),
    )
    client = ScriptedModelClient([wants_tool, done])
    result = ToolResultMessage(
        results=(ToolResult(call_id='call_1', content='Are you free for lunch?'),)
    )

    # The loop: send the history, append the reply as it came, run the tool, send again.
    history = [UserMessage('Summarize the lunch email.')]
    first = client.complete(
        ModelRequest(system=SYSTEM, messages=tuple(history), tools=(READ_EMAIL,))
    )
    history += [first.message, result]
    second = client.complete(
        ModelRequest(system=SYSTEM, messages=tuple(history), tools=(READ_EMAIL,))
    )

    assert (first, second) == (wants_tool, done)
    # provider_data counts in equality, so tests can check it went back unchanged.
    assert AssistantMessage(text='Let me read it.', tool_calls=(call,)) != wants_tool.message
    assert client.requests[1] == ModelRequest(
        system=SYSTEM,
        messages=(UserMessage('Summarize the lunch email.'), wants_tool.message, result),
        tools=(READ_EMAIL,),
    )
    assert result.results[0].is_error is False  # results are successes unless marked


def test_replies_come_back_in_order_and_every_request_is_recorded():
    replies = [text_reply('one'), text_reply('two'), text_reply('three')]
    client = ScriptedModelClient(replies)
    requests = [ask('first'), ask('second'), ask('third')]

    got = [client.complete(request) for request in requests]

    assert got == replies
    assert client.requests == requests


def test_a_recorded_request_stays_as_it_was_sent():
    # The types are frozen, but a dict inside one can still change in place, as a
    # pruner shortening an older tool call's arguments would. The record must keep
    # what was actually sent.
    call = ToolCall(id='call_1', name='read_email', arguments={'id': 'abc', 'reason': 'long'})
    client = ScriptedModelClient([text_reply('ok')])
    history = (UserMessage('hi'), AssistantMessage(text='', tool_calls=(call,)))

    client.complete(ModelRequest(system=SYSTEM, messages=history))
    call.arguments['reason'] = 'short'

    recorded = client.requests[0].messages[1]
    assert isinstance(recorded, AssistantMessage)
    assert recorded.tool_calls[0].arguments == {'id': 'abc', 'reason': 'long'}


def test_the_script_is_copied_so_later_changes_to_it_have_no_effect():
    replies = [text_reply('one')]
    client = ScriptedModelClient(replies)
    replies.append(text_reply('two'))

    client.complete(ask('first'))

    with pytest.raises(ScriptExhaustedError):
        client.complete(ask('second'))


@pytest.mark.parametrize('scripted', [0, 2])
def test_running_out_of_replies_raises_an_error_naming_the_request(scripted):
    client = ScriptedModelClient([text_reply(f'reply {n}') for n in range(scripted)])
    for _ in range(scripted):
        client.complete(ask('again'))

    # A missing reply must fail the test loudly, saying which call had none.
    with pytest.raises(ScriptExhaustedError, match=f'request {scripted + 1}'):
        client.complete(ask('one too many'))
    assert len(client.requests) == scripted + 1  # the unanswered request is recorded too


def test_the_interface_imports_no_provider_sdk():
    # The loop, the router and the tests depend on these neutral types only. A
    # provider's SDK belongs in that provider's own client module.
    code = (
        'import sys, email_agent.model; '
        "print(sorted({name.split('.')[0] for name in sys.modules} & {'anthropic', 'openai'}))"
    )
    result = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True, timeout=30
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[]'

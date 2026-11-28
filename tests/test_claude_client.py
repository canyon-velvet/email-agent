"""The Claude model client, over a fake HTTP transport: nothing touches the network (#14).

A real Anthropic SDK client runs against `httpx2.MockTransport`, so these tests see
exactly what would go over the wire, and answer with canned Messages API responses.
"""

import json
import subprocess
import sys
import time
import traceback
from typing import Any

import anthropic
import httpx2
import pytest

from email_agent.agent import run_agent
from email_agent.mail import FixtureProvider
from email_agent.model import (
    AssistantMessage,
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequest,
    ModelRequestError,
    StopReason,
    ToolCall,
    ToolResult,
    ToolResultMessage,
    ToolSchema,
    Usage,
    UserMessage,
)
from email_agent.model.claude_client import ClaudeClient
from email_agent.router import ModelRouter
from email_agent.trace import start_run

KEY = 'sk-ant-test-0123456789-SECRET'
MODEL = 'claude-opus-5-5'
SYSTEM = 'You triage email.'
TASK = 'Triage my unread email.'
READ_EMAIL = ToolSchema(
    name='read_email',
    description='Read one message in full.',
    input_schema={
        'type': 'object',
        'properties': {'message_id': {'type': 'string', 'description': 'The ID.'}},
        'required': ['message_id'],
        'additionalProperties': False,
    },
)

# Thinking text is empty under Opus 5.5's default display, but may be a summary.
THINKING = {'type': 'thinking', 'thinking': 'Both look urgent.', 'signature': 'sig-opaque-abc'}
REDACTED = {'type': 'redacted_thinking', 'data': 'encrypted-opaque-xyz'}
TEXT = {'type': 'text', 'text': 'Let me read both.'}
USE_1 = {'type': 'tool_use', 'id': 'toolu_1', 'name': 'read_email', 'input': {'message_id': 'm1'}}
USE_2 = {'type': 'tool_use', 'id': 'toolu_2', 'name': 'read_email', 'input': {'message_id': 'm2'}}


def message(*content: dict, stop_reason: str = 'end_turn', **usage: Any) -> dict:
    """A Messages API response body."""
    return {
        'id': 'msg_1',
        'type': 'message',
        'role': 'assistant',
        'model': MODEL,
        'content': list(content),
        'stop_reason': stop_reason,
        'stop_sequence': None,
        'usage': {
            'input_tokens': 10,
            'output_tokens': 5,
            'cache_creation_input_tokens': None,
            'cache_read_input_tokens': None,
            **usage,
        },
    }


def api_error(status: int, error_type: str) -> httpx2.Response:
    return httpx2.Response(
        status,
        json={
            'type': 'error',
            'error': {'type': error_type, 'message': f'Something about {error_type}.'},
            'request_id': f'req_{status}',
        },
        # Tells the SDK not to retry, so error tests don't wait on its backoff.
        headers={'request-id': f'req_{status}', 'x-should-retry': 'false'},
    )


class FakeAPI:
    """Answers each request with the next scripted response, and records what was sent."""

    def __init__(self, *responses: dict | httpx2.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, httpx2.Response):
            return response
        return httpx2.Response(200, json=response, headers={'request-id': 'req_ok'})

    def body(self, n: int) -> dict:
        return json.loads(self.requests[n].content)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    # Only our key: nothing else in the environment may change what the SDK does.
    for name in ('ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_PROFILE'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', KEY)


def claude(api: FakeAPI, model: str = MODEL, **options: Any) -> ClaudeClient:
    transport = httpx2.MockTransport(api.handle)
    http_client = anthropic.DefaultHttpxClient(transport=transport)
    return ClaudeClient(model, http_client=http_client, **options)


def ask(api: FakeAPI, *messages) -> Any:
    return claude(api).complete(
        ModelRequest(system=SYSTEM, messages=messages or (UserMessage(TASK),), tools=(READ_EMAIL,))
    )


def traceback_of(error: BaseException) -> str:
    """The traceback as it would print, with every chained cause."""
    return ''.join(traceback.format_exception(error))


def without_nulls(blocks: list[dict]) -> list[dict]:
    """Blocks as sent back, ignoring null fields, which mean the same as absent ones."""
    return [{k: v for k, v in block.items() if v is not None} for block in blocks]


def test_a_request_is_sent_in_the_messages_api_shape():
    api = FakeAPI(message(TEXT))

    ask(api)

    # Exactly these fields: nothing Opus 5.5 rejects (a thinking budget, a forced
    # tool_choice, temperature) and no strict mode, which minLength would break.
    assert api.body(0) == {
        'model': MODEL,
        'max_tokens': 16000,
        'system': SYSTEM,
        'messages': [{'role': 'user', 'content': TASK}],
        'tools': [
            {
                'name': 'read_email',
                'description': 'Read one message in full.',
                'input_schema': READ_EMAIL.input_schema,
            }
        ],
    }


@pytest.mark.parametrize('value', [KEY, f'{KEY}\n', f'  {KEY} '])
def test_the_api_key_comes_from_the_environment(monkeypatch, value):
    # Spaces or a newline around the key, easy to get from a .env file, are dropped. Sent
    # as is, they break the header, and the HTTP layer's error quotes the whole key.
    monkeypatch.setenv('ANTHROPIC_API_KEY', value)
    api = FakeAPI(message(TEXT))

    ask(api)

    assert api.requests[0].headers['authorization'] == f'Bearer {KEY}'


def test_the_request_uses_the_model_and_max_tokens_the_client_was_made_with():
    api = FakeAPI(message(TEXT))

    claude(api, 'claude-sonnet-5-5', max_tokens=2000).complete(
        ModelRequest(system=SYSTEM, messages=(UserMessage(TASK),))
    )

    assert (api.body(0)['model'], api.body(0)['max_tokens']) == ('claude-sonnet-5-5', 2000)


@pytest.mark.parametrize('value', [None, '', '   '])
def test_a_missing_api_key_fails_clearly_when_the_client_is_made(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('ANTHROPIC_API_KEY')
    else:
        monkeypatch.setenv('ANTHROPIC_API_KEY', value)

    with pytest.raises(ModelAuthError, match='ANTHROPIC_API_KEY'):
        ClaudeClient(MODEL)


def test_the_client_declares_itself_a_cloud_model():
    # The router learns where a client sends data from the client, not from config.
    assert ClaudeClient.destination == 'cloud'


def test_a_reply_becomes_text_tool_calls_a_stop_reason_and_usage():
    api = FakeAPI(
        message(
            THINKING,
            TEXT,
            USE_1,
            USE_2,
            stop_reason='tool_use',
            cache_read_input_tokens=3,
            cache_creation_input_tokens=7,
        )
    )

    reply = ask(api)

    assert reply.message.text == 'Let me read both.'  # never the thinking
    assert reply.message.tool_calls == (
        ToolCall(id='toolu_1', name='read_email', arguments={'message_id': 'm1'}),
        ToolCall(id='toolu_2', name='read_email', arguments={'message_id': 'm2'}),
    )
    assert reply.stop_reason == StopReason.TOOL_USE
    assert reply.usage == Usage(
        input_tokens=10, output_tokens=5, cache_read_tokens=3, cache_write_tokens=7
    )


def test_the_text_is_every_text_block_joined():
    first = {'type': 'text', 'text': 'Reading it. '}
    second = {'type': 'text', 'text': 'Then deciding.'}

    reply = ask(FakeAPI(message(first, USE_1, second, stop_reason='tool_use')))

    assert reply.message.text == 'Reading it. Then deciding.'


def test_missing_cache_counts_are_zero():
    reply = ask(FakeAPI(message(TEXT)))

    assert reply.usage == Usage(input_tokens=10, output_tokens=5)


def test_claudes_reply_goes_back_exactly_as_it_came_with_the_tool_results_after_it():
    api = FakeAPI(
        message(THINKING, REDACTED, TEXT, USE_1, USE_2, stop_reason='tool_use'), message(TEXT)
    )
    first = ask(api)
    results = ToolResultMessage(
        (
            ToolResult(call_id='toolu_1', content='{"subject": "Lunch"}'),
            ToolResult(call_id='toolu_2', content='{"error": "not_found"}', is_error=True),
        )
    )

    ask(api, UserMessage(TASK), first.message, results)

    user, assistant, tool_results = api.body(1)['messages']
    assert user == {'role': 'user', 'content': TASK}
    # Every block in order, the thinking signature intact: Opus 5.5 checks it.
    assert assistant['role'] == 'assistant'
    assert without_nulls(assistant['content']) == [THINKING, REDACTED, TEXT, USE_1, USE_2]
    # All results in one user message, holding nothing but the results.
    assert tool_results['role'] == 'user'
    assert [
        (b['type'], b['tool_use_id'], b['content'], b.get('is_error', False))
        for b in tool_results['content']
    ] == [
        ('tool_result', 'toolu_1', '{"subject": "Lunch"}', False),
        ('tool_result', 'toolu_2', '{"error": "not_found"}', True),
    ]


def test_a_replys_provider_data_is_plain_json_for_the_trace():
    reply = ask(FakeAPI(message(THINKING, TEXT, USE_1, stop_reason='tool_use')))

    data = reply.message.provider_data
    assert json.loads(json.dumps(data)) == data


@pytest.mark.parametrize('provider_data', [None, {'local': 'another client made this'}])
@pytest.mark.parametrize(
    ('text', 'blocks'),
    [
        ('Checking.', [{'type': 'text', 'text': 'Checking.'}]),
        ('', []),  # the API refuses an empty text block
    ],
)
def test_a_message_another_client_made_is_rebuilt_from_its_text_and_tool_calls(
    provider_data, text, blocks
):
    api = FakeAPI(message(TEXT))
    other = AssistantMessage(
        text=text,
        tool_calls=(ToolCall(id='c1', name='read_email', arguments={'message_id': 'm1'}),),
        provider_data=provider_data,
    )
    results = ToolResultMessage((ToolResult(call_id='c1', content='{}'),))

    ask(api, UserMessage(TASK), other, results)

    assistant = api.body(0)['messages'][1]
    assert assistant['content'] == [
        *blocks,
        {'type': 'tool_use', 'id': 'c1', 'name': 'read_email', 'input': {'message_id': 'm1'}},
    ]


@pytest.mark.parametrize(
    ('api_reason', 'stop_reason'),
    [
        ('end_turn', StopReason.END_TURN),
        ('tool_use', StopReason.TOOL_USE),
        ('max_tokens', StopReason.MAX_TOKENS),
        ('refusal', StopReason.REFUSAL),
        ('model_context_window_exceeded', StopReason.CONTEXT_WINDOW_EXCEEDED),
    ],
)
def test_each_stop_reason_maps_to_ours(api_reason, stop_reason):
    reply = ask(FakeAPI(message(TEXT, stop_reason=api_reason)))

    assert reply.stop_reason == stop_reason


def test_the_context_window_stop_reason_names_itself():
    assert StopReason.CONTEXT_WINDOW_EXCEEDED == 'context_window_exceeded'


@pytest.mark.parametrize('api_reason', ['pause_turn', 'stop_sequence'])
def test_a_stop_reason_this_client_never_asks_for_is_an_error(api_reason):
    # pause_turn comes only from server tools, and stop_sequence only from stop
    # sequences; we send neither, so getting one means something is wrong.
    with pytest.raises(ModelError, match=api_reason):
        ask(FakeAPI(message(TEXT, stop_reason=api_reason)))


def test_a_refusal_may_have_no_content():
    reply = ask(FakeAPI(message(stop_reason='refusal')))

    assert reply.message.text == ''
    assert reply.message.tool_calls == ()
    assert reply.stop_reason == StopReason.REFUSAL


@pytest.mark.parametrize(
    ('status', 'error_type', 'error'),
    [
        (400, 'invalid_request_error', ModelRequestError),
        (404, 'not_found_error', ModelRequestError),  # a mistyped model name
        (413, 'request_too_large', ModelRequestError),
        (422, 'invalid_request_error', ModelRequestError),
        (401, 'authentication_error', ModelAuthError),
        (403, 'permission_error', ModelAuthError),
        (429, 'rate_limit_error', ModelRateLimitError),
        (500, 'api_error', ModelError),
        (529, 'overloaded_error', ModelError),
    ],
)
def test_an_api_error_surfaces_as_our_own_error_with_what_went_wrong(status, error_type, error):
    with pytest.raises(ModelError) as raised:
        ask(FakeAPI(api_error(status, error_type)))

    assert type(raised.value) is error  # a rate limit is never mistaken for a bad request
    assert not isinstance(raised.value, anthropic.AnthropicError)  # the loop needs no SDK
    message = str(raised.value)
    assert str(status) in message
    assert f'Something about {error_type}.' in message
    assert f'req_{status}' in message  # the request ID, for a support ticket
    assert KEY not in traceback_of(raised.value)


def test_a_connection_failure_surfaces_as_a_model_error(monkeypatch):
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError('no network', request=request)

    monkeypatch.setattr(time, 'sleep', lambda seconds: None)  # skip the SDK's retry backoff
    client = ClaudeClient(
        MODEL,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(unreachable)),
    )

    with pytest.raises(ModelError) as raised:
        client.complete(ModelRequest(system=SYSTEM, messages=(UserMessage(TASK),)))

    assert type(raised.value) is ModelError
    assert not isinstance(raised.value, anthropic.AnthropicError)
    assert KEY not in traceback_of(raised.value)


def test_importing_the_model_package_does_not_load_the_sdk():
    # Only the Claude client needs the SDK: the loop, the router and the scripted client
    # import the neutral types alone.
    code = 'import sys, email_agent.agent, email_agent.model; print("anthropic" in sys.modules)'
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)

    assert (result.returncode, result.stdout.strip()) == (0, 'False'), result.stderr


def test_a_run_through_the_loop_records_claudes_thinking_and_never_the_key(
    contract_mailbox, tmp_path
):
    fetch = {
        'type': 'tool_use',
        'id': 'toolu_1',
        'name': 'fetch_unread_emails',
        'input': {'reason': 'Start triage.'},
    }
    api = FakeAPI(message(THINKING, fetch, stop_reason='tool_use'), message(TEXT))
    trace = start_run(tmp_path)

    result = run_agent(
        TASK,
        mailbox=FixtureProvider(contract_mailbox),
        router=ModelRouter({'cloud': claude(api)}),
        trace=trace,
        system=SYSTEM,
    )

    assert result.status == 'end_turn'
    assert without_nulls(api.body(1)['messages'][1]['content']) == [THINKING, fetch]
    recorded = (tmp_path / f'{trace.run_id}.jsonl').read_text()
    assert 'sig-opaque-abc' in recorded  # the thinking block is in the trace
    assert KEY not in recorded

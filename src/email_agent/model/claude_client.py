from typing import ClassVar, Any
from email_agent.router import Destination
from email_agent.model.model_client import ModelAuthError, ModelRequest, ToolSchema, Message, UserMessage, AssistantMessage, ToolResultMessage, ModelReply, ToolCall, ModelRateLimitError, ModelRequestError, ModelError, StopReason, Usage
import os
import anthropic
import httpx2

STOP_REASONS = {
    'end_turn': StopReason.END_TURN,
    'tool_use': StopReason.TOOL_USE,
    'max_tokens': StopReason.MAX_TOKENS,
    'refusal': StopReason.REFUSAL,
    'model_context_window_exceeded': StopReason.CONTEXT_WINDOW_EXCEEDED,
}

class ClaudeClient:
    destination: ClassVar[Destination] = 'cloud'

    def __init__(self, model: str, *, max_tokens: int = 16000, http_client: httpx2.Client | None = None):
        self._model = model
        self._max_tokens = max_tokens
        key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not key.strip():
            raise ModelAuthError('ANTHROPIC_API_KEY is not set')
        self._client = anthropic.Anthropic(api_key=key, http_client=http_client)

    def complete(self, request: ModelRequest) -> ModelReply:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=request.system,
                messages=[_message_to_api(m) for m in request.messages],
                tools=[_tool_to_api(t) for t in request.tools]
            )
        except anthropic.RateLimitError as e:
            raise ModelRateLimitError(_describe(e)) from e
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise ModelAuthError(_describe(e)) from e
        except (
            anthropic.BadRequestError,
            anthropic.ContentTooLargeError,
            anthropic.UnprocessableEntityError,
        ) as e:
            raise ModelRequestError(_describe(e)) from e
        except anthropic.APIStatusError as e:
            raise ModelError(_describe(e)) from e
        except anthropic.APIConnectionError as e:
            raise ModelError(f'Could not reach the Claude API: {e}') from e

        if response.stop_reason not in STOP_REASONS:
            raise ModelError(f'Claude stopped for an unexpected reason: {response.stop_reason}')

        blocks = [b.model_dump(mode='json', exclude_none=True) for b in response.content]
        text = ''.join([b['text'] for b in blocks if b['type'] == 'text'])
        tool_calls = tuple(ToolCall(id=b['id'], name=b['name'], arguments=b['input']) for b in blocks if b['type'] == 'tool_use')
        message = AssistantMessage(text=text, tool_calls=tool_calls, provider_data={'claude_content': blocks})
        usage = response.usage
        return ModelReply(
            message=message,
            stop_reason=STOP_REASONS[response.stop_reason],
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
            )
        )

def _tool_to_api(tool: ToolSchema) -> dict[str, Any]:
    return {
        'name': tool.name,
        'description': tool.description,
        'input_schema': tool.input_schema
    }

def _message_to_api(message: Message) -> dict[str, Any]:
    if isinstance(message, UserMessage):
        return {
            'role': 'user',
            'content': message.text
        }

    if isinstance(message, ToolResultMessage):
        return {
            'role': 'user',
            'content': [{
                'type': 'tool_result',
                'tool_use_id': res.call_id,
                'content': res.content,
                'is_error': res.is_error
            } for res in message.results]
        }
    if isinstance(message, AssistantMessage):
        data = message.provider_data
        if isinstance(data, dict) and 'claude_content' in data:
            return {'role': 'assistant', 'content': data['claude_content']}
        content: list[dict[str, Any]] = []
        if message.text:
            content.append({'type': 'text', 'text': message.text})
        for call in message.tool_calls:
            content.append(
                {'type': 'tool_use', 'id': call.id, 'name': call.name, 'input': call.arguments}
            )
        return {'role': 'assistant', 'content': content}

def _describe(error: anthropic.APIStatusError) -> str:
    """What went wrong, for an error message: never the key, always the request ID."""
    return f'Claude API error {error.status_code}: {error.api_message} (request ID {error.request_id})'



        

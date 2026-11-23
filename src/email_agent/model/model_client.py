"""The model-client interface: provider-neutral types for talking to a model.

The agent loop, the router and the tests use only these types. Each provider's
client (Claude, a local model, the scripted test double) translates them to and from
its own API in its own module, so no provider SDK type appears here.

All the types are frozen, and every sequence is a tuple. The dict fields
(`input_schema`, `arguments`) and `provider_data` can still be changed in place, so
treat them as read-only and build changed copies instead (`dataclasses.replace`
with a new dict). Anything holding one of those dicts (a ToolCall, a ToolSchema, or
a message or request containing one) can't be hashed, so don't use these types as
set members or dict keys.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSchema:
    """A tool the model may call: its name, when to use it, and its inputs.

    `input_schema` is a JSON Schema for the call's arguments. Tools declare no
    output schema: the model only reads a tool's result, as text.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """The model asking to run a tool. `id` links the call to its `ToolResult`."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class UserMessage:
    """A message from the user (or the harness acting for them)."""

    text: str


@dataclass(frozen=True)
class AssistantMessage:
    """A message from the model: its text, and any tools it wants run.

    `provider_data` is opaque to everything but the client that made it. It holds
    whatever that provider needs sent back verbatim on later requests, such as
    Claude's thinking blocks. The neutral fields describe the turn; `provider_data`
    adds only what they can't express, and a client ignores `provider_data` it
    didn't produce (after the router switches models, say). Clients should keep it
    JSON-serializable so the trace can record it. The loop appends the message to
    its history as it came.
    """

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    provider_data: Any = None


@dataclass(frozen=True)
class ToolResult:
    """What running one tool call returned, as text; `is_error` marks a failure."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolResultMessage:
    """The results of all the tool calls in one assistant message, sent back together."""

    results: tuple[ToolResult, ...]


Message = UserMessage | AssistantMessage | ToolResultMessage


class StopReason(StrEnum):
    """Why the model stopped writing."""

    END_TURN = 'end_turn'  # finished its reply
    TOOL_USE = 'tool_use'  # wants its tool calls run
    MAX_TOKENS = 'max_tokens'  # cut off at the output limit
    REFUSAL = 'refusal'  # declined the request


@dataclass(frozen=True)
class Usage:
    """Token counts for one request.

    `input_tokens` excludes the input read from or written to the prompt cache, which
    are counted separately; total input is the sum of the three.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class ModelRequest:
    """Everything one model call is sent: the system prompt, the history, the tools."""

    system: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSchema, ...] = ()


@dataclass(frozen=True)
class ModelReply:
    """The model's answer to one request.

    A MAX_TOKENS or REFUSAL reply may still carry incomplete tool calls; clients keep
    them in the message, and the loop runs `tool_calls` only on TOOL_USE.
    """

    message: AssistantMessage
    stop_reason: StopReason
    usage: Usage


class ModelClient(Protocol):
    """Sends one request to a model and returns its reply."""

    def complete(self, request: ModelRequest) -> ModelReply: ...

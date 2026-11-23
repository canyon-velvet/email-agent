from dataclasses import dataclass
from typing import Any, Protocol
from enum import StrEnum

@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]

@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class UserMessage:
    text: str

@dataclass(frozen=True)
class AssistantMessage:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    provider_data: Any = None

@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False

@dataclass(frozen=True)
class ToolResultMessage:
    results: tuple[ToolResult, ...]

Message = UserMessage | AssistantMessage | ToolResultMessage

class StopReason(StrEnum):
    END_TURN = 'end_turn'
    TOOL_USE = 'tool_use'
    MAX_TOKENS = 'max_tokens'
    REFUSAL = 'refusal'

@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

@dataclass(frozen=True)
class ModelRequest:
    system: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSchema, ...] = ()

@dataclass(frozen=True)
class ModelReply:
    message: AssistantMessage
    stop_reason: StopReason
    usage: Usage

class ModelClient(Protocol):
    def complete(self, request: ModelRequest) -> ModelReply: ...

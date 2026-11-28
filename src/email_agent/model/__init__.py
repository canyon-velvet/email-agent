"""Model clients: one provider-neutral interface, and its implementations.

Provider clients that import an SDK (Claude, a local model) are not imported here,
so importing this package never loads a provider SDK.
"""

from email_agent.model.model_client import (
    AssistantMessage,
    Message,
    ModelAuthError,
    ModelClient,
    ModelError,
    ModelRateLimitError,
    ModelReply,
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
from email_agent.model.scripted_client import ScriptedModelClient, ScriptExhaustedError

__all__ = [
    'ToolSchema',
    'ToolCall',
    'UserMessage',
    'AssistantMessage',
    'ToolResult',
    'ToolResultMessage',
    'Message',
    'StopReason',
    'Usage',
    'ModelRequest',
    'ModelReply',
    'ModelClient',
    'ScriptedModelClient',
    'ScriptExhaustedError',
    'ModelError',
    'ModelAuthError',
    'ModelRateLimitError',
    'ModelRequestError',
]

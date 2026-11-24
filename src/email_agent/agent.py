"""The agent loop: ask the model, run the tools it asks for, and repeat until it stops.

Each iteration routes the request by the origin of everything the conversation holds,
sends the whole history, and runs every tool call in the reply, sending all the
results back together. The model never touches the mailbox: it only asks, through
tool calls, and the loop does the work. Every step is written to the trace as it
happens, so even a run that crashes leaves a record of what was sent.
"""

from dataclasses import asdict, dataclass
from typing import Any

from email_agent.mail.mail_provider import DataOrigin, MailProvider
from email_agent.model.model_client import (
    AssistantMessage,
    Message,
    ModelRequest,
    StopReason,
    ToolResult,
    ToolResultMessage,
    UserMessage,
)
from email_agent.router import ModelRouter
from email_agent.tools.inbox_tools import FetchUnreadEmails, ReadEmail
from email_agent.tools.tool import ToolError, ToolOutcome
from email_agent.trace import Trace


@dataclass(frozen=True)
class RunResult:
    """How a run ended, and the model's last text.

    `status` is the model's stop reason ('end_turn', 'max_tokens' or 'refusal'), or
    'max_iterations' if the run reached its limit before the model stopped.
    """

    status: str
    text: str


# A message's role in the trace, so it reads back unambiguously.
ROLES = {UserMessage: 'user', AssistantMessage: 'assistant', ToolResultMessage: 'tool_results'}


def as_json(message: Message) -> dict[str, Any]:
    """A message as trace data: its fields, plus its role."""
    return {'role': ROLES[type(message)], **asdict(message)}


def run_agent(
    task: str,
    *,
    mailbox: MailProvider,
    router: ModelRouter,
    trace: Trace,
    system: str,
    max_iterations: int = 20,
) -> RunResult:
    """Run the agent on `task` against `mailbox`, until the model stops or the limit.

    `max_iterations` caps the model calls. Tools run only on a `tool_use` reply, and
    not after the last allowed call, because their results could never go back. A
    tool error goes back to the model as a result, and the run continues.

    The run's origins start from the mailbox's, so its first request is tagged by the
    mailbox's data before any tool has run. Raises RoutingError if the router allows
    a request nowhere: a real mailbox with only a cloud model fails before any call.
    """
    tools = {tool.name: tool for tool in (FetchUnreadEmails(mailbox), ReadEmail(mailbox))}
    schemas = tuple(tool.schema() for tool in tools.values())
    origins: list[DataOrigin] = [mailbox.data_origin]
    history: list[Message] = [UserMessage(task)]

    status = 'max_iterations'
    text = ''
    for i in range(1, max_iterations + 1):
        client, decision = router.route(origins)
        trace.append(
            'model_request',
            {
                **asdict(decision),
                'system': system,
                'tools': [schema.name for schema in schemas],
                'messages': [as_json(m) for m in history],
            },
        )
        reply = client.complete(ModelRequest(system=system, messages=tuple(history), tools=schemas))
        text = reply.message.text
        trace.append(
            'model_reply',
            {
                **asdict(reply.message),
                'stop_reason': reply.stop_reason,
                'usage': asdict(reply.usage),
            },
        )
        history.append(reply.message)
        if reply.stop_reason != StopReason.TOOL_USE:
            status = reply.stop_reason
            break

        if i == max_iterations:
            break

        results: list[ToolResult] = []
        for call in reply.message.tool_calls:
            tool = tools.get(call.name)
            trace.append('tool_call', asdict(call))
            if tool is None:
                message = f"No tool named '{call.name}'. Use one of: {', '.join(tools)}."
                outcome = ToolOutcome(ToolError(error='unknown_tool', message=message), 'public')
            else:
                outcome = tool.call(call.arguments)
            is_error = isinstance(outcome.output, ToolError)
            origin = outcome.origin
            trace.append(
                'tool_output',
                {
                    'call_id': call.id,
                    'output': outcome.output.model_dump(),
                    'is_error': is_error,
                    'origin': origin,
                },
            )

            origins.append(origin)
            results.append(ToolResult(call.id, outcome.output.model_dump_json(), is_error=is_error))
        history.append(ToolResultMessage(tuple(results)))
    trace.append('run_finished', {'status': status, 'text': text})

    return RunResult(status, text)

from dataclasses import dataclass, asdict
from email_agent.mail.mail_provider import MailProvider, DataOrigin
from email_agent.router import ModelRouter
from email_agent.trace import Trace
from email_agent.model.model_client import Message, ModelRequest, StopReason, ToolResult, ToolResultMessage, UserMessage, AssistantMessage
from email_agent.tools.inbox_tools import FetchUnreadEmails, ReadEmail
from email_agent.tools.tool import ToolError, ToolOutcome
from typing import Any

@dataclass(frozen=True)
class RunResult:
    status: str
    text: str

ROLES = {UserMessage: 'user', AssistantMessage: 'assistant', ToolResultMessage: 'tool_results'}

def as_json(message: Message) -> dict[str, Any]:
    return {'role': ROLES[type(message)], **asdict(message)}

def run_agent(task: str, *, mailbox: MailProvider, router: ModelRouter, trace: Trace, system: str, max_iterations: int = 20) -> RunResult:
    tools = {tool.name: tool for tool in (FetchUnreadEmails(mailbox), ReadEmail(mailbox))}
    schemas = tuple(tool.schema() for tool in tools.values())
    origins: list[DataOrigin] = [mailbox.data_origin]
    history: list[Message] =[UserMessage(task)]

    status = 'max_iterations'
    for i in range(1, max_iterations + 1):
        client, decision = router.route(origins)
        trace.append('model_request', {**asdict(decision), 'system': system, 'tools': [schema.name for schema in schemas], 'messages': [as_json(m) for m in history]})
        reply = client.complete(ModelRequest(system=system, messages=tuple(history), tools=schemas))
        trace.append('model_reply', {**asdict(reply.message), 'stop_reason': reply.stop_reason, 'usage': asdict(reply.usage)})
        history.append(reply.message)
        if reply.stop_reason != StopReason.TOOL_USE:
            status = reply.stop_reason
            break

        if i == max_iterations:
            break

        results = []
        for call in reply.message.tool_calls:
            tool = tools.get(call.name)
            trace.append('tool_call', asdict(call))
            if tool is None:
                 outcome = ToolOutcome(ToolError(error='unknown_tool', message='TODO'), 'public')
            else:
                outcome = tool.call(call.arguments)
            is_error = isinstance(outcome.output, ToolError)
            origin = outcome.origin
            trace.append('tool_output', {'call_id': call.id, 'output': outcome.output.model_dump(), 'is_error': is_error, 'origin': origin})
                
            origins.append(origin)
            results.append(ToolResult(call.id, outcome.output.model_dump_json(), is_error=is_error))
        history.append(ToolResultMessage(tuple(results)))
    trace.append('run_finished', {'status': status, 'text': reply.message.text})

    return RunResult(status, reply.message.text)

        

        
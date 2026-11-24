"""Agent tools: the tool protocol, and the tools built on it."""

from email_agent.tools.inbox_tools import FetchUnreadEmails, ReadEmail
from email_agent.tools.tool import Tool, ToolError, ToolInput, ToolOutcome

__all__ = ['Tool', 'ToolInput', 'ToolError', 'ToolOutcome', 'FetchUnreadEmails', 'ReadEmail']

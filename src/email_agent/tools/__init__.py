"""Agent tools: the tool protocol, and the tools built on it."""

from email_agent.tools.action_tools import (
    ApplyLabel,
    ArchiveEmail,
    DraftReply,
    MarkAsRead,
    ReportSpam,
    StarEmail,
    TrashEmail,
)
from email_agent.tools.inbox_tools import FetchUnreadEmails, ReadEmail
from email_agent.tools.tool import Tool, ToolError, ToolInput, ToolOutcome

MAIL_TOOLS: tuple[type[Tool], ...] = (
    FetchUnreadEmails,
    ReadEmail,
    StarEmail,
    MarkAsRead,
    ArchiveEmail,
    ApplyLabel,
    ReportSpam,
    TrashEmail,
    DraftReply,
)

__all__ = ['MAIL_TOOLS', 'Tool', 'ToolInput', 'ToolError', 'ToolOutcome', 'FetchUnreadEmails', 'ReadEmail']

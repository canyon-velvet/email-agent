from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Message:
    """One full message, as reading it shows: headers plus the body as readable text.

    All fields are plain text. A missing header is an empty string; `date` is the raw
    Date header. HTML-only bodies are converted to text, so `body` never has markup.
    """

    id: str
    thread_id: str
    sender: str
    to: str
    date: str
    subject: str
    body: str


@dataclass(frozen=True)
class MessageSummary:
    """One message as an inbox listing shows it: ids, headers, and snippet, never the body.

    All fields are plain text. A missing header is an empty string, and `snippet` is
    unescaped (Gmail's API returns it HTML-escaped, e.g. `&#39;`).
    """

    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str


class MessageNotFoundError(LookupError):
    """Raised when a mailbox has no message with the requested ID."""


# Where data came from. The model router (#10) uses it to decide which models may see it.
DataOrigin = Literal['email_content', 'synthetic', 'public']


class MailProvider(Protocol):
    """A mailbox the agent reads and changes: fixture files now, Gmail later.

    Callers depend only on this interface, never on a concrete provider.
    """

    data_origin: DataOrigin

    def list_unread(self) -> list[MessageSummary]:
        """Return unread inbox messages (labelled INBOX and UNREAD), newest first.

        Summaries carry snippets only, never message bodies.
        """
        ...

    def get_message(self, message_id: str) -> Message:
        """Return the full message with this ID.

        Raises MessageNotFoundError if the mailbox has no such message.
        """
        ...

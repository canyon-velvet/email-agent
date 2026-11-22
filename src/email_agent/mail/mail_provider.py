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
class Draft:
    """An unsent reply, stored on the thread of the message it answers.

    `in_reply_to` is the ID of that message. Nothing in the harness can send a
    draft: v1 never sends mail (spec #3).
    """

    id: str
    thread_id: str
    in_reply_to: str
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

    Label changes follow Gmail, where labels are not folders: being read, archived,
    or out of spam is the *absence* of a label. Each change maps onto one Gmail call
    (`messages.modify`, `drafts.create`), is idempotent, and raises
    MessageNotFoundError for an unknown message ID. Labels are reported by name.
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

    def star(self, message_id: str) -> None:
        """Add STARRED."""
        ...

    def mark_read(self, message_id: str) -> None:
        """Remove UNREAD."""
        ...

    def archive(self, message_id: str) -> None:
        """Remove INBOX. The message keeps its other labels (Gmail's "All Mail")."""
        ...

    def report_spam(self, message_id: str) -> None:
        """Add SPAM and remove INBOX."""
        ...

    def apply_label(self, message_id: str, label_name: str) -> None:
        """Add the user label called `label_name`, creating it first if it doesn't exist."""
        ...

    def create_draft(self, message_id: str, body: str) -> Draft:
        """Store an unsent reply to this message on its thread, and return it."""
        ...

    def list_drafts(self) -> list[Draft]:
        """Return every draft created so far, oldest first."""
        ...

    def snapshot(self) -> dict[str, frozenset[str]]:
        """Return every message's label names, by message ID, for diffs and evals.

        It is a copy: later changes to the mailbox leave it unchanged.
        """
        ...

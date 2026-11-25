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

    `in_reply_to` is that message's provider ID, not its RFC 2822 `Message-ID` header
    (which a Gmail provider must look up to set `In-Reply-To` when it creates the
    draft). Nothing in the harness can send a draft: v1 never sends mail (spec #3).
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

# Gmail's system labels, whose IDs equal their names. No user label may use one of
# these names; they change only through MailProvider's dedicated methods, or not at
# all. Gmail's reserved list isn't exhaustive, so a Gmail provider should also turn
# its 400 "Invalid label name" into ValueError.
SYSTEM_LABELS = frozenset(
    {
        'INBOX',
        'SPAM',
        'TRASH',
        'UNREAD',
        'STARRED',
        'IMPORTANT',
        'SENT',
        'DRAFT',
        'CHAT',
        'CATEGORY_PERSONAL',
        'CATEGORY_SOCIAL',
        'CATEGORY_PROMOTIONS',
        'CATEGORY_UPDATES',
        'CATEGORY_FORUMS',
    }
)


class MailProvider(Protocol):
    """A mailbox the agent reads and changes: fixture files now, Gmail later.

    Callers depend only on this interface, never on a concrete provider.

    Label changes follow Gmail, where labels are not folders: being read, archived,
    or out of spam is the *absence* of a label. Label changes map onto Gmail's
    `messages.modify` (plus `labels.create` for a new user label), or `messages.trash`
    for `trash`, and are idempotent. `create_draft` maps onto `drafts.create` and is
    not: each call makes a new draft.
    Every change raises MessageNotFoundError for an unknown message ID. Labels are
    reported by name.
    """

    data_origin: DataOrigin

    def list_unread(self) -> list[MessageSummary]:
        """Return unread inbox messages (labelled INBOX and UNREAD), newest first.

        A trashed message is never listed, even if it keeps INBOX and UNREAD.
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

    def trash(self, message_id: str) -> None:
        """Move the message to the trash: add TRASH, and drop it from the inbox listing.

        Only TRASH is promised: Gmail's docs don't say what trash does to the other
        labels. The fixture keeps them, so restoring a message (removing TRASH) puts it
        back where it was; a Gmail provider should confirm Gmail does the same.
        Its own method, not an `apply_label`, so a permission policy can gate it.
        """
        ...

    def apply_label(self, message_id: str, label_name: str) -> None:
        """Add the user label called `label_name`, creating it first if it doesn't exist.

        Raises ValueError for a blank name or a system label name such as INBOX (in any
        case, ignoring surrounding spaces): those change through the methods above, and
        Gmail rejects them too.
        """
        ...

    def create_draft(self, message_id: str, body: str) -> Draft:
        """Store an unsent reply to this message on its thread, and return it."""
        ...

    def list_drafts(self) -> list[Draft]:
        """Return the drafts created through this provider, in creation order."""
        ...

    def snapshot(self) -> dict[str, frozenset[str]]:
        """Return every message's label names, by message ID, for diffs and evals.

        Covers every message, including spam and trash, but not drafts. It is a copy:
        later changes to the mailbox leave it unchanged.
        """
        ...

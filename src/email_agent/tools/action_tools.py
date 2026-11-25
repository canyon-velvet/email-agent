"""The triage action tools: every change the agent can make to the mailbox.

Each label action reports the change it made as a LabelChange, so the trace shows
every mailbox change next to the tool call that caused it. There is no tool that
sends or forwards mail: draft_reply only saves a draft for the user to review.
"""

from pydantic import BaseModel, Field, field_validator

from email_agent.mail.mail_provider import SYSTEM_LABELS
from email_agent.tools.tool import Tool, ToolInput


class LabelChange(BaseModel):
    """The labels a label action added to and removed from one message, by name.

    It reports what the action applied, not a before/after diff: starring a message
    that is already starred still reports STARRED as added.
    """

    message_id: str
    added: list[str] = []
    removed: list[str] = []


class DraftCreated(BaseModel):
    """A new draft reply: its ID, and the message and thread it answers."""

    draft_id: str
    thread_id: str
    in_reply_to: str


class MessageInput(ToolInput):
    """The input of an action on one message."""

    message_id: str = Field(
        description='The ID of the message, exactly as fetch_unread_emails gave it.'
    )


class ApplyLabelInput(MessageInput):
    label_name: str = Field(
        description=(
            'The name of a user label, such as "Finance" or "Travel". It is created '
            'if it does not exist yet. System labels such as INBOX, STARRED or SPAM are '
            'not allowed: use the tool for that action instead.'
        )
    )

    @field_validator('label_name')
    @classmethod
    def check_label_name(cls, value: str) -> str:
        """Refuse a blank or system label name, here as bad arguments the model can fix,
        and drop surrounding spaces so ' Finance ' and 'Finance' are the same label."""
        name = value.strip()
        if not name or name.upper() in SYSTEM_LABELS:
            raise ValueError(
                'must be a user label name, not blank or a system label such as INBOX; '
                'to star, mark as read, archive, report spam or trash a message, use '
                'that tool instead'
            )
        return name


class DraftReplyInput(MessageInput):
    body: str = Field(
        min_length=1,
        description=(
            'The reply, as plain text, ready for the user to review and send. State only '
            'facts you have from the email or from the user; if you do not have them, '
            'write a short holding reply instead.'
        ),
    )


class StarEmail(Tool):
    name = 'star_email'
    description = (
        "Star a message, to flag it for the user's attention or follow-up. It stays in "
        'the inbox. Returns the labels added.'
    )
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.star(args.message_id)
        return LabelChange(message_id=args.message_id, added=['STARRED'])


class MarkAsRead(Tool):
    name = 'mark_as_read'
    description = (
        'Mark a message as read, when it needs no attention from the user. It stays in '
        'the inbox unless you also archive it. Returns the labels removed.'
    )
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.mark_read(args.message_id)
        return LabelChange(message_id=args.message_id, removed=['UNREAD'])


class ArchiveEmail(Tool):
    name = 'archive_email'
    description = (
        'Archive a message: remove it from the inbox. It keeps its other labels and can '
        'still be found, so use this for mail that needs no further action. It does not '
        'mark the message as read. Returns the labels removed.'
    )
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.archive(args.message_id)
        return LabelChange(message_id=args.message_id, removed=['INBOX'])


class ReportSpam(Tool):
    name = 'report_spam'
    description = (
        'Report a message as spam: move it out of the inbox into spam. Use it for scams, '
        'phishing and unsolicited bulk mail, not for mail that is merely unwanted; archive '
        'that instead. Returns the labels added and removed.'
    )
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.report_spam(args.message_id)
        return LabelChange(message_id=args.message_id, added=['SPAM'], removed=['INBOX'])


class TrashEmail(Tool):
    name = 'trash_email'
    description = (
        'Move a message to the trash: remove it from the inbox. Trashed mail can be '
        'restored for a while, then is deleted for good, so use this only for mail with '
        'nothing worth keeping, and prefer archive_email when in doubt. Returns the '
        'labels added and removed.'
    )
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.trash(args.message_id)
        return LabelChange(message_id=args.message_id, added=['TRASH'], removed=['INBOX'])


class ApplyLabel(Tool):
    name = 'apply_label'
    description = (
        'Add a user label to a message, such as "Finance" or "Travel", creating the label '
        'if needed. A message can have several labels, and labelling it does not remove '
        'it from the inbox. Returns the label added.'
    )
    input_model = ApplyLabelInput

    def run(self, args: ApplyLabelInput) -> LabelChange:
        self._mailbox.apply_label(args.message_id, args.label_name)
        return LabelChange(message_id=args.message_id, added=[args.label_name])


class DraftReply(Tool):
    name = 'draft_reply'
    description = (
        'Write a reply to a message and save it as a draft on its thread, for the user '
        'to review and send. This never sends email; nothing you can do sends email. '
        "Each call creates a new draft, so draft each reply once. Returns the draft's ID."
    )
    input_model = DraftReplyInput

    def run(self, args: DraftReplyInput) -> DraftCreated:
        draft = self._mailbox.create_draft(args.message_id, args.body)
        return DraftCreated(
            draft_id=draft.id, thread_id=draft.thread_id, in_reply_to=draft.in_reply_to
        )

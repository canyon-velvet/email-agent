from pydantic import BaseModel, Field, field_validator
from email_agent.tools.tool import Tool, ToolInput
from email_agent.mail.mail_provider import SYSTEM_LABELS

class LabelChange(BaseModel):
    message_id: str
    added: list[str] = []
    removed: list[str] = []

class DraftCreated(BaseModel):
    draft_id: str
    thread_id: str
    in_reply_to: str

class MessageInput(ToolInput):
    message_id: str = Field(description='TODO')

class ApplyLabelInput(MessageInput):
    label_name: str = Field(description='TODO')

    @field_validator('label_name')
    @classmethod
    def check_label_name(cls, value: str) -> str:
        name = value.strip()
        if not name or name.upper() in SYSTEM_LABELS:
            raise ValueError('TODO')
        return name

class DraftReplyInput(MessageInput):
    body: str = Field(min_length=1, description='TODO')

class StarEmail(Tool):
    name = 'star_email'
    description = 'TODO'
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.star(args.message_id)
        return LabelChange(message_id=args.message_id, added=['STARRED'])

class MarkAsRead(Tool):
    name = 'mark_as_read'
    description = 'TODO'
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.mark_read(args.message_id)
        return LabelChange(message_id=args.message_id, removed=['UNREAD'])

class ArchiveEmail(Tool):
    name = 'archive_email'
    description = 'TODO'
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.archive(args.message_id)
        return LabelChange(message_id=args.message_id, removed=['INBOX'])

class ReportSpam(Tool):
    name = 'report_spam'
    description = 'TODO'
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.report_spam(args.message_id)
        return LabelChange(message_id=args.message_id, added=['SPAM'], removed=['INBOX'])

class TrashEmail(Tool):
    name = 'trash_email'
    description = 'TODO'
    input_model = MessageInput

    def run(self, args: MessageInput) -> LabelChange:
        self._mailbox.trash(args.message_id)
        return LabelChange(message_id=args.message_id, added=['TRASH'], removed=['INBOX'])

class ApplyLabel(Tool):
    name = 'apply_label'
    description = 'TODO'
    input_model = ApplyLabelInput

    def run(self, args: ApplyLabelInput) -> LabelChange:
        self._mailbox.apply_label(args.message_id, args.label_name)
        return LabelChange(message_id=args.message_id, added=[args.label_name])

class DraftReply(Tool):
    name = 'draft_reply'
    description = 'TODO'
    input_model = DraftReplyInput

    def run(self, args: DraftReplyInput) -> DraftCreated:
        draft = self._mailbox.create_draft(args.message_id, args.body)
        return DraftCreated(draft_id=draft.id, thread_id=draft.thread_id, in_reply_to=draft.in_reply_to)

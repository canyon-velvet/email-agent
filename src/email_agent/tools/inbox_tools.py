from pydantic import BaseModel, Field
from email_agent.tools.tool import Tool, ToolInput
from dataclasses import asdict

class EmailSummary(BaseModel):
    id: str
    sender: str
    subject: str
    snippet: str

class UnreadEmails(BaseModel):
    emails: list[EmailSummary]

class Email(BaseModel):
    id: str
    thread_id: str
    sender: str
    to: str
    date: str
    subject: str
    body: str


class FetchUnreadEmailsInput(ToolInput):
    pass

class ReadEmailInput(ToolInput):
    message_id: str = Field(
        description='The ID of the message to read, exactly as fetch_unread_emails gave it.'
    )

class FetchUnreadEmails(Tool):
    name = 'fetch_unread_emails'
    description = (
        'List the unread messages in the inbox, newest first. Each has its ID, sender, '
        'subject and a short snippet of the body, never the full text. Call this first '
        'to see what needs handling, then use read_email with an ID to read a message '
        'in full.'
    )
    input_model = FetchUnreadEmailsInput

    def run(self, args: FetchUnreadEmailsInput) -> UnreadEmails:
        emails = []
        messages = self._mailbox.list_unread()
        for msg in messages:
            emails.append(EmailSummary(id=msg.id, sender=msg.sender, subject=msg.subject, snippet=msg.snippet))
        return UnreadEmails(emails=emails)

class ReadEmail(Tool):
    name = 'read_email'
    description = (
        'Read one message in full: sender, recipients, date, subject and the body as '
        'plain text. Use it when the snippet from fetch_unread_emails is not enough to '
        'decide what to do. Reading a message does not mark it as read.'
    )
    input_model = ReadEmailInput

    def run(self, args: ReadEmailInput) -> Email:
        message = self._mailbox.get_message(args.message_id)
        return Email(**asdict(message))

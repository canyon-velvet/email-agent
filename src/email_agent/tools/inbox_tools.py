from pydantic import BaseModel
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
    message_id: str

class FetchUnreadEmails(Tool):
    name = 'fetch_unread_emails'
    description = 'TODO'
    input_model = FetchUnreadEmailsInput

    def run(self, args: FetchUnreadEmailsInput) -> UnreadEmails:
        emails = []
        messages = self._mailbox.list_unread()
        for msg in messages:
            emails.append(EmailSummary(id=msg.id, sender=msg.sender, subject=msg.subject, snippet=msg.snippet))
        return UnreadEmails(emails=emails)

class ReadEmail(Tool):
    name = 'read_email'
    description = 'TODO'
    input_model = ReadEmailInput

    def run(self, args: ReadEmailInput) -> Email:
        message = self._mailbox.get_message(args.message_id)
        return Email(**asdict(message))

import json
from pathlib import Path
from email_agent.mail.mail_provider import MessageSummary
from email import policy
from email.parser import BytesHeaderParser

class FixtureProvider:
    def __init__(self, mailbox_dir):
        self.path = Path(mailbox_dir)
    
    data_origin = 'synthetic'

    def list_unread(self):
        unread = []
        for message in json.loads((self.path / 'messages.json').read_text()):
            if {"INBOX", "UNREAD"} <= set(message['labelIds']):
                unread.append(message)

        unread.sort(key=lambda x: int(x["internalDate"]), reverse = True)
        messages = []
        for message in unread:
            with open(self.path / f"{message['id']}.eml", 'rb') as f:
                headers = BytesHeaderParser(policy=policy.default).parse(f)
            message_summary = MessageSummary(
                id = message['id'],
                thread_id = message['threadId'],
                sender = str(headers["From"]),
                subject = str(headers["Subject"]),
                snippet = message['snippet']
            )
            messages.append(message_summary)

        return messages


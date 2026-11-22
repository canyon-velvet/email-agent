import json
from email import policy
from email.parser import BytesHeaderParser
from pathlib import Path

from email_agent.mail.mail_provider import DataOrigin, MessageSummary, Message, MessageNotFoundError
from email_agent.mail.parser import parse_message


class FixtureProvider:
    """A Gmail-shaped mailbox read from a fixture directory.

    The directory holds `messages.json` (Gmail message metadata: id, threadId,
    labelIds, internalDate, snippet) and one raw RFC 2822 `<id>.eml` per message.
    """

    data_origin: DataOrigin = 'synthetic'

    def __init__(self, mailbox_dir: Path) -> None:
        self.path = Path(mailbox_dir)

    def list_unread(self) -> list[MessageSummary]:
        """Return unread inbox messages, newest first (see `MailProvider.list_unread`)."""
        unread = []
        for message in self._load_message_json():
            if {'INBOX', 'UNREAD'} <= set(message.get('labelIds', [])):
                unread.append(message)

        unread.sort(key=lambda x: int(x['internalDate']), reverse=True)
        messages = []
        for message in unread:
            with open(self.path / f'{message["id"]}.eml', 'rb') as f:
                headers = BytesHeaderParser(policy=policy.default).parse(f)
            message_summary = MessageSummary(
                id=message['id'],
                thread_id=message['threadId'],
                sender=str(headers.get('From', '')),
                subject=str(headers.get('Subject', '')),
                snippet=message['snippet'],
            )
            messages.append(message_summary)

        return messages

    def get_message(self, message_id: str) -> Message:
        msg = None
        for message in self._load_message_json():
            if message.get('id', '') == message_id:
                msg = message
                break

        if msg is None:
            raise MessageNotFoundError(message_id)

        raw_bytes = (self.path / f'{message_id}.eml').read_bytes()
        parsed_msg = parse_message(raw_bytes)
        return Message(
            id = msg['id'],
            thread_id = msg['threadId'],
            sender = parsed_msg.sender,
            to = parsed_msg.to,
            subject = parsed_msg.subject,
            body = parsed_msg.body,
            date = parsed_msg.date
        )

    def _load_message_json(self):
        return json.loads((self.path / 'messages.json').read_text(encoding='utf-8'))




import json
from email.parser import BytesHeaderParser
from pathlib import Path
from typing import Any

from email_agent.mail.mail_provider import DataOrigin, Message, MessageNotFoundError, MessageSummary
from email_agent.mail.parser import LENIENT_POLICY, header_text, parse_message


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
                headers = BytesHeaderParser(policy=LENIENT_POLICY).parse(f)
            message_summary = MessageSummary(
                id=message['id'],
                thread_id=message['threadId'],
                sender=header_text(headers, 'From'),
                subject=header_text(headers, 'Subject'),
                snippet=message['snippet'],
            )
            messages.append(message_summary)

        return messages

    def get_message(self, message_id: str) -> Message:
        """Return the full message with this ID (see `MailProvider.get_message`)."""
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
            id=msg['id'],
            thread_id=msg['threadId'],
            sender=parsed_msg.sender,
            to=parsed_msg.to,
            subject=parsed_msg.subject,
            body=parsed_msg.body,
            date=parsed_msg.date,
        )

    def _load_message_json(self) -> list[dict[str, Any]]:
        """Read the mailbox's Gmail message metadata from `messages.json`."""
        return json.loads((self.path / 'messages.json').read_text(encoding='utf-8'))

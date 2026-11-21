import json
from email import policy
from email.parser import BytesHeaderParser
from pathlib import Path

from email_agent.mail.mail_provider import DataOrigin, MessageSummary


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
        for message in json.loads((self.path / 'messages.json').read_text(encoding='utf-8')):
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

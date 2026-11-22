import json
from collections.abc import Set
from email.parser import BytesHeaderParser
from pathlib import Path
from typing import Any

from email_agent.mail.mail_provider import (
    DataOrigin,
    Draft,
    Message,
    MessageNotFoundError,
    MessageSummary,
)
from email_agent.mail.parser import LENIENT_POLICY, header_text, parse_message


class FixtureProvider:
    """A Gmail-shaped mailbox read from a fixture directory.

    The directory holds `messages.json` (Gmail message metadata: id, threadId,
    labelIds, internalDate, snippet) and one raw RFC 2822 `<id>.eml` per message.
    Label changes and drafts live in memory only: the files are never written, so
    loading the same directory again starts from the original state.
    """

    data_origin: DataOrigin = 'synthetic'

    def __init__(self, mailbox_dir: Path) -> None:
        self.path = Path(mailbox_dir)
        self._metadata: dict[str, dict[str, Any]] = {}
        self._labels: dict[str, set[str]] = {}
        messages = json.loads((self.path / 'messages.json').read_text(encoding='utf-8'))
        for msg in messages:
            self._metadata[msg['id']] = msg
            self._labels[msg['id']] = set(msg.pop('labelIds', []))
        self._drafts: list[Draft] = []

    def list_unread(self) -> list[MessageSummary]:
        """Return unread inbox messages, newest first (see `MailProvider.list_unread`)."""
        unread = []
        for message in self._metadata.values():
            if {'INBOX', 'UNREAD'} <= self._labels[message['id']]:
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
        msg = self._metadata.get(message_id)

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

    def snapshot(self) -> dict[str, frozenset[str]]:
        """Return a copy of every message's labels (see `MailProvider.snapshot`)."""
        return {message_id: frozenset(labels) for message_id, labels in self._labels.items()}

    def list_drafts(self) -> list[Draft]:
        """Return a copy of the drafts, oldest first (see `MailProvider.list_drafts`)."""
        return list(self._drafts)

    def _modify(
        self, message_id: str, add: Set[str] = frozenset(), remove: Set[str] = frozenset()
    ) -> None:
        """Add and remove labels on one message, like Gmail's `messages.modify`."""
        if message_id not in self._labels:
            raise MessageNotFoundError(message_id)

        self._labels[message_id] = (self._labels[message_id] | add) - remove

    def star(self, message_id: str) -> None:
        """Add STARRED (see `MailProvider.star`)."""
        self._modify(message_id, add={'STARRED'})

    def mark_read(self, message_id: str) -> None:
        """Remove UNREAD (see `MailProvider.mark_read`)."""
        self._modify(message_id, remove={'UNREAD'})

    def archive(self, message_id: str) -> None:
        """Remove INBOX (see `MailProvider.archive`)."""
        self._modify(message_id, remove={'INBOX'})

    def report_spam(self, message_id: str) -> None:
        """Add SPAM and remove INBOX (see `MailProvider.report_spam`)."""
        self._modify(message_id, add={'SPAM'}, remove={'INBOX'})

    def trash(self, message_id: str) -> None:
        self._modify(message_id, add={'TRASH'}, remove={'INBOX'})

    def apply_label(self, message_id: str, label_name: str) -> None:
        """Add a user label by name (see `MailProvider.apply_label`).

        Fixture labels are plain names, so there is no label to create first.
        """
        self._modify(message_id, add={label_name})

    def create_draft(self, message_id: str, body: str) -> Draft:
        """Store an unsent reply on the message's thread (see `MailProvider.create_draft`)."""
        if message_id not in self._labels:
            raise MessageNotFoundError(message_id)

        message = self._metadata[message_id]

        draft = Draft(
            id=f'draft-{len(self._drafts) + 1}',
            thread_id=message['threadId'],
            in_reply_to=message_id,
            body=body,
        )
        self._drafts.append(draft)
        return draft

"""Shared pytest fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def contract_mailbox() -> Path:
    """The Gmail-shaped fixture mailbox that every mail provider is tested against.

    Layout: `messages.json` holds Gmail message metadata (id, threadId, labelIds,
    internalDate, snippet); each message's raw RFC 2822 source is in `<id>.eml`.
    As in Gmail, a snippet is the first ~200 characters of the body text with
    whitespace collapsed, and `labelIds` is absent when a message has no labels.
    Unlike Gmail's API, snippets are stored as plain text, not HTML-escaped, and user
    labels in `labelIds` are listed by name, not by ID like `Label_123` (system label
    IDs such as INBOX already equal their names).
    """
    return FIXTURES / 'mailboxes' / 'contract'

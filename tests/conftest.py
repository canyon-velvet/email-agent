"""Shared pytest fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def contract_mailbox() -> Path:
    """The Gmail-shaped fixture mailbox that every mail provider is tested against.

    Layout: `messages.json` holds Gmail message metadata (id, threadId, labelIds,
    internalDate, snippet); each message's raw RFC 2822 source is in `<id>.eml`.
    """
    return FIXTURES / "mailboxes" / "contract"

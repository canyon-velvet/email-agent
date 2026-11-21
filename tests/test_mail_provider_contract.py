"""Mail-provider contract (Seam 2): "list unread".

Every MailProvider must pass this suite against the contract mailbox. The fixture
provider reads it from disk; a future Gmail provider will run the same tests
against a test account seeded with the same messages.
"""

import pytest

from email_agent.mail import FixtureProvider, MailProvider

# The three unread inbox messages, newest first. The contract mailbox also holds a
# read inbox message, an archived unread one, and an unread spam one.
LUNCH = "19a8f3c2b1d04e01"
BUILD = "19a8a1e7c3f25b02"
INVOICE = "19a84d6b9e1c7a03"

# Appears in the lunch message's body but not in its snippet.
BODY_ONLY_TEXT = "ramen place on 5th Street"


@pytest.fixture(params=["fixture_provider"])
def provider(request, contract_mailbox) -> MailProvider:
    """Each provider under test, loaded with the contract mailbox."""
    if request.param == "fixture_provider":
        return FixtureProvider(contract_mailbox)
    raise NotImplementedError(request.param)


def test_list_unread_returns_only_unread_inbox_messages_newest_first(provider):
    assert [summary.id for summary in provider.list_unread()] == [LUNCH, BUILD, INVOICE]


def test_list_unread_summary_has_ids_headers_and_snippet(provider):
    lunch = provider.list_unread()[0]

    assert lunch.id == LUNCH
    assert lunch.thread_id == "19a7e0d1c2b3a400"
    assert lunch.sender == "Alice Chen <alice@example.com>"
    assert lunch.subject == "Re: Lunch on Thursday?"
    assert lunch.snippet == "Are you free for lunch on Thursday? I was thinking about noon."


def test_list_unread_never_includes_message_bodies(provider):
    for summary in provider.list_unread():
        assert BODY_ONLY_TEXT not in repr(summary)

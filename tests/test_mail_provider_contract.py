"""Mail-provider contract (Seam 2): "list unread".

Every MailProvider must pass this suite against the contract mailbox. The fixture
provider reads it from disk. Gmail assigns its own message IDs, so when the Gmail
provider arrives (M4) its run will seed a test account with these messages and map
fixture IDs to Gmail IDs.
"""

import pytest

from email_agent.mail import FixtureProvider, MailProvider

# The four unread inbox messages, newest first. Their IDs deliberately don't sort
# in date order, so sorting by ID instead of internalDate fails the order test.
# The contract mailbox also holds a read inbox message, an archived unread one, an
# unread spam one, and an archived one with no labelIds at all (Gmail omits the key).
LUNCH = '19a8f3c2b1d04e01'
BUILD = '19a80b17c3f25b02'
INVOICE = '19a84d6b9e1c7a03'
NO_SUBJECT = '19a83c5d7e9f1a07'

# Appears in the lunch message's body, past the ~200 characters its snippet covers.
BODY_ONLY_TEXT = 'ramen place on 5th Street'


@pytest.fixture(params=['fixture_provider'])
def provider(request, contract_mailbox) -> MailProvider:
    """Each provider under test, loaded with the contract mailbox."""
    if request.param == 'fixture_provider':
        return FixtureProvider(contract_mailbox)
    raise NotImplementedError(request.param)


def test_list_unread_returns_only_unread_inbox_messages_newest_first(provider):
    ids = [summary.id for summary in provider.list_unread()]

    assert ids == [LUNCH, BUILD, INVOICE, NO_SUBJECT]


def test_list_unread_summary_has_ids_headers_and_snippet(provider):
    lunch = provider.list_unread()[0]

    assert lunch.id == LUNCH
    assert lunch.thread_id == '19a7e0d1c2b3a400'
    assert lunch.sender == 'Alice Chen <alice@example.com>'
    assert lunch.subject == 'Re: Lunch on Thursday?'
    assert lunch.snippet.startswith('Are you free for lunch on Thursday? I was thinking')


def test_list_unread_gives_an_empty_subject_when_the_header_is_missing(provider):
    no_subject = next(s for s in provider.list_unread() if s.id == NO_SUBJECT)

    assert no_subject.subject == ''


def test_list_unread_never_includes_message_bodies(provider):
    for summary in provider.list_unread():
        assert BODY_ONLY_TEXT not in repr(summary)

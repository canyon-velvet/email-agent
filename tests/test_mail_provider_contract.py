"""Mail-provider contract (Seam 2): "list unread" and "get message".

Every MailProvider must pass this suite against the contract mailbox. The fixture
provider reads it from disk. Gmail assigns its own message IDs, so when the Gmail
provider arrives (M4) its run will seed a test account with these messages and map
fixture IDs to Gmail IDs.
"""

import pytest

from email_agent.mail import FixtureProvider, MailProvider, MessageNotFoundError

# The four unread inbox messages, newest first. Their IDs deliberately don't sort
# in date order, so sorting by ID instead of internalDate fails the order test.
# The contract mailbox also holds a read inbox message, an archived unread one, an
# unread spam one, and an archived one with no labelIds at all (Gmail omits the key).
LUNCH = '19a8f3c2b1d04e01'
BUILD = '19a80b17c3f25b02'
INVOICE = '19a84d6b9e1c7a03'
NO_SUBJECT = '19a83c5d7e9f1a07'

# Read messages that exercise the message parser (none are unread).
SHIPPED = '19a7c1d2e3f40a09'  # multipart/alternative: text/plain and text/html parts
NEWSLETTER = '19a7b0c1d2e3f40a'  # HTML only, with a <style>, a <script>, and &amp;
REUNION = '19a7a0b1c2d3e40b'  # encoded From/Subject, ISO-8859-1 quoted-printable body

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


def test_get_message_returns_headers_and_the_full_body(provider):
    lunch = provider.get_message(LUNCH)

    assert lunch.id == LUNCH
    assert lunch.thread_id == '19a7e0d1c2b3a400'
    assert lunch.sender == 'Alice Chen <alice@example.com>'
    assert lunch.to == 'Me <me@example.com>'
    assert lunch.date == 'Thu, 19 Nov 2026 09:15:00 +0000'
    assert lunch.subject == 'Re: Lunch on Thursday?'
    assert BODY_ONLY_TEXT in lunch.body  # the part the snippet leaves out


def test_get_message_prefers_the_plain_text_part(provider):
    body = provider.get_message(SHIPPED).body

    assert 'Track it at https://shop.example.com/track/5521' in body  # only in text/plain
    assert '<' not in body


def test_get_message_converts_html_only_mail_to_readable_text(provider):
    body = provider.get_message(NEWSLETTER).body

    assert 'Read the full story' in body  # link text is kept
    assert 'Fish & chips' in body  # entities are decoded
    assert '<' not in body  # tags are gone
    assert 'font-family' not in body  # <style> content is dropped
    assert 'trackOpen' not in body  # <script> content is dropped
    # Paragraphs stay on separate lines.
    assert not any('Astronomers' in line and 'Fish' in line for line in body.splitlines())


def test_get_message_decodes_encoded_headers_and_non_utf8_bodies(provider):
    reunion = provider.get_message(REUNION)

    assert reunion.sender == 'José Pérez <jose@example.com>'
    assert reunion.subject == 'Réunion : café vendredi ☕'
    assert 'café à 10h, près de la gare' in reunion.body


def test_get_message_does_not_mark_the_message_as_read(provider):
    # As with Gmail's messages.get, reading is not an action; marking as read is (#7).
    provider.get_message(LUNCH)

    assert LUNCH in [summary.id for summary in provider.list_unread()]


def test_get_message_gives_an_empty_subject_when_the_header_is_missing(provider):
    assert provider.get_message(NO_SUBJECT).subject == ''


def test_get_message_raises_for_an_unknown_id(provider):
    with pytest.raises(MessageNotFoundError):
        provider.get_message('0000000000000000')

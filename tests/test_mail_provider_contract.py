"""Mail-provider contract (Seam 2): reading messages, changing labels, and drafts.

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

LUNCH_THREAD = '19a7e0d1c2b3a400'  # a reply, so its thread ID differs from its own ID
LUNCH_LABELS = frozenset({'INBOX', 'UNREAD', 'IMPORTANT', 'CATEGORY_PERSONAL'})
NO_LABELS = '19a82a4b6c8d0e08'  # archived and read: Gmail omits labelIds entirely

# Each mailbox change, as a test calls it. Each maps onto one Gmail API call:
# messages.modify for the label changes, drafts.create for the draft.
CHANGES = {
    'star': lambda provider, message_id: provider.star(message_id),
    'mark_read': lambda provider, message_id: provider.mark_read(message_id),
    'archive': lambda provider, message_id: provider.archive(message_id),
    'apply_label': lambda provider, message_id: provider.apply_label(message_id, 'Receipts'),
    'report_spam': lambda provider, message_id: provider.report_spam(message_id),
    'create_draft': lambda provider, message_id: provider.create_draft(message_id, 'Thanks!'),
}

# The labels each label change adds and removes, with Gmail's semantics: a label is
# not a folder, so archiving removes INBOX and reporting spam swaps INBOX for SPAM.
LABEL_CHANGES = {
    'star': ({'STARRED'}, set()),
    'mark_read': (set(), {'UNREAD'}),
    'archive': (set(), {'INBOX'}),
    'apply_label': ({'Receipts'}, set()),
    'report_spam': ({'SPAM'}, {'INBOX'}),
}


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


def test_snapshot_reports_the_labels_of_every_message(provider):
    snapshot = provider.snapshot()

    assert len(snapshot) == 11
    assert snapshot[LUNCH] == LUNCH_LABELS
    assert snapshot[NO_LABELS] == frozenset()


def test_a_snapshot_is_a_copy_that_later_changes_leave_alone(provider):
    snapshot = provider.snapshot()

    provider.star(LUNCH)

    assert snapshot[LUNCH] == LUNCH_LABELS


@pytest.mark.parametrize('change', LABEL_CHANGES)
def test_each_label_change_matches_gmail(provider, change):
    added, removed = LABEL_CHANGES[change]
    before = provider.snapshot()

    CHANGES[change](provider, LUNCH)

    after = provider.snapshot()
    assert after[LUNCH] == (LUNCH_LABELS | added) - removed
    others_before = {id_: labels for id_, labels in before.items() if id_ != LUNCH}
    assert {id_: labels for id_, labels in after.items() if id_ != LUNCH} == others_before


@pytest.mark.parametrize('change', LABEL_CHANGES)
def test_label_changes_are_idempotent(provider, change):
    # An agent may repeat an action, e.g. after a retry; doing it twice must be safe.
    CHANGES[change](provider, LUNCH)
    once = provider.snapshot()

    CHANGES[change](provider, LUNCH)

    assert provider.snapshot() == once


def test_label_changes_show_up_in_list_unread(provider):
    provider.mark_read(LUNCH)
    provider.archive(BUILD)
    provider.report_spam(INVOICE)

    assert [summary.id for summary in provider.list_unread()] == [NO_SUBJECT]


def test_a_new_user_label_is_created_once_then_reused(provider):
    # In Gmail a user label must exist before it's applied, and creating a label that
    # already exists is an error: the first call creates it, the second reuses it.
    provider.apply_label(LUNCH, 'Travel')
    provider.apply_label(BUILD, 'Travel')

    snapshot = provider.snapshot()
    assert 'Travel' in snapshot[LUNCH]
    assert 'Travel' in snapshot[BUILD]


@pytest.mark.parametrize('change', CHANGES)
def test_changing_an_unknown_message_raises(provider, change):
    with pytest.raises(MessageNotFoundError):
        CHANGES[change](provider, '0000000000000000')


def test_create_draft_stores_a_reply_on_the_message_thread(provider):
    labels_before = provider.snapshot()

    first = provider.create_draft(LUNCH, 'Thursday works for me.')
    second = provider.create_draft(LUNCH, 'Actually, could we do Friday?')

    assert first.thread_id == LUNCH_THREAD  # the thread, not the message's own ID
    assert first.in_reply_to == LUNCH
    assert first.body == 'Thursday works for me.'
    assert first.id != second.id
    assert provider.list_drafts() == [first, second]
    provider.list_drafts().clear()  # changing the returned list...
    assert provider.list_drafts() == [first, second]  # ...leaves the stored drafts alone
    assert provider.snapshot() == labels_before  # drafting changes no labels


@pytest.mark.parametrize('label_name', ['INBOX', 'inbox', 'TRASH', 'SPAM', 'UNREAD', 'DRAFT', ''])
def test_apply_label_rejects_system_labels_and_empty_names(provider, label_name):
    # Otherwise the generic label change is a back door around the dedicated ones,
    # e.g. INBOX un-archives and rescues spam. Gmail rejects these user labels too.
    before = provider.snapshot()

    with pytest.raises(ValueError):
        provider.apply_label(LUNCH, label_name)

    assert provider.snapshot() == before


def test_the_interface_offers_no_way_to_send():
    # v1 never sends mail (spec #3). Callers see only MailProvider, so this is all the
    # agent can do; any new capability has to be added here on purpose.
    public_methods = {name for name in dir(MailProvider) if not name.startswith('_')}

    assert public_methods == {
        'list_unread',
        'get_message',
        'snapshot',
        'list_drafts',
        'star',
        'mark_read',
        'archive',
        'report_spam',
        'apply_label',
        'create_draft',
    }

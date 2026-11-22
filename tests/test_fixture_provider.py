"""Fixture-provider behaviour outside the shared mail-provider contract."""

import json
import shutil

from email_agent.mail import FixtureProvider

LUNCH = '19a8f3c2b1d04e01'  # an unread inbox message in the contract mailbox


def test_fixture_data_is_tagged_synthetic(contract_mailbox):
    # The model router (#10) uses this tag: synthetic data may go to a cloud model.
    assert FixtureProvider(contract_mailbox).data_origin == 'synthetic'


def test_one_malformed_unread_message_does_not_break_the_listing(tmp_path):
    unread = {'labelIds': ['INBOX', 'UNREAD'], 'snippet': 'Hello.'}
    messages = [
        {'id': 'aaa', 'threadId': 'aaa', 'internalDate': '2', **unread},
        {'id': 'bbb', 'threadId': 'bbb', 'internalDate': '1', **unread},
    ]
    (tmp_path / 'messages.json').write_text(json.dumps(messages), encoding='utf-8')
    (tmp_path / 'aaa.eml').write_bytes(  # each of these headers made the listing raise
        b'From: =?utf-8?b?QQo=?= <a@example.com>\n'
        b'Subject: =?utf-7?q?+2AA-?=\n'
        b'Content-Type: text/plain; charset*\n'
        b'\n'
        b'Hello.\n'
    )
    (tmp_path / 'bbb.eml').write_bytes(b'From: Bo <bo@example.com>\nSubject: Hi\n\nHello.\n')

    summaries = FixtureProvider(tmp_path).list_unread()

    assert [(s.id, s.sender, s.subject) for s in summaries] == [
        ('aaa', 'A <a@example.com>', ''),
        ('bbb', 'Bo <bo@example.com>', 'Hi'),
    ]


def mailbox_files(mailbox_dir):
    return {path.name: path.read_bytes() for path in mailbox_dir.iterdir() if path.is_file()}


def test_changes_stay_in_memory_and_a_fresh_load_starts_over(contract_mailbox, tmp_path):
    # A copy, so a provider that does write to disk can't damage the shared fixture.
    mailbox = shutil.copytree(contract_mailbox, tmp_path / 'mailbox')
    files_before = mailbox_files(mailbox)
    provider = FixtureProvider(mailbox)
    original = provider.snapshot()

    provider.star(LUNCH)
    provider.archive(LUNCH)
    provider.create_draft(LUNCH, 'Thursday works for me.')

    assert mailbox_files(mailbox) == files_before
    fresh = FixtureProvider(mailbox)  # the same fixture, loaded again
    assert fresh.snapshot() == original
    assert fresh.list_drafts() == []

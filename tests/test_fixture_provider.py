"""Fixture-provider behaviour outside the shared mail-provider contract."""

import json

from email_agent.mail import FixtureProvider


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
        b'Subject: Spam\n'
        b'Content-Type: text/plain; charset*\n'
        b'\n'
        b'Hello.\n'
    )
    (tmp_path / 'bbb.eml').write_bytes(b'From: Bo <bo@example.com>\nSubject: Hi\n\nHello.\n')

    summaries = FixtureProvider(tmp_path).list_unread()

    assert [(s.id, s.sender, s.subject) for s in summaries] == [
        ('aaa', 'A <a@example.com>', 'Spam'),
        ('bbb', 'Bo <bo@example.com>', 'Hi'),
    ]

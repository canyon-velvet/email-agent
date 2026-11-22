"""The shared parser on messy real-world email, using small inline raw messages.

These stay out of the contract mailbox: in M4 that mailbox is imported into a real
Gmail account, which may reject or rewrite malformed mail.
"""

import pytest

from email_agent.mail.parser import parse_message


# Each of these makes Python's address parser raise, on 3.12 and 3.13 alike.
@pytest.mark.parametrize(
    ('raw_from', 'expected'),
    [
        (',\t:', ', :'),  # IndexError
        ('=?utf-8?b?QQo=?= <a@example.com>', 'A <a@example.com>'),  # name decodes to "A\n"
        ('Café =?utf-8?b?QQo=?= <a@example.com>', 'Café A <a@example.com>'),  # raw 8-bit too
    ],
)
def test_a_sender_python_cannot_parse_falls_back_to_plain_text(raw_from, expected):
    raw = f'From: {raw_from}\nSubject: Hi\n\nHello.\n'.encode()

    parsed = parse_message(raw)

    assert parsed.sender == expected
    assert parsed.subject == 'Hi'  # the failure stays inside one field
    assert parsed.body == 'Hello.'


@pytest.mark.parametrize(
    'mime_header',
    [
        'Content-Type: text/plain; charset*',  # IndexError while parsing the message
        'Content-Disposition: inline; filename*',  # IndexError while picking the body
        'Content-Type: text/plain; x=' + '(' * 5000,  # RecursionError
    ],
    ids=['content-type', 'content-disposition', 'deep-comment'],
)
def test_a_malformed_mime_header_still_gives_the_body(mime_header):
    raw = f'Subject: Hi\n{mime_header}\n\nHello.\n'.encode()

    assert parse_message(raw).body == 'Hello.'


def test_an_encoded_line_break_cannot_start_a_forged_header_line():
    raw = b'Subject: =?UTF-8?Q?Invoice=0D=0AFrom:_CEO_<ceo@example.com>?=\n\nHello.\n'

    assert parse_message(raw).subject == 'Invoice From: CEO <ceo@example.com>'


@pytest.mark.parametrize(
    'charset',
    [
        'unknown-8bit',  # LookupError: no such codec
        'x-unknown',
        'idna',  # UnicodeError: a real codec that can't decode text
        'undefined',
    ],
)
def test_an_unknown_charset_decodes_as_utf8(charset):
    raw = f'Content-Type: text/plain; charset={charset}\n\ncafé\n'.encode()

    assert parse_message(raw).body == 'café'


@pytest.mark.parametrize(
    'content_type',
    ['Content-Type: text/plain\nContent-Transfer-Encoding: 8bit\n', ''],
    ids=['no-charset', 'no-content-type'],
)
def test_an_undeclared_charset_decodes_as_utf8(content_type):
    raw = f'Subject: Hi\n{content_type}\ncafé\n'.encode()

    assert parse_message(raw).body == 'café'


def test_bytes_that_are_not_utf8_become_replacement_characters():
    raw = b'Content-Type: text/plain\n\ncaf\xe9\n'  # Latin-1, but no charset says so

    assert parse_message(raw).body == 'caf�'


def test_crlf_line_endings_become_newlines():
    raw = b'Subject: Hi\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nLine one\r\nLine two\r\n'

    assert parse_message(raw).body == 'Line one\nLine two'


def test_only_cr_and_lf_count_as_line_breaks_in_a_body():
    # Latin-1 0x85 is U+0085, a line break to str.splitlines(); it must stay as text.
    raw = b'Content-Type: text/plain; charset=iso-8859-1\n\nWait\x85 what?\rNext\n'

    assert parse_message(raw).body == 'Wait\x85 what?\nNext'


def test_missing_to_and_date_headers_are_empty():
    parsed = parse_message(b'From: a@example.com\nSubject: Hi\n\nHello.\n')

    assert parsed.to == ''
    assert parsed.date == ''


def test_a_message_without_a_text_part_has_an_empty_body():
    raw = (
        b'Content-Type: multipart/mixed; boundary="b"\n'
        b'\n'
        b'--b\n'
        b'Content-Type: application/pdf\n'
        b'Content-Transfer-Encoding: base64\n'
        b'\n'
        b'JVBERi0xLjQK\n'
        b'--b--\n'
    )

    assert parse_message(raw).body == ''

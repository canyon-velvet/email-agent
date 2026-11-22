"""Acceptance tests for the email-agent command line (ticket #4: project skeleton).

These run the installed console script as a subprocess, so they don't depend on
which CLI library the implementation uses.
"""

import shutil
import subprocess
import sysconfig
from importlib.metadata import version

# The contract mailbox's unread inbox messages, newest first:
# (id, sender address, subject, start of snippet).
UNREAD_ROWS = [
    ('19a8f3c2b1d04e01', 'alice@example.com', 'Re: Lunch on Thursday?', 'Are you free for lunch'),
    ('19a80b17c3f25b02', 'ci@example.com', 'Build failed on main', 'The build for commit'),
    ('19a84d6b9e1c7a03', 'bob@example.com', 'Invoice 1042 for November', 'Hi, please find'),
    ('19a83c5d7e9f1a07', 'sam@example.com', '', 'Quick question about the trip'),
]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed `email-agent` command and capture its output."""
    # Search only this environment's scripts directory, so the test can't pick up
    # another `email-agent` on PATH. `which` also finds `email-agent.exe` on Windows.
    script = shutil.which('email-agent', path=sysconfig.get_path('scripts'))
    assert script, 'console script `email-agent` is not installed in this environment'
    return subprocess.run([script, *args], capture_output=True, text=True, timeout=30)


def test_version_flag_prints_the_installed_version():
    result = run_cli('--version')

    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[-1] == version('email-agent')


def test_inbox_prints_one_line_per_unread_message_newest_first(contract_mailbox):
    result = run_cli('inbox', '--mailbox', str(contract_mailbox))

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(UNREAD_ROWS), result.stdout
    for line, (message_id, address, subject, snippet_start) in zip(lines, UNREAD_ROWS, strict=True):
        assert message_id in line
        assert address in line
        assert subject in line
        assert snippet_start in line
    # A missing Subject shows as empty, not as the text "None".
    assert 'None' not in result.stdout
    # Text from the lunch message's body (not its snippet) is never printed.
    assert 'ramen place on 5th Street' not in result.stdout


def test_inbox_says_so_when_nothing_is_unread(tmp_path):
    (tmp_path / 'messages.json').write_text('[]')

    result = run_cli('inbox', '--mailbox', str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert 'no unread messages' in result.stdout.lower()


def test_inbox_rejects_a_missing_mailbox_with_a_short_error(tmp_path):
    result = run_cli('inbox', '--mailbox', str(tmp_path / 'does-not-exist'))

    assert result.returncode != 0
    assert 'Traceback' not in result.stderr


def test_show_prints_headers_and_the_full_body(contract_mailbox):
    result = run_cli('show', '19a8f3c2b1d04e01', '--mailbox', str(contract_mailbox))

    assert result.returncode == 0, result.stderr
    assert 'From: Alice Chen <alice@example.com>' in result.stdout
    assert 'To: Me <me@example.com>' in result.stdout
    assert 'Date: Thu, 19 Nov 2026 09:15:00 +0000' in result.stdout
    assert 'Subject: Re: Lunch on Thursday?' in result.stdout
    assert 'ramen place on 5th Street' in result.stdout  # beyond the snippet


def test_show_rejects_an_unknown_id_with_a_short_error(contract_mailbox):
    result = run_cli('show', '0000000000000000', '--mailbox', str(contract_mailbox))

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert '0000000000000000' in output
    assert 'not found' in output.lower()
    assert 'Traceback' not in output

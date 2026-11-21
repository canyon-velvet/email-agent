"""Acceptance tests for the email-agent command line (ticket #4: project skeleton).

These run the installed console script as a subprocess, so they don't depend on
which CLI library the implementation uses.
"""

import shutil
import subprocess
import sysconfig
from email.utils import parseaddr
from importlib.metadata import version

from email_agent.mail import FixtureProvider


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed `email-agent` command and capture its output."""
    # Search only this environment's scripts directory, so the test can't pick up
    # another `email-agent` on PATH. `which` also finds `email-agent.exe` on Windows.
    script = shutil.which("email-agent", path=sysconfig.get_path("scripts"))
    assert script, "console script `email-agent` is not installed in this environment"
    return subprocess.run([script, *args], capture_output=True, text=True, timeout=30)


def test_version_flag_prints_the_installed_version():
    result = run_cli("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[-1] == version("email-agent")


def test_inbox_prints_one_line_per_unread_message_newest_first(contract_mailbox):
    expected = FixtureProvider(contract_mailbox).list_unread()

    result = run_cli("inbox", "--mailbox", str(contract_mailbox))

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(expected), result.stdout
    for line, message in zip(lines, expected, strict=True):
        assert message.id in line
        assert message.subject in line
        assert message.snippet in line
        name, address = parseaddr(message.sender)
        assert name in line or address in line
    # Text from the lunch message's body (not its snippet) is never printed.
    assert "ramen place on 5th Street" not in result.stdout


def test_inbox_says_so_when_nothing_is_unread(tmp_path):
    (tmp_path / "messages.json").write_text("[]")

    result = run_cli("inbox", "--mailbox", str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "no unread messages" in result.stdout.lower()

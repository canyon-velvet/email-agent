"""Acceptance tests for the email-agent command line (ticket #4: project skeleton).

These run the installed console script as a subprocess, so they don't depend on
which CLI library the implementation uses.
"""

import shutil
import subprocess
import sysconfig
from importlib.metadata import version


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

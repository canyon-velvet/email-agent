"""Acceptance tests for the email-agent command line (ticket #4: project skeleton).

These run the installed console script as a subprocess, so they don't depend on
which CLI library the implementation uses.
"""

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed `email-agent` command and capture its output."""
    # uv installs console scripts next to the interpreter that runs the tests.
    script = Path(sys.executable).parent / "email-agent"
    assert script.exists(), f"console script not installed at {script}"
    return subprocess.run([str(script), *args], capture_output=True, text=True, timeout=30)


def test_version_flag_prints_the_installed_version():
    result = run_cli("--version")

    assert result.returncode == 0, result.stderr
    assert version("email-agent") in result.stdout

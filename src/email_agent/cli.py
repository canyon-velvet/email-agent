"""Command-line entry point for email-agent."""

from importlib import metadata
from pathlib import Path
from typing import Annotated

import typer

from email_agent.mail import FixtureProvider, MailProvider

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f'email-agent {metadata.version("email-agent")}')
        raise typer.Exit()


# A callback (rather than a single command) makes the app a command group,
# so later subcommands (`inbox`, `show`, `trace`, ...) slot in without changes here.
@app.callback()
def main(
    show_version: Annotated[
        bool,
        typer.Option(
            '--version',
            callback=_print_version,
            is_eager=True,
            help='Show the version and exit.',
        ),
    ] = False,
) -> None:
    """Triage an inbox with an AI agent."""


def _open_mailbox(path: Path) -> MailProvider:
    """Open the mailbox at `path`. The only place that picks a provider implementation."""
    return FixtureProvider(path)


@app.command()
def inbox(
    mailbox: Annotated[
        Path,
        typer.Option(
            '--mailbox', exists=True, file_okay=False, help='Open the mailbox at this path.'
        ),
    ],
) -> None:
    """List unread inbox messages, newest first."""
    provider = _open_mailbox(mailbox)
    summaries = provider.list_unread()
    if not summaries:
        typer.echo('No unread messages.')
    for summary in summaries:
        typer.echo(f'{summary.id}  {summary.sender}  {summary.subject}  {summary.snippet}')

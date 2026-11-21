"""Command-line entry point for email-agent."""

from importlib import metadata
from typing import Annotated
from pathlib import Path
from email_agent.mail import MailProvider, FixtureProvider

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"email-agent {metadata.version('email-agent')}")
        raise typer.Exit()


# A callback (rather than a single command) makes the app a command group,
# so later subcommands (`inbox`, `show`, `trace`, ...) slot in without changes here.
@app.callback()
def main(
    show_version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Triage an inbox with an AI agent."""

def _open_mailbox(path) -> MailProvider:
    return FixtureProvider(path)

@app.command()
def inbox(
    mailbox: Annotated[
        Path,
        typer.Option(
            "--mailbox",
            help='open the mailbox at this path'
        )
    ]
) -> None:
    provider = _open_mailbox(mailbox)
    summaries = provider.list_unread()
    if not summaries:
        typer.echo('No unread messages.')
    for summary in summaries:
        typer.echo(f"{summary.id}  {summary.sender}  {summary.subject}  {summary.snippet}")


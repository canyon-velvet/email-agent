"""Command-line entry point for email-agent."""

import json
from importlib import metadata
from pathlib import Path
from typing import Annotated

import typer

from email_agent.mail import FixtureProvider, MailProvider, MessageNotFoundError
from email_agent.trace import RunNotFoundError, read_trace

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


@app.command()
def show(
    message_id: Annotated[str, typer.Argument(help='ID of the message to show.')],
    mailbox: Annotated[
        Path,
        typer.Option(
            '--mailbox', exists=True, file_okay=False, help='Open the mailbox at this path.'
        ),
    ],
) -> None:
    """Show one message: its headers, then the body as readable text."""
    provider = _open_mailbox(mailbox)
    try:
        message = provider.get_message(message_id)
    except MessageNotFoundError:
        typer.echo(f'Message {message_id} not found.', err=True)
        raise typer.Exit(code=1) from None
    else:
        typer.echo(
            f'From: {message.sender}\n'
            f'To: {message.to}\n'
            f'Date: {message.date}\n'
            f'Subject: {message.subject}\n'
            '\n'
            f'{message.body}'
        )


@app.command()
def trace(
    run_id: Annotated[str, typer.Argument(help='ID of the run to show.')],
    trace_dir: Annotated[
        Path,
        typer.Option('--trace-dir', help='Read runs from this directory.'),
    ] = Path('traces'),
) -> None:
    """Print a run's trace, one event per line: seq, time, type, then the payload."""
    try:
        events = read_trace(trace_dir, run_id)
    except RunNotFoundError:
        typer.echo(f'Run {run_id} not found.', err=True)
        raise typer.Exit(code=1) from None
    else:
        for event in events:
            payload = json.dumps(event.payload, ensure_ascii=False)
            typer.echo(f'{event.seq}  {event.timestamp}  {event.type}  {payload}')

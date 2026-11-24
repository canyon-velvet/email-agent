"""The tool protocol and the two inbox tools (ticket #11)."""

from dataclasses import asdict

import pytest
from pydantic import TypeAdapter, ValidationError

from email_agent.mail import FixtureProvider, MailProvider
from email_agent.model import ToolSchema
from email_agent.tools import FetchUnreadEmails, ReadEmail, Tool, ToolError

LUNCH = '19a8f3c2b1d04e01'  # an unread message in the contract mailbox


@pytest.fixture
def mailbox(contract_mailbox) -> FixtureProvider:
    return FixtureProvider(contract_mailbox)


def inbox_tools(mailbox: MailProvider) -> dict[str, Tool]:
    return {'fetch_unread_emails': FetchUnreadEmails(mailbox), 'read_email': ReadEmail(mailbox)}


@pytest.mark.parametrize(
    ('name', 'required'),
    [('fetch_unread_emails', {'reason'}), ('read_email', {'reason', 'message_id'})],
)
def test_each_tool_exports_its_schema_for_model_requests(mailbox, name, required):
    schema = inbox_tools(mailbox)[name].schema()

    assert isinstance(schema, ToolSchema)
    assert schema.name == name
    assert schema.description  # written for the model: what the tool does, when to use it
    assert schema.input_schema['type'] == 'object'
    assert set(schema.input_schema['required']) == required
    # Unknown arguments are refused, as Claude's strict tool use also requires.
    assert schema.input_schema['additionalProperties'] is False
    properties = schema.input_schema['properties']
    assert set(properties) == required  # no optional extras
    # Every argument has a description: it's how the model learns what to write.
    assert all(field.get('description') for field in properties.values())


def test_fetch_unread_emails_lists_snippets_never_bodies(mailbox):
    outcome = FetchUnreadEmails(mailbox).call({'reason': 'Start triage.'})

    assert outcome.output.model_dump() == {
        'emails': [
            {'id': s.id, 'sender': s.sender, 'subject': s.subject, 'snippet': s.snippet}
            for s in mailbox.list_unread()
        ]
    }
    assert outcome.origin == 'synthetic'


def test_read_email_returns_the_full_parsed_message(mailbox):
    outcome = ReadEmail(mailbox).call({'message_id': LUNCH, 'reason': 'Read the lunch invite.'})

    assert outcome.output.model_dump() == asdict(mailbox.get_message(LUNCH))
    assert outcome.origin == 'synthetic'


@pytest.mark.parametrize(
    ('name', 'arguments', 'field'),
    [
        ('fetch_unread_emails', {}, 'reason'),
        ('fetch_unread_emails', {'reason': 'Start triage.', 'limit': 5}, 'limit'),
        ('read_email', {'message_id': LUNCH}, 'reason'),
        ('read_email', {'message_id': LUNCH, 'reason': ''}, 'reason'),
        ('read_email', {'message_id': 42, 'reason': 'Read it.'}, 'message_id'),
        ('read_email', {'id': LUNCH, 'reason': 'Read it.'}, 'message_id'),
    ],
)
def test_bad_arguments_return_a_tool_error_naming_the_field(mailbox, name, arguments, field):
    outcome = inbox_tools(mailbox)[name].call(arguments)

    assert isinstance(outcome.output, ToolError)
    assert outcome.output.error == 'invalid_arguments'
    assert field in outcome.output.message  # so the model can fix its call
    assert name in outcome.output.message  # and knows which tool to call again


def test_an_unknown_message_id_returns_a_tool_error_saying_what_to_do(mailbox):
    outcome = ReadEmail(mailbox).call({'message_id': 'no-such-id', 'reason': 'Read it.'})

    assert isinstance(outcome.output, ToolError)
    assert outcome.output.error == 'not_found'
    assert 'no-such-id' in outcome.output.message
    assert 'fetch_unread_emails' in outcome.output.message  # where a valid ID comes from


@pytest.mark.parametrize('origin', ['synthetic', 'email_content'])  # fixture, real mailbox
@pytest.mark.parametrize(
    ('name', 'arguments'),
    [
        ('fetch_unread_emails', {'reason': 'Start triage.'}),
        ('read_email', {'message_id': LUNCH, 'reason': 'Read it.'}),
        ('read_email', {'message_id': 'no-such-id', 'reason': 'Read it.'}),
        ('read_email', {'reason': ''}),
    ],
)
def test_every_outcome_carries_its_mailbox_origin_errors_included(mailbox, name, arguments, origin):
    mailbox.data_origin = origin

    outcome = inbox_tools(mailbox)[name].call(arguments)

    assert outcome.origin == origin


def disk_on_fire(message_id: str):
    raise RuntimeError('disk on fire')


def missing_metadata(message_id: str):
    raise KeyError('threadId')  # a LookupError, like MessageNotFoundError, but a bug


def bad_data_from_our_side(message_id: str):
    # A ValidationError from our own code, not from the model's arguments: telling
    # the model to fix its arguments would send it round in circles.
    return TypeAdapter(int).validate_python('not a number')


@pytest.mark.parametrize(
    ('broken', 'error'),
    [
        (disk_on_fire, RuntimeError),
        (missing_metadata, KeyError),
        (bad_data_from_our_side, ValidationError),
    ],
)
def test_an_unexpected_failure_is_raised_not_handed_to_the_model(
    mailbox, monkeypatch, broken, error
):
    # Only the expected failures become tool errors. A bug in our code should crash
    # loudly, not reach the model looking like its own mistake.
    monkeypatch.setattr(mailbox, 'get_message', broken)

    with pytest.raises(error):
        ReadEmail(mailbox).call({'message_id': LUNCH, 'reason': 'Read it.'})

"""The triage action tools: each mailbox change the agent can make (ticket #13)."""

import pytest

from email_agent.mail import Draft, FixtureProvider
from email_agent.tools import MAIL_TOOLS, Tool, ToolError

LUNCH = '19a8f3c2b1d04e01'  # unread, in the inbox, not starred or labelled
LUNCH_THREAD = '19a7e0d1c2b3a400'

# Each label action, its extra arguments, and the change it makes and reports.
LABEL_ACTIONS = [
    ('star_email', {}, {'added': ['STARRED'], 'removed': []}),
    ('mark_as_read', {}, {'added': [], 'removed': ['UNREAD']}),
    ('archive_email', {}, {'added': [], 'removed': ['INBOX']}),
    ('report_spam', {}, {'added': ['SPAM'], 'removed': ['INBOX']}),
    ('trash_email', {}, {'added': ['TRASH'], 'removed': ['INBOX']}),
    ('apply_label', {'label_name': 'Finance'}, {'added': ['Finance'], 'removed': []}),
]
ACTIONS = {
    'star_email': {},
    'mark_as_read': {},
    'archive_email': {},
    'report_spam': {},
    'trash_email': {},
    'apply_label': {'label_name': 'Finance'},
    'draft_reply': {'body': 'Thursday at noon works for me.'},
}


@pytest.fixture
def mailbox(contract_mailbox) -> FixtureProvider:
    return FixtureProvider(contract_mailbox)


def tool(mailbox: FixtureProvider, name: str) -> Tool:
    [found] = [cls(mailbox) for cls in MAIL_TOOLS if cls.name == name]
    return found


def act(mailbox: FixtureProvider, name: str, message_id: str = LUNCH, **arguments):
    return tool(mailbox, name).call(
        {'message_id': message_id, 'reason': 'Triage.', **ACTIONS[name], **arguments}
    )


@pytest.mark.parametrize(
    ('name', 'extra'),
    [
        ('star_email', set()),
        ('mark_as_read', set()),
        ('archive_email', set()),
        ('report_spam', set()),
        ('trash_email', set()),
        ('apply_label', {'label_name'}),
        ('draft_reply', {'body'}),
    ],
)
def test_each_action_tool_exports_its_schema(mailbox, name, extra):
    schema = tool(mailbox, name).schema()

    assert schema.description  # written for the model: what it does, when to use it
    required = {'reason', 'message_id'} | extra
    assert set(schema.input_schema['required']) == required
    assert set(schema.input_schema['properties']) == required
    assert schema.input_schema['additionalProperties'] is False
    assert all(field.get('description') for field in schema.input_schema['properties'].values())


@pytest.mark.parametrize(('name', 'arguments', 'change'), LABEL_ACTIONS)
def test_a_label_action_changes_only_that_message_and_reports_the_change(
    mailbox, name, arguments, change
):
    before = mailbox.snapshot()

    outcome = act(mailbox, name, **arguments)

    after = mailbox.snapshot()
    assert outcome.output.model_dump() == {'message_id': LUNCH, **change}
    # The report matches what really changed, here where every change is a real one.
    assert after[LUNCH] - before[LUNCH] == set(change['added'])
    assert before[LUNCH] - after[LUNCH] == set(change['removed'])
    assert {k: v for k, v in after.items() if k != LUNCH} == {
        k: v for k, v in before.items() if k != LUNCH
    }
    assert mailbox.list_drafts() == []
    assert outcome.origin == 'synthetic'


def test_draft_reply_only_creates_a_draft_on_the_message_thread(mailbox):
    before = mailbox.snapshot()

    outcome = act(mailbox, 'draft_reply', body='Thursday at noon works for me.')

    [draft] = mailbox.list_drafts()
    assert draft == Draft(
        id=draft.id,
        thread_id=LUNCH_THREAD,
        in_reply_to=LUNCH,
        body='Thursday at noon works for me.',
    )
    assert outcome.output.model_dump() == {
        'draft_id': draft.id,
        'thread_id': LUNCH_THREAD,
        'in_reply_to': LUNCH,
    }
    assert mailbox.snapshot() == before  # drafting changes no labels, and sends nothing


@pytest.mark.parametrize('name', ACTIONS)
def test_an_action_on_an_unknown_id_is_a_tool_error_and_changes_nothing(mailbox, name):
    before = mailbox.snapshot()

    outcome = act(mailbox, name, message_id='no-such-id')

    assert isinstance(outcome.output, ToolError)
    assert outcome.output.error == 'not_found'
    assert 'no-such-id' in outcome.output.message
    assert mailbox.snapshot() == before
    assert mailbox.list_drafts() == []


@pytest.mark.parametrize('label_name', ['', '   ', 'INBOX', ' starred ', 'Spam', 'TRASH'])
def test_a_blank_or_system_label_name_is_refused_as_bad_arguments(mailbox, label_name):
    # System labels change only through their own tools (star_email, archive_email, ...).
    before = mailbox.snapshot()

    outcome = act(mailbox, 'apply_label', label_name=label_name)

    assert isinstance(outcome.output, ToolError)
    assert outcome.output.error == 'invalid_arguments'
    assert 'label_name' in outcome.output.message
    assert mailbox.snapshot() == before


def test_a_label_name_is_applied_without_surrounding_spaces(mailbox):
    outcome = act(mailbox, 'apply_label', label_name='  Finance ')

    assert outcome.output.model_dump()['added'] == ['Finance']
    assert 'Finance' in mailbox.snapshot()[LUNCH]


def test_a_blank_draft_is_refused_as_bad_arguments(mailbox):
    outcome = act(mailbox, 'draft_reply', body='')

    assert isinstance(outcome.output, ToolError)
    assert outcome.output.error == 'invalid_arguments'
    assert 'body' in outcome.output.message
    assert mailbox.list_drafts() == []

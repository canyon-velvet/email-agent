"""The model router: data tags and the routing policy (ticket #10)."""

from dataclasses import asdict

import pytest

from email_agent.model import ScriptedModelClient
from email_agent.router import DEFAULT_POLICY, ModelRouter, RoutingError
from email_agent.trace import read_trace, start_run

# Stand-ins for real models. The router only picks one; it never calls it.
CLOUD_MODEL = ScriptedModelClient([])
LOCAL_MODEL = ScriptedModelClient([])


def both_models() -> ModelRouter:
    return ModelRouter({'cloud': CLOUD_MODEL, 'local': LOCAL_MODEL})


def test_the_default_policy_keeps_real_email_local():
    assert DEFAULT_POLICY == {
        'email_content': ('local',),
        'synthetic': ('cloud', 'local'),
        'public': ('cloud', 'local'),
    }


@pytest.mark.parametrize(
    ('origins', 'tag'),
    [
        ([], 'public'),
        (['public'], 'public'),
        (['public', 'synthetic', 'public'], 'synthetic'),
        (['email_content'], 'email_content'),
        (['email_content', 'public'], 'email_content'),
        (['synthetic', 'public', 'email_content'], 'email_content'),
    ],
)
def test_a_request_is_tagged_with_its_most_sensitive_input(origins, tag):
    # Any iterable will do, including a generator, which can be read only once.
    _, decision = both_models().route(iter(origins))

    assert decision.tag == tag


def test_an_unknown_origin_is_refused_not_treated_as_public():
    # A misspelling (say, from a trace read back as plain strings) must never be
    # guessed harmless: refusing it keeps real email off the cloud.
    with pytest.raises(ValueError):
        both_models().route(['synthetic', 'emial_content'])  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ('origin', 'destination'),
    [('email_content', 'local'), ('synthetic', 'cloud'), ('public', 'cloud')],
)
def test_with_both_models_a_request_goes_to_its_first_allowed_destination(origin, destination):
    client, decision = both_models().route([origin])

    assert client is {'cloud': CLOUD_MODEL, 'local': LOCAL_MODEL}[destination]
    assert decision.destination == destination


def test_with_only_a_cloud_model_real_email_is_refused_not_sent_to_the_cloud():
    router = ModelRouter({'cloud': CLOUD_MODEL})

    assert router.route(['synthetic'])[0] is CLOUD_MODEL
    # Fail closed: no fallback to a model the policy doesn't allow.
    with pytest.raises(RoutingError) as raised:
        router.route(['synthetic', 'email_content'])
    assert 'email_content' in str(raised.value)  # the tag
    assert 'local' in str(raised.value)  # where the policy allows it


@pytest.mark.parametrize('origin', ['email_content', 'synthetic', 'public'])
def test_with_only_a_local_model_everything_goes_local(origin):
    client, decision = ModelRouter({'local': LOCAL_MODEL}).route([origin])

    assert client is LOCAL_MODEL
    assert decision.destination == 'local'


def test_the_router_follows_whatever_policy_table_it_is_given():
    router = ModelRouter(
        {'cloud': CLOUD_MODEL, 'local': LOCAL_MODEL},
        policy={'email_content': ('local',), 'synthetic': ('local', 'cloud')},
    )

    # The table's order is the order of preference.
    assert router.route(['synthetic'])[0] is LOCAL_MODEL
    # A tag the table leaves out may go nowhere, and the error says so.
    with pytest.raises(RoutingError, match='public') as raised:
        router.route(['public'])
    assert 'nowhere' in str(raised.value)


def test_the_router_remembers_nothing_between_requests():
    # Carrying taint is the caller's job: it passes every origin that has been in
    # the conversation, pruned outputs included. The router judges each request alone.
    router = both_models()
    router.route(['email_content'])

    assert router.route(['public'])[0] is CLOUD_MODEL


def test_the_decision_can_be_recorded_in_the_trace(tmp_path):
    _, decision = both_models().route(['public', 'email_content'])

    trace = start_run(tmp_path)
    trace.append('model_routed', asdict(decision))

    [event] = read_trace(tmp_path, trace.run_id)
    assert event.payload == {
        'tag': 'email_content',
        'destination': 'local',
        'reason': decision.reason,
    }
    assert decision.reason  # why, in words, for whoever reads the trace

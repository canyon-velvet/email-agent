"""Fixture-provider behaviour outside the shared mail-provider contract."""

from email_agent.mail import FixtureProvider


def test_fixture_data_is_tagged_synthetic(contract_mailbox):
    # The model router (#10) uses this tag: synthetic data may go to a cloud model.
    assert FixtureProvider(contract_mailbox).data_origin == "synthetic"

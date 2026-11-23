"""The model router: decides which model may see a request, from where its data came.

Every request is tagged with the most sensitive origin among its inputs, and a policy
table says where each tag may go. Routing is code, never a model decision, so an
injected email can't talk its way past it. A request with nowhere to go is refused:
there is no fallback to another model.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from email_agent.mail.mail_provider import DataOrigin
from email_agent.model.model_client import ModelClient

Destination = Literal['cloud', 'local']

# For each tag, where it may go, in order of preference.
Policy = Mapping[DataOrigin, tuple[Destination, ...]]

# Least to most sensitive. A request takes the most sensitive tag among its inputs.
SENSITIVITY: tuple[DataOrigin, ...] = ('public', 'synthetic', 'email_content')

# Real email stays on this machine; fixtures and content-free requests may use the cloud.
DEFAULT_POLICY: Policy = {
    'email_content': ('local',),
    'synthetic': ('cloud', 'local'),
    'public': ('cloud', 'local'),
}


class RoutingError(Exception):
    """Raised when the policy allows a request nowhere among the configured models."""


@dataclass(frozen=True)
class RoutingDecision:
    """Where one request went and why, for the trace."""

    tag: DataOrigin
    destination: Destination
    reason: str


class ModelRouter:
    """Picks the model for each request, following a policy table.

    `clients` holds at most one model per destination: only a cloud model today, both
    once a local model is set up. The router keeps no state between requests.
    """

    def __init__(
        self, clients: Mapping[Destination, ModelClient], policy: Policy = DEFAULT_POLICY
    ) -> None:
        self._clients = clients
        self._policy = policy

    def route(self, origins: Iterable[DataOrigin]) -> tuple[ModelClient, RoutingDecision]:
        """Return the model for a request whose inputs came from `origins`, and why.

        Pass the origin of everything that has been in the conversation, including
        outputs since pruned: the model may still be repeating what they said. No
        origins means a content-free request, tagged 'public'.

        The request goes to the first destination its tag allows that has a model.
        Raises RoutingError if there is none, including for a tag the policy leaves out.
        """
        # cast: given a default, pyright widens max()'s result to str.
        tag = cast(DataOrigin, max(origins, key=SENSITIVITY.index, default='public'))
        allowed = self._policy.get(tag, ())
        for dest in allowed:
            if dest in self._clients:
                return self._clients[dest], RoutingDecision(
                    tag=tag,
                    destination=dest,
                    reason=f'{tag} may go to {", ".join(allowed)}; using {dest}',
                )
        raise RoutingError(f'no model for {tag} data: the policy allows {", ".join(allowed)}')

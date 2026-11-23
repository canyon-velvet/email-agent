from email_agent.mail.mail_provider import DataOrigin
from email_agent.model.model_client import ModelClient

from typing import Literal
from dataclasses import dataclass

Destination = Literal['cloud', 'local']

SENSITIVITY = ('public', 'synthetic', 'email_content')
DEFAULT_POLICY = {
    'email_content': ('local',),
    'synthetic': ('cloud', 'local'),
    'public': ('cloud', 'local'),
}

class RoutingError(Exception): ...

@dataclass(frozen=True)
class RoutingDecision:
    tag: DataOrigin
    destination: Destination
    reason: str

class ModelRouter:
    def __init__(self, clients, policy=DEFAULT_POLICY):
        self._clients = clients
        self._policy = policy

    def route(self, origins):
        tag = max(origins, key=SENSITIVITY.index, default='public')
        allowed = self._policy.get(tag, ())
        for dest in allowed:
            if dest in self._clients:
                return self._clients[dest], RoutingDecision(tag=tag, destination=dest, reason=f'{tag} may go to {", ".join(allowed)}; using {dest}')
        raise RoutingError(f'no model for {tag} data: the policy allows {', '.join(allowed)}')
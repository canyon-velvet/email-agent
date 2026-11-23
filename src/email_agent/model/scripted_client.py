"""A scripted test double for the model: pre-written replies, every request recorded."""

from collections.abc import Iterable

from email_agent.model.model_client import (
    ModelReply,
    ModelRequest,
)


class ScriptExhaustedError(RuntimeError):
    """Raised when a scripted client is called more times than it has replies."""


class ScriptedModelClient:
    """A model that returns pre-written replies, in order, and records each request.

    A spy: tests script the model's side of a conversation, then check exactly what
    the loop sent in `requests`. Each request is recorded as a deep copy, so later
    changes to the caller's objects can't alter the record, and the request that
    runs out is recorded too. Running out of replies raises ScriptExhaustedError,
    so a loop that calls the model too often fails the test loudly.
    """

    def __init__(self, replies: Iterable[ModelReply]) -> None:
        self._replies = list(replies)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelReply:
        """Record the request and return the next scripted reply."""
        self.requests.append(request)
        n = len(self.requests)
        k = len(self._replies)
        if n - 1 >= k:
            raise ScriptExhaustedError(f'no scripted reply for request {n}; only {k} were scripted')
        return self._replies[n - 1]

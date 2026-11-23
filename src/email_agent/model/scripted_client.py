from collections.abc import Iterable

from email_agent.model.model_client import (
    ModelRequest,
    ModelReply,
)

class ScriptExhaustedError(RuntimeError): ...

class ScriptedModelClient:
    def __init__(self, replies: Iterable[ModelReply]):
        self._replies = list(replies)
        self.requests = []

    def complete(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        n = len(self.requests)
        k = len(self._replies)
        if n - 1 >= k:
            raise ScriptExhaustedError(f'no scripted reply for request {n}; only {k} were scripted')
        return self._replies[n - 1]

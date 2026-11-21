from dataclasses import dataclass
from typing import Protocol, Literal

@dataclass(frozen=True)
class MessageSummary:
    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str

DataOrigin = Literal["email_content", "synthetic", "public"]

class MailProvider(Protocol):
    data_origin: DataOrigin

    def list_unread(self) -> list[MessageSummary]: ...
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal, ClassVar, Any
from dataclasses import dataclass
from email_agent.mail.mail_provider import DataOrigin, MailProvider, MessageNotFoundError
from email_agent.model.model_client import ToolSchema
from abc import ABC, abstractmethod

class ToolInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(
        min_length=1,
        description=(
            'One sentence on why you are making this call, for example "Check whether '
            'this invoice needs a reply." It is recorded so your actions can be reviewed.'
        ),
    )

class ToolError(BaseModel):
    error: Literal['invalid_arguments', 'not_found']
    message: str

@dataclass(frozen=True)
class ToolOutcome:
    output: BaseModel
    origin: DataOrigin

class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[ToolInput]]

    def __init__(self, mailbox: MailProvider):
        self._mailbox = mailbox

    @classmethod
    def schema(cls) -> ToolSchema:
        return ToolSchema(cls.name, cls.description, cls.input_model.model_json_schema())

    def call(self, arguments: dict[str, Any]) -> ToolOutcome:
        origin = self._mailbox.data_origin
        try:
            args = self.input_model.model_validate(arguments)
        except ValidationError as e:
            # e.g. "message_id: Field required; id: Extra inputs are not permitted"
            problems = '; '.join(
                f'{".".join(str(part) for part in error["loc"])}: {error["msg"]}'
                for error in e.errors()
            )
            message = f'Invalid arguments ({problems}). Fix them and call {self.name} again.'
            return ToolOutcome(ToolError(error='invalid_arguments', message=message), origin)

        try:
            output = self.run(args)
        except MessageNotFoundError as e:
            message = f"No message with ID '{e}'. Use an ID from fetch_unread_emails."
            return ToolOutcome(ToolError(error='not_found', message=message), origin)
        return ToolOutcome(output, origin)

    @abstractmethod
    def run(self, args: Any) -> BaseModel: ...



from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal, ClassVar, Any
from dataclasses import dataclass
from email_agent.mail.mail_provider import DataOrigin, MailProvider, MessageNotFoundError
from email_agent.model.model_client import ToolSchema
from abc import ABC, abstractmethod

class ToolInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=1, description='Why you are calling this tool, in one sentence.')

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
            return ToolOutcome(ToolError(error='invalid_arguments', message='TODO'), origin)

        try:
            output = self.run(args)
        except MessageNotFoundError as e:
             return ToolOutcome(ToolError(error='not_found', message='TODO'), origin)
        return ToolOutcome(output, origin)

    @abstractmethod
    def run(self, args: Any) -> BaseModel: ...



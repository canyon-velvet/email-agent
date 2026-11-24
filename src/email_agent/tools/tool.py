"""The tool protocol: how every agent tool declares its inputs and outputs, and fails.

The loop calls a tool with the arguments the model wrote, as a plain dict:

    tool.call(arguments) -> ToolOutcome(output, origin)
      validate the arguments against the tool's input model
      run the tool's own work
      turn the expected failures (bad arguments, an unknown ID) into a ToolError
      tag the outcome, errors included, with the mailbox's data origin

Inputs, outputs and errors are pydantic models, because they cross the boundary with
the model: arguments arrive as JSON it wrote, and outputs go back as JSON it reads.
The origin stays outside them, so the model never sees what decides routing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from email_agent.mail.mail_provider import DataOrigin, MailProvider, MessageNotFoundError
from email_agent.model.model_client import ToolSchema


class ToolInput(BaseModel):
    """The base of every tool's input: a required, non-empty `reason`.

    Unknown arguments are refused, so a misspelled one is an error rather than
    silently ignored. Subclasses inherit that, and it puts
    `"additionalProperties": false` in the schema, as strict tool use requires.
    """

    model_config = ConfigDict(extra='forbid')
    reason: str = Field(
        min_length=1,
        description=(
            'One sentence on why you are making this call, for example "Check whether '
            'this invoice needs a reply." It is recorded so your actions can be reviewed.'
        ),
    )


class ToolError(BaseModel):
    """A failure the model can act on: what went wrong, and what to do next."""

    error: Literal['invalid_arguments', 'not_found', 'unknown_tool']
    message: str


@dataclass(frozen=True)
class ToolOutcome:
    """What a call produced (the tool's output, or a ToolError) and its data origin."""

    output: BaseModel
    origin: DataOrigin


class Tool(ABC):
    """An agent tool that works on a mailbox.

    Each subclass sets `name`, `description` (a prompt: what the tool does, when to
    use it, what it returns) and `input_model`, and writes `run`. Everything else,
    validation, errors and origin tagging, comes from `call`.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[ToolInput]]

    def __init__(self, mailbox: MailProvider) -> None:
        self._mailbox = mailbox

    @classmethod
    def schema(cls) -> ToolSchema:
        """Describe this tool for a model request, with its input model's JSON schema."""
        return ToolSchema(cls.name, cls.description, cls.input_model.model_json_schema())

    def call(self, arguments: dict[str, Any]) -> ToolOutcome:
        """Run the tool on the arguments the model wrote.

        Bad arguments or an unknown message ID come back as a ToolError, never an
        exception. Any other exception is a bug, and is raised.
        """
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
    def run(self, args: Any) -> BaseModel:
        """Do the tool's work. `args` is already valid: an instance of `input_model`.

        Raise MessageNotFoundError for an unknown ID; `call` reports it to the model.
        """
        ...

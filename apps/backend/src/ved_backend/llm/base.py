from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator


class LLMRequestError(RuntimeError):
    pass


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class ToolOutcome(BaseModel):
    call_id: str
    content: str
    is_error: bool = False


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    text: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    provider_content: list[dict[str, Any]] | None = Field(default=None, exclude=True)


class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    outcomes: list[ToolOutcome]


Message = UserMessage | AssistantMessage | ToolResultMessage


class TextDelta(BaseModel):
    text: str


class ReasoningDelta(BaseModel):
    pass


TOKEN_COUNT_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


class ModelUsage(BaseModel):
    model: str
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0

    @field_validator(*TOKEN_COUNT_FIELDS, mode="before")
    @classmethod
    def missing_count_is_zero(cls, value: int | None) -> int:
        return 0 if value is None else value


UsageReporter = Callable[[ModelUsage], Awaitable[None]]


StreamChunk = TextDelta | ReasoningDelta | AssistantMessage


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AssistantMessage: ...

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AsyncIterator[StreamChunk]: ...

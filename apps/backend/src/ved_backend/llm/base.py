from collections.abc import Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


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


class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    outcomes: list[ToolOutcome]


Message = UserMessage | AssistantMessage | ToolResultMessage


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

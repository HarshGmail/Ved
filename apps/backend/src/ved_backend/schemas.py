from typing import Any, Literal

from pydantic import BaseModel, Field

ServiceState = Literal["ok", "degraded", "down"]

MAX_PROMPT_LENGTH = 2000


class HealthStatus(BaseModel):
    status: ServiceState
    version: str
    database: ServiceState


class ToolInvocation(BaseModel):
    name: str
    arguments: dict[str, Any]
    failed: bool


class AgentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)


class AgentReply(BaseModel):
    text: str
    model: str
    tool_calls: list[ToolInvocation] = Field(default_factory=list)

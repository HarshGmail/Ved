import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="Omit to start a new conversation; the reply carries the id.",
    )


class AgentTurn(BaseModel):
    text: str
    model: str
    tool_calls: list[ToolInvocation] = Field(default_factory=list)


class AgentReply(AgentTurn):
    conversation_id: uuid.UUID


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime


class ConversationList(BaseModel):
    conversations: list[ConversationSummary]


class TranscriptMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    role: str
    text: str
    model: str | None
    tool_calls: list[ToolInvocation]
    created_at: datetime


class ConversationTranscript(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    messages: list[TranscriptMessage]

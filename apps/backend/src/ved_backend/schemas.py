import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ved_backend.connections import (
    TOKEN_MAX_LENGTH,
    validate_name,
    validate_token,
    validate_url,
)

ServiceState = Literal["ok", "degraded", "down"]

MAX_PROMPT_LENGTH = 2000
MAX_CLAUDE_BALANCE_USD = 10_000
VOICE_TEXT_LIMIT = 1500
VOICE_MIN_SPEED = 0.8
VOICE_MAX_SPEED = 1.3


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
    voice: bool = Field(
        default=False,
        description="True when the reply is read aloud, so it should be short.",
    )


class VoiceStatus(BaseModel):
    stt: bool
    tts_languages: list[str]
    default_voice: str | None


class VoiceInfo(BaseModel):
    id: str
    name: str
    language: str
    gender: str


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=VOICE_TEXT_LIMIT)
    voice: str | None = None
    speed: float | None = Field(default=None, ge=VOICE_MIN_SPEED, le=VOICE_MAX_SPEED)


class VoiceTranscript(BaseModel):
    text: str
    language: str
    duration_seconds: float


class AgentTurn(BaseModel):
    text: str
    model: str
    tool_calls: list[ToolInvocation] = Field(default_factory=list)


class AgentReply(AgentTurn):
    conversation_id: uuid.UUID


class TokenEvent(BaseModel):
    text: str


class ToolStartedEvent(BaseModel):
    name: str
    arguments: dict[str, Any]


class ToolFinishedEvent(BaseModel):
    name: str
    failed: bool


class ThinkingEvent(BaseModel):
    pass


class AcknowledgementEvent(BaseModel):
    text: str


class StreamErrorEvent(BaseModel):
    detail: str


AgentEvent = (
    TokenEvent
    | ThinkingEvent
    | AcknowledgementEvent
    | ToolStartedEvent
    | ToolFinishedEvent
    | AgentTurn
)


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


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    keys: PushKeys
    label: str | None = Field(default=None, max_length=200)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)


class PushStatus(BaseModel):
    configured: bool
    public_key: str | None
    subscriptions: int


class PushTestResult(BaseModel):
    sent: int
    expired: int


class ConversationStatus(BaseModel):
    answering: bool


class ConversationTranscript(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    messages: list[TranscriptMessage]


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    media_type: str
    size_bytes: int
    page_count: int | None
    status: str
    error: str | None
    created_at: datetime


class DocumentList(BaseModel):
    documents: list[DocumentSummary]


class MeResponse(BaseModel):
    email: str
    name: str | None = None


class FamilyPersonSummary(BaseModel):
    id: str
    name: str
    aliases: list[str]
    relation: str | None
    birthday_month: int | None
    birthday_day: int | None
    language: str | None


class FamilyOverview(BaseModel):
    people: list[FamilyPersonSummary]
    me: FamilyPersonSummary | None
    owner_name: str | None


class FamilyNoteSummary(BaseModel):
    id: uuid.UUID
    text: str
    author_name: str | None
    created_at: datetime
    mine: bool


class FamilyNoteList(BaseModel):
    notes: list[FamilyNoteSummary]


class PrivateNoteSummary(BaseModel):
    id: uuid.UUID
    text: str
    created_at: datetime


class PrivateNoteList(BaseModel):
    notes: list[PrivateNoteSummary]


class ConnectionSummary(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    enabled: bool
    has_token: bool
    created_at: datetime


class ConnectionList(BaseModel):
    connections: list[ConnectionSummary]


class ConnectionCreate(BaseModel):
    name: str
    url: str = Field(max_length=2048)
    token: str = Field(max_length=2048)

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return validate_name(value)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return validate_url(value)

    @field_validator("token")
    @classmethod
    def check_token(cls, value: str) -> str:
        return validate_token(value)


class ConnectionUpdate(BaseModel):
    enabled: bool | None = None
    url: str | None = Field(default=None, max_length=2048)
    token: str | None = Field(default=None, max_length=TOKEN_MAX_LENGTH)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        return None if value is None else validate_url(value)

    @field_validator("token")
    @classmethod
    def check_token(cls, value: str | None) -> str | None:
        return None if value is None else validate_token(value)


class ConnectionTest(BaseModel):
    ok: bool
    tool_count: int
    error: str | None


class ConnectionPresetSummary(BaseModel):
    id: str
    label: str
    name: str
    url: str
    help: str


class ConnectionPresetList(BaseModel):
    presets: list[ConnectionPresetSummary]


class ClaudeUsage(BaseModel):
    provider: str
    model: str
    tracking: bool
    balance_usd: float | None
    balance_set_at: datetime | None
    spent_since_balance_usd: float
    remaining_usd: float | None
    today_usd: float
    today_messages: int
    month_usd: float
    last_30_days_usd: float
    can_edit: bool


class ClaudeBalanceUpdate(BaseModel):
    balance_usd: Decimal = Field(ge=0, le=MAX_CLAUDE_BALANCE_USD)

from pydantic import BaseModel, Field

from ved_voice.limits import DEFAULT_SPEED, MAX_SPEED, MAX_TEXT_CHARACTERS, MIN_SPEED


class Voice(BaseModel):
    id: str
    name: str
    language: str
    gender: str


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARACTERS)
    voice: str | None = None
    speed: float = Field(default=DEFAULT_SPEED, ge=MIN_SPEED, le=MAX_SPEED)


class StatusResponse(BaseModel):
    stt: bool
    tts_languages: list[str]
    default_voice: str


class TranscriptResponse(BaseModel):
    text: str
    language: str
    duration_seconds: float

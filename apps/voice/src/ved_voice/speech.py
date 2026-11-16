from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from ved_voice.schemas import Voice


class AudioTooLongError(Exception):
    def __init__(self, limit_seconds: float) -> None:
        super().__init__(f"Audio is longer than {limit_seconds:g} seconds")
        self.limit_seconds = limit_seconds


class AudioDecodeError(Exception):
    pass


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    duration_seconds: float


class SpeechSynthesizer(Protocol):
    sample_rate: int

    def voices(self) -> list[Voice]: ...

    def synthesize(
        self, text: str, voice: str, speed: float
    ) -> NDArray[np.float32]: ...


class SpeechRecognizer(Protocol):
    def transcribe(
        self, audio: bytes, language: str | None, max_seconds: float
    ) -> Transcript: ...

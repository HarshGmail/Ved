import numpy as np
from fastapi.testclient import TestClient

from ved_voice.app import create_app
from ved_voice.schemas import Voice
from ved_voice.service import VoiceService
from ved_voice.speech import AudioTooLongError, Transcript

SAMPLE_RATE = 24000
ENGLISH_VOICE = Voice(id="bm_george", name="George", language="en", gender="male")
HINDI_VOICE = Voice(id="hf_alpha", name="Alpha", language="hi", gender="female")
WEBM_AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
WAV_AUDIO = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 64


class FakeSynthesizer:
    sample_rate = SAMPLE_RATE

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def voices(self) -> list[Voice]:
        return [ENGLISH_VOICE, HINDI_VOICE]

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        self.calls.append((text, voice, speed))
        return np.full(SAMPLE_RATE // 10, 0.5, dtype=np.float32)


class FakeRecognizer:
    def __init__(self, text: str = "hello there", duration: float = 1.5) -> None:
        self.text = text
        self.duration = duration
        self.calls: list[tuple[bytes, str | None, float]] = []

    def transcribe(
        self, audio: bytes, language: str | None, max_seconds: float
    ) -> Transcript:
        self.calls.append((audio, language, max_seconds))
        if self.duration > max_seconds:
            raise AudioTooLongError(max_seconds)
        return Transcript(
            text=self.text,
            language=language or "en",
            duration_seconds=self.duration,
        )


def client_for(synthesizer: FakeSynthesizer, recognizer) -> TestClient:
    service = VoiceService(
        synthesizer,
        recognizer,
        default_voice="bm_george",
        speech_concurrency=2,
        transcription_concurrency=1,
    )
    return TestClient(create_app(service))

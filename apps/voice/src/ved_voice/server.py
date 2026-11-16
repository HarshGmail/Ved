from pathlib import Path

from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict

from ved_voice.app import create_app
from ved_voice.kokoro_engine import KokoroSynthesizer
from ved_voice.service import VoiceService
from ved_voice.whisper_engine import FasterWhisperRecognizer

MODELS_DIR = Path("/opt/models")


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_VOICE_")

    kokoro_model_path: Path = MODELS_DIR / "kokoro" / "kokoro-v1.0.int8.onnx"
    kokoro_voices_path: Path = MODELS_DIR / "kokoro" / "voices-v1.0.bin"
    whisper_model_path: Path = MODELS_DIR / "whisper-small"
    default_voice: str = "bm_george"
    speech_concurrency: int = 2
    transcription_concurrency: int = 1
    transcription_threads: int = 4


def build_app() -> FastAPI:
    settings = VoiceSettings()
    service = VoiceService(
        KokoroSynthesizer(settings.kokoro_model_path, settings.kokoro_voices_path),
        FasterWhisperRecognizer(
            settings.whisper_model_path, threads=settings.transcription_threads
        ),
        default_voice=settings.default_voice,
        speech_concurrency=settings.speech_concurrency,
        transcription_concurrency=settings.transcription_concurrency,
    )
    return create_app(service)


app = build_app()

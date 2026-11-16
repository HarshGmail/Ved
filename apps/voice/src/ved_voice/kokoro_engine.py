from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro
from numpy.typing import NDArray

from ved_voice.schemas import Voice

SAMPLE_RATE = 24000
VOICE_NAME_SEPARATOR = "_"
LANGUAGE_BY_PREFIX = {"a": "en", "b": "en", "h": "hi"}
PHONEME_LANGUAGE_BY_PREFIX = {"a": "en-us", "b": "en-gb", "h": "hi"}
GENDER_BY_CODE = {"f": "female", "m": "male"}


def describe_voice(voice_id: str) -> Voice | None:
    code, separator, name = voice_id.partition(VOICE_NAME_SEPARATOR)
    language = LANGUAGE_BY_PREFIX.get(code[:1])
    gender = GENDER_BY_CODE.get(code[1:])
    if not separator or language is None or gender is None or not name:
        return None
    return Voice(id=voice_id, name=name.capitalize(), language=language, gender=gender)


class KokoroSynthesizer:
    sample_rate = SAMPLE_RATE

    def __init__(self, model_path: Path, voices_path: Path) -> None:
        self._engine = Kokoro(str(model_path), str(voices_path))
        described = (describe_voice(voice_id) for voice_id in self._engine.get_voices())
        self._voices = {voice.id: voice for voice in described if voice is not None}

    def voices(self) -> list[Voice]:
        return list(self._voices.values())

    def synthesize(self, text: str, voice: str, speed: float) -> NDArray[np.float32]:
        phoneme_language = PHONEME_LANGUAGE_BY_PREFIX[voice[0]]
        samples, _ = self._engine.create(
            text, voice=voice, speed=speed, lang=phoneme_language
        )
        return np.asarray(samples, dtype=np.float32)

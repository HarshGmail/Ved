from io import BytesIO
from pathlib import Path

import av
from faster_whisper import WhisperModel

from ved_voice.speech import AudioDecodeError, AudioTooLongError, Transcript

COMPUTE_TYPE = "int8"
DEVICE = "cpu"
DURATION_PRECISION = 2


class FasterWhisperRecognizer:
    def __init__(self, model_path: Path, *, threads: int) -> None:
        self._model = WhisperModel(
            str(model_path),
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            cpu_threads=threads,
        )

    def transcribe(
        self, audio: bytes, language: str | None, max_seconds: float
    ) -> Transcript:
        try:
            segments, info = self._model.transcribe(
                BytesIO(audio), language=language, vad_filter=True
            )
        except (av.FFmpegError, ValueError) as error:
            raise AudioDecodeError() from error
        if info.duration > max_seconds:
            raise AudioTooLongError(max_seconds)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcript(
            text=text,
            language=info.language,
            duration_seconds=round(info.duration, DURATION_PRECISION),
        )

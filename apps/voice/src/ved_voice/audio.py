import io
import wave
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

PCM_16_SAMPLE_WIDTH_BYTES = 2
PCM_16_PEAK = 32767
RIFF_MAGIC = b"RIFF"
WAVE_MAGIC = b"WAVE"
OGG_MAGIC = b"OggS"
EBML_MAGIC = b"\x1a\x45\xdf\xa3"
MP4_BOX_TYPE = b"ftyp"
MP4_BOX_TYPE_OFFSET = 4
RIFF_FORM_TYPE_OFFSET = 8

WAV = "wav"
OGG = "ogg"
WEBM = "webm"
MP4 = "mp4"


def sniff_container(data: bytes) -> str | None:
    if data[:4] == RIFF_MAGIC and data[RIFF_FORM_TYPE_OFFSET:12] == WAVE_MAGIC:
        return WAV
    if data[:4] == OGG_MAGIC:
        return OGG
    if data[:4] == EBML_MAGIC:
        return WEBM
    if data[MP4_BOX_TYPE_OFFSET : MP4_BOX_TYPE_OFFSET + 4] == MP4_BOX_TYPE:
        return MP4
    return None


def silence(seconds: float, sample_rate: int) -> NDArray[np.float32]:
    return np.zeros(round(seconds * sample_rate), dtype=np.float32)


def join_with_pauses(
    clips: Sequence[NDArray[np.float32]], sample_rate: int, pause_seconds: float
) -> NDArray[np.float32]:
    pause = silence(pause_seconds, sample_rate)
    pieces: list[NDArray[np.float32]] = []
    for clip in clips:
        if pieces:
            pieces.append(pause)
        pieces.append(clip)
    return np.concatenate(pieces)


def wav_bytes(samples: NDArray[np.float32], sample_rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * PCM_16_PEAK).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(PCM_16_SAMPLE_WIDTH_BYTES)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()

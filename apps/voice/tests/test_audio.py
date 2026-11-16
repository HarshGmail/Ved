import io
import wave

import numpy as np
import pytest

from ved_voice.audio import join_with_pauses, silence, sniff_container, wav_bytes

RATE = 24000


@pytest.mark.parametrize(
    ("data", "container"),
    [
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "wav"),
        (b"OggS\x00\x02", "ogg"),
        (b"\x1a\x45\xdf\xa3\x9f", "webm"),
        (b"\x00\x00\x00\x20ftypisom", "mp4"),
        (b"\x00\x00\x00\x20ftypM4A ", "mp4"),
        (b"RIFF\x00\x00\x00\x00AVI LIST", None),
        (b"plain text", None),
        (b"", None),
    ],
)
def test_containers_are_sniffed_from_magic_bytes(
    data: bytes, container: str | None
) -> None:
    assert sniff_container(data) == container


def test_wav_output_is_mono_16_bit_at_the_sample_rate() -> None:
    samples = np.linspace(-2.0, 2.0, RATE // 2, dtype=np.float32)

    with wave.open(io.BytesIO(wav_bytes(samples, RATE)), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == RATE
        assert reader.getnframes() == RATE // 2


def test_joined_clips_are_separated_by_pauses() -> None:
    first = np.ones(100, dtype=np.float32)
    second = np.ones(50, dtype=np.float32)

    joined = join_with_pauses([first, second], sample_rate=1000, pause_seconds=0.02)

    assert len(joined) == 100 + 20 + 50
    assert np.all(joined[100:120] == 0)


def test_silence_has_the_requested_length() -> None:
    assert len(silence(0.25, RATE)) == RATE // 4

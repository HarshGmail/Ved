import io
import wave

from fakes import (
    ENGLISH_VOICE,
    HINDI_VOICE,
    WAV_AUDIO,
    WEBM_AUDIO,
    FakeRecognizer,
    client_for,
)
from ved_voice.limits import MAX_AUDIO_BYTES, MAX_TEXT_CHARACTERS
from ved_voice.schemas import SpeakRequest
from ved_voice.service import RequestRejectedError, language_hint
from ved_voice.speech import AudioDecodeError


def test_status_reports_the_engines_and_default_voice(client) -> None:
    response = client.get("/status")

    assert response.status_code == 200
    assert response.json() == {
        "stt": True,
        "tts_languages": ["en", "hi"],
        "default_voice": "bm_george",
    }


def test_voices_list_every_installed_voice(client) -> None:
    response = client.get("/voices")

    assert response.status_code == 200
    assert response.json() == [
        ENGLISH_VOICE.model_dump(),
        HINDI_VOICE.model_dump(),
    ]


def test_speak_returns_a_mono_wav_at_24_khz(client) -> None:
    response = client.post("/speak", json={"text": "Good evening, sir."})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content), "rb") as reader:
        assert reader.getframerate() == 24000
        assert reader.getnchannels() == 1


def test_speak_uses_the_default_voice_and_speed(client, synthesizer) -> None:
    client.post("/speak", json={"text": "Hello."})

    assert synthesizer.calls == [("Hello.", "bm_george", 1.0)]


def test_speak_passes_the_requested_voice_and_speed(client, synthesizer) -> None:
    client.post("/speak", json={"text": "Namaste.", "voice": "hf_alpha", "speed": 1.2})

    assert synthesizer.calls == [("Namaste.", "hf_alpha", 1.2)]


def test_speak_synthesizes_each_sentence_in_order(client, synthesizer) -> None:
    client.post("/speak", json={"text": "First line. Second line? Third!"})

    assert [call[0] for call in synthesizer.calls] == [
        "First line.",
        "Second line?",
        "Third!",
    ]


def test_speak_strips_markup_before_synthesis(client, synthesizer) -> None:
    client.post("/speak", json={"text": "**Done** — see [notes](https://x.test) 🎉"})

    assert [call[0] for call in synthesizer.calls] == ["Done — see notes."]


def test_speak_rejects_text_that_is_only_markup(client, synthesizer) -> None:
    response = client.post("/speak", json={"text": "```\ncode\n```"})

    assert response.status_code == 422
    assert "nothing to say" in response.json()["detail"]
    assert synthesizer.calls == []


def test_speak_rejects_text_over_the_limit(client, synthesizer) -> None:
    response = client.post("/speak", json={"text": "a" * (MAX_TEXT_CHARACTERS + 1)})

    assert response.status_code == 422
    assert synthesizer.calls == []


def test_speak_accepts_text_at_the_limit(client) -> None:
    response = client.post("/speak", json={"text": "a" * MAX_TEXT_CHARACTERS})

    assert response.status_code == 200


def test_speak_rejects_speed_outside_the_range(client) -> None:
    assert client.post("/speak", json={"text": "Hi.", "speed": 0.5}).status_code == 422
    assert client.post("/speak", json={"text": "Hi.", "speed": 1.4}).status_code == 422


def test_speak_rejects_an_unknown_voice(client, synthesizer) -> None:
    response = client.post("/speak", json={"text": "Hi.", "voice": "zz_nobody"})

    assert response.status_code == 400
    assert "zz_nobody" in response.json()["detail"]
    assert synthesizer.calls == []


def test_transcribe_returns_text_language_and_duration(client) -> None:
    response = client.post(
        "/transcribe",
        files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "text": "hello there",
        "language": "en",
        "duration_seconds": 1.5,
    }


def test_transcribe_passes_the_language_hint_to_the_engine(client, recognizer) -> None:
    client.post(
        "/transcribe",
        files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")},
        data={"language": "te"},
    )

    assert recognizer.calls == [(WEBM_AUDIO, "te", 60.0)]


def test_auto_or_missing_language_lets_the_engine_detect(client, recognizer) -> None:
    client.post(
        "/transcribe",
        files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")},
        data={"language": "auto"},
    )
    client.post(
        "/transcribe",
        files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")},
    )

    assert [call[1] for call in recognizer.calls] == [None, None]


def test_unknown_language_hint_is_a_clear_client_error(client, recognizer) -> None:
    response = client.post(
        "/transcribe",
        files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")},
        data={"language": "klingon"},
    )

    assert response.status_code == 400
    assert "en, hi, te, auto" in response.json()["detail"]
    assert recognizer.calls == []


def test_oversized_audio_is_rejected_before_transcription(client, recognizer) -> None:
    oversized = WEBM_AUDIO + b"\x00" * MAX_AUDIO_BYTES

    response = client.post(
        "/transcribe", files={"audio": ("clip.webm", oversized, "audio/webm")}
    )

    assert response.status_code == 413
    assert "10 MB" in response.json()["detail"]
    assert recognizer.calls == []


def test_audio_longer_than_the_limit_is_rejected(synthesizer) -> None:
    client = client_for(synthesizer, FakeRecognizer(duration=61.0))

    response = client.post(
        "/transcribe", files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")}
    )

    assert response.status_code == 413
    assert "60 seconds" in response.json()["detail"]


def test_unsupported_audio_is_rejected(client, recognizer) -> None:
    response = client.post(
        "/transcribe", files={"audio": ("notes.txt", b"hello world", "text/plain")}
    )

    assert response.status_code == 415
    assert recognizer.calls == []


def test_wav_uploads_are_accepted(client) -> None:
    response = client.post(
        "/transcribe", files={"audio": ("clip.wav", WAV_AUDIO, "audio/wav")}
    )

    assert response.status_code == 200


def test_empty_upload_is_rejected(client) -> None:
    response = client.post(
        "/transcribe", files={"audio": ("clip.webm", b"", "audio/webm")}
    )

    assert response.status_code == 422


def test_undecodable_audio_is_a_client_error(synthesizer) -> None:
    class BrokenRecognizer(FakeRecognizer):
        def transcribe(self, audio, language, max_seconds):
            raise AudioDecodeError()

    client = client_for(synthesizer, BrokenRecognizer())

    response = client.post(
        "/transcribe", files={"audio": ("clip.webm", WEBM_AUDIO, "audio/webm")}
    )

    assert response.status_code == 422
    assert "decode" in response.json()["detail"]


def test_language_hint_normalisation() -> None:
    assert language_hint(None) is None
    assert language_hint("  AUTO ") is None
    assert language_hint(" Hi ") == "hi"


def test_speak_request_defaults() -> None:
    request = SpeakRequest(text="Hi")

    assert request.voice is None
    assert request.speed == 1.0


def test_rejected_request_carries_status_and_detail() -> None:
    error = RequestRejectedError(413, "too big")

    assert (error.status_code, error.detail) == (413, "too big")

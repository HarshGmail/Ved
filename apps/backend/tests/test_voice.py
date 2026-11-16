import json
import uuid

import httpx2
import pytest
from fastapi.testclient import TestClient
from ved_db import User

from ved_backend.main import app
from ved_backend.schemas import VoiceInfo, VoiceStatus, VoiceTranscript
from ved_backend.users import current_user
from ved_backend.voice import (
    MAX_AUDIO_BYTES,
    SPEAK_TIMEOUT_SECONDS,
    TRANSCRIBE_TIMEOUT_SECONDS,
    UNAVAILABLE_MESSAGE,
    UNREACHABLE_STATUS,
    VoiceClient,
    VoiceRejectedError,
    VoiceUnavailableError,
)

USER = User(id=uuid.uuid4(), email="first@example.com", name=None)
WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x01\x02\x03"
STATUS_BODY = {
    "stt": True,
    "tts_languages": ["en", "hi"],
    "default_voice": "bm_george",
}
TRANSCRIPT_BODY = {"text": "namaste", "language": "hi", "duration_seconds": 2.0}


def service_answering(handler) -> VoiceClient:
    return VoiceClient(
        "http://voice.test:8300/", transport=httpx2.MockTransport(handler)
    )


def unreachable(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


def json_response(body, status_code: int = 200) -> httpx2.Response:
    return httpx2.Response(status_code, json=body)


def wav_response(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, content=WAV, headers={"content-type": "audio/wav"})


@pytest.fixture
def signed_in():
    app.dependency_overrides[current_user] = lambda: USER
    yield
    app.dependency_overrides.pop(current_user, None)


@pytest.fixture
def voice_service(signed_in):
    def install(handler) -> None:
        app.state.voice = service_answering(handler)

    yield install
    app.state.voice = None


async def test_status_reads_the_service() -> None:
    client = service_answering(lambda request: json_response(STATUS_BODY))

    status = await client.status()

    assert status == VoiceStatus(
        stt=True, tts_languages=["en", "hi"], default_voice="bm_george"
    )


async def test_status_falls_back_when_the_service_is_unreachable() -> None:
    assert await service_answering(unreachable).status() == UNREACHABLE_STATUS


async def test_status_falls_back_when_the_service_errors() -> None:
    client = service_answering(lambda request: httpx2.Response(500))

    assert await client.status() == UNREACHABLE_STATUS


async def test_voices_are_parsed_from_the_service() -> None:
    body = [{"id": "bm_george", "name": "George", "language": "en", "gender": "male"}]

    voices = await service_answering(lambda request: json_response(body)).voices()

    assert voices == [
        VoiceInfo(id="bm_george", name="George", language="en", gender="male")
    ]


async def test_speak_forwards_the_body_and_streams_the_wav() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["timeout"] = request.extensions["timeout"]["read"]
        return wav_response(request)

    client = service_answering(handler)
    upstream = await client.speak({"text": "Good evening.", "speed": 1.1})
    streamed = b"".join([chunk async for chunk in upstream.aiter_bytes()])
    await upstream.aclose()

    assert seen == {
        "path": "/speak",
        "body": {"text": "Good evening.", "speed": 1.1},
        "timeout": SPEAK_TIMEOUT_SECONDS,
    }
    assert streamed == WAV


async def test_speak_rejections_keep_the_status_and_the_detail() -> None:
    client = service_answering(
        lambda request: json_response({"detail": "Unknown voice 'x'."}, 400)
    )

    with pytest.raises(VoiceRejectedError) as raised:
        await client.speak({"text": "Hi."})

    assert raised.value.status_code == 400
    assert raised.value.detail == "Unknown voice 'x'."


async def test_speak_when_unreachable_is_unavailable() -> None:
    with pytest.raises(VoiceUnavailableError):
        await service_answering(unreachable).speak({"text": "Hi."})


async def test_transcribe_sends_the_audio_and_language_hint() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        seen["timeout"] = request.extensions["timeout"]["read"]
        return json_response(TRANSCRIPT_BODY)

    transcript = await service_answering(handler).transcribe(
        b"audio-bytes",
        filename="clip.mp4",
        content_type="audio/mp4",
        language="hi",
    )

    assert transcript == VoiceTranscript(**TRANSCRIPT_BODY)
    assert seen["path"] == "/transcribe"
    assert seen["content_type"].startswith("multipart/form-data")
    assert b'filename="clip.mp4"' in seen["body"]
    assert b"audio-bytes" in seen["body"]
    assert b'name="language"' in seen["body"]
    assert seen["timeout"] == TRANSCRIBE_TIMEOUT_SECONDS


async def test_transcribe_omits_the_language_when_none_is_given() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = request.content
        return json_response(TRANSCRIPT_BODY)

    await service_answering(handler).transcribe(
        b"audio-bytes",
        filename="clip.webm",
        content_type="audio/webm",
        language=None,
    )

    assert b'name="language"' not in seen["body"]


def test_voice_status_route_answers_200_when_the_service_is_down(voice_service) -> None:
    voice_service(unreachable)

    response = TestClient(app).get("/voice/status")

    assert response.status_code == 200
    assert response.json() == {
        "stt": False,
        "tts_languages": [],
        "default_voice": None,
    }


def test_voices_route_lists_the_service_voices(voice_service) -> None:
    body = [{"id": "hf_alpha", "name": "Alpha", "language": "hi", "gender": "female"}]
    voice_service(lambda request: json_response(body))

    response = TestClient(app).get("/voice/voices")

    assert response.status_code == 200
    assert response.json() == body


def test_speak_route_streams_the_wav_back(voice_service) -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return wav_response(request)

    voice_service(handler)

    response = TestClient(app).post(
        "/voice/speak", json={"text": "Hi there.", "speed": 1.1}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == WAV
    assert seen["body"] == {"text": "Hi there.", "speed": 1.1}


def test_speak_route_is_503_when_the_service_is_down(voice_service) -> None:
    voice_service(unreachable)

    response = TestClient(app).post("/voice/speak", json={"text": "Hi there."})

    assert response.status_code == 503
    assert response.json() == {"detail": UNAVAILABLE_MESSAGE}


def test_speak_route_keeps_the_service_rejection_status(voice_service) -> None:
    voice_service(lambda request: json_response({"detail": "Too long."}, 413))

    response = TestClient(app).post("/voice/speak", json={"text": "Hi there."})

    assert response.status_code == 413
    assert response.json() == {"detail": "Too long."}


def test_speak_route_validates_speed_before_calling_the_service(voice_service) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return wav_response(request)

    voice_service(handler)

    response = TestClient(app).post("/voice/speak", json={"text": "Hi.", "speed": 2.0})

    assert response.status_code == 422
    assert calls == []


def test_transcribe_route_forwards_the_upload(voice_service) -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = request.content
        return json_response(TRANSCRIPT_BODY)

    voice_service(handler)

    response = TestClient(app).post(
        "/voice/transcribe",
        files={"audio": ("clip.mp4", b"mp4-bytes", "audio/mp4")},
        data={"language": "hi"},
    )

    assert response.status_code == 200
    assert response.json() == TRANSCRIPT_BODY
    assert b"mp4-bytes" in seen["body"]
    assert b"namaste" not in seen["body"]


def test_transcribe_route_rejects_oversized_audio_before_calling_the_service(
    voice_service,
) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return json_response(TRANSCRIPT_BODY)

    voice_service(handler)

    response = TestClient(app).post(
        "/voice/transcribe",
        files={"audio": ("clip.webm", b"0" * (MAX_AUDIO_BYTES + 1), "audio/webm")},
    )

    assert response.status_code == 413
    assert calls == []

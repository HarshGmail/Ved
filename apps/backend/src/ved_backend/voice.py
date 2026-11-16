from typing import Any

import httpx2

from ved_backend.schemas import VoiceInfo, VoiceStatus, VoiceTranscript

MAX_AUDIO_BYTES = 10 * 1024 * 1024
WAV_MEDIA_TYPE = "audio/wav"
STATUS_TIMEOUT_SECONDS = 5.0
SPEAK_TIMEOUT_SECONDS = 30.0
TRANSCRIBE_TIMEOUT_SECONDS = 45.0
UNREACHABLE_STATUS = VoiceStatus(stt=False, tts_languages=[], default_voice=None)
UNAVAILABLE_MESSAGE = "The voice service is not reachable right now."
REJECTED_MESSAGE = "The voice service could not handle that request."


class VoiceUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__(UNAVAILABLE_MESSAGE)


class VoiceRejectedError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def rejection_detail(response: httpx2.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return REJECTED_MESSAGE
    return detail if isinstance(detail, str) else REJECTED_MESSAGE


class VoiceClient:
    def __init__(
        self, base_url: str, *, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"), transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def status(self) -> VoiceStatus:
        try:
            response = await self._client.get("/status", timeout=STATUS_TIMEOUT_SECONDS)
        except httpx2.HTTPError:
            return UNREACHABLE_STATUS
        if response.status_code != httpx2.codes.OK:
            return UNREACHABLE_STATUS
        return VoiceStatus.model_validate(response.json())

    async def voices(self) -> list[VoiceInfo]:
        response = await self._send(
            self._client.build_request("GET", "/voices", timeout=STATUS_TIMEOUT_SECONDS)
        )
        return [VoiceInfo.model_validate(item) for item in response.json()]

    async def speak(self, body: dict[str, Any]) -> httpx2.Response:
        request = self._client.build_request(
            "POST", "/speak", json=body, timeout=SPEAK_TIMEOUT_SECONDS
        )
        return await self._send(request, stream=True)

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str | None,
    ) -> VoiceTranscript:
        request = self._client.build_request(
            "POST",
            "/transcribe",
            files={"audio": (filename, audio, content_type)},
            data={"language": language} if language else None,
            timeout=TRANSCRIBE_TIMEOUT_SECONDS,
        )
        response = await self._send(request)
        return VoiceTranscript.model_validate(response.json())

    async def _send(
        self, request: httpx2.Request, *, stream: bool = False
    ) -> httpx2.Response:
        try:
            response = await self._client.send(request, stream=stream)
        except httpx2.HTTPError as error:
            raise VoiceUnavailableError() from error
        if response.status_code != httpx2.codes.OK:
            await response.aread()
            detail = rejection_detail(response)
            await response.aclose()
            raise VoiceRejectedError(response.status_code, detail)
        return response

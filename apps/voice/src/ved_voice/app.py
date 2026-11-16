from typing import Annotated

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from ved_voice.limits import MAX_AUDIO_BYTES
from ved_voice.schemas import SpeakRequest, StatusResponse, TranscriptResponse, Voice
from ved_voice.service import RequestRejectedError, VoiceService

WAV_MEDIA_TYPE = "audio/wav"
VERSION = "0.1.0"


def create_app(service: VoiceService) -> FastAPI:
    app = FastAPI(title="Ved voice", version=VERSION)

    @app.exception_handler(RequestRejectedError)
    async def reject(_request: Request, error: RequestRejectedError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}
        )

    @app.get("/status")
    def status() -> StatusResponse:
        return service.status()

    @app.get("/voices")
    def voices() -> list[Voice]:
        return service.voices()

    @app.post("/speak")
    async def speak(request: SpeakRequest) -> Response:
        wav = await service.speak(request)
        return Response(content=wav, media_type=WAV_MEDIA_TYPE)

    @app.post("/transcribe")
    async def transcribe(
        audio: Annotated[UploadFile, File()],
        language: Annotated[str | None, Form()] = None,
    ) -> TranscriptResponse:
        data = await audio.read(MAX_AUDIO_BYTES + 1)
        return await service.transcribe(data, language)

    return app

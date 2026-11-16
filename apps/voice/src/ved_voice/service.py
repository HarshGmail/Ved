import asyncio

from ved_voice.audio import join_with_pauses, sniff_container, wav_bytes
from ved_voice.limits import MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS, MIB
from ved_voice.schemas import (
    SpeakRequest,
    StatusResponse,
    TranscriptResponse,
    Voice,
)
from ved_voice.speech import (
    AudioDecodeError,
    AudioTooLongError,
    SpeechRecognizer,
    SpeechSynthesizer,
    Transcript,
)
from ved_voice.speech_text import clean_for_speech, split_sentences

SENTENCE_PAUSE_SECONDS = 0.25
AUTO_LANGUAGE = "auto"
LANGUAGE_HINTS = ("en", "hi", "te", AUTO_LANGUAGE)
EMPTY_AUDIO = "The audio is empty."
UNSUPPORTED_AUDIO = "Send WAV, WebM, Ogg, MP4 or M4A audio."
NOTHING_TO_SAY = "There is nothing to say once markup is removed."
UNDECODABLE_AUDIO = "Could not decode the audio."


class RequestRejectedError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def language_hint(language: str | None) -> str | None:
    normalised = (language or AUTO_LANGUAGE).strip().lower()
    if normalised == AUTO_LANGUAGE:
        return None
    if normalised not in LANGUAGE_HINTS:
        allowed = ", ".join(LANGUAGE_HINTS)
        raise RequestRejectedError(400, f"Language must be one of {allowed}.")
    return normalised


class VoiceService:
    def __init__(
        self,
        synthesizer: SpeechSynthesizer,
        recognizer: SpeechRecognizer,
        *,
        default_voice: str,
        speech_concurrency: int,
        transcription_concurrency: int,
    ) -> None:
        self._synthesizer = synthesizer
        self._recognizer = recognizer
        self._voices = {voice.id: voice for voice in synthesizer.voices()}
        if default_voice not in self._voices:
            raise ValueError(f"Default voice {default_voice!r} is not installed")
        self._default_voice = default_voice
        self._speech_gate = asyncio.Semaphore(speech_concurrency)
        self._transcription_gate = asyncio.Semaphore(transcription_concurrency)

    def status(self) -> StatusResponse:
        return StatusResponse(
            stt=True,
            tts_languages=sorted({voice.language for voice in self._voices.values()}),
            default_voice=self._default_voice,
        )

    def voices(self) -> list[Voice]:
        return list(self._voices.values())

    async def speak(self, request: SpeakRequest) -> bytes:
        sentences = split_sentences(clean_for_speech(request.text))
        if not sentences:
            raise RequestRejectedError(422, NOTHING_TO_SAY)
        voice = self._voice_id(request.voice)
        async with self._speech_gate:
            return await asyncio.to_thread(
                self._render_wav, sentences, voice, request.speed
            )

    async def transcribe(
        self, audio: bytes, language: str | None
    ) -> TranscriptResponse:
        if not audio:
            raise RequestRejectedError(422, EMPTY_AUDIO)
        if len(audio) > MAX_AUDIO_BYTES:
            raise RequestRejectedError(
                413, f"Audio is larger than {MAX_AUDIO_BYTES // MIB} MB."
            )
        if sniff_container(audio) is None:
            raise RequestRejectedError(415, UNSUPPORTED_AUDIO)
        hint = language_hint(language)
        async with self._transcription_gate:
            transcript = await self._transcribe_in_thread(audio, hint)
        return TranscriptResponse(
            text=transcript.text,
            language=transcript.language,
            duration_seconds=transcript.duration_seconds,
        )

    async def _transcribe_in_thread(self, audio: bytes, hint: str | None) -> Transcript:
        try:
            return await asyncio.to_thread(
                self._recognizer.transcribe, audio, hint, MAX_AUDIO_SECONDS
            )
        except AudioTooLongError as error:
            raise RequestRejectedError(
                413, f"Audio is longer than {MAX_AUDIO_SECONDS:g} seconds."
            ) from error
        except AudioDecodeError as error:
            raise RequestRejectedError(422, UNDECODABLE_AUDIO) from error

    def _render_wav(self, sentences: list[str], voice: str, speed: float) -> bytes:
        clips = [
            self._synthesizer.synthesize(sentence, voice, speed)
            for sentence in sentences
        ]
        samples = join_with_pauses(
            clips, self._synthesizer.sample_rate, SENTENCE_PAUSE_SECONDS
        )
        return wav_bytes(samples, self._synthesizer.sample_rate)

    def _voice_id(self, requested: str | None) -> str:
        if requested is None:
            return self._default_voice
        if requested not in self._voices:
            raise RequestRejectedError(
                400,
                f"Unknown voice {requested!r}. GET /voices lists the available voices.",
            )
        return requested

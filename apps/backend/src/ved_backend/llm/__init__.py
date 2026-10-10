from ved_backend.config import Settings
from ved_backend.llm.base import LLMProvider
from ved_backend.llm.embeddings import OpenAICompatibleEmbedder
from ved_backend.llm.openai_compatible import OpenAICompatibleProvider
from ved_backend.llm.stub import StubProvider

STUB = "stub"
OPENAI_COMPATIBLE = "openai-compatible"

PROVIDER_NAMES = (STUB, OPENAI_COMPATIBLE)


class UnknownProviderError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Unknown VED_LLM_PROVIDER {name!r}, expected one of: "
            + ", ".join(PROVIDER_NAMES)
        )
        self.name = name


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == STUB:
        return StubProvider(timezone=settings.timezone)
    if settings.llm_provider == OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
        )
    raise UnknownProviderError(settings.llm_provider)


def build_embedder(settings: Settings) -> OpenAICompatibleEmbedder | None:
    if settings.llm_provider == STUB:
        return None
    return OpenAICompatibleEmbedder(
        base_url=settings.llm_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.embedding_timeout_seconds,
        document_prefix=settings.embedding_document_prefix,
    )


__all__ = [
    "OPENAI_COMPATIBLE",
    "STUB",
    "LLMProvider",
    "UnknownProviderError",
    "build_embedder",
    "build_provider",
]

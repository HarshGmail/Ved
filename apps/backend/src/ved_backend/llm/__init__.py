from ved_backend.config import Settings
from ved_backend.llm.anthropic_provider import AnthropicProvider
from ved_backend.llm.base import LLMProvider
from ved_backend.llm.embeddings import OpenAICompatibleEmbedder
from ved_backend.llm.openai_compatible import OpenAICompatibleProvider
from ved_backend.llm.stub import StubProvider

STUB = "stub"
OPENAI_COMPATIBLE = "openai-compatible"
ANTHROPIC = "anthropic"

PROVIDER_NAMES = (STUB, OPENAI_COMPATIBLE, ANTHROPIC)


class UnknownProviderError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Unknown VED_LLM_PROVIDER {name!r}, expected one of: "
            + ", ".join(PROVIDER_NAMES)
        )
        self.name = name


class MissingAnthropicKeyError(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "VED_LLM_PROVIDER is anthropic but VED_ANTHROPIC_API_KEY is not set."
        )


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
    if settings.llm_provider == ANTHROPIC:
        if not settings.anthropic_api_key:
            raise MissingAnthropicKeyError()
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
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
    "ANTHROPIC",
    "OPENAI_COMPATIBLE",
    "STUB",
    "LLMProvider",
    "MissingAnthropicKeyError",
    "UnknownProviderError",
    "build_embedder",
    "build_provider",
]

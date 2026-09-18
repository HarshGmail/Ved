from ved_backend.config import Settings
from ved_backend.llm.base import LLMProvider
from ved_backend.llm.stub import StubProvider

STUB = "stub"


class UnknownProviderError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown VED_LLM_PROVIDER {name!r}, expected one of: {STUB}")
        self.name = name


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == STUB:
        return StubProvider(timezone=settings.timezone)
    raise UnknownProviderError(settings.llm_provider)


__all__ = ["LLMProvider", "UnknownProviderError", "build_provider"]

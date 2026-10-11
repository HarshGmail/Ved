from collections.abc import Callable

from ved_web.config import Settings
from ved_web.search.base import (
    SearchHit,
    SearchProvider,
    SearchResult,
    SearchUnavailableError,
    tidy_hits,
)
from ved_web.search.providers import searxng

SEARXNG = "searxng"

ProviderFactory = Callable[[Settings], SearchProvider]

PROVIDERS: dict[str, ProviderFactory] = {
    SEARXNG: searxng.build,
}
PROVIDER_NAMES = tuple(PROVIDERS)


class UnknownSearchProviderError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Unknown VED_SEARCH_PROVIDER {name!r}, expected one of: "
            + ", ".join(PROVIDER_NAMES)
        )
        self.name = name


def build_search_provider(settings: Settings) -> SearchProvider:
    factory = PROVIDERS.get(settings.search_provider.strip().lower())
    if factory is None:
        raise UnknownSearchProviderError(settings.search_provider)
    return factory(settings)


__all__ = [
    "PROVIDER_NAMES",
    "SEARXNG",
    "SearchHit",
    "SearchProvider",
    "SearchResult",
    "SearchUnavailableError",
    "UnknownSearchProviderError",
    "build_search_provider",
    "tidy_hits",
]

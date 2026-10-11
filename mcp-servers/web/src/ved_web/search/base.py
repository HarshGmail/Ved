from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, Field

from ved_web.trust import UntrustedWebContent

SNIPPET_MAX_CHARACTERS = 500
UNKNOWN_ENGINE = "unknown"


class SearchUnavailableError(RuntimeError):
    def __init__(self, *, provider: str, problem: str, remedy: str) -> None:
        super().__init__(f"Web search is unavailable: {provider} {problem}. {remedy}")
        self.provider = provider
        self.problem = problem
        self.remedy = remedy


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str = Field(description="Short excerpt the search engine showed")
    engine: str = Field(description="Which search engine returned it")
    published: str | None = Field(
        default=None, description="Publication time when the engine knows it"
    )


class SearchResult(UntrustedWebContent):
    query: str
    hits: list[SearchHit]


class SearchProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def search(self, query: str, *, limit: int) -> list[SearchHit]: ...

    async def aclose(self) -> None: ...


def clip(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"


def tidy_hits(hits: Iterable[SearchHit], limit: int) -> list[SearchHit]:
    tidied: list[SearchHit] = []
    seen_urls: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        tidied.append(
            SearchHit(
                title=clip(hit.title or url, SNIPPET_MAX_CHARACTERS),
                url=url,
                snippet=clip(hit.snippet, SNIPPET_MAX_CHARACTERS),
                engine=hit.engine or UNKNOWN_ENGINE,
                published=hit.published or None,
            )
        )
        if len(tidied) == limit:
            break
    return tidied

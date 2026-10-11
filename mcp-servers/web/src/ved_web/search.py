from typing import Any

import httpx2
from pydantic import BaseModel, Field

from ved_web.trust import UntrustedWebContent

SEARCH_PATH = "/search"
SNIPPET_MAX_CHARACTERS = 500


class SearchUnavailableError(RuntimeError):
    pass


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


def clip(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"


def parse_hits(payload: dict[str, Any], limit: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    seen_urls: set[str] = set()
    for item in payload.get("results") or []:
        url = (item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        engines = item.get("engines") or []
        hits.append(
            SearchHit(
                title=clip(item.get("title") or url, SNIPPET_MAX_CHARACTERS),
                url=url,
                snippet=clip(item.get("content") or "", SNIPPET_MAX_CHARACTERS),
                engine=item.get("engine") or (engines[0] if engines else "unknown"),
                published=item.get("publishedDate") or None,
            )
        )
        if len(hits) == limit:
            break
    return hits


class SearxngClient:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx2.AsyncClient(
            base_url=self._base_url, timeout=timeout_seconds
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, *, limit: int) -> SearchResult:
        try:
            response = await self._client.get(
                SEARCH_PATH, params={"q": query, "format": "json"}
            )
        except httpx2.HTTPError as error:
            raise SearchUnavailableError(
                f"Web search is unavailable: SearXNG at {self._base_url} did not "
                f"answer ({str(error) or type(error).__name__}). Start it with "
                f"./ved db."
            ) from error

        if response.status_code == httpx2.codes.FORBIDDEN:
            raise SearchUnavailableError(
                "SearXNG refused the JSON request (403). Its settings.yml must "
                "list json under search.formats."
            )
        if response.status_code != httpx2.codes.OK:
            raise SearchUnavailableError(
                f"SearXNG returned {response.status_code}: {response.text[:300]}"
            )

        return SearchResult(query=query, hits=parse_hits(response.json(), limit))

from typing import Any

import httpx2
from pydantic_settings import BaseSettings, SettingsConfigDict

from ved_web.config import Settings
from ved_web.search.base import UNKNOWN_ENGINE, SearchHit, SearchUnavailableError

NAME = "SearXNG"
LOCAL_URL = "http://127.0.0.1:8888"
SEARCH_PATH = "/search"
ERROR_BODY_MAX_CHARACTERS = 300
START_IT = "Start it with ./ved db."


class SearxngSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VED_SEARXNG_", env_file=".env", extra="ignore"
    )

    url: str = LOCAL_URL


def parse_hits(payload: dict[str, Any]) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for item in payload.get("results") or []:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        engines = item.get("engines") or []
        hits.append(
            SearchHit(
                title=item.get("title") or url,
                url=url,
                snippet=item.get("content") or "",
                engine=item.get("engine")
                or (engines[0] if engines else UNKNOWN_ENGINE),
                published=item.get("publishedDate") or None,
            )
        )
    return hits


class SearxngProvider:
    name = NAME

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx2.AsyncClient(
            base_url=self._base_url, timeout=timeout_seconds, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, *, limit: int) -> list[SearchHit]:
        try:
            response = await self._client.get(
                SEARCH_PATH, params={"q": query, "format": "json"}
            )
        except httpx2.HTTPError as error:
            raise SearchUnavailableError(
                provider=NAME,
                problem=(
                    f"at {self._base_url} did not answer "
                    f"({str(error) or type(error).__name__})"
                ),
                remedy=f"{START_IT} Its address is VED_SEARXNG_URL.",
            ) from error

        if response.status_code == httpx2.codes.FORBIDDEN:
            raise SearchUnavailableError(
                provider=NAME,
                problem="refused the JSON request (403)",
                remedy="Its settings.yml must list json under search.formats.",
            )
        if response.status_code != httpx2.codes.OK:
            raise SearchUnavailableError(
                provider=NAME,
                problem=(
                    f"returned {response.status_code}: "
                    f"{response.text[:ERROR_BODY_MAX_CHARACTERS]}"
                ),
                remedy=f"Check its logs with docker logs ved-search-1. {START_IT}",
            )

        return parse_hits(response.json())


def build(settings: Settings) -> SearxngProvider:
    return SearxngProvider(
        base_url=SearxngSettings().url,
        timeout_seconds=settings.search_timeout_seconds,
    )

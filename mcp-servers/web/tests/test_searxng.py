import json
from pathlib import Path

import httpx2
import pytest

from ved_web.search import SearchUnavailableError
from ved_web.search.providers.searxng import NAME, SearxngProvider, parse_hits

RECORDED_NEWS = json.loads(
    (Path(__file__).parent / "fixtures" / "searxng_news.json").read_text()
)


def provider(handler) -> SearxngProvider:
    return SearxngProvider(
        base_url="http://search.invalid",
        timeout_seconds=5,
        transport=httpx2.MockTransport(handler),
    )


def test_recorded_results_become_hits():
    hits = parse_hits(RECORDED_NEWS)

    assert len(hits) == 4
    first = hits[0]
    assert first.title.startswith("India's 'Cockroach' protest movement")
    assert first.url.startswith("https://apnews.com/article/")
    assert first.snippet.startswith("Leaders of the Cockroach Janata Party")
    assert first.engine == "duckduckgo news"
    assert first.published == "2026-10-11T09:14:00"


def test_results_without_a_url_are_skipped():
    assert all(hit.url for hit in parse_hits(RECORDED_NEWS))


def test_the_first_listed_engine_is_used_when_engine_is_missing():
    item = {**RECORDED_NEWS["results"][0], "engine": None, "engines": ["bing news"]}

    assert parse_hits({"results": [item]})[0].engine == "bing news"


def test_an_empty_payload_has_no_hits():
    assert parse_hits({}) == []


async def test_the_query_is_sent_as_json_search():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx2.Response(200, json=RECORDED_NEWS)

    hits = await provider(handler).search("india", limit=3)

    assert seen == {"path": "/search", "params": {"q": "india", "format": "json"}}
    assert len(hits) == 4


async def test_a_403_explains_the_json_format_setting():
    def handler(request):
        return httpx2.Response(403, text="Forbidden")

    with pytest.raises(SearchUnavailableError, match="search.formats"):
        await provider(handler).search("india", limit=3)


async def test_an_unreachable_searxng_names_itself_and_how_to_start_it():
    def handler(request):
        raise httpx2.ConnectError("refused")

    with pytest.raises(SearchUnavailableError) as raised:
        await provider(handler).search("india", limit=3)

    assert raised.value.provider == NAME
    assert "did not answer" in str(raised.value)
    assert "./ved db" in str(raised.value)


async def test_an_error_status_is_reported_with_its_body():
    def handler(request):
        return httpx2.Response(500, text="engine exploded")

    with pytest.raises(SearchUnavailableError, match="returned 500: engine exploded"):
        await provider(handler).search("india", limit=3)

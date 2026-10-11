import json
from pathlib import Path

import httpx2
import pytest

from ved_web.search import SearchUnavailableError, SearxngClient, parse_hits

RECORDED_NEWS = json.loads(
    (Path(__file__).parent / "fixtures" / "searxng_news.json").read_text()
)


def client(handler) -> SearxngClient:
    searxng = SearxngClient(base_url="http://search.invalid", timeout_seconds=5)
    searxng._client = httpx2.AsyncClient(
        base_url="http://search.invalid", transport=httpx2.MockTransport(handler)
    )
    return searxng


def test_recorded_results_become_hits():
    hits = parse_hits(RECORDED_NEWS, limit=10)

    assert len(hits) == 4
    first = hits[0]
    assert first.title.startswith("India's 'Cockroach' protest movement")
    assert first.url.startswith("https://apnews.com/article/")
    assert first.snippet.startswith("Leaders of the Cockroach Janata Party")
    assert first.engine == "duckduckgo news"
    assert first.published == "2026-10-11T09:14:00"


def test_results_without_a_url_are_skipped():
    assert all(hit.url for hit in parse_hits(RECORDED_NEWS, limit=10))


def test_duplicate_urls_are_returned_once():
    payload = {"results": [RECORDED_NEWS["results"][0]] * 3}

    assert len(parse_hits(payload, limit=10)) == 1


def test_the_limit_is_respected():
    assert len(parse_hits(RECORDED_NEWS, limit=2)) == 2


def test_long_snippets_are_clipped():
    item = {**RECORDED_NEWS["results"][0], "content": "word " * 1_000}

    hit = parse_hits({"results": [item]}, limit=1)[0]

    assert len(hit.snippet) <= 501
    assert hit.snippet.endswith("…")


async def test_the_query_is_sent_as_json_search():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx2.Response(200, json=RECORDED_NEWS)

    result = await client(handler).search("india", limit=3)

    assert seen == {"path": "/search", "params": {"q": "india", "format": "json"}}
    assert len(result.hits) == 3
    assert result.untrusted is True


async def test_a_403_explains_the_json_format_setting():
    def handler(request):
        return httpx2.Response(403, text="Forbidden")

    with pytest.raises(SearchUnavailableError, match="search.formats"):
        await client(handler).search("india", limit=3)


async def test_an_unreachable_searxng_is_reported():
    def handler(request):
        raise httpx2.ConnectError("refused")

    with pytest.raises(SearchUnavailableError, match="did not answer"):
        await client(handler).search("india", limit=3)

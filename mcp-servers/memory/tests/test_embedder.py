import json

import httpx2
import pytest

from ved_memory.embedder import EmbeddingError, QueryEmbedder

DIMENSIONS = 3


def build(handler, **kwargs) -> QueryEmbedder:
    embedder = QueryEmbedder(
        base_url="http://model.invalid/v1",
        model="test-embed",
        dimensions=DIMENSIONS,
        **kwargs,
    )
    embedder._client = httpx2.AsyncClient(
        base_url="http://model.invalid/v1",
        transport=httpx2.MockTransport(handler),
    )
    return embedder


def vector_response(vector: list[float]) -> httpx2.Response:
    return httpx2.Response(200, json={"data": [{"index": 0, "embedding": vector}]})


async def test_the_query_is_prefixed_and_sent_to_the_embeddings_endpoint():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return vector_response([0.1, 0.2, 0.3])

    embedder = build(handler, query_prefix="search_query: ")

    vector = await embedder.embed_query("home server")

    assert vector == [0.1, 0.2, 0.3]
    assert seen["path"] == "/v1/embeddings"
    assert seen["body"]["input"] == "search_query: home server"


async def test_a_wrong_dimension_count_is_reported():
    embedder = build(lambda request: vector_response([0.1, 0.2]))

    with pytest.raises(EmbeddingError, match="VED_EMBEDDING_DIMENSIONS"):
        await embedder.embed_query("home server")


async def test_an_error_status_is_reported():
    embedder = build(lambda request: httpx2.Response(404, text="model not found"))

    with pytest.raises(EmbeddingError, match="404"):
        await embedder.embed_query("home server")


async def test_an_unreachable_model_is_reported():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    with pytest.raises(EmbeddingError, match="Could not reach"):
        await build(handler).embed_query("home server")


async def test_an_empty_response_is_reported():
    embedder = build(lambda request: httpx2.Response(200, json={"data": []}))

    with pytest.raises(EmbeddingError, match="no embedding"):
        await embedder.embed_query("home server")

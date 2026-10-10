import json

import httpx2
import pytest

from ved_backend.llm.embeddings import EmbeddingRequestError, OpenAICompatibleEmbedder

DIMENSIONS = 3
DOCUMENT_PREFIX = "search_document: "


def build_embedder(handler, **kwargs) -> OpenAICompatibleEmbedder:
    embedder = OpenAICompatibleEmbedder(
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


def embeddings_response(vectors: list[list[float]]) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "data": [
                {"index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ]
        },
    )


async def test_documents_are_prefixed_and_sent_in_one_request():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return embeddings_response([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

    embedder = build_embedder(handler, document_prefix=DOCUMENT_PREFIX)

    vectors = await embedder.embed_documents(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert seen["path"] == "/v1/embeddings"
    assert seen["body"]["model"] == "test-embed"
    assert seen["body"]["input"] == [
        f"{DOCUMENT_PREFIX}first",
        f"{DOCUMENT_PREFIX}second",
    ]


async def test_vectors_come_back_in_input_order_whatever_the_response_order():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            },
        )

    vectors = await build_embedder(handler).embed_documents(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


async def test_nothing_is_requested_for_no_texts():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request expected")

    assert await build_embedder(handler).embed_documents([]) == []


async def test_a_wrong_dimension_count_is_reported():
    embedder = build_embedder(lambda request: embeddings_response([[1.0, 0.0]]))

    with pytest.raises(EmbeddingRequestError, match="VED_EMBEDDING_DIMENSIONS"):
        await embedder.embed_documents(["first"])


async def test_a_missing_vector_is_reported():
    embedder = build_embedder(lambda request: embeddings_response([[1.0, 0.0, 0.0]]))

    with pytest.raises(EmbeddingRequestError, match="Asked for 2"):
        await embedder.embed_documents(["first", "second"])


async def test_an_error_status_is_reported():
    embedder = build_embedder(
        lambda request: httpx2.Response(404, text="model not found")
    )

    with pytest.raises(EmbeddingRequestError, match="404"):
        await embedder.embed_documents(["first"])


async def test_an_unreachable_model_is_reported():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    with pytest.raises(EmbeddingRequestError, match="Could not reach"):
        await build_embedder(handler).embed_documents(["first"])


async def test_a_timeout_is_reported():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("")

    with pytest.raises(EmbeddingRequestError, match="did not answer in time"):
        await build_embedder(handler).embed_documents(["first"])

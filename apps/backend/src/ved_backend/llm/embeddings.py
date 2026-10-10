from collections.abc import Sequence
from typing import Protocol

import httpx2

EMBEDDINGS_PATH = "/embeddings"
PLACEHOLDER_API_KEY = "not-needed"


class EmbeddingRequestError(RuntimeError):
    pass


class Embedder(Protocol):
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


def _describe(error: Exception) -> str:
    detail = str(error) or type(error).__name__
    if isinstance(error, httpx2.TimeoutException):
        return f"The embedding model did not answer in time ({detail})"
    return f"Could not reach the embedding model: {detail}"


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimensions: int,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        document_prefix: str = "",
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._document_prefix = document_prefix
        self._client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key or PLACEHOLDER_API_KEY}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = await self._client.post(
                EMBEDDINGS_PATH,
                json={
                    "model": self._model,
                    "input": [f"{self._document_prefix}{text}" for text in texts],
                },
            )
        except httpx2.HTTPError as error:
            raise EmbeddingRequestError(_describe(error)) from error

        if response.status_code != httpx2.codes.OK:
            raise EmbeddingRequestError(
                f"Embedding model returned {response.status_code}: "
                f"{response.text[:400]}"
            )

        items = sorted(
            response.json().get("data") or [], key=lambda item: item["index"]
        )
        vectors = [item["embedding"] for item in items]
        if len(vectors) != len(texts):
            raise EmbeddingRequestError(
                f"Asked for {len(texts)} embeddings, received {len(vectors)}"
            )
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise EmbeddingRequestError(
                    f"Expected {self._dimensions} dimensions from {self._model}, "
                    f"received {len(vector)}. Check VED_EMBEDDING_DIMENSIONS."
                )
        return vectors

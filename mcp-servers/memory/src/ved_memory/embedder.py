import httpx2

EMBEDDINGS_PATH = "/embeddings"
PLACEHOLDER_API_KEY = "not-needed"


class EmbeddingError(RuntimeError):
    pass


class QueryEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimensions: int,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        query_prefix: str = "",
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._query_prefix = query_prefix
        self._client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key or PLACEHOLDER_API_KEY}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_query(self, query: str) -> list[float]:
        try:
            response = await self._client.post(
                EMBEDDINGS_PATH,
                json={"model": self._model, "input": f"{self._query_prefix}{query}"},
            )
        except httpx2.HTTPError as error:
            raise EmbeddingError(
                f"Could not reach the embedding model: "
                f"{str(error) or type(error).__name__}"
            ) from error

        if response.status_code != httpx2.codes.OK:
            raise EmbeddingError(
                f"Embedding model returned {response.status_code}: "
                f"{response.text[:400]}"
            )

        items = response.json().get("data") or []
        if not items:
            raise EmbeddingError("Embedding model returned no embedding")
        vector = items[0]["embedding"]
        if len(vector) != self._dimensions:
            raise EmbeddingError(
                f"Expected {self._dimensions} dimensions from {self._model}, "
                f"received {len(vector)}. Check VED_EMBEDDING_DIMENSIONS."
            )
        return vector

from ved_web.search import SearchHit, SearchUnavailableError

FAKE_PROVIDER_NAME = "Fake search"
FAKE_REMEDY = "Turn the fake back on."


class FakeSearchProvider:
    name = FAKE_PROVIDER_NAME

    def __init__(
        self, hits: list[SearchHit] | None = None, *, unavailable: bool = False
    ) -> None:
        self.hits = hits or []
        self.unavailable = unavailable
        self.queries: list[tuple[str, int]] = []
        self.closed = False

    async def search(self, query: str, *, limit: int) -> list[SearchHit]:
        self.queries.append((query, limit))
        if self.unavailable:
            raise SearchUnavailableError(
                provider=self.name, problem="is switched off", remedy=FAKE_REMEDY
            )
        return self.hits

    async def aclose(self) -> None:
        self.closed = True

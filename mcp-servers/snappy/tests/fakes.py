import json
from typing import Any

import httpx2

API_URL = "https://photos.example.test/api"
PUBLIC_URL = "https://photos.example.test"
PHOTO_ID = "6f1c2a4e-8b9d-4c3a-9e21-0a5b7d9c1e11"
OTHER_PHOTO_ID = "2d7e9f10-3a4b-4c5d-8e6f-7a8b9c0d1e22"
PERSON_ID = "11111111-2222-4333-8444-555555555555"
ALBUM_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
API_KEY = "snappy-key-for-tests"


def asset(
    asset_id: str = PHOTO_ID,
    *,
    file_name: str = "IMG_0001.jpg",
    taken: str = "2026-10-02T09:30:00.000+05:30",
    city: str | None = "Panaji",
    country: str | None = "India",
    make: str | None = "Google",
    model: str | None = "Pixel 8",
    people: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": asset_id,
        "originalFileName": file_name,
        "fileCreatedAt": "2026-10-02T04:00:00.000Z",
        "exifInfo": {
            "dateTimeOriginal": taken,
            "city": city,
            "country": country,
            "make": make,
            "model": model,
        },
        "people": [{"id": PERSON_ID, "name": name} for name in people or []],
    }


class FakeSnappy:
    def __init__(self) -> None:
        self.people_named: list[dict[str, Any]] = []
        self.people: list[dict[str, Any]] = []
        self.albums: list[dict[str, Any]] = []
        self.assets: list[dict[str, Any]] = [asset()]
        self.asset_by_id: dict[str, dict[str, Any]] = {}
        self.status_for_everything: int | None = None
        self.unreachable = False
        self.requests: list[httpx2.Request] = []

    def bodies(self, path: str) -> list[dict[str, Any]]:
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path == f"/api/{path}"
        ]

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.unreachable:
            raise httpx2.ConnectError("refused", request=request)
        if self.status_for_everything is not None:
            return httpx2.Response(self.status_for_everything, request=request)
        path = request.url.path
        if request.method == "POST" and path == "/api/search/smart":
            return self._search_answer(request)
        if request.method == "POST" and path == "/api/search/metadata":
            return self._search_answer(request)
        if path == "/api/search/person":
            return httpx2.Response(200, json=self.people_named, request=request)
        if path == "/api/people":
            return httpx2.Response(
                200,
                json={
                    "people": self.people,
                    "total": len(self.people),
                    "hidden": 0,
                    "hasNextPage": False,
                },
                request=request,
            )
        if path == "/api/albums":
            return httpx2.Response(200, json=self.albums, request=request)
        if path.startswith("/api/assets/"):
            found = self.asset_by_id.get(path.rsplit("/", 1)[1])
            return httpx2.Response(
                200 if found else 404, json=found or {}, request=request
            )
        return httpx2.Response(500, request=request)

    def _search_answer(self, request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "assets": {
                    "items": self.assets,
                    "total": len(self.assets),
                    "count": len(self.assets),
                    "facets": [],
                    "nextCursor": None,
                    "nextPage": None,
                },
                "albums": {
                    "items": [],
                    "total": 0,
                    "count": 0,
                    "facets": [],
                    "nextCursor": None,
                    "nextPage": None,
                },
            },
            request=request,
        )

    def client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle))

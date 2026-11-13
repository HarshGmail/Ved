from typing import Any

import httpx2
from mcp.server.mcpserver.exceptions import ToolError

API_KEY_HEADER = "x-api-key"
PEOPLE_PAGE_SIZE = 200


class SnappyClient:
    def __init__(self, http: httpx2.AsyncClient, api_url: str, public_url: str) -> None:
        self._http = http
        self._api_base = api_url.rstrip("/") + "/"
        self._public_url = public_url.rstrip("/")

    def photo_link(self, asset_id: str) -> str:
        return f"{self._public_url}/photos/{asset_id}"

    async def smart_search(
        self, api_key: str, query: str, size: int
    ) -> list[dict[str, Any]]:
        answer = await self._send(
            "POST",
            "search/smart",
            api_key,
            json={"query": query, "size": size, "withExif": True},
        )
        return answer["assets"]["items"]

    async def metadata_search(
        self, api_key: str, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        answer = await self._send(
            "POST", "search/metadata", api_key, json={**filters, "withExif": True}
        )
        return answer["assets"]["items"]

    async def named_people(self, api_key: str, name: str) -> list[dict[str, Any]]:
        return await self._send("GET", "search/person", api_key, params={"name": name})

    async def people(self, api_key: str) -> list[dict[str, Any]]:
        answer = await self._send(
            "GET", "people", api_key, params={"size": PEOPLE_PAGE_SIZE}
        )
        return answer["people"]

    async def albums(self, api_key: str) -> list[dict[str, Any]]:
        return await self._send("GET", "albums", api_key)

    async def asset(self, api_key: str, asset_id: str) -> dict[str, Any]:
        return await self._send("GET", f"assets/{asset_id}", api_key)

    async def _send(self, method: str, path: str, api_key: str, **options: Any) -> Any:
        try:
            response = await self._http.request(
                method,
                self._api_base + path,
                headers={API_KEY_HEADER: api_key},
                **options,
            )
        except httpx2.RequestError as error:
            raise ToolError(
                f"snappy is unreachable right now ({type(error).__name__})"
            ) from error
        raise_for_status(response)
        try:
            return response.json()
        except ValueError as error:
            raise ToolError("snappy sent an answer Ved could not read") from error


def raise_for_status(response: httpx2.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    if status == 401:
        raise ToolError("snappy rejected the API key")
    if status == 403:
        raise ToolError("snappy refused this request; the API key may not have access")
    if status == 404:
        raise ToolError("snappy could not find that")
    raise ToolError(f"snappy answered with HTTP {status}")

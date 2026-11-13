from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx2
import uvicorn
from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from starlette.types import ASGIApp

from ved_snappy import photos
from ved_snappy.auth import BearerTokenMiddleware, bearer_token
from ved_snappy.config import settings
from ved_snappy.photos import (
    DEFAULT_PHOTO_LIMIT,
    DEFAULT_RECENT_DAYS,
    DEFAULT_SEARCH_LIMIT,
    AlbumList,
    PeopleList,
    PhotoDetails,
    PhotoList,
)
from ved_snappy.snappy_client import SnappyClient

HOST = "0.0.0.0"
PORT = 8200
MCP_PATH = "/mcp"
LIMIT_NOTE = "up to 50"


@dataclass
class ServerContext:
    snappy: SnappyClient


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[ServerContext]:
    async with httpx2.AsyncClient(timeout=settings.request_timeout_seconds) as http:
        yield ServerContext(
            snappy=SnappyClient(http, settings.api_url, settings.public_url)
        )


mcp = MCPServer(
    "ved-snappy",
    instructions=(
        "Find the user's photos in snappy by what is in them, by person, by album "
        "or by when they were taken. Every call needs the user's snappy API key, "
        "which Ved sends for them."
    ),
    lifespan=lifespan,
)


def services(ctx: Context) -> ServerContext:
    return ctx.request_context.lifespan_context


def api_key_from(ctx: Context) -> str:
    headers = {name.lower(): value for name, value in (ctx.headers or {}).items()}
    token = bearer_token(headers.get("authorization"))
    if token is None:
        raise ToolError("no snappy API key was sent with this request")
    return token


@mcp.tool(
    name="search_photos",
    description=(
        "Search the user's photos in snappy by what they show, such as "
        "'beach at sunset'. Returns photo records with a link to each photo; "
        f"limit is how many, best first, {LIMIT_NOTE}."
    ),
)
async def search_photos(
    query: str, ctx: Context, limit: int = DEFAULT_SEARCH_LIMIT
) -> PhotoList:
    return await photos.search_photos(
        services(ctx).snappy, api_key_from(ctx), query, limit
    )


@mcp.tool(
    name="list_people",
    description=(
        "List the people snappy has named in the user's photos. Use this to find "
        "the exact name before calling photos_of_person."
    ),
)
async def list_people(ctx: Context) -> PeopleList:
    return await photos.list_people(services(ctx).snappy, api_key_from(ctx))


@mcp.tool(
    name="photos_of_person",
    description=(
        "Find the user's photos of one named person in snappy, newest first. "
        "The name is as list_people shows it."
    ),
)
async def photos_of_person(
    name: str, ctx: Context, limit: int = DEFAULT_PHOTO_LIMIT
) -> PhotoList:
    return await photos.photos_of_person(
        services(ctx).snappy, api_key_from(ctx), name, limit
    )


@mcp.tool(
    name="list_albums",
    description=(
        "List the user's photo albums in snappy with how many photos each holds."
    ),
)
async def list_albums(ctx: Context) -> AlbumList:
    return await photos.list_albums(services(ctx).snappy, api_key_from(ctx))


@mcp.tool(
    name="album_photos",
    description=(
        "List photos from one of the user's albums in snappy, newest first. The "
        "album name is as list_albums shows it."
    ),
)
async def album_photos(
    album_name: str, ctx: Context, limit: int = DEFAULT_PHOTO_LIMIT
) -> PhotoList:
    return await photos.album_photos(
        services(ctx).snappy, api_key_from(ctx), album_name, limit
    )


@mcp.tool(
    name="recent_photos",
    description=(
        "List the user's photos in snappy taken in the last few days, newest first. "
        "days is how far back to look."
    ),
)
async def recent_photos(
    ctx: Context,
    days: int = DEFAULT_RECENT_DAYS,
    limit: int = DEFAULT_PHOTO_LIMIT,
) -> PhotoList:
    return await photos.recent_photos(
        services(ctx).snappy, api_key_from(ctx), days, limit
    )


@mcp.tool(
    name="photo_details",
    description=(
        "Describe one of the user's photos in snappy: when it was taken, where, "
        "the camera and the people in it. photo_id comes from any photo result."
    ),
)
async def photo_details(photo_id: str, ctx: Context) -> PhotoDetails:
    return await photos.photo_details(services(ctx).snappy, api_key_from(ctx), photo_id)


def create_app() -> ASGIApp:
    return BearerTokenMiddleware(
        mcp.streamable_http_app(streamable_http_path=MCP_PATH, host=HOST)
    )


def main() -> None:
    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from ved_snappy.snappy_client import SnappyClient

DEFAULT_SEARCH_LIMIT = 12
DEFAULT_PHOTO_LIMIT = 24
MAX_PHOTO_LIMIT = 50
DEFAULT_RECENT_DAYS = 7
MAX_RECENT_DAYS = 366
MAX_LISTED = 50
AMBIGUOUS_NAMES_SHOWN = 5


class PhotoSummary(BaseModel):
    id: str
    taken_at: str | None
    city: str | None
    country: str | None
    filename: str
    link: str


class PhotoList(BaseModel):
    count: int
    photos: list[PhotoSummary]


class PhotoDetails(PhotoSummary):
    camera: str | None
    people: list[str]


class PersonSummary(BaseModel):
    id: str
    name: str


class PeopleList(BaseModel):
    count: int
    people: list[PersonSummary]


class AlbumSummary(BaseModel):
    name: str
    photo_count: int


class AlbumList(BaseModel):
    count: int
    albums: list[AlbumSummary]


def bounded_limit(value: int) -> int:
    if value < 1:
        raise ToolError(f"limit must be at least 1, got {value}")
    return min(value, MAX_PHOTO_LIMIT)


def required_text(value: str, label: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ToolError(f"{label} must not be empty")
    return cleaned


def photo_id_from(value: str) -> str:
    try:
        return str(uuid.UUID(value.strip()))
    except ValueError as error:
        raise ToolError(f"{value!r} is not a photo id from snappy") from error


def summarize_photo(snappy: SnappyClient, asset: dict[str, Any]) -> PhotoSummary:
    exif = asset.get("exifInfo") or {}
    return PhotoSummary(
        id=asset["id"],
        taken_at=exif.get("dateTimeOriginal") or asset.get("fileCreatedAt"),
        city=exif.get("city"),
        country=exif.get("country"),
        filename=asset.get("originalFileName", ""),
        link=snappy.photo_link(asset["id"]),
    )


def photo_list(snappy: SnappyClient, assets: list[dict[str, Any]]) -> PhotoList:
    photos = [summarize_photo(snappy, asset) for asset in assets]
    return PhotoList(count=len(photos), photos=photos)


def camera_name(exif: dict[str, Any]) -> str | None:
    camera = " ".join(part for part in (exif.get("make"), exif.get("model")) if part)
    return camera or None


def person_names(asset: dict[str, Any]) -> list[str]:
    return [
        person["name"] for person in asset.get("people") or [] if person.get("name")
    ]


def details_of(snappy: SnappyClient, asset: dict[str, Any]) -> PhotoDetails:
    summary = summarize_photo(snappy, asset)
    return PhotoDetails(
        **summary.model_dump(),
        camera=camera_name(asset.get("exifInfo") or {}),
        people=person_names(asset),
    )


def pick_person(candidates: list[dict[str, Any]], name: str) -> dict[str, Any]:
    wanted = name.casefold()
    if not candidates:
        raise ToolError(f"no person named {name!r} in snappy")
    exact = [
        person for person in candidates if person.get("name", "").casefold() == wanted
    ]
    if exact:
        return exact[0]
    if len(candidates) == 1:
        return candidates[0]
    shown = ", ".join(
        person["name"]
        for person in candidates[:AMBIGUOUS_NAMES_SHOWN]
        if person.get("name")
    )
    raise ToolError(
        f"several people match {name!r}: {shown}. Ask again with the full name"
    )


def pick_album(albums: list[dict[str, Any]], name: str) -> dict[str, Any]:
    wanted = name.casefold()
    for album in albums:
        if album.get("albumName", "").casefold() == wanted:
            return album
    raise ToolError(f"no album named {name!r} in snappy")


async def search_photos(
    snappy: SnappyClient, api_key: str, query: str, limit: int
) -> PhotoList:
    text = required_text(query, "query")
    assets = await snappy.smart_search(api_key, text, bounded_limit(limit))
    return photo_list(snappy, assets)


async def photos_of_person(
    snappy: SnappyClient, api_key: str, name: str, limit: int
) -> PhotoList:
    person_name = required_text(name, "name")
    people = await snappy.named_people(api_key, person_name)
    person = pick_person(people, person_name)
    assets = await snappy.metadata_search(
        api_key, {"personIds": [person["id"]], "size": bounded_limit(limit)}
    )
    return photo_list(snappy, assets)


async def list_people(snappy: SnappyClient, api_key: str) -> PeopleList:
    named = [person for person in await snappy.people(api_key) if person.get("name")]
    listed = [
        PersonSummary(id=person["id"], name=person["name"])
        for person in named[:MAX_LISTED]
    ]
    return PeopleList(count=len(named), people=listed)


async def list_albums(snappy: SnappyClient, api_key: str) -> AlbumList:
    albums = await snappy.albums(api_key)
    listed = [
        AlbumSummary(name=album["albumName"], photo_count=album["assetCount"])
        for album in albums[:MAX_LISTED]
    ]
    return AlbumList(count=len(albums), albums=listed)


async def album_photos(
    snappy: SnappyClient, api_key: str, album_name: str, limit: int
) -> PhotoList:
    wanted = required_text(album_name, "album_name")
    album = pick_album(await snappy.albums(api_key), wanted)
    assets = await snappy.metadata_search(
        api_key, {"albumIds": [album["id"]], "size": bounded_limit(limit)}
    )
    return photo_list(snappy, assets)


async def recent_photos(
    snappy: SnappyClient, api_key: str, days: int, limit: int
) -> PhotoList:
    if days < 1:
        raise ToolError(f"days must be at least 1, got {days}")
    since = datetime.now(UTC) - timedelta(days=min(days, MAX_RECENT_DAYS))
    assets = await snappy.metadata_search(
        api_key, {"takenAfter": since.isoformat(), "size": bounded_limit(limit)}
    )
    return photo_list(snappy, assets)


async def photo_details(
    snappy: SnappyClient, api_key: str, photo_id: str
) -> PhotoDetails:
    asset = await snappy.asset(api_key, photo_id_from(photo_id))
    return details_of(snappy, asset)

from datetime import UTC, datetime, timedelta

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from tests.fakes import (
    ALBUM_ID,
    API_KEY,
    API_URL,
    OTHER_PHOTO_ID,
    PERSON_ID,
    PHOTO_ID,
    PUBLIC_URL,
    FakeSnappy,
    asset,
)
from ved_snappy import photos
from ved_snappy.snappy_client import SnappyClient


@pytest.fixture
def snappy_fake() -> FakeSnappy:
    return FakeSnappy()


@pytest.fixture
def snappy(snappy_fake):
    return SnappyClient(snappy_fake.client(), API_URL, PUBLIC_URL)


def named(person_id: str, name: str) -> dict:
    return {"id": person_id, "name": name, "isHidden": False}


async def test_search_photos_shapes_results_with_public_links(snappy, snappy_fake):
    snappy_fake.assets = [asset(), asset(OTHER_PHOTO_ID, city=None, country=None)]

    result = await photos.search_photos(snappy, API_KEY, "  beach   at sunset ", 2)

    assert result.count == 2
    first = result.photos[0]
    assert first.model_dump() == {
        "id": PHOTO_ID,
        "taken_at": "2026-10-02T09:30:00.000+05:30",
        "city": "Panaji",
        "country": "India",
        "filename": "IMG_0001.jpg",
        "link": f"{PUBLIC_URL}/photos/{PHOTO_ID}",
    }
    assert result.photos[1].city is None
    assert snappy_fake.bodies("search/smart") == [
        {"query": "beach at sunset", "size": 2, "withExif": True}
    ]


async def test_every_call_forwards_the_callers_key_as_x_api_key(snappy, snappy_fake):
    snappy_fake.people_named = [named(PERSON_ID, "Asha")]
    snappy_fake.albums = [{"id": ALBUM_ID, "albumName": "Goa", "assetCount": 3}]
    snappy_fake.asset_by_id[PHOTO_ID] = asset()

    await photos.search_photos(snappy, API_KEY, "food", 5)
    await photos.list_people(snappy, API_KEY)
    await photos.list_albums(snappy, API_KEY)
    await photos.photos_of_person(snappy, API_KEY, "Asha", 5)
    await photos.photo_details(snappy, API_KEY, PHOTO_ID)

    assert snappy_fake.requests
    assert all(
        request.headers["x-api-key"] == API_KEY for request in snappy_fake.requests
    )


async def test_photo_limits_are_capped_and_must_be_positive(snappy, snappy_fake):
    await photos.search_photos(snappy, API_KEY, "food", 500)

    assert snappy_fake.bodies("search/smart")[0]["size"] == photos.MAX_PHOTO_LIMIT
    with pytest.raises(ToolError, match="at least 1"):
        await photos.search_photos(snappy, API_KEY, "food", 0)


async def test_blank_queries_are_refused_before_any_request(snappy, snappy_fake):
    with pytest.raises(ToolError, match="must not be empty"):
        await photos.search_photos(snappy, API_KEY, "   ", 5)

    assert snappy_fake.requests == []


async def test_person_name_matches_exactly_regardless_of_case(snappy, snappy_fake):
    snappy_fake.people_named = [named("other-id", "Asha Rao"), named(PERSON_ID, "asha")]

    await photos.photos_of_person(snappy, API_KEY, "ASHA", 4)

    assert snappy_fake.bodies("search/metadata") == [
        {"personIds": [PERSON_ID], "size": 4, "withExif": True}
    ]


async def test_a_single_partial_person_match_is_used(snappy, snappy_fake):
    snappy_fake.people_named = [named(PERSON_ID, "Amma Lakshmi")]

    await photos.photos_of_person(snappy, API_KEY, "Amma", 4)

    assert snappy_fake.bodies("search/metadata")[0]["personIds"] == [PERSON_ID]


async def test_ambiguous_person_names_ask_for_the_full_name(snappy, snappy_fake):
    snappy_fake.people_named = [named("a", "Ravi Kumar"), named("b", "Ravi Shankar")]

    with pytest.raises(ToolError, match="Ravi Kumar, Ravi Shankar"):
        await photos.photos_of_person(snappy, API_KEY, "Ravi", 4)
    assert snappy_fake.bodies("search/metadata") == []


async def test_unknown_person_is_a_readable_error(snappy, snappy_fake):
    with pytest.raises(ToolError, match="no person named 'Nobody'"):
        await photos.photos_of_person(snappy, API_KEY, "Nobody", 4)


async def test_album_photos_resolve_the_album_name(snappy, snappy_fake):
    snappy_fake.albums = [
        {"id": "other", "albumName": "Office", "assetCount": 1},
        {"id": ALBUM_ID, "albumName": "Goa trip", "assetCount": 40},
    ]

    await photos.album_photos(snappy, API_KEY, "goa TRIP", 24)

    assert snappy_fake.bodies("search/metadata") == [
        {"albumIds": [ALBUM_ID], "size": 24, "withExif": True}
    ]


async def test_unknown_album_is_a_readable_error(snappy, snappy_fake):
    with pytest.raises(ToolError, match="no album named 'Mars'"):
        await photos.album_photos(snappy, API_KEY, "Mars", 24)


async def test_list_albums_reports_counts(snappy, snappy_fake):
    snappy_fake.albums = [{"id": ALBUM_ID, "albumName": "Goa trip", "assetCount": 40}]

    result = await photos.list_albums(snappy, API_KEY)

    assert result.model_dump() == {
        "count": 1,
        "albums": [{"name": "Goa trip", "photo_count": 40}],
    }


async def test_list_people_skips_unnamed_faces_and_caps_the_list(snappy, snappy_fake):
    snappy_fake.people = [{"id": "unnamed", "name": ""}] + [
        named(f"id-{number}", f"Person {number}") for number in range(60)
    ]

    result = await photos.list_people(snappy, API_KEY)

    assert result.count == 60
    assert len(result.people) == photos.MAX_LISTED
    assert result.people[0].name == "Person 0"


async def test_recent_photos_ask_for_the_last_days_only(snappy, snappy_fake):
    before = datetime.now(UTC)

    await photos.recent_photos(snappy, API_KEY, 3, 10)

    body = snappy_fake.bodies("search/metadata")[0]
    taken_after = datetime.fromisoformat(body["takenAfter"])
    assert (
        before - timedelta(days=3, seconds=5)
        <= taken_after
        <= before - timedelta(days=3) + timedelta(seconds=5)
    )
    assert body["size"] == 10


async def test_recent_photos_refuse_zero_days(snappy):
    with pytest.raises(ToolError, match="days must be at least 1"):
        await photos.recent_photos(snappy, API_KEY, 0, 10)


async def test_photo_details_name_the_camera_place_and_people(snappy, snappy_fake):
    snappy_fake.asset_by_id[PHOTO_ID] = asset(people=["Asha", ""])

    details = await photos.photo_details(snappy, API_KEY, PHOTO_ID.upper())

    assert details.camera == "Google Pixel 8"
    assert details.people == ["Asha"]
    assert details.city == "Panaji"
    assert details.link == f"{PUBLIC_URL}/photos/{PHOTO_ID}"


async def test_photo_details_refuse_ids_that_are_not_uuids(snappy, snappy_fake):
    with pytest.raises(ToolError, match="is not a photo id"):
        await photos.photo_details(snappy, API_KEY, "../people")

    assert snappy_fake.requests == []


async def test_a_rejected_key_is_reported_in_plain_words(snappy, snappy_fake):
    snappy_fake.status_for_everything = 401

    with pytest.raises(ToolError, match="snappy rejected the API key") as error:
        await photos.search_photos(snappy, API_KEY, "food", 5)

    assert API_KEY not in str(error.value)


async def test_an_unreachable_snappy_is_reported_without_a_traceback(
    snappy, snappy_fake
):
    snappy_fake.unreachable = True

    with pytest.raises(ToolError, match="snappy is unreachable right now"):
        await photos.search_photos(snappy, API_KEY, "food", 5)

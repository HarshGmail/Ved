import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from ved_db import FamilyNote, User

from ved_backend.family import Family
from ved_backend.family_notes import FAMILY_NOTES_LIMIT, FamilyNoteStore
from ved_backend.main import app
from ved_backend.users import UserDirectory, current_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

HARSH = {
    "id": "p1",
    "name": "Harsh",
    "aliases": ["Chinna"],
    "relation": "self",
    "email": "first@example.com",
    "birthday": "2001-08-16",
    "language": "en",
}
AMMA = {
    "id": "p2",
    "name": "Amma",
    "aliases": ["Mummy"],
    "relation": "mother",
    "email": "second@example.com",
    "birthday": "--03-03",
    "language": "te",
}


class FixedFamily:
    def __init__(self, *people: dict) -> None:
        self._family = Family.model_validate({"people": list(people)})

    async def current(self) -> Family:
        return self._family

    async def aclose(self) -> None:
        return None


@pytest.fixture
def api(session_factory, user, other_user):
    app.state.family = FixedFamily(HARSH, AMMA)
    app.state.family_notes = FamilyNoteStore(session_factory)
    app.state.users = UserDirectory(session_factory)

    def as_user(person: User) -> httpx2.AsyncClient:
        app.dependency_overrides[current_user] = lambda: person
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://ved.test"
        )

    yield as_user
    app.dependency_overrides.pop(current_user, None)
    app.state.family_notes = None
    app.state.users = None


async def add_note(session_factory, text, author, minutes_ago=0) -> uuid.UUID:
    async with session_factory() as session:
        note = FamilyNote(
            text=text,
            author_user_id=None if author is None else author.id,
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
        session.add(note)
        await session.commit()
        return note.id


async def note_count(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(FamilyNote))


async def test_the_overview_says_who_the_caller_is_and_lists_the_family(api, user):
    response = await api(user).get("/family")

    body = response.json()
    assert response.status_code == 200
    assert body["owner_name"] == "Harsh"
    assert body["me"]["name"] == "Harsh"
    assert body["me"]["relation"] == "self"
    assert body["me"]["language"] == "en"
    assert [person["name"] for person in body["people"]] == ["Harsh", "Amma"]
    amma = body["people"][1]
    assert (amma["birthday_month"], amma["birthday_day"]) == (3, 3)
    assert amma["aliases"] == ["Mummy"]


async def test_the_overview_has_no_emails_and_no_birth_years(api, user):
    response = await api(user).get("/family")

    assert "@" not in response.text
    assert "example.com" not in response.text
    assert "2001" not in response.text
    assert "email" not in response.text


async def test_the_overview_matches_someone_else_as_themselves(api, other_user):
    body = (await api(other_user).get("/family")).json()

    assert body["me"]["name"] == "Amma"


async def test_a_caller_outside_the_directory_has_no_me(api, session_factory):
    async with session_factory() as session:
        stranger = User(email="stranger@example.com")
        session.add(stranger)
        await session.commit()

    body = (await api(stranger).get("/family")).json()

    assert body["me"] is None
    assert len(body["people"]) == 2


async def test_an_unconfigured_directory_gives_an_empty_overview(api, user):
    app.state.family = FixedFamily()

    body = (await api(user).get("/family")).json()

    assert body == {"people": [], "me": None, "owner_name": None}


async def test_notes_list_newest_first_with_author_and_ownership(
    api, session_factory, user, other_user
):
    async with session_factory() as session:
        stored = await session.get(User, other_user.id)
        stored.name = "Amma"
        await session.commit()
    await add_note(session_factory, "older", other_user, minutes_ago=20)
    await add_note(session_factory, "newer", user, minutes_ago=1)

    response = await api(user).get("/family/notes")

    notes = response.json()["notes"]
    assert [note["text"] for note in notes] == ["newer", "older"]
    assert [note["mine"] for note in notes] == [True, False]
    assert notes[1]["author_name"] == "Amma"
    assert notes[0]["author_name"] is None
    assert "@" not in response.text


async def test_everyoneees_everyone_notes(api, session_factory, user, other_user):
    await add_note(session_factory, "for all", user)

    notes = (await api(other_user).get("/family/notes")).json()["notes"]

    assert [(note["text"], note["mine"]) for note in notes] == [("for all", False)]


async def test_the_list_is_capped(api, session_factory, user):
    async with session_factory() as session:
        session.add_all(
            FamilyNote(text=f"note {index}", author_user_id=user.id)
            for index in range(FAMILY_NOTES_LIMIT + 5)
        )
        await session.commit()

    notes = (await api(user).get("/family/notes")).json()["notes"]

    assert len(notes) == FAMILY_NOTES_LIMIT


async def test_an_author_deletes_their_own_note(api, session_factory, user):
    note_id = await add_note(session_factory, "mine", user)

    response = await api(user).delete(f"/family/notes/{note_id}")

    assert response.status_code == 204
    assert await note_count(session_factory) == 0


async def test_nobody_deletes_someone_else_s_note(
    api, session_factory, user, other_user
):
    note_id = await add_note(session_factory, "hers", other_user)

    response = await api(user).delete(f"/family/notes/{note_id}")

    assert response.status_code == 403
    assert await note_count(session_factory) == 1


async def test_a_note_whose_author_is_gone_cannot_be_deleted(
    api, session_factory, user
):
    note_id = await add_note(session_factory, "orphan", None)

    response = await api(user).delete(f"/family/notes/{note_id}")

    assert response.status_code == 403
    assert await note_count(session_factory) == 1


async def test_deleting_a_missing_note_is_a_404(api, user):
    response = await api(user).delete(f"/family/notes/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_deleting_with_a_malformed_id_is_rejected(api, user):
    response = await api(user).delete("/family/notes/not-a-uuid")

    assert response.status_code == 422


async def test_a_note_outlives_its_author_without_one(session_factory, user):
    note_id = await add_note(session_factory, "stays", user)

    async with session_factory() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()
    async with session_factory() as session:
        note = await session.get(FamilyNote, note_id)

    assert note.author_user_id is None


@pytest.mark.parametrize("text", ["", "x" * 1001])
async def test_the_database_rejects_empty_and_oversized_notes(
    session_factory, user, text
):
    async with session_factory() as session:
        session.add(FamilyNote(text=text, author_user_id=user.id))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_thousand_character_note_is_accepted(session_factory, user):
    await add_note(session_factory, "x" * 1000, user)

    assert await note_count(session_factory) == 1


async def test_adopt_name_fills_an_empty_name_once(session_factory, user):
    directory = UserDirectory(session_factory)

    await directory.adopt_name(user.id, "Harsh")
    await directory.adopt_name(user.id, "Somebody Else")

    async with session_factory() as session:
        stored = await session.get(User, user.id)
    assert stored.name == "Harsh"


async def test_adopt_name_never_overwrites_a_chosen_name(session_factory, user):
    async with session_factory() as session:
        stored = await session.get(User, user.id)
        stored.name = "Chosen"
        await session.commit()

    await UserDirectory(session_factory).adopt_name(user.id, "From Directory")

    async with session_factory() as session:
        assert (await session.get(User, user.id)).name == "Chosen"


async def test_adopt_name_fills_a_blank_name(session_factory, user):
    async with session_factory() as session:
        stored = await session.get(User, user.id)
        stored.name = ""
        await session.commit()

    await UserDirectory(session_factory).adopt_name(user.id, "Harsh")

    async with session_factory() as session:
        assert (await session.get(User, user.id)).name == "Harsh"

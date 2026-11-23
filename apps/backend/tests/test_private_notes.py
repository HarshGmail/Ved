import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from ved_db import PrivateNote, User

from ved_backend.main import app
from ved_backend.private_notes import PRIVATE_NOTES_LIMIT, PrivateNoteStore
from ved_backend.users import current_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


@pytest.fixture
def api(session_factory, user, other_user):
    app.state.private_notes = PrivateNoteStore(session_factory)

    def as_user(person: User) -> httpx2.AsyncClient:
        app.dependency_overrides[current_user] = lambda: person
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://ved.test"
        )

    yield as_user
    app.dependency_overrides.pop(current_user, None)
    app.state.private_notes = None


async def add_note(session_factory, text, owner, minutes_ago=0) -> uuid.UUID:
    async with session_factory() as session:
        note = PrivateNote(
            user_id=owner.id,
            text=text,
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
        session.add(note)
        await session.commit()
        return note.id


async def note_count(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(PrivateNote))


async def test_notes_list_newest_first_for_the_caller_only(
    api, session_factory, user, other_user
):
    await add_note(session_factory, "older", user, minutes_ago=20)
    await add_note(session_factory, "newer", user, minutes_ago=1)
    await add_note(session_factory, "hers", other_user)

    response = await api(user).get("/notes")

    notes = response.json()["notes"]
    assert response.status_code == 200
    assert [note["text"] for note in notes] == ["newer", "older"]
    assert set(notes[0]) == {"id", "text", "created_at"}
    assert "hers" not in response.text


async def test_nobody_has_notes_until_they_save_one(api, user):
    assert (await api(user).get("/notes")).json() == {"notes": []}


async def test_the_list_is_capped(api, session_factory, user):
    async with session_factory() as session:
        session.add_all(
            PrivateNote(user_id=user.id, text=f"note {index}")
            for index in range(PRIVATE_NOTES_LIMIT + 5)
        )
        await session.commit()

    notes = (await api(user).get("/notes")).json()["notes"]

    assert len(notes) == PRIVATE_NOTES_LIMIT


async def test_a_person_deletes_their_own_note(api, session_factory, user):
    note_id = await add_note(session_factory, "mine", user)

    response = await api(user).delete(f"/notes/{note_id}")

    assert response.status_code == 204
    assert await note_count(session_factory) == 0


async def test_nobody_deletes_someone_else_s_note(
    api, session_factory, user, other_user
):
    note_id = await add_note(session_factory, "hers", other_user)

    response = await api(user).delete(f"/notes/{note_id}")

    assert response.status_code == 404
    assert await note_count(session_factory) == 1


async def test_deleting_a_missing_note_is_a_404(api, user):
    response = await api(user).delete(f"/notes/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_deleting_with_a_malformed_id_is_rejected(api, user):
    response = await api(user).delete("/notes/not-a-uuid")

    assert response.status_code == 422


async def test_notes_go_with_their_owner(session_factory, user, other_user):
    await add_note(session_factory, "goes", user)
    await add_note(session_factory, "stays", other_user)

    async with session_factory() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()

    assert await note_count(session_factory) == 1


@pytest.mark.parametrize("text", ["", "x" * 1001])
async def test_the_database_rejects_empty_and_oversized_notes(
    session_factory, user, text
):
    async with session_factory() as session:
        session.add(PrivateNote(user_id=user.id, text=text))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_thousand_character_note_is_accepted(session_factory, user):
    await add_note(session_factory, "x" * 1000, user)

    assert await note_count(session_factory) == 1

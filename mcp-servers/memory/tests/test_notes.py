import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from ved_db import PrivateNote

from ved_memory import server
from ved_memory.server import ServerContext

from .conftest import requires_database

pytestmark = requires_database


@pytest.fixture
def context(session):
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    lifespan = ServerContext(session_factory=factory, embedder=None)
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=lifespan))


async def add_note(session, text, owner, minutes_ago=0):
    session.add(
        PrivateNote(
            user_id=owner.id,
            text=text,
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
    )
    await session.commit()


async def test_remembering_saves_a_note_for_its_owner(session, user, context):
    saved = await server.remember_private_note(str(user.id), "  Wifi is X  ", context)

    row = await session.get(PrivateNote, uuid.UUID(saved.id))
    assert saved.text == "Wifi is X"
    assert row.user_id == user.id
    assert row.text == "Wifi is X"


async def test_remembering_rejects_a_blank_or_oversized_note(session, user, context):
    with pytest.raises(ToolError, match="empty"):
        await server.remember_private_note(str(user.id), " ", context)
    with pytest.raises(ToolError, match="at most"):
        await server.remember_private_note(str(user.id), "x" * 1001, context)

    assert await session.scalar(select(func.count()).select_from(PrivateNote)) == 0


async def test_remembering_needs_a_uuid_user_id(context):
    with pytest.raises(ToolError, match="user_id must be a UUID"):
        await server.remember_private_note("not-a-uuid", "hello", context)


async def test_recalling_needs_a_uuid_user_id(context):
    with pytest.raises(ToolError, match="user_id must be a UUID"):
        await server.recall_private_notes("not-a-uuid", context)


async def test_notes_come_newest_first(session, user, context):
    await add_note(session, "older", user, minutes_ago=30)
    await add_note(session, "newer", user, minutes_ago=5)

    result = await server.recall_private_notes(str(user.id), context)

    assert [note.text for note in result.notes] == ["newer", "older"]


async def test_nobody_recalls_someone_else_s_notes(session, user, other_user, context):
    await add_note(session, "my secret", user)
    await add_note(session, "her secret", other_user)

    mine = await server.recall_private_notes(str(user.id), context)
    hers = await server.recall_private_notes(str(other_user.id), context)
    searched = await server.recall_private_notes(
        str(other_user.id), context, "my secret"
    )

    assert [note.text for note in mine.notes] == ["my secret"]
    assert [note.text for note in hers.notes] == ["her secret"]
    assert searched.notes == []


async def test_a_note_saved_by_one_person_is_not_in_the_family_tools(
    session, user, other_user, context
):
    await server.remember_private_note(str(user.id), "just mine", context)

    family_view = await server.read_family_notes(str(other_user.id), context)

    assert family_view.notes == []


async def test_the_query_filters_ignoring_case(session, user, context):
    await add_note(session, "Wifi password is X", user)
    await add_note(session, "Dentist on Monday", user)

    result = await server.recall_private_notes(str(user.id), context, "WIFI")

    assert [note.text for note in result.notes] == ["Wifi password is X"]


async def test_query_wildcards_are_matched_literally(session, user, context):
    await add_note(session, "100% sure", user)
    await add_note(session, "a_b", user)
    await add_note(session, "nothing here", user)

    percent = await server.recall_private_notes(str(user.id), context, "%")
    underscore = await server.recall_private_notes(str(user.id), context, "_")

    assert [note.text for note in percent.notes] == ["100% sure"]
    assert [note.text for note in underscore.notes] == ["a_b"]


async def test_a_blank_query_returns_everything(session, user, context):
    await add_note(session, "one", user)
    await add_note(session, "two", user)

    result = await server.recall_private_notes(str(user.id), context, "   ")

    assert len(result.notes) == 2


async def test_notes_are_capped_at_the_limit(session, user, context, monkeypatch):
    monkeypatch.setattr(server.settings, "private_notes_limit", 3)
    for index in range(5):
        await add_note(session, f"note {index}", user, minutes_ago=index)

    result = await server.recall_private_notes(str(user.id), context)

    assert [note.text for note in result.notes] == ["note 0", "note 1", "note 2"]


async def test_the_default_limit_is_one_hundred():
    assert server.settings.private_notes_limit == 100


async def test_both_tools_declare_user_id_and_there_is_no_delete_tool():
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    assert "user_id" in tools["notes.remember"].input_schema["properties"]
    assert "user_id" in tools["notes.recall"].input_schema["properties"]
    assert not [
        name for name in tools if name.startswith("notes.") and "delete" in name
    ]

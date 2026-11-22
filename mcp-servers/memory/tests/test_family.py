import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from ved_db import FamilyNote

from ved_memory import family, server
from ved_memory.server import ServerContext

from .conftest import requires_database

pytestmark = requires_database


@pytest.fixture
def context(session):
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    lifespan = ServerContext(session_factory=factory, embedder=None)
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=lifespan))


async def add_note(session, text, author, minutes_ago=0):
    note = FamilyNote(
        text=text,
        author_user_id=None if author is None else author.id,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    session.add(note)
    await session.commit()


async def test_remembering_saves_a_note_for_its_author(session, user, context):
    saved = await server.remember_family_note(str(user.id), "  Wifi changed  ", context)

    row = await session.get(FamilyNote, uuid.UUID(saved.id))
    assert saved.text == "Wifi changed"
    assert row.author_user_id == user.id
    assert row.text == "Wifi changed"


async def test_remembering_rejects_a_blank_or_oversized_note(session, user, context):
    with pytest.raises(ToolError, match="empty"):
        await server.remember_family_note(str(user.id), " ", context)
    with pytest.raises(ToolError, match="at most"):
        await server.remember_family_note(str(user.id), "x" * 1001, context)

    assert await session.scalar(select(func.count()).select_from(FamilyNote)) == 0


async def test_remembering_needs_a_uuid_user_id(context):
    with pytest.raises(ToolError, match="user_id must be a UUID"):
        await server.remember_family_note("not-a-uuid", "hello", context)


async def test_notes_come_newest_first_with_author_names(
    session, user, other_user, context
):
    user.name = "Harsh"
    await session.commit()
    await add_note(session, "older", other_user, minutes_ago=30)
    await add_note(session, "newer", user, minutes_ago=5)

    result = await server.read_family_notes(str(user.id), context)

    assert [note.text for note in result.notes] == ["newer", "older"]
    assert [note.author for note in result.notes] == ["Harsh", family.UNKNOWN_AUTHOR]


async def test_anyone_reads_notes_written_by_anyone(session, user, other_user, context):
    await add_note(session, "for everyone", user)

    result = await server.read_family_notes(str(other_user.id), context)

    assert [note.text for note in result.notes] == ["for everyone"]


async def test_a_note_whose_author_is_gone_still_reads(session, user, context):
    await add_note(session, "orphaned", None)

    result = await server.read_family_notes(str(user.id), context)

    assert result.notes[0].author == family.UNKNOWN_AUTHOR


async def test_the_query_filters_ignoring_case(session, user, context):
    await add_note(session, "Wifi password changed", user)
    await add_note(session, "Trip to Vizag on the 5th", user)

    result = await server.read_family_notes(str(user.id), context, "WIFI")

    assert [note.text for note in result.notes] == ["Wifi password changed"]


async def test_query_wildcards_are_matched_literally(session, user, context):
    await add_note(session, "100% sure", user)
    await add_note(session, "nothing here", user)

    result = await server.read_family_notes(str(user.id), context, "%")

    assert [note.text for note in result.notes] == ["100% sure"]


async def test_a_blank_query_returns_everything(session, user, context):
    await add_note(session, "one", user)
    await add_note(session, "two", user)

    result = await server.read_family_notes(str(user.id), context, "   ")

    assert len(result.notes) == 2


async def test_notes_are_capped_at_the_limit(session, user, context, monkeypatch):
    monkeypatch.setattr(server.settings, "family_notes_limit", 3)
    for index in range(5):
        await add_note(session, f"note {index}", user, minutes_ago=index)

    result = await server.read_family_notes(str(user.id), context)

    assert [note.text for note in result.notes] == ["note 0", "note 1", "note 2"]


async def test_the_default_limit_is_one_hundred():
    assert server.settings.family_notes_limit == 100


async def test_both_tools_declare_user_id_and_there_is_no_delete_tool():
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    assert "user_id" in tools["family.remember"].input_schema["properties"]
    assert "user_id" in tools["family.notes"].input_schema["properties"]
    assert not [
        name for name in tools if name.startswith("family.") and "delete" in name
    ]
    assert not [name for name in tools if name.startswith("delete_")]

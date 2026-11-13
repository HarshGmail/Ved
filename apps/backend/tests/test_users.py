import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from ved_db import User

from ved_backend import access, users
from ved_backend.access import AccessResult
from ved_backend.config import DEFAULT_OWNER_EMAIL, Settings
from ved_backend.main import app
from ved_backend.memory import ConversationStore
from ved_backend.turns import TurnRegistry
from ved_backend.users import UserDirectory, current_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

OWNER_EMAIL = "owner@example.com"


@pytest.fixture
def directory(session_factory):
    return UserDirectory(session_factory)


@pytest.fixture
def client(session_factory, directory):
    app.state.users = directory
    app.state.conversations = ConversationStore(session_factory, history_limit=20)
    app.state.turns = TurnRegistry()
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)
    app.state.users = None
    app.state.conversations = None
    app.state.turns = None


async def user_count(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(User))


def test_the_owner_email_defaults_when_unset_or_blank(monkeypatch):
    monkeypatch.delenv("VED_OWNER_EMAIL", raising=False)
    assert Settings(_env_file=None).owner_email == DEFAULT_OWNER_EMAIL

    monkeypatch.setenv("VED_OWNER_EMAIL", "  ")
    assert Settings(_env_file=None).owner_email == DEFAULT_OWNER_EMAIL

    monkeypatch.setenv("VED_OWNER_EMAIL", " Me@Example.COM ")
    assert Settings(_env_file=None).owner_email == "me@example.com"


async def test_get_or_create_is_idempotent_and_lowercases(directory, session_factory):
    first = await directory.get_or_create("Alice@Example.com")
    second = await directory.get_or_create("alice@example.com")

    assert first.id == second.id
    assert first.email == "alice@example.com"
    assert await user_count(session_factory) == 1


async def test_a_name_is_filled_in_once_known(directory):
    await directory.get_or_create("alice@example.com")

    named = await directory.get_or_create("alice@example.com", "Alice")

    assert named.name == "Alice"
    assert (await directory.get_or_create("alice@example.com")).name == "Alice"


def test_with_auth_off_requests_resolve_to_the_owner(client, monkeypatch):
    monkeypatch.setattr(access, "settings", Settings(_env_file=None, auth="off"))
    monkeypatch.setattr(
        users, "settings", Settings(_env_file=None, owner_email=OWNER_EMAIL)
    )

    first = client.get("/me")
    second = client.get("/me")

    assert first.status_code == 200
    assert first.json() == {"email": OWNER_EMAIL, "name": None}
    assert second.json() == first.json()


def test_with_auth_off_the_owner_owns_the_conversations(
    client, monkeypatch, session_factory
):
    monkeypatch.setattr(access, "settings", Settings(_env_file=None, auth="off"))
    monkeypatch.setattr(
        users, "settings", Settings(_env_file=None, owner_email=OWNER_EMAIL)
    )
    store = ConversationStore(session_factory, history_limit=20)
    owner = asyncio.run(UserDirectory(session_factory).get_or_create(OWNER_EMAIL))
    asyncio.run(store.start(owner.id, "owner thread"))

    listed = client.get("/conversations").json()["conversations"]

    assert [row["title"] for row in listed] == ["owner thread"]


def sign_in_as(monkeypatch, email, name=None):
    monkeypatch.setattr(
        access, "settings", Settings(_env_file=None, auth="cloudflare-access")
    )
    monkeypatch.setattr(
        access,
        "check_access",
        lambda token, settings, resolver: AccessResult(
            email=email, reason=None, name=name
        ),
    )


def test_with_auth_on_the_access_email_picks_the_user(client, monkeypatch):
    sign_in_as(monkeypatch, "alice@example.com", "Alice")

    response = client.get("/me")

    assert response.json() == {"email": "alice@example.com", "name": "Alice"}


def test_two_signed_in_people_never_see_each_others_conversations(
    client, monkeypatch, session_factory
):
    store = ConversationStore(session_factory, history_limit=20)
    directory = UserDirectory(session_factory)
    alice = asyncio.run(directory.get_or_create("alice@example.com"))
    bob = asyncio.run(directory.get_or_create("bob@example.com"))
    alice_thread = asyncio.run(store.start(alice.id, "alice private"))
    asyncio.run(
        store.record_turn(
            alice.id,
            alice_thread,
            prompt="secret",
            answer="ok",
            model="m",
            tool_calls=[],
        )
    )
    bob_thread = asyncio.run(store.start(bob.id, "bob private"))

    sign_in_as(monkeypatch, "bob@example.com")

    listed = client.get("/conversations").json()["conversations"]
    assert [row["id"] for row in listed] == [str(bob_thread)]
    assert client.get(f"/conversations/{alice_thread}").status_code == 404
    assert client.get(f"/conversations/{alice_thread}/status").status_code == 404
    assert client.get(f"/conversations/{bob_thread}").status_code == 200

    sign_in_as(monkeypatch, "alice@example.com")

    transcript = client.get(f"/conversations/{alice_thread}").json()
    assert [message["text"] for message in transcript["messages"]] == ["secret", "ok"]
    assert client.get(f"/conversations/{bob_thread}").status_code == 404


def test_continuing_another_users_conversation_is_a_404(
    client, monkeypatch, session_factory
):
    store = ConversationStore(session_factory, history_limit=20)
    directory = UserDirectory(session_factory)
    alice = asyncio.run(directory.get_or_create("alice@example.com"))
    alice_thread = asyncio.run(store.start(alice.id, "alice private"))
    sign_in_as(monkeypatch, "bob@example.com")

    class OneTool:
        tools = [object()]

    app.state.toolbox = OneTool()
    try:
        message = client.post(
            "/agent/message",
            json={"prompt": "hi", "conversation_id": str(alice_thread)},
        )
        stream = client.post(
            "/agent/message/stream",
            json={"prompt": "hi", "conversation_id": str(alice_thread)},
        )
    finally:
        app.state.toolbox = None

    assert message.status_code == 404
    assert stream.status_code == 404

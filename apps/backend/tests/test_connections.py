import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from ved_db import MCPConnection

from ved_backend.connections import (
    ConnectionNameTakenError,
    ConnectionNotFoundError,
    ConnectionsDisabledError,
    ConnectionStore,
    InvalidConnectionError,
    validate_name,
    validate_token,
    validate_url,
)
from ved_backend.main import app
from ved_backend.token_cipher import TokenCipher
from ved_backend.tools.toolbox import PLAN, RemoteConnection
from ved_backend.users import current_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

SECRET = "plt_super_secret_token"
OWNER_EMAIL = "first@example.com"
OWNER_PLAN_URL = "http://family-planner:3456/api/mcp"


def new_cipher() -> TokenCipher:
    return TokenCipher(Fernet.generate_key().decode())


def store_for(session_factory, *, cipher=None, owner_plan=None) -> ConnectionStore:
    return ConnectionStore(
        session_factory,
        cipher if cipher is not None else new_cipher(),
        owner_email=OWNER_EMAIL,
        owner_plan=owner_plan,
    )


@pytest.mark.parametrize("name", ["plan", "finances", "my-tools", "ab", "tool2"])
def test_valid_names_are_accepted(name):
    assert validate_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "a",
        "x" * 21,
        "Plan",
        "has space",
        "under_score",
        "dot.name",
        "-leading",
        "trailing-",
        "double--dash",
    ],
)
def test_malformed_names_are_rejected(name):
    with pytest.raises(InvalidConnectionError):
        validate_name(name)


@pytest.mark.parametrize("name", ["memory", "documents", "web", "people", "reminders"])
def test_built_in_prefixes_are_reserved(name):
    with pytest.raises(InvalidConnectionError, match="reserved"):
        validate_name(name)


@pytest.mark.parametrize("url", ["https://mcp.example.com/mcp", " http://host:3456/x "])
def test_http_urls_are_accepted_and_trimmed(url):
    assert validate_url(url) == url.strip()


@pytest.mark.parametrize(
    "url", ["ftp://host/x", "javascript:alert(1)", "https://", "plain"]
)
def test_non_http_urls_are_rejected(url):
    with pytest.raises(InvalidConnectionError):
        validate_url(url)


@pytest.mark.parametrize("token", ["", "   "])
def test_blank_tokens_are_rejected(token):
    with pytest.raises(InvalidConnectionError):
        validate_token(token)


async def test_connections_are_listed_only_for_their_owner(
    session_factory, user, other_user
):
    store = store_for(session_factory)
    await store.create(user.id, "plan", "https://a.example/mcp", SECRET)

    assert [row.name for row in await store.list_for(user.id)] == ["plan"]
    assert await store.list_for(other_user.id) == []


async def test_the_same_name_is_allowed_for_different_users(
    session_factory, user, other_user
):
    store = store_for(session_factory)
    await store.create(user.id, "plan", "https://a.example/mcp", SECRET)
    await store.create(other_user.id, "plan", "https://b.example/mcp", SECRET)

    with pytest.raises(ConnectionNameTakenError):
        await store.create(user.id, "plan", "https://c.example/mcp", SECRET)


async def test_another_users_connection_cannot_be_read_changed_or_deleted(
    session_factory, user, other_user
):
    store = store_for(session_factory)
    row = await store.create(user.id, "plan", "https://a.example/mcp", SECRET)

    with pytest.raises(ConnectionNotFoundError):
        await store.remote_connection(other_user.id, row.id)
    with pytest.raises(ConnectionNotFoundError):
        await store.update(other_user.id, row.id, enabled=False, url=None, token=None)
    with pytest.raises(ConnectionNotFoundError):
        await store.delete(other_user.id, row.id)

    still_there = await store.remote_connection(user.id, row.id)
    assert still_there.url == "https://a.example/mcp"


async def test_the_token_is_encrypted_at_rest_and_round_trips(session_factory, user):
    cipher = new_cipher()
    store = store_for(session_factory, cipher=cipher)
    row = await store.create(user.id, "plan", "https://a.example/mcp", SECRET)

    async with session_factory() as session:
        stored = await session.scalar(
            select(MCPConnection.token_encrypted).where(MCPConnection.id == row.id)
        )
    assert SECRET not in stored
    assert cipher.decrypt(stored) == SECRET

    connection = await store.remote_connection(user.id, row.id)
    assert connection == RemoteConnection(
        name="plan", url="https://a.example/mcp", token=SECRET
    )


async def test_only_enabled_connections_are_returned_for_a_turn(session_factory, user):
    store = store_for(session_factory)
    on = await store.create(user.id, "plan", "https://a.example/mcp", SECRET)
    off = await store.create(user.id, "finances", "https://b.example/mcp", SECRET)
    await store.update(user.id, off.id, enabled=False, url=None, token=None)

    names = [connection.name for connection in await store.enabled_for(user.id)]

    assert names == ["plan"]
    assert on.id != off.id


async def test_the_owner_gets_the_global_plan_fallback_without_a_plan_connection(
    session_factory, user, other_user
):
    fallback = RemoteConnection(name=PLAN, url=OWNER_PLAN_URL, token="env-token")
    store = store_for(session_factory, owner_plan=fallback)

    assert await store.enabled_for(user.id) == [fallback]
    assert await store.enabled_for(other_user.id) == []


async def test_the_owners_own_plan_connection_replaces_the_fallback(
    session_factory, user
):
    fallback = RemoteConnection(name=PLAN, url=OWNER_PLAN_URL, token="env-token")
    store = store_for(session_factory, owner_plan=fallback)
    await store.create(user.id, "plan", "https://mine.example/mcp", SECRET)

    connections = await store.enabled_for(user.id)

    assert [connection.url for connection in connections] == [
        "https://mine.example/mcp"
    ]


async def test_without_a_secret_key_connections_cannot_be_created_or_read(
    session_factory, user
):
    store = ConnectionStore(
        session_factory, None, owner_email=OWNER_EMAIL, owner_plan=None
    )

    with pytest.raises(ConnectionsDisabledError):
        await store.create(user.id, "plan", "https://a.example/mcp", SECRET)
    assert await store.enabled_for(user.id) == []


@pytest.fixture
def api(session_factory, user):
    app.dependency_overrides[current_user] = lambda: user
    app.state.connections = store_for(session_factory)
    yield TestClient(app)
    app.dependency_overrides.pop(current_user, None)
    app.state.connections = None


def test_creating_a_connection_never_returns_the_token(api):
    response = api.post(
        "/connections",
        json={"name": "plan", "url": "https://a.example/mcp", "token": SECRET},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "plan"
    assert body["has_token"] is True
    assert body["enabled"] is True
    assert SECRET not in response.text
    assert "token" not in body
    assert SECRET not in api.get("/connections").text


def test_a_duplicate_name_is_a_conflict(api):
    payload = {"name": "plan", "url": "https://a.example/mcp", "token": SECRET}
    api.post("/connections", json=payload)

    assert api.post("/connections", json=payload).status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Plan", "url": "https://a.example/mcp", "token": SECRET},
        {"name": "web", "url": "https://a.example/mcp", "token": SECRET},
        {"name": "plan", "url": "ftp://a.example/mcp", "token": SECRET},
        {"name": "plan", "url": "https://a.example/mcp", "token": ""},
    ],
)
def test_invalid_connections_are_rejected_with_422(api, payload):
    assert api.post("/connections", json=payload).status_code == 422


def test_connections_are_scoped_to_the_signed_in_user(
    session_factory, user, other_user
):
    app.state.connections = store_for(session_factory)
    try:
        app.dependency_overrides[current_user] = lambda: user
        created = (
            TestClient(app)
            .post(
                "/connections",
                json={"name": "plan", "url": "https://a.example/mcp", "token": SECRET},
            )
            .json()
        )

        app.dependency_overrides[current_user] = lambda: other_user
        other = TestClient(app)
        assert other.get("/connections").json()["connections"] == []
        assert (
            other.patch(
                f"/connections/{created['id']}", json={"enabled": False}
            ).status_code
            == 404
        )
        assert other.post(f"/connections/{created['id']}/test").status_code == 404
        assert other.delete(f"/connections/{created['id']}").status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)
        app.state.connections = None


def test_patch_toggles_and_replaces_the_token_without_echoing_it(api):
    created = api.post(
        "/connections",
        json={"name": "plan", "url": "https://a.example/mcp", "token": SECRET},
    ).json()

    response = api.patch(
        f"/connections/{created['id']}",
        json={
            "enabled": False,
            "token": "rotated-token",
            "url": "https://b.example/mcp",
        },
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["url"] == "https://b.example/mcp"
    assert "rotated-token" not in response.text


def test_delete_removes_the_connection(api):
    created = api.post(
        "/connections",
        json={"name": "plan", "url": "https://a.example/mcp", "token": SECRET},
    ).json()

    assert api.delete(f"/connections/{created['id']}").status_code == 204
    assert api.get("/connections").json()["connections"] == []


def test_the_test_endpoint_reports_an_unreachable_server(api):
    created = api.post(
        "/connections",
        json={"name": "plan", "url": "http://127.0.0.1:9/api/mcp", "token": SECRET},
    ).json()

    response = api.post(f"/connections/{created['id']}/test")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["tool_count"] == 0
    assert body["error"]
    assert SECRET not in response.text


def test_presets_offer_plan_and_myfinances(api):
    presets = {
        preset["id"]: preset
        for preset in api.get("/connections/presets").json()["presets"]
    }

    assert presets["plan"]["name"] == "plan"
    assert presets["plan"]["url"] == OWNER_PLAN_URL
    assert presets["plan"]["help"] == "Plan → Settings → API tokens"
    assert presets["finances"]["name"] == "finances"
    assert presets["finances"]["url"] == "https://mcp.my-finances.site/mcp"
    assert (
        presets["finances"]["help"] == "MyFinances → Integrations → MCP → ingest token"
    )


def test_presets_offer_snappy_the_tv_remote_home_admin_and_cards(api):
    presets = {
        preset["id"]: preset
        for preset in api.get("/connections/presets").json()["presets"]
    }

    assert presets["snappy"]["label"] == "Snappy (photos)"
    assert presets["snappy"]["name"] == "photos"
    assert presets["snappy"]["url"] == "http://ved-mcp-snappy:8200/mcp"
    assert (
        presets["snappy"]["help"]
        == "snappy → Account settings → API keys → New API key"
    )
    assert presets["tv"]["label"] == "TV remote"
    assert presets["tv"]["name"] == "tv"
    assert presets["tv"]["url"] == "http://host.docker.internal:8766/mcp"
    assert presets["tv"]["help"] == "On noddy: cd ~/home-ai-tv && deploy/tv mcp-token"
    assert presets["home-admin"]["label"] == "home-admin"
    assert presets["home-admin"]["name"] == "home"
    assert presets["home-admin"]["url"] == "http://home-admin:3470/api/mcp"
    assert (
        presets["home-admin"]["help"]
        == "On noddy: cd ~/home-admin && ./home-admin mcp-token"
    )
    assert presets["cards"]["name"] == "cards"
    assert presets["cards"]["url"] == "https://playing-cards-nine.vercel.app/api/mcp"


@pytest.mark.parametrize("name", ["photos", "tv", "home", "cards"])
def test_preset_names_are_valid_and_not_reserved(name):
    assert validate_name(name) == name


def test_a_missing_secret_key_is_a_503_for_writes(api):
    app.state.connections = ConnectionStore(
        api.app.state.connections._session_factory,
        None,
        owner_email=OWNER_EMAIL,
        owner_plan=None,
    )

    response = api.post(
        "/connections",
        json={"name": "plan", "url": "https://a.example/mcp", "token": SECRET},
    )

    assert response.status_code == 503
    assert "VED_SECRET_KEY" in response.json()["detail"]

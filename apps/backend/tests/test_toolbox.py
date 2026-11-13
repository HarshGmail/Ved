import asyncio
import json
import os
import socket
import sys
import uuid
from pathlib import Path

import pytest
import uvicorn
from mcp import StdioServerParameters
from mcp.server.mcpserver import MCPServer

from ved_backend.config import Settings
from ved_backend.tools.servers import (
    MEMORY,
    PEOPLE,
    PLAN,
    REMINDERS,
    configured_servers,
)
from ved_backend.tools.toolbox import MCPToolbox, RemoteServer, ToolNotAvailableError

FAKE_TOKEN = "plt_test_token"
SCOPED_SERVER = Path(__file__).parent / "scoped_server.py"
USER_ID = uuid.uuid4()


def build_fake_plan(seen_authorization: list[str]) -> MCPServer:
    plan = MCPServer("fake-plan")

    @plan.tool()
    def list_projects() -> str:
        return "projects"

    @plan.tool()
    def create_reminder(title: str) -> str:
        return f"created {title}"

    @plan.tool()
    def echo_user(note: str, user_id: str = "not-injected") -> str:
        return f"{note}|{user_id}"

    @plan.tool()
    def delete_reminder(reminder_id: str) -> str:
        return f"deleted {reminder_id}"

    plan.seen_authorization = seen_authorization
    return plan


class AuthorizedOnly:
    def __init__(self, app, seen_authorization: list[str]) -> None:
        self._app = app
        self._seen = seen_authorization

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            header = dict(scope["headers"]).get(b"authorization", b"").decode()
            self._seen.append(header)
            if header != f"Bearer {FAKE_TOKEN}":
                await send(
                    {"type": "http.response.start", "status": 401, "headers": []}
                )
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await self._app(scope, receive, send)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
async def fake_plan():
    seen: list[str] = []
    port = free_port()
    app = build_fake_plan(seen).streamable_http_app(
        streamable_http_path="/api/mcp", json_response=True, stateless_http=True
    )
    server = uvicorn.Server(
        uvicorn.Config(
            AuthorizedOnly(app, seen), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)

    yield f"http://127.0.0.1:{port}/api/mcp", seen

    server.should_exit = True
    await task


async def test_remote_tools_are_prefixed_and_destructive_ones_hidden(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox({PLAN: RemoteServer(url=url, token=FAKE_TOKEN)})

    await toolbox.connect()
    try:
        names = {tool.name for tool in toolbox.tools}
    finally:
        await toolbox.aclose()

    assert names == {
        "plan.list_projects",
        "plan.create_reminder",
        "plan.echo_user",
    }


async def test_remote_call_is_routed_with_the_auth_header(fake_plan):
    url, seen = fake_plan
    toolbox = MCPToolbox({PLAN: RemoteServer(url=url, token=FAKE_TOKEN)})
    await toolbox.connect()
    try:
        text, failed = await toolbox.call(
            "plan.create_reminder", {"title": "Call Amma"}, user_id=USER_ID
        )
    finally:
        await toolbox.aclose()

    assert "created Call Amma" in text
    assert failed is False
    assert f"Bearer {FAKE_TOKEN}" in seen


async def test_unknown_remote_tool_is_not_available(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox({PLAN: RemoteServer(url=url, token=FAKE_TOKEN)})
    await toolbox.connect()
    try:
        with pytest.raises(ToolNotAvailableError):
            await toolbox.call(
                "plan.delete_reminder", {"reminder_id": "r1"}, user_id=USER_ID
            )
    finally:
        await toolbox.aclose()


async def test_remote_server_rejecting_the_token_is_skipped(fake_plan, caplog):
    url, _ = fake_plan
    toolbox = MCPToolbox({PLAN: RemoteServer(url=url, token="wrong")})

    await toolbox.connect()
    try:
        assert toolbox.tools == []
        assert toolbox.connected_servers == []
    finally:
        await toolbox.aclose()

    assert f"MCP server {PLAN} failed to start" in caplog.text


async def test_unreachable_plan_does_not_break_startup(caplog):
    unreachable = f"http://127.0.0.1:{free_port()}/api/mcp"
    toolbox = MCPToolbox({PLAN: RemoteServer(url=unreachable, token=FAKE_TOKEN)})

    await toolbox.connect()
    try:
        assert toolbox.tools == []
        assert toolbox.connected_servers == []
    finally:
        await toolbox.aclose()

    assert "continuing without its tools" in caplog.text


def test_plan_replaces_reminders_when_its_token_is_set():
    settings = Settings(_env_file=None, plan_mcp_token=FAKE_TOKEN)

    servers = configured_servers(settings)

    assert PLAN in servers
    assert REMINDERS not in servers
    assert {"people", "memory", "web"} <= servers.keys()


def test_reminders_stay_when_no_plan_token_is_set():
    settings = Settings(_env_file=None, plan_mcp_token="")

    servers = configured_servers(settings)

    assert REMINDERS in servers
    assert PLAN not in servers


def scoped_toolbox() -> MCPToolbox:
    return MCPToolbox(
        {
            "scoped": StdioServerParameters(
                command=sys.executable, args=[str(SCOPED_SERVER)]
            )
        }
    )


async def test_stdio_tools_hide_user_id_from_the_model():
    toolbox = scoped_toolbox()
    await toolbox.connect()
    try:
        schemas = {tool.name: tool.input_schema for tool in toolbox.tools}
    finally:
        await toolbox.aclose()

    assert set(schemas["notes.list"]["properties"]) == {"topic"}
    assert schemas["notes.list"]["required"] == ["topic"]
    assert set(schemas["plain.echo"]["properties"]) == {"text"}


async def test_stdio_calls_get_the_users_id_injected():
    toolbox = scoped_toolbox()
    await toolbox.connect()
    try:
        text, failed = await toolbox.call(
            "notes.list", {"topic": "birthdays"}, user_id=USER_ID
        )
    finally:
        await toolbox.aclose()

    assert failed is False
    assert json.loads(text)["result"] == f"{USER_ID}|birthdays"


async def test_a_user_id_chosen_by_the_model_is_overwritten():
    toolbox = scoped_toolbox()
    await toolbox.connect()
    try:
        text, _ = await toolbox.call(
            "notes.list",
            {"topic": "birthdays", "user_id": str(uuid.uuid4())},
            user_id=USER_ID,
        )
    finally:
        await toolbox.aclose()

    assert json.loads(text)["result"] == f"{USER_ID}|birthdays"


async def test_stdio_tools_without_a_user_id_parameter_get_nothing_injected():
    toolbox = scoped_toolbox()
    await toolbox.connect()
    try:
        text, failed = await toolbox.call(
            "plain.echo", {"text": "hello"}, user_id=USER_ID
        )
    finally:
        await toolbox.aclose()

    assert failed is False
    assert json.loads(text)["result"] == "hello"


async def test_remote_servers_keep_their_schemas_and_get_nothing_injected(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox({PLAN: RemoteServer(url=url, token=FAKE_TOKEN)})
    await toolbox.connect()
    try:
        schema = next(
            tool.input_schema for tool in toolbox.tools if tool.name == "plan.echo_user"
        )
        text, _ = await toolbox.call("plan.echo_user", {"note": "hi"}, user_id=USER_ID)
    finally:
        await toolbox.aclose()

    assert "user_id" in schema["properties"]
    assert json.loads(text)["result"] == "hi|not-injected"


requires_database = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


def ved_servers() -> MCPToolbox:
    settings = Settings(
        _env_file=None,
        plan_mcp_token="",
        database_url=os.environ["VED_TEST_DATABASE_URL"],
    )
    servers = configured_servers(settings)
    return MCPToolbox({name: servers[name] for name in (REMINDERS, PEOPLE, MEMORY)})


@requires_database
async def test_ved_servers_never_show_user_id_to_the_model(session_factory):
    toolbox = ved_servers()
    await toolbox.connect()
    try:
        tools = toolbox.tools
    finally:
        await toolbox.aclose()

    assert {tool.name for tool in tools} >= {
        "reminders.create",
        "people.remember",
        "memory.search",
        "documents.search",
        "documents.list",
    }
    for tool in tools:
        assert "user_id" not in tool.input_schema.get("properties", {})
        assert "user_id" not in tool.input_schema.get("required", [])


@requires_database
async def test_real_tool_calls_are_scoped_to_the_injected_user(
    session_factory, user, other_user
):
    toolbox = ved_servers()
    await toolbox.connect()
    try:
        await toolbox.call(
            "people.remember", {"name": "Mom", "relation": "mine"}, user_id=user.id
        )
        await toolbox.call(
            "reminders.create",
            {"text": "mine", "due_at": "2030-01-01T09:00:00+05:30"},
            user_id=user.id,
        )
        theirs_people, _ = await toolbox.call("people.list", {}, user_id=other_user.id)
        mine_people, _ = await toolbox.call("people.list", {}, user_id=user.id)
        theirs_reminders, _ = await toolbox.call(
            "reminders.list", {}, user_id=other_user.id
        )
        mine_reminders, _ = await toolbox.call("reminders.list", {}, user_id=user.id)
    finally:
        await toolbox.aclose()

    assert "Mom" not in theirs_people
    assert "Mom" in mine_people
    assert "mine" not in theirs_reminders
    assert "mine" in mine_reminders

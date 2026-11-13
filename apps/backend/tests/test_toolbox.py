import asyncio
import contextlib
import json
import os
import socket
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import uvicorn
from mcp import StdioServerParameters
from mcp.server.mcpserver import MCPServer

from ved_backend.config import Settings
from ved_backend.connections import list_remote_tools, probe
from ved_backend.tools.servers import (
    configured_servers,
    connection_tool_limit_for,
    exposed_tools_for,
)
from ved_backend.tools.toolbox import (
    CONNECTION_TOOL_LIMIT,
    PLAN,
    REMINDERS,
    MCPToolbox,
    RemoteConnection,
    ToolNotAvailableError,
)

FAKE_TOKEN = "plt_test_token"
SCOPED_SERVER = Path(__file__).parent / "scoped_server.py"
USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


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


def build_fake_crm(count: int) -> MCPServer:
    crm = MCPServer("fake-crm")
    for index in range(count):
        crm.tool(name=f"contacts.lookup_{index:02d}")(lambda: "found")
    crm.tool(name="delete_all")(lambda: "gone")
    return crm


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
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        return probe_socket.getsockname()[1]


@contextlib.asynccontextmanager
async def serving(server: MCPServer, seen: list[str]) -> AsyncIterator[str]:
    port = free_port()
    app = server.streamable_http_app(
        streamable_http_path="/api/mcp", json_response=True, stateless_http=True
    )
    running = uvicorn.Server(
        uvicorn.Config(
            AuthorizedOnly(app, seen), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    task = asyncio.create_task(running.serve())
    while not running.started:
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}/api/mcp"
    finally:
        running.should_exit = True
        await task


@pytest.fixture
async def fake_plan():
    seen: list[str] = []
    async with serving(build_fake_plan(seen), seen) as url:
        yield url, seen


def plan_connection(url: str, token: str = FAKE_TOKEN) -> RemoteConnection:
    return RemoteConnection(name=PLAN, url=url, token=token)


def connections_for(mapping: dict[uuid.UUID, list[RemoteConnection]]):
    async def source(user_id: uuid.UUID) -> list[RemoteConnection]:
        return list(mapping.get(user_id, []))

    return source


def remote_only(*connections: RemoteConnection):
    return connections_for({USER_ID: list(connections)})


async def test_remote_tools_are_prefixed_and_destructive_ones_hidden(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(url)))

    await toolbox.connect()
    try:
        names = {tool.name for tool in await toolbox.tools_for(USER_ID)}
    finally:
        await toolbox.aclose()

    assert names == {
        "plan.list_projects",
        "plan.create_reminder",
        "plan.echo_user",
    }


async def test_remote_call_is_routed_with_the_auth_header(fake_plan):
    url, seen = fake_plan
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(url)))
    await toolbox.connect()
    try:
        await toolbox.tools_for(USER_ID)
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
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(url)))
    await toolbox.connect()
    try:
        await toolbox.tools_for(USER_ID)
        with pytest.raises(ToolNotAvailableError):
            await toolbox.call(
                "plan.delete_reminder", {"reminder_id": "r1"}, user_id=USER_ID
            )
    finally:
        await toolbox.aclose()


async def test_a_call_before_tools_are_listed_is_refused(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(url)))
    await toolbox.connect()
    try:
        with pytest.raises(ToolNotAvailableError):
            await toolbox.call("plan.list_projects", {}, user_id=USER_ID)
    finally:
        await toolbox.aclose()


async def test_remote_server_rejecting_the_token_is_skipped(fake_plan, caplog):
    url, _ = fake_plan
    toolbox = MCPToolbox(
        {}, connections=remote_only(plan_connection(url, token="wrong"))
    )

    await toolbox.connect()
    try:
        assert await toolbox.tools_for(USER_ID) == []
    finally:
        await toolbox.aclose()

    assert f"MCP server {PLAN} failed to start" in caplog.text


async def test_unreachable_connection_does_not_break_listing(caplog):
    unreachable = f"http://127.0.0.1:{free_port()}/api/mcp"
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(unreachable)))

    await toolbox.connect()
    try:
        assert await toolbox.tools_for(USER_ID) == []
    finally:
        await toolbox.aclose()

    assert "continuing without its tools" in caplog.text


async def test_only_exposed_plan_tools_are_listed_in_name_order(fake_plan):
    url, _ = fake_plan
    exposed = ["plan.list_projects", "plan.create_reminder"]
    toolbox = MCPToolbox({}, exposed, connections=remote_only(plan_connection(url)))
    await toolbox.connect()
    try:
        first = [tool.name for tool in await toolbox.tools_for(USER_ID)]
        second = [tool.name for tool in await toolbox.tools_for(USER_ID)]
    finally:
        await toolbox.aclose()

    assert first == ["plan.create_reminder", "plan.list_projects"]
    assert first == second


async def test_a_plan_call_outside_the_allowlist_is_refused(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox(
        {},
        ["plan.create_reminder"],
        connections=remote_only(plan_connection(url)),
    )
    await toolbox.connect()
    try:
        await toolbox.tools_for(USER_ID)
        with pytest.raises(ToolNotAvailableError):
            await toolbox.call("plan.list_projects", {}, user_id=USER_ID)
    finally:
        await toolbox.aclose()


async def test_other_connections_are_exposed_in_full_and_capped_by_name():
    crm = build_fake_crm(CONNECTION_TOOL_LIMIT + 4)
    seen: list[str] = []
    async with serving(crm, seen) as url:
        toolbox = MCPToolbox(
            {},
            ["plan.list_projects"],
            connections=remote_only(RemoteConnection("crm", url, FAKE_TOKEN)),
        )
        await toolbox.connect()
        try:
            names = [tool.name for tool in await toolbox.tools_for(USER_ID)]
        finally:
            await toolbox.aclose()

    assert len(names) == CONNECTION_TOOL_LIMIT
    assert names == sorted(names)
    assert all(name.startswith("crm.contacts.lookup_") for name in names)
    assert "crm.delete_all" not in names


async def test_a_connection_is_visible_only_to_its_owner(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox(
        {}, connections=connections_for({USER_ID: [plan_connection(url)]})
    )
    await toolbox.connect()
    try:
        mine = [tool.name for tool in await toolbox.tools_for(USER_ID)]
        theirs = [tool.name for tool in await toolbox.tools_for(OTHER_USER_ID)]
        with pytest.raises(ToolNotAvailableError):
            await toolbox.call("plan.list_projects", {}, user_id=OTHER_USER_ID)
    finally:
        await toolbox.aclose()

    assert "plan.list_projects" in mine
    assert theirs == []


async def test_removing_a_connection_drops_its_tools(fake_plan):
    url, _ = fake_plan
    mapping = {USER_ID: [plan_connection(url)]}
    toolbox = MCPToolbox({}, connections=connections_for(mapping))
    await toolbox.connect()
    try:
        assert await toolbox.tools_for(USER_ID)
        mapping[USER_ID] = []
        assert await toolbox.tools_for(USER_ID) == []
    finally:
        await toolbox.aclose()


async def test_a_live_session_is_reused_between_turns(fake_plan):
    url, seen = fake_plan
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(url)))
    await toolbox.connect()
    try:
        await toolbox.tools_for(USER_ID)
        requests_after_first_listing = len(seen)
        await toolbox.tools_for(USER_ID)
    finally:
        await toolbox.aclose()

    assert len(seen) == requests_after_first_listing


async def test_a_changed_token_reconnects_with_the_new_one(fake_plan):
    url, seen = fake_plan
    mapping = {USER_ID: [plan_connection(url, token="wrong")]}
    toolbox = MCPToolbox({}, connections=connections_for(mapping))
    await toolbox.connect()
    try:
        assert await toolbox.tools_for(USER_ID) == []
        mapping[USER_ID] = [plan_connection(url)]
        tools = await toolbox.tools_for(USER_ID)
    finally:
        await toolbox.aclose()

    assert any(tool.name == "plan.list_projects" for tool in tools)


async def test_remote_connections_are_never_user_scoped(fake_plan):
    url, _ = fake_plan
    toolbox = MCPToolbox({}, connections=remote_only(plan_connection(url)))
    await toolbox.connect()
    try:
        schema = next(
            tool.input_schema
            for tool in await toolbox.tools_for(USER_ID)
            if tool.name == "plan.echo_user"
        )
        text, _ = await toolbox.call("plan.echo_user", {"note": "hi"}, user_id=USER_ID)
    finally:
        await toolbox.aclose()

    assert "user_id" in schema["properties"]
    assert json.loads(text)["result"] == "hi|not-injected"


async def test_probe_reports_the_exposed_tool_count(fake_plan):
    url, _ = fake_plan
    report = await probe(plan_connection(url))

    assert report.ok is True
    assert report.tool_count == 3
    assert report.error is None


async def test_probe_reports_a_rejected_token(fake_plan):
    url, _ = fake_plan
    report = await probe(plan_connection(url, token="wrong"))

    assert report.ok is False
    assert report.tool_count == 0
    assert report.error


async def test_list_remote_tools_returns_every_tool(fake_plan):
    url, _ = fake_plan
    names = {tool.name for tool in await list_remote_tools(plan_connection(url))}

    assert "plan.list_projects" not in names
    assert {"list_projects", "delete_reminder"} <= names


def test_reminders_are_always_configured_as_a_built_in():
    with_plan = Settings(_env_file=None, plan_mcp_token=FAKE_TOKEN)
    without_plan = Settings(_env_file=None, plan_mcp_token="")

    assert REMINDERS in configured_servers(with_plan)
    assert REMINDERS in configured_servers(without_plan)
    assert PLAN not in configured_servers(with_plan)


async def test_built_in_reminders_are_hidden_while_plan_is_connected(fake_plan, caplog):
    url, _ = fake_plan
    toolbox = MCPToolbox(
        {
            "scoped": StdioServerParameters(
                command=sys.executable, args=[str(SCOPED_SERVER)]
            )
        },
        connections=connections_for(
            {USER_ID: [plan_connection(url)], OTHER_USER_ID: []}
        ),
    )
    await toolbox.connect()
    try:
        with_plan = {tool.name for tool in await toolbox.tools_for(USER_ID)}
        without_plan = {tool.name for tool in await toolbox.tools_for(OTHER_USER_ID)}
        with pytest.raises(ToolNotAvailableError):
            await toolbox.call("reminders.create", {"text": "x"}, user_id=USER_ID)
    finally:
        await toolbox.aclose()

    assert "reminders.create" not in with_plan
    assert "reminders.create" in without_plan


def scoped_toolbox(**kwargs) -> MCPToolbox:
    return MCPToolbox(
        {
            "scoped": StdioServerParameters(
                command=sys.executable, args=[str(SCOPED_SERVER)]
            )
        },
        **kwargs,
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


def test_exposed_tools_default_and_parse_from_a_comma_list():
    defaults = Settings(_env_file=None)
    parsed = Settings(_env_file=None, exposed_tools="memory.search, web.fetch ,")

    assert "memory.search" in defaults.exposed_tools
    assert "reminders.create" in defaults.exposed_tools
    assert len(defaults.exposed_tools) == 14
    assert parsed.exposed_tools == ["memory.search", "web.fetch"]


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
    return MCPToolbox({name: servers[name] for name in (REMINDERS, "people", "memory")})


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


async def test_under_anthropic_every_tool_but_deletes_is_exposed_up_to_forty():
    crm = build_fake_crm(44)
    seen: list[str] = []
    async with serving(crm, seen) as url:
        toolbox = MCPToolbox(
            {},
            [],
            connections=remote_only(RemoteConnection("crm", url, FAKE_TOKEN)),
            connection_tool_limit=40,
        )
        await toolbox.connect()
        try:
            names = [tool.name for tool in await toolbox.tools_for(USER_ID)]
        finally:
            await toolbox.aclose()

    assert len(names) == 40
    assert all(name.startswith("crm.contacts.lookup_") for name in names)
    assert "crm.delete_all" not in names


def test_anthropic_settings_drop_the_allowlist_and_raise_the_limit():
    anthropic = Settings(_env_file=None, llm_provider="anthropic")
    local = Settings(_env_file=None, llm_provider="openai-compatible")

    assert exposed_tools_for(anthropic) == []
    assert connection_tool_limit_for(anthropic) == 40
    assert exposed_tools_for(local) == local.exposed_tools
    assert connection_tool_limit_for(local) == CONNECTION_TOOL_LIMIT == 15

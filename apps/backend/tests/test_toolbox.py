import asyncio
import socket

import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer

from ved_backend.config import Settings
from ved_backend.tools.servers import PLAN, REMINDERS, configured_servers
from ved_backend.tools.toolbox import MCPToolbox, RemoteServer, ToolNotAvailableError

FAKE_TOKEN = "plt_test_token"


def build_fake_plan(seen_authorization: list[str]) -> MCPServer:
    plan = MCPServer("fake-plan")

    @plan.tool()
    def list_projects() -> str:
        return "projects"

    @plan.tool()
    def create_reminder(title: str) -> str:
        return f"created {title}"

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

    assert names == {"plan.list_projects", "plan.create_reminder"}


async def test_remote_call_is_routed_with_the_auth_header(fake_plan):
    url, seen = fake_plan
    toolbox = MCPToolbox({PLAN: RemoteServer(url=url, token=FAKE_TOKEN)})
    await toolbox.connect()
    try:
        text, failed = await toolbox.call(
            "plan.create_reminder", {"title": "Call Amma"}
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
            await toolbox.call("plan.delete_reminder", {"reminder_id": "r1"})
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

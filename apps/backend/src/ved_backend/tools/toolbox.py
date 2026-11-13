import asyncio
import copy
import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Collection
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent, Tool

from ved_backend.llm.base import ToolSpec

logger = logging.getLogger(__name__)

DOMAIN_SEPARATOR = "."
DESTRUCTIVE_TOOL_PREFIX = "delete_"
REMOTE_TIMEOUT_SECONDS = 30.0
REMOTE_CONNECT_TIMEOUT_SECONDS = 5.0
REMOTE_OPEN_TIMEOUT_SECONDS = 15.0
REMOTE_SESSION_TTL_SECONDS = 300.0
CONNECTION_TOOL_LIMIT = 15
USER_ID_ARGUMENT = "user_id"
PLAN = "plan"
REMINDERS = "reminders"
REMINDERS_PREFIX = f"{REMINDERS}{DOMAIN_SEPARATOR}"


class ToolNotAvailableError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"No connected MCP server exposes {name!r}")
        self.name = name


@dataclass(frozen=True)
class RemoteConnection:
    name: str
    url: str
    token: str

    @property
    def authorization(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


ConnectionSource = Callable[[uuid.UUID], Awaitable[list[RemoteConnection]]]


async def no_connections(user_id: uuid.UUID) -> list[RemoteConnection]:
    return []


@dataclass(frozen=True)
class Route:
    server: str
    tool_name: str
    user_scoped: bool = False
    connection: RemoteConnection | None = None


def render_result(result: CallToolResult) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content, separators=(",", ":"))

    parts = [block.text for block in result.content if isinstance(block, TextContent)]
    return "\n".join(parts) if parts else "(no content)"


def is_destructive(tool_name: str) -> bool:
    return tool_name.startswith(DESTRUCTIVE_TOOL_PREFIX)


def declares_user_id(input_schema: dict[str, Any]) -> bool:
    return USER_ID_ARGUMENT in input_schema.get("properties", {})


def without_user_id(input_schema: dict[str, Any]) -> dict[str, Any]:
    visible = copy.deepcopy(input_schema)
    visible.get("properties", {}).pop(USER_ID_ARGUMENT, None)
    required = [
        name for name in visible.get("required", []) if name != USER_ID_ARGUMENT
    ]
    if required:
        visible["required"] = required
    else:
        visible.pop("required", None)
    return visible


async def open_remote(connection: RemoteConnection, stack: AsyncExitStack) -> Client:
    timeout = httpx2.Timeout(
        REMOTE_TIMEOUT_SECONDS, connect=REMOTE_CONNECT_TIMEOUT_SECONDS
    )
    http_client = await stack.enter_async_context(
        httpx2.AsyncClient(headers=connection.authorization, timeout=timeout)
    )
    transport = streamable_http_client(connection.url, http_client=http_client)
    return await stack.enter_async_context(Client(transport))


async def list_remote_tools(connection: RemoteConnection) -> list[Tool]:
    async with AsyncExitStack() as stack:
        client = await open_remote(connection, stack)
        return list((await client.list_tools()).tools)


async def hold_remote_open(
    connection: RemoteConnection,
    opened: asyncio.Future[tuple[Client, list[Tool]]],
    release: asyncio.Event,
) -> None:
    try:
        async with AsyncExitStack() as stack:
            client = await open_remote(connection, stack)
            tools = list((await client.list_tools()).tools)
            if not opened.done():
                opened.set_result((client, tools))
            await release.wait()
    except Exception as error:
        if opened.done():
            logger.warning(
                "MCP connection %s closed with an error",
                connection.name,
                exc_info=True,
            )
        else:
            opened.set_exception(error)


class RemoteSession:
    def __init__(
        self,
        connection: RemoteConnection,
        client: Client,
        tools: list[Tool],
        release: asyncio.Event,
        keeper: asyncio.Task[None],
    ) -> None:
        self.connection = connection
        self.client = client
        self.tools = tools
        self._release = release
        self._keeper = keeper
        self._opened_at = time.monotonic()

    @classmethod
    async def open(cls, connection: RemoteConnection) -> "RemoteSession":
        opened: asyncio.Future[tuple[Client, list[Tool]]] = (
            asyncio.get_running_loop().create_future()
        )
        release = asyncio.Event()
        keeper = asyncio.create_task(hold_remote_open(connection, opened, release))
        try:
            client, tools = await asyncio.wait_for(opened, REMOTE_OPEN_TIMEOUT_SECONDS)
        except BaseException:
            keeper.cancel()
            await asyncio.gather(keeper, return_exceptions=True)
            raise
        return cls(connection, client, tools, release, keeper)

    def serves(self, connection: RemoteConnection) -> bool:
        age = time.monotonic() - self._opened_at
        return self.connection == connection and age < REMOTE_SESSION_TTL_SECONDS

    async def close(self) -> None:
        self._release.set()
        with suppress(BaseException):
            await asyncio.gather(self._keeper, return_exceptions=True)


class MCPToolbox:
    def __init__(
        self,
        servers: dict[str, StdioServerParameters],
        exposed_tools: Collection[str] = (),
        *,
        connections: ConnectionSource = no_connections,
        connection_tool_limit: int = CONNECTION_TOOL_LIMIT,
    ) -> None:
        self._servers = servers
        self._exposed_tools = frozenset(exposed_tools)
        self._connections = connections
        self._connection_tool_limit = connection_tool_limit
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._routes: dict[str, Route] = {}
        self._tools: list[ToolSpec] = []
        self._sessions: dict[tuple[uuid.UUID, str], RemoteSession] = {}
        self._session_locks: defaultdict[tuple[uuid.UUID, str], asyncio.Lock] = (
            defaultdict(asyncio.Lock)
        )
        self._user_routes: dict[uuid.UUID, dict[str, Route]] = {}

    @property
    def tools(self) -> list[ToolSpec]:
        return list(self._tools)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients)

    async def connect(self) -> None:
        for name, spec in self._servers.items():
            try:
                client = await self._stack.enter_async_context(Client(spec))
                listing = await client.list_tools()
            except Exception:
                logger.warning(
                    "MCP server %s failed to start; continuing without its tools",
                    name,
                    exc_info=True,
                )
                continue

            self._clients[name] = client
            exposed = 0
            for tool in listing.tools:
                if is_destructive(tool.name) or not self._is_exposed(tool.name):
                    continue
                user_scoped = declares_user_id(tool.input_schema)
                self._routes[tool.name] = Route(
                    server=name, tool_name=tool.name, user_scoped=user_scoped
                )
                self._tools.append(
                    ToolSpec(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=(
                            without_user_id(tool.input_schema)
                            if user_scoped
                            else tool.input_schema
                        ),
                    )
                )
                exposed += 1
            logger.info("MCP server %s exposed %d tools", name, exposed)
        self._tools.sort(key=lambda tool: tool.name)

    def _is_exposed(self, exposed_name: str) -> bool:
        return not self._exposed_tools or exposed_name in self._exposed_tools

    async def tools_for(self, user_id: uuid.UUID) -> list[ToolSpec]:
        connections = await self._connections(user_id)
        await self._retire_sessions(user_id, {c.name for c in connections})
        routes = self._builtin_routes_for(connections)
        specs = [spec for spec in self._tools if spec.name in routes]
        for connection in connections:
            session = await self._session(user_id, connection)
            if session is None:
                continue
            for tool in self._exposed_remote_tools(connection, session.tools):
                name = f"{connection.name}{DOMAIN_SEPARATOR}{tool.name}"
                routes[name] = Route(
                    server=connection.name,
                    tool_name=tool.name,
                    connection=connection,
                )
                specs.append(
                    ToolSpec(
                        name=name,
                        description=tool.description or "",
                        input_schema=tool.input_schema,
                    )
                )
        self._user_routes[user_id] = routes
        return sorted(specs, key=lambda spec: spec.name)

    def _builtin_routes_for(
        self, connections: list[RemoteConnection]
    ) -> dict[str, Route]:
        plan_connected = any(connection.name == PLAN for connection in connections)
        return {
            name: route
            for name, route in self._routes.items()
            if not (plan_connected and name.startswith(REMINDERS_PREFIX))
        }

    def _exposed_remote_tools(
        self, connection: RemoteConnection, tools: list[Tool]
    ) -> list[Tool]:
        visible = [tool for tool in tools if not is_destructive(tool.name)]
        if connection.name == PLAN:
            return [
                tool
                for tool in visible
                if self._is_exposed(f"{PLAN}{DOMAIN_SEPARATOR}{tool.name}")
            ]
        return sorted(visible, key=lambda tool: tool.name)[
            : self._connection_tool_limit
        ]

    async def _session(
        self, user_id: uuid.UUID, connection: RemoteConnection
    ) -> RemoteSession | None:
        key = (user_id, connection.name)
        async with self._session_locks[key]:
            current = self._sessions.get(key)
            if current is not None and current.serves(connection):
                return current
            if current is not None:
                del self._sessions[key]
                await current.close()
            try:
                session = await RemoteSession.open(connection)
            except Exception:
                logger.warning(
                    "MCP server %s failed to start; continuing without its tools",
                    connection.name,
                    exc_info=True,
                )
                return None
            self._sessions[key] = session
            return session

    async def _retire_sessions(self, user_id: uuid.UUID, keep: set[str]) -> None:
        for key in [
            key for key in self._sessions if key[0] == user_id and key[1] not in keep
        ]:
            await self._sessions.pop(key).close()

    async def _retire(self, user_id: uuid.UUID, name: str) -> None:
        session = self._sessions.pop((user_id, name), None)
        if session is not None:
            await session.close()

    async def aclose(self) -> None:
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()
        self._user_routes.clear()
        await self._stack.aclose()
        self._clients.clear()
        self._routes.clear()
        self._tools.clear()

    async def call(
        self, name: str, arguments: dict[str, Any], *, user_id: uuid.UUID
    ) -> tuple[str, bool]:
        route = self._route(name, user_id)
        if route is None:
            raise ToolNotAvailableError(name)

        if route.connection is not None:
            return await self._call_remote(
                name, user_id, route.connection, route.tool_name, arguments
            )
        if route.user_scoped:
            arguments = {**arguments, USER_ID_ARGUMENT: str(user_id)}
        result = await self._clients[route.server].call_tool(route.tool_name, arguments)
        return render_result(result), bool(result.is_error)

    def _route(self, name: str, user_id: uuid.UUID) -> Route | None:
        resolved = self._user_routes.get(user_id)
        if resolved is None:
            return self._routes.get(name)
        return resolved.get(name)

    async def _call_remote(
        self,
        name: str,
        user_id: uuid.UUID,
        connection: RemoteConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[str, bool]:
        session = await self._session(user_id, connection)
        if session is None:
            raise ToolNotAvailableError(name)
        try:
            result = await session.client.call_tool(tool_name, arguments)
        except Exception:
            await self._retire(user_id, connection.name)
            raise
        return render_result(result), bool(result.is_error)

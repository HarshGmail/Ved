import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from ved_backend.llm.base import ToolSpec

logger = logging.getLogger(__name__)

DOMAIN_SEPARATOR = "."
DESTRUCTIVE_TOOL_PREFIX = "delete_"
REMOTE_TIMEOUT_SECONDS = 30.0


class ToolNotAvailableError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"No connected MCP server exposes {name!r}")
        self.name = name


@dataclass(frozen=True)
class RemoteServer:
    url: str
    token: str

    @property
    def authorization(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


ServerSpec = StdioServerParameters | RemoteServer


@dataclass(frozen=True)
class Route:
    server: str
    tool_name: str


def render_result(result: CallToolResult) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content, separators=(",", ":"))

    parts = [block.text for block in result.content if isinstance(block, TextContent)]
    return "\n".join(parts) if parts else "(no content)"


def is_destructive(tool_name: str) -> bool:
    return tool_name.startswith(DESTRUCTIVE_TOOL_PREFIX)


class MCPToolbox:
    def __init__(self, servers: dict[str, ServerSpec]) -> None:
        self._servers = servers
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._routes: dict[str, Route] = {}
        self._tools: list[ToolSpec] = []

    @property
    def tools(self) -> list[ToolSpec]:
        return list(self._tools)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients)

    async def connect(self) -> None:
        for name, spec in self._servers.items():
            try:
                client = await self._open(spec)
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
                if is_destructive(tool.name):
                    continue
                exposed_name = self._exposed_name(name, spec, tool.name)
                self._routes[exposed_name] = Route(server=name, tool_name=tool.name)
                self._tools.append(
                    ToolSpec(
                        name=exposed_name,
                        description=tool.description or "",
                        input_schema=tool.input_schema,
                    )
                )
                exposed += 1
            logger.info("MCP server %s exposed %d tools", name, exposed)

    async def _open(self, spec: ServerSpec) -> Client:
        if isinstance(spec, RemoteServer):
            http_client = await self._stack.enter_async_context(
                httpx2.AsyncClient(
                    headers=spec.authorization, timeout=REMOTE_TIMEOUT_SECONDS
                )
            )
            transport = streamable_http_client(spec.url, http_client=http_client)
            return await self._stack.enter_async_context(Client(transport))
        return await self._stack.enter_async_context(Client(spec))

    @staticmethod
    def _exposed_name(server: str, spec: ServerSpec, tool_name: str) -> str:
        if isinstance(spec, RemoteServer):
            return f"{server}{DOMAIN_SEPARATOR}{tool_name}"
        return tool_name

    async def aclose(self) -> None:
        await self._stack.aclose()
        self._clients.clear()
        self._routes.clear()
        self._tools.clear()

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        route = self._routes.get(name)
        if route is None:
            raise ToolNotAvailableError(name)

        result = await self._clients[route.server].call_tool(route.tool_name, arguments)
        return render_result(result), bool(result.is_error)

import json
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.types import CallToolResult, TextContent

from ved_backend.llm.base import ToolSpec

logger = logging.getLogger(__name__)


class ToolNotAvailableError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"No connected MCP server exposes {name!r}")
        self.name = name


def render_result(result: CallToolResult) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content, separators=(",", ":"))

    parts = [block.text for block in result.content if isinstance(block, TextContent)]
    return "\n".join(parts) if parts else "(no content)"


class MCPToolbox:
    def __init__(self, servers: dict[str, StdioServerParameters]) -> None:
        self._servers = servers
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._routes: dict[str, str] = {}
        self._tools: list[ToolSpec] = []

    @property
    def tools(self) -> list[ToolSpec]:
        return list(self._tools)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients)

    async def connect(self) -> None:
        for name, parameters in self._servers.items():
            try:
                client = await self._stack.enter_async_context(Client(parameters))
                listing = await client.list_tools()
            except Exception:
                logger.exception("MCP server %s failed to start", name)
                continue

            self._clients[name] = client
            for tool in listing.tools:
                self._routes[tool.name] = name
                self._tools.append(
                    ToolSpec(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.input_schema,
                    )
                )
            logger.info("MCP server %s exposed %d tools", name, len(listing.tools))

    async def aclose(self) -> None:
        await self._stack.aclose()
        self._clients.clear()
        self._routes.clear()
        self._tools.clear()

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        server = self._routes.get(name)
        if server is None:
            raise ToolNotAvailableError(name)

        result = await self._clients[server].call_tool(name, arguments)
        return render_result(result), bool(result.is_error)

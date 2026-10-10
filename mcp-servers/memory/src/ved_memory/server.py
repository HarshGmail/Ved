from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import create_engine, create_session_factory

from ved_memory import storage
from ved_memory.config import settings
from ved_memory.embedder import EmbeddingError, QueryEmbedder
from ved_memory.storage import MemorySearchResult


@dataclass
class ServerContext:
    session_factory: async_sessionmaker[AsyncSession]
    embedder: QueryEmbedder


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[ServerContext]:
    engine = create_engine(settings.database_url)
    embedder = QueryEmbedder(
        base_url=settings.llm_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.embedding_timeout_seconds,
        query_prefix=settings.embedding_query_prefix,
    )
    try:
        yield ServerContext(
            session_factory=create_session_factory(engine), embedder=embedder
        )
    finally:
        await embedder.aclose()
        await engine.dispose()


mcp = MCPServer(
    "ved-memory",
    instructions=(
        "Search what the user and Ved said in past conversations, by meaning "
        "rather than exact words."
    ),
    lifespan=lifespan,
)


def parse_query(value: str) -> str:
    query = value.strip()
    if not query:
        raise ToolError("query must not be empty")
    return query


def parse_limit(value: int) -> int:
    if not 1 <= value <= settings.search_max_limit:
        raise ToolError(
            f"limit must be between 1 and {settings.search_max_limit}, got {value}"
        )
    return value


@mcp.tool(name="memory.search")
async def search(
    query: str, ctx: Context, limit: int = settings.search_default_limit
) -> MemorySearchResult:
    """Search past conversations by meaning and return the closest messages.

    Use this when the user refers to something said or decided earlier, such as
    "what did I decide about the home server last month". Results are ranked by
    similarity and carry the date, so use created_at to judge "last month".

    Args:
        query: What to look for, phrased as a topic or question, e.g. "decision
            about the home server".
        limit: How many messages to return, best first.
    """
    parsed_query = parse_query(query)
    parsed_limit = parse_limit(limit)

    context: ServerContext = ctx.request_context.lifespan_context
    try:
        query_vector = await context.embedder.embed_query(parsed_query)
    except EmbeddingError as error:
        raise ToolError(str(error)) from error

    async with context.session_factory() as session:
        hits = await storage.search_messages(session, query_vector, limit=parsed_limit)
    return MemorySearchResult(hits=hits)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

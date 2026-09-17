import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ved_reminders import storage
from ved_reminders.config import settings
from ved_reminders.storage import ReminderList, ReminderRecord


@dataclass
class ServerContext:
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[ServerContext]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        yield ServerContext(session_factory=async_sessionmaker(engine))
    finally:
        await engine.dispose()


mcp = MCPServer(
    "ved-reminders",
    instructions=(
        "Create and manage the user's reminders. Times must be sent as ISO 8601 "
        "strings that include a UTC offset, e.g. 2026-09-17T20:00:00+05:30."
    ),
    lifespan=lifespan,
)


def parse_due_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ToolError(
            f"due_at must be an ISO 8601 datetime, got {value!r}"
        ) from error

    if parsed.tzinfo is None:
        raise ToolError(
            f"due_at must include a UTC offset so the reminder fires at the "
            f"intended local time, got {value!r}"
        )
    return parsed


@mcp.tool(name="reminders.create")
async def create(text: str, due_at: str, ctx: Context) -> ReminderRecord:
    """Create a reminder.

    Args:
        text: What to remind the user about.
        due_at: When it is due, ISO 8601 with a UTC offset.
    """
    if not text.strip():
        raise ToolError("text must not be empty")

    context: ServerContext = ctx.request_context.lifespan_context
    async with context.session_factory() as session:
        return await storage.create_reminder(
            session, text.strip(), parse_due_at(due_at)
        )


@mcp.tool(name="reminders.list")
async def list_all(
    ctx: Context,
    include_completed: bool = False,
    limit: int = 20,
) -> ReminderList:
    """List reminders, soonest first.

    Args:
        include_completed: Include reminders already completed.
        limit: Maximum number to return.
    """
    capped = max(1, min(limit, settings.max_list_limit))

    context: ServerContext = ctx.request_context.lifespan_context
    async with context.session_factory() as session:
        records = await storage.list_reminders(
            session, include_completed=include_completed, limit=capped
        )
    return ReminderList(reminders=records)


@mcp.tool(name="reminders.complete")
async def complete(reminder_id: str, ctx: Context) -> ReminderRecord:
    """Mark a reminder as completed.

    Args:
        reminder_id: The id returned by reminders.create or reminders.list.
    """
    try:
        parsed_id = uuid.UUID(reminder_id)
    except ValueError as error:
        raise ToolError(f"reminder_id must be a UUID, got {reminder_id!r}") from error

    context: ServerContext = ctx.request_context.lifespan_context
    async with context.session_factory() as session:
        try:
            return await storage.complete_reminder(session, parsed_id)
        except storage.ReminderNotFoundError as error:
            raise ToolError(str(error)) from error


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

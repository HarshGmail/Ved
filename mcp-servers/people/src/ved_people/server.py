import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import create_engine, create_session_factory

from ved_people import storage
from ved_people.config import settings
from ved_people.storage import Birthday, Forgotten, PersonList, PersonRecord

BIRTHDAY_PATTERN = re.compile(r"^(?:(\d{4})-|--)?(\d{1,2})-(\d{1,2})$")
LEAP_YEAR_FOR_VALIDATION = 2000


@dataclass
class ServerContext:
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[ServerContext]:
    engine = create_engine(settings.database_url)
    try:
        yield ServerContext(session_factory=create_session_factory(engine))
    finally:
        await engine.dispose()


mcp = MCPServer(
    "ved-people",
    instructions=(
        "Remember the people in the user's life and their birthdays. Ved reminds "
        "the user of every saved birthday automatically, every year, so never "
        "create a separate reminder for one."
    ),
    lifespan=lifespan,
)


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def parse_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ToolError("name must not be empty")
    return name


def parse_birthday(value: str) -> Birthday:
    match = BIRTHDAY_PATTERN.match(value.strip())
    if match is None:
        raise ToolError(
            f"birthday must be YYYY-MM-DD, or MM-DD when the year is unknown, "
            f"got {value!r}"
        )

    year_text, month_text, day_text = match.groups()
    year = None if year_text is None else int(year_text)
    month, day = int(month_text), int(day_text)
    try:
        date(year or LEAP_YEAR_FOR_VALIDATION, month, day)
    except ValueError as error:
        raise ToolError(f"birthday {value!r} is not a real date") from error

    if year is not None and year > today().year:
        raise ToolError(f"birthday {value!r} is in the future")
    return Birthday(month=month, day=day, year=year)


def parse_notice_days(value: int) -> int:
    if not 0 <= value <= settings.max_notice_days:
        raise ToolError(
            f"birthday_notice_days must be between 0 and "
            f"{settings.max_notice_days}, got {value}"
        )
    return value


@mcp.tool(name="people.remember")
async def remember(
    name: str,
    ctx: Context,
    relation: str | None = None,
    birthday: str | None = None,
    birthday_notice_days: int | None = None,
) -> PersonRecord:
    """Save a person, or update what is known about someone already saved.

    Only the fields you pass are changed. Ved sends a reminder on the birthday
    itself, plus one birthday_notice_days earlier when that is above zero, every
    year, on its own. Do not also call reminders.create for a birthday.

    Args:
        name: How the user refers to them, e.g. "Mom" or "Rahul". Matching an
            existing person ignores case.
        relation: Who they are to the user, e.g. "mother" or "college friend".
        birthday: YYYY-MM-DD, or MM-DD when the user does not give the year.
        birthday_notice_days: Days before the birthday to remind the user, so
            they have time to plan or buy a gift. 0 means only on the day.
    """
    parsed_birthday = None if birthday is None else parse_birthday(birthday)
    parsed_notice = (
        None
        if birthday_notice_days is None
        else parse_notice_days(birthday_notice_days)
    )
    cleaned_relation = None if relation is None else relation.strip() or None

    context: ServerContext = ctx.request_context.lifespan_context
    async with context.session_factory() as session:
        return await storage.save_person(
            session,
            parse_name(name),
            today=today(),
            relation=cleaned_relation,
            birthday=parsed_birthday,
            birthday_notice_days=parsed_notice,
        )


@mcp.tool(name="people.list")
async def list_all(ctx: Context) -> PersonList:
    """List everyone Ved knows about, soonest birthday first."""
    context: ServerContext = ctx.request_context.lifespan_context
    async with context.session_factory() as session:
        records = await storage.list_people(session, today=today())
    return PersonList(people=records)


@mcp.tool(name="people.forget")
async def forget(name: str, ctx: Context) -> Forgotten:
    """Remove a person and stop their birthday reminders.

    Args:
        name: The name they were saved under.
    """
    context: ServerContext = ctx.request_context.lifespan_context
    async with context.session_factory() as session:
        try:
            return await storage.forget_person(session, parse_name(name))
        except storage.PersonNotFoundError as error:
            raise ToolError(str(error)) from error


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

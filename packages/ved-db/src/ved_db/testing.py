from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from ved_db.models import Base

REQUIRED_EXTENSIONS = ("vector",)
REQUIRED_NAME_MARKER = "test"


class UnsafeTestDatabaseError(RuntimeError):
    pass


def guard_test_url(url: str) -> str:
    name = make_url(url).database or ""
    if REQUIRED_NAME_MARKER not in name.lower():
        raise UnsafeTestDatabaseError(
            f"Refusing to run destructive tests against database {name!r}. "
            f"These tests drop every table, so VED_TEST_DATABASE_URL must point "
            f"at a database whose name contains {REQUIRED_NAME_MARKER!r}."
        )
    return url


async def recreate_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        for extension in REQUIRED_EXTENSIONS:
            await connection.exec_driver_sql(
                f"CREATE EXTENSION IF NOT EXISTS {extension}"
            )
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


async def drop_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

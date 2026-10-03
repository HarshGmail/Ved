import os

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ved_db import Base

TEST_DATABASE_URL = os.environ.get("VED_TEST_DATABASE_URL")
REQUIRED_NAME_MARKER = "test"

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


def guard(url: str) -> str:
    name = make_url(url).database or ""
    if REQUIRED_NAME_MARKER not in name.lower():
        raise RuntimeError(
            f"Refusing to run destructive tests against database {name!r}. "
            f"These tests drop every table, so VED_TEST_DATABASE_URL must point "
            f"at a database whose name contains {REQUIRED_NAME_MARKER!r}."
        )
    return url


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(guard(TEST_DATABASE_URL))

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()

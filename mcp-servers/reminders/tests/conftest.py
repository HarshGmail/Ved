import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ved_reminders.models import Base

TEST_DATABASE_URL = os.environ.get("VED_TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine)
    async with factory() as active_session:
        yield active_session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()

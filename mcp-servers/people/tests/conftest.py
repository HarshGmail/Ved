import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ved_db.testing import drop_schema, guard_test_url, recreate_schema

TEST_DATABASE_URL = os.environ.get("VED_TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(guard_test_url(TEST_DATABASE_URL))
    await recreate_schema(engine)

    factory = async_sessionmaker(engine)
    async with factory() as active_session:
        yield active_session

    await drop_schema(engine)
    await engine.dispose()

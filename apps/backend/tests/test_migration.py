import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from ved_db.testing import guard_test_url

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REVISION_BEFORE_USERS = "0c5bb64b7977"
OWNED_TABLES = (
    "people",
    "reminders",
    "push_subscriptions",
    "conversations",
    "documents",
)
DEFAULT_OWNER = "owner@ved.local"

EXISTING_ROWS = [
    "INSERT INTO people (id, name) VALUES (gen_random_uuid(), 'Mom'), "
    "(gen_random_uuid(), 'Dad')",
    "INSERT INTO reminders (id, text, due_at) "
    "VALUES (gen_random_uuid(), 'call Mom', now())",
    "INSERT INTO push_subscriptions (id, endpoint, keys) "
    "VALUES (gen_random_uuid(), 'https://push.example/a', '{}')",
    "INSERT INTO conversations (id, title) VALUES (gen_random_uuid(), 'old thread')",
    "INSERT INTO documents (id, filename, media_type, size_bytes, sha256) "
    "VALUES (gen_random_uuid(), 'lease.pdf', 'application/pdf', 10, 'abc')",
]


@pytest_asyncio.fixture
async def engine():
    database_engine = create_async_engine(
        guard_test_url(os.environ["VED_TEST_DATABASE_URL"])
    )
    await reset_schema(database_engine)
    yield database_engine
    await reset_schema(database_engine)
    await database_engine.dispose()


async def reset_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        await connection.exec_driver_sql("CREATE SCHEMA public")
        await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")


def alembic(*arguments: str, owner_email: str | None = None) -> None:
    environment = {
        **os.environ,
        "VED_DATABASE_URL": os.environ["VED_TEST_DATABASE_URL"],
    }
    environment.pop("VED_OWNER_EMAIL", None)
    if owner_email is not None:
        environment["VED_OWNER_EMAIL"] = owner_email
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
    )


async def seed_existing_rows(engine) -> None:
    async with engine.begin() as connection:
        for statement in EXISTING_ROWS:
            await connection.exec_driver_sql(statement)


async def scalar(engine, statement: str):
    async with engine.connect() as connection:
        return await connection.scalar(text(statement))


@pytest.mark.parametrize(
    ("configured", "expected_email"),
    [("Me@Example.com", "me@example.com"), (None, DEFAULT_OWNER)],
)
async def test_existing_rows_are_backfilled_to_the_owner(
    engine, configured, expected_email
):
    alembic("upgrade", REVISION_BEFORE_USERS)
    await seed_existing_rows(engine)

    alembic("upgrade", "head", owner_email=configured)

    assert await scalar(engine, "SELECT count(*) FROM users") == 1
    assert await scalar(engine, "SELECT email FROM users") == expected_email
    owner_id = await scalar(engine, "SELECT id FROM users")
    for table in OWNED_TABLES:
        total = await scalar(engine, f"SELECT count(*) FROM {table}")
        owned = await scalar(
            engine, f"SELECT count(*) FROM {table} WHERE user_id = '{owner_id}'"
        )
        assert total > 0
        assert owned == total, table


async def test_an_empty_database_still_gets_the_owner(engine):
    alembic("upgrade", "head", owner_email="solo@example.com")

    assert await scalar(engine, "SELECT email FROM users") == "solo@example.com"


async def test_ownership_is_required_after_the_migration(engine):
    alembic("upgrade", "head")

    for table in OWNED_TABLES:
        nullable = await scalar(
            engine,
            "SELECT is_nullable FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND column_name = 'user_id'",
        )
        assert nullable == "NO", table


async def test_two_users_can_hold_the_same_person_name_and_file(engine):
    alembic("upgrade", "head")
    first, second = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as connection:
        for user_id, email in ((first, "a@example.com"), (second, "b@example.com")):
            await connection.exec_driver_sql(
                f"INSERT INTO users (id, email) VALUES ('{user_id}', '{email}')"
            )
            await connection.exec_driver_sql(
                f"INSERT INTO people (id, user_id, name) "
                f"VALUES (gen_random_uuid(), '{user_id}', 'Mom')"
            )
            await connection.exec_driver_sql(
                f"INSERT INTO documents "
                f"(id, user_id, filename, media_type, size_bytes, sha256) "
                f"VALUES (gen_random_uuid(), '{user_id}', 'a.pdf', 'x', 1, 'same')"
            )

    assert await scalar(engine, "SELECT count(*) FROM people WHERE name = 'Mom'") == 2


async def test_the_migration_round_trips(engine):
    alembic("upgrade", "head")
    alembic("downgrade", REVISION_BEFORE_USERS)
    alembic("upgrade", "head")
    alembic("check")

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from ved_db import LlmBalance, LlmUsage

from ved_backend.llm.base import ModelUsage
from ved_backend.usage import UsageStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

HAIKU = "claude-haiku-5-5"
ZONE = "Asia/Kolkata"
NOVEMBER_FIRST_UTC = datetime(2026, 11, 1, tzinfo=UTC)


def store_for(session_factory) -> UsageStore:
    return UsageStore(session_factory, timezone=ZONE)


async def insert_spend(session_factory, moment: datetime, cost: str) -> None:
    async with session_factory() as session:
        session.add(
            LlmUsage(
                created_at=moment,
                model=HAIKU,
                input_tokens=0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal(cost),
            )
        )
        await session.commit()


async def test_record_stores_the_token_counts_and_the_computed_cost(session_factory):
    store = store_for(session_factory)

    await store.record(ModelUsage(model=HAIKU, input_tokens=2_000, output_tokens=500))

    async with session_factory() as session:
        row = await session.scalar(select(LlmUsage))
    assert row.cost_usd == Decimal("0.000450")
    assert (row.input_tokens, row.output_tokens) == (2_000, 500)
    assert row.model == HAIKU


async def test_record_leaves_the_cost_empty_for_an_unpriced_model(session_factory):
    store = store_for(session_factory)

    await store.record(ModelUsage(model="other-model", input_tokens=10))

    async with session_factory() as session:
        row = await session.scalar(select(LlmUsage))
    assert row.cost_usd is None


async def test_remaining_is_the_balance_minus_spend_since_it_was_set(session_factory):
    store = store_for(session_factory)
    set_at = datetime(2026, 11, 14, 6, 0, tzinfo=UTC)
    now = set_at + timedelta(hours=2)
    await insert_spend(session_factory, set_at - timedelta(days=1), "0.40")
    await insert_spend(session_factory, set_at + timedelta(minutes=10), "0.10")
    await insert_spend(session_factory, set_at + timedelta(minutes=30), "0.25")
    await store.set_balance(Decimal("5.00"), set_at)

    summary = await store.summary(now)

    assert summary.balance_usd == Decimal("5.00")
    assert summary.balance_set_at == set_at
    assert summary.spent_since_balance_usd == Decimal("0.35")
    assert summary.remaining_usd == Decimal("4.65")
    assert summary.today.messages == 2
    assert summary.today.usd == Decimal("0.35")
    assert summary.month_usd == Decimal("0.75")
    assert summary.last_30_days_usd == Decimal("0.75")


async def test_spend_without_a_balance_counts_from_the_beginning(session_factory):
    store = store_for(session_factory)
    now = datetime(2026, 11, 14, 6, 0, tzinfo=UTC)
    await insert_spend(session_factory, now - timedelta(hours=3), "0.41")

    summary = await store.summary(now)

    assert summary.balance_usd is None
    assert summary.remaining_usd is None
    assert summary.spent_since_balance_usd == Decimal("0.41")


async def test_today_and_the_month_follow_the_configured_timezone(session_factory):
    store = store_for(session_factory)
    now = datetime(2026, 11, 13, 19, 30, tzinfo=UTC)
    await store.set_balance(Decimal("10.00"), NOVEMBER_FIRST_UTC)
    await insert_spend(
        session_factory, datetime(2026, 11, 13, 18, 0, tzinfo=UTC), "0.10"
    )
    await insert_spend(
        session_factory, datetime(2026, 11, 13, 18, 45, tzinfo=UTC), "0.03"
    )
    await insert_spend(
        session_factory, datetime(2026, 11, 13, 19, 0, tzinfo=UTC), "0.02"
    )
    await insert_spend(
        session_factory, datetime(2026, 10, 31, 18, 0, tzinfo=UTC), "0.50"
    )

    summary = await store.summary(now)

    assert summary.today.usd == Decimal("0.05")
    assert summary.today.messages == 2
    assert summary.month_usd == Decimal("0.15")
    assert summary.last_30_days_usd == Decimal("0.65")


async def test_remaining_never_goes_below_zero(session_factory):
    store = store_for(session_factory)
    set_at = datetime(2026, 11, 14, 6, 0, tzinfo=UTC)
    await store.set_balance(Decimal("1.00"), set_at)
    await insert_spend(session_factory, set_at + timedelta(minutes=5), "1.50")

    summary = await store.summary(set_at + timedelta(hours=1))

    assert summary.remaining_usd == Decimal("0")


async def test_setting_the_balance_again_replaces_the_single_row(session_factory):
    store = store_for(session_factory)
    first = datetime(2026, 11, 10, tzinfo=UTC)
    second = datetime(2026, 11, 14, tzinfo=UTC)

    await store.set_balance(Decimal("5"), first)
    await store.set_balance(Decimal("7.5"), second)

    async with session_factory() as session:
        rows = list((await session.scalars(select(LlmBalance))).all())
    assert [(row.id, row.balance_usd, row.set_at) for row in rows] == [
        (1, Decimal("7.50"), second)
    ]

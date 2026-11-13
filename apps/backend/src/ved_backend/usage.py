from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import LlmBalance, LlmUsage

from ved_backend.llm.base import ModelUsage
from ved_backend.llm.pricing import cost_usd

BALANCE_ROW_ID = 1
BALANCE_CENTS = Decimal("0.01")
MONEY_DISPLAY = Decimal("0.0001")
RECENT_WINDOW = timedelta(days=30)
NO_SPEND = Decimal(0)


@dataclass(frozen=True)
class Spend:
    usd: Decimal
    messages: int


@dataclass(frozen=True)
class UsageSummary:
    balance_usd: Decimal | None
    balance_set_at: datetime | None
    spent_since_balance_usd: Decimal
    today: Spend
    month_usd: Decimal
    last_30_days_usd: Decimal

    @property
    def remaining_usd(self) -> Decimal | None:
        if self.balance_usd is None:
            return None
        return max(self.balance_usd - self.spent_since_balance_usd, NO_SPEND)


def money(value: Decimal) -> float:
    return float(value.quantize(MONEY_DISPLAY, rounding=ROUND_HALF_UP))


def money_or_none(value: Decimal | None) -> float | None:
    return None if value is None else money(value)


def local_day_start(moment: datetime, zone: ZoneInfo) -> datetime:
    return datetime.combine(moment.astimezone(zone).date(), time.min, zone)


def spend_query(since: datetime | None):
    query = select(
        func.coalesce(func.sum(LlmUsage.cost_usd), NO_SPEND),
        func.count(LlmUsage.id),
    )
    if since is not None:
        query = query.where(LlmUsage.created_at >= since)
    return query


async def spend_since(session: AsyncSession, since: datetime | None) -> Spend:
    total, messages = (await session.execute(spend_query(since))).one()
    return Spend(usd=Decimal(total), messages=messages)


class UsageStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        timezone: str,
    ) -> None:
        self._session_factory = session_factory
        self._zone = ZoneInfo(timezone)

    async def record(self, usage: ModelUsage) -> None:
        row = LlmUsage(
            model=usage.model,
            input_tokens=usage.input_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost_usd(usage.model, usage),
        )
        async with self._session_factory() as session:
            session.add(row)
            await session.commit()

    async def set_balance(self, balance_usd: Decimal, set_at: datetime) -> None:
        amount = balance_usd.quantize(BALANCE_CENTS, rounding=ROUND_HALF_UP)
        statement = insert(LlmBalance).values(
            id=BALANCE_ROW_ID, balance_usd=amount, set_at=set_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[LlmBalance.id],
            set_={"balance_usd": amount, "set_at": set_at},
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def summary(self, now: datetime) -> UsageSummary:
        local_today = local_day_start(now, self._zone)
        month_start = local_today.replace(day=1)
        async with self._session_factory() as session:
            balance = await session.get(LlmBalance, BALANCE_ROW_ID)
            since_balance = None if balance is None else balance.set_at
            spent_since_balance = await spend_since(session, since_balance)
            today = await spend_since(session, local_today)
            month = await spend_since(session, month_start)
            last_30_days = await spend_since(session, now - RECENT_WINDOW)
        return UsageSummary(
            balance_usd=None if balance is None else balance.balance_usd,
            balance_set_at=None if balance is None else balance.set_at,
            spent_since_balance_usd=spent_since_balance.usd,
            today=today,
            month_usd=month.usd,
            last_30_days_usd=last_30_days.usd,
        )

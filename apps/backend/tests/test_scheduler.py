import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from ved_db import Reminder

from ved_backend.push import DeliveryReport, Notification
from ved_backend.scheduler import ReminderScheduler, claim_due_reminders, describe

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

ZONE = ZoneInfo("Asia/Kolkata")
GIVE_UP = timedelta(hours=24)


def at(offset_minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=offset_minutes)


class RecordingPush:
    def __init__(self, configured: bool = True, sent: int = 1) -> None:
        self.configured = configured
        self.sent: list[Notification] = []
        self._sent_count = sent

    async def send(self, notification: Notification) -> DeliveryReport:
        self.sent.append(notification)
        return DeliveryReport(sent=self._sent_count, expired=0)


def build(session_factory, push, poll_seconds: float = 30.0) -> ReminderScheduler:
    return ReminderScheduler(
        session_factory, push, timezone="Asia/Kolkata", poll_seconds=poll_seconds
    )


def test_description_renders_local_time():
    due = datetime(2026, 10, 3, 14, 30, tzinfo=UTC)
    reminder = Reminder(text="call Mom", due_at=due)

    assert describe(reminder, ZONE) == "call Mom — 8:00 PM"


async def test_a_due_reminder_is_announced(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="call Mom", due_at=at(-1)))
        await session.commit()

    push = RecordingPush()
    fired = await build(session_factory, push).tick()

    assert fired == 1
    assert push.sent[0].body.startswith("call Mom")
    assert push.sent[0].tag == "reminder"


async def test_a_future_reminder_is_left_alone(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="later", due_at=at(60)))
        await session.commit()

    push = RecordingPush()

    assert await build(session_factory, push).tick() == 0
    assert push.sent == []


async def test_a_reminder_fires_only_once(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="call Mom", due_at=at(-1)))
        await session.commit()

    push = RecordingPush()
    scheduler = build(session_factory, push)

    assert await scheduler.tick() == 1
    assert await scheduler.tick() == 0
    assert len(push.sent) == 1


async def test_completed_reminders_never_fire(session_factory):
    async with session_factory() as session:
        session.add(
            Reminder(text="done", due_at=at(-1), completed_at=datetime.now(UTC))
        )
        await session.commit()

    push = RecordingPush()

    assert await build(session_factory, push).tick() == 0
    assert push.sent == []


async def test_firing_stamps_notified_at(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="call Mom", due_at=at(-1)))
        await session.commit()

    await build(session_factory, RecordingPush()).tick()

    async with session_factory() as session:
        stored = await session.scalar(select(Reminder))
        assert stored.notified_at is not None


async def test_several_due_reminders_all_fire(session_factory):
    async with session_factory() as session:
        for index in range(3):
            session.add(Reminder(text=f"task {index}", due_at=at(-index - 1)))
        await session.commit()

    push = RecordingPush()

    assert await build(session_factory, push).tick() == 3
    assert len(push.sent) == 3


async def test_reminders_still_fire_without_push_configured(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="call Mom", due_at=at(-1)))
        await session.commit()

    push = RecordingPush(configured=False)

    assert await build(session_factory, push).tick() == 1
    assert push.sent == []

    async with session_factory() as session:
        stored = await session.scalar(select(Reminder))
        assert stored.notified_at is not None


async def test_claim_marks_rows_in_one_transaction(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="call Mom", due_at=at(-1)))
        await session.commit()

    async with session_factory() as session:
        claimed = await claim_due_reminders(
            session, now=datetime.now(UTC), zone=ZONE, give_up_after=GIVE_UP
        )

    assert len(claimed) == 1

    async with session_factory() as session:
        again = await claim_due_reminders(
            session, now=datetime.now(UTC), zone=ZONE, give_up_after=GIVE_UP
        )

    assert again == []


async def test_an_undelivered_reminder_is_retried_not_lost(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="call Mom", due_at=at(-1)))
        await session.commit()

    unreachable = RecordingPush(sent=0)
    scheduler = build(session_factory, unreachable)

    assert await scheduler.tick() == 1

    async with session_factory() as session:
        stored = await session.scalar(select(Reminder))
        assert stored.notified_at is None, "should be released for another attempt"

    reachable = RecordingPush(sent=1)
    assert await build(session_factory, reachable).tick() == 1
    assert len(reachable.sent) == 1


async def test_a_long_undeliverable_reminder_is_given_up_on(session_factory):
    async with session_factory() as session:
        session.add(Reminder(text="ancient", due_at=at(-60 * 48)))
        await session.commit()

    scheduler = ReminderScheduler(
        session_factory,
        RecordingPush(sent=0),
        timezone="Asia/Kolkata",
        poll_seconds=30.0,
        give_up_after=timedelta(hours=24),
    )

    assert await scheduler.tick() == 1

    async with session_factory() as session:
        stored = await session.scalar(select(Reminder))
        assert stored.notified_at is not None, "should stop retrying forever"

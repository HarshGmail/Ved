import asyncio
import logging
import uuid
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import Reminder

from ved_backend.birthdays import schedule_birthday_reminders
from ved_backend.checkins import is_early_birthday_notice, open_check_in
from ved_backend.push import Notification, PushService

logger = logging.getLogger(__name__)

NOTIFICATION_TITLE = "Ved"
DEFAULT_GIVE_UP_AFTER = timedelta(hours=24)
DEFAULT_BIRTHDAY_REMINDER_TIME = time(9, 0)
REMINDER_TAG = "reminder"
BIRTHDAY_TAG = "birthday"
HOME_URL = "/"


class Indexer(Protocol):
    def trigger(self) -> None: ...


def describe(reminder: Reminder, zone: ZoneInfo) -> str:
    if reminder.person_id is not None:
        return reminder.text
    when = reminder.due_at.astimezone(zone).strftime("%-I:%M %p")
    return f"{reminder.text} — {when}"


@dataclass(frozen=True)
class ClaimedReminder:
    id: uuid.UUID
    summary: str
    stale: bool
    tag: str = REMINDER_TAG
    url: str = HOME_URL


async def claim_due_reminders(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, give_up_after: timedelta
) -> list[ClaimedReminder]:
    rows = await session.scalars(
        select(Reminder)
        .where(
            Reminder.due_at <= now,
            Reminder.notified_at.is_(None),
            Reminder.completed_at.is_(None),
        )
        .order_by(Reminder.due_at)
        .with_for_update(skip_locked=True)
    )

    today = now.astimezone(zone).date()
    claimed = []
    for reminder in rows.all():
        reminder.notified_at = func.now()
        summary, url = describe(reminder, zone), HOME_URL
        if is_early_birthday_notice(reminder):
            check_in = await open_check_in(session, reminder, today=today)
            if check_in is not None:
                summary, url = check_in.opening, check_in.url
        claimed.append(
            ClaimedReminder(
                id=reminder.id,
                summary=summary,
                stale=now - reminder.due_at > give_up_after,
                tag=REMINDER_TAG if reminder.person_id is None else BIRTHDAY_TAG,
                url=url,
            )
        )
    await session.commit()
    return claimed


async def release(session: AsyncSession, reminder_id: uuid.UUID) -> None:
    await session.execute(
        update(Reminder).where(Reminder.id == reminder_id).values(notified_at=None)
    )
    await session.commit()


class ReminderScheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        push: PushService,
        *,
        timezone: str,
        poll_seconds: float,
        birthday_reminder_time: time = DEFAULT_BIRTHDAY_REMINDER_TIME,
        give_up_after: timedelta = DEFAULT_GIVE_UP_AFTER,
        indexers: Sequence[Indexer] = (),
    ) -> None:
        self._session_factory = session_factory
        self._push = push
        self._zone = ZoneInfo(timezone)
        self._poll_seconds = poll_seconds
        self._birthday_reminder_time = birthday_reminder_time
        self._give_up_after = give_up_after
        self._indexers = tuple(indexers)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="reminder-scheduler")
        logger.info("Reminder scheduler polling every %ss", self._poll_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Reminder scheduler tick failed")
            await asyncio.sleep(self._poll_seconds)

    async def tick(self) -> int:
        now = datetime.now(self._zone)
        async with self._session_factory() as session:
            scheduled = await schedule_birthday_reminders(
                session,
                now=now,
                zone=self._zone,
                remind_at=self._birthday_reminder_time,
            )
        if scheduled:
            logger.info("Scheduled %d birthday reminders", scheduled)

        async with self._session_factory() as session:
            due = await claim_due_reminders(
                session,
                now=now,
                zone=self._zone,
                give_up_after=self._give_up_after,
            )

        for reminder in due:
            await self._announce(reminder)

        for indexer in self._indexers:
            indexer.trigger()
        return len(due)

    async def _announce(self, reminder: ClaimedReminder) -> None:
        logger.info("Reminder due: %s", reminder.summary)
        if not self._push.configured:
            return

        report = await self._push.send(
            Notification(
                title=NOTIFICATION_TITLE,
                body=reminder.summary,
                tag=reminder.tag,
                url=reminder.url,
            )
        )
        if report.reached_anyone:
            return

        if reminder.stale:
            logger.error(
                "Giving up on %r — undeliverable for over %s",
                reminder.summary,
                self._give_up_after,
            )
            return

        logger.warning("Nothing reachable for %r, will retry", reminder.summary)
        async with self._session_factory() as session:
            await release(session, reminder.id)

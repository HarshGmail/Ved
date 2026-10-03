import asyncio
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import Reminder

from ved_backend.push import Notification, PushService

logger = logging.getLogger(__name__)

NOTIFICATION_TITLE = "Ved"
DEFAULT_GIVE_UP_AFTER = timedelta(hours=24)


def describe(reminder: Reminder, zone: ZoneInfo) -> str:
    when = reminder.due_at.astimezone(zone).strftime("%-I:%M %p")
    return f"{reminder.text} — {when}"


@dataclass(frozen=True)
class ClaimedReminder:
    id: uuid.UUID
    summary: str
    stale: bool


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

    claimed = []
    for reminder in rows:
        reminder.notified_at = func.now()
        claimed.append(
            ClaimedReminder(
                id=reminder.id,
                summary=describe(reminder, zone),
                stale=now - reminder.due_at > give_up_after,
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
        give_up_after: timedelta = DEFAULT_GIVE_UP_AFTER,
    ) -> None:
        self._session_factory = session_factory
        self._push = push
        self._zone = ZoneInfo(timezone)
        self._poll_seconds = poll_seconds
        self._give_up_after = give_up_after
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
        async with self._session_factory() as session:
            due = await claim_due_reminders(
                session,
                now=datetime.now(self._zone),
                zone=self._zone,
                give_up_after=self._give_up_after,
            )

        for reminder in due:
            await self._announce(reminder)
        return len(due)

    async def _announce(self, reminder: ClaimedReminder) -> None:
        logger.info("Reminder due: %s", reminder.summary)
        if not self._push.configured:
            return

        report = await self._push.send(
            Notification(
                title=NOTIFICATION_TITLE, body=reminder.summary, tag="reminder"
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

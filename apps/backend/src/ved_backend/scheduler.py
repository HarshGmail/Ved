import asyncio
import logging
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import Reminder

from ved_backend.push import Notification, PushService

logger = logging.getLogger(__name__)

NOTIFICATION_TITLE = "Ved"


def describe(reminder: Reminder, zone: ZoneInfo) -> str:
    when = reminder.due_at.astimezone(zone).strftime("%-I:%M %p")
    return f"{reminder.text} — {when}"


async def claim_due_reminders(
    session: AsyncSession, *, now: datetime
) -> list[Reminder]:
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
    claimed = list(rows)
    for reminder in claimed:
        reminder.notified_at = func.now()
    await session.commit()
    return claimed


class ReminderScheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        push: PushService,
        *,
        timezone: str,
        poll_seconds: float,
    ) -> None:
        self._session_factory = session_factory
        self._push = push
        self._zone = ZoneInfo(timezone)
        self._poll_seconds = poll_seconds
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
            due = await claim_due_reminders(session, now=datetime.now(self._zone))
            summaries = [describe(reminder, self._zone) for reminder in due]

        for summary in summaries:
            await self._announce(summary)
        return len(summaries)

    async def _announce(self, summary: str) -> None:
        logger.info("Reminder due: %s", summary)
        if not self._push.configured:
            return
        report = await self._push.send(
            Notification(title=NOTIFICATION_TITLE, body=summary, tag="reminder")
        )
        if not report.reached_anyone:
            logger.warning("Reminder fired with no reachable device: %s", summary)

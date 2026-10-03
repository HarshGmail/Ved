import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import Reminder


class ReminderNotFoundError(LookupError):
    def __init__(self, reminder_id: uuid.UUID) -> None:
        super().__init__(f"No reminder with id {reminder_id}")
        self.reminder_id = reminder_id


class ReminderRecord(BaseModel):
    id: str = Field(description="Stable identifier for this reminder")
    text: str = Field(description="What the user asked to be reminded about")
    due_at: str = Field(description="When it is due, ISO 8601 with UTC offset")
    completed: bool = Field(description="Whether it has been completed")

    @classmethod
    def from_row(cls, row: Reminder) -> "ReminderRecord":
        return cls(
            id=str(row.id),
            text=row.text,
            due_at=row.due_at.isoformat(),
            completed=row.completed_at is not None,
        )


class ReminderList(BaseModel):
    reminders: list[ReminderRecord]


async def create_reminder(
    session: AsyncSession, text: str, due_at: datetime
) -> ReminderRecord:
    reminder = Reminder(text=text, due_at=due_at)
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)
    return ReminderRecord.from_row(reminder)


async def list_reminders(
    session: AsyncSession, *, include_completed: bool, limit: int
) -> list[ReminderRecord]:
    query = select(Reminder).order_by(Reminder.due_at).limit(limit)
    if not include_completed:
        query = query.where(Reminder.completed_at.is_(None))

    rows = await session.scalars(query)
    return [ReminderRecord.from_row(row) for row in rows]


async def complete_reminder(
    session: AsyncSession, reminder_id: uuid.UUID
) -> ReminderRecord:
    reminder = await session.get(Reminder, reminder_id)
    if reminder is None:
        raise ReminderNotFoundError(reminder_id)

    if reminder.completed_at is None:
        reminder.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(reminder)

    return ReminderRecord.from_row(reminder)


async def reschedule_reminder(
    session: AsyncSession, reminder_id: uuid.UUID, due_at: datetime
) -> ReminderRecord:
    reminder = await session.get(Reminder, reminder_id)
    if reminder is None:
        raise ReminderNotFoundError(reminder_id)

    reminder.due_at = due_at
    reminder.notified_at = None
    await session.commit()
    await session.refresh(reminder)
    return ReminderRecord.from_row(reminder)

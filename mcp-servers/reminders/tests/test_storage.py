import uuid
from datetime import UTC, datetime, timedelta

import pytest

from ved_reminders import storage
from ved_reminders.storage import ReminderNotFoundError

from .conftest import requires_database

pytestmark = requires_database


def at(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


async def test_create_returns_persisted_reminder(session):
    record = await storage.create_reminder(session, "Call Mom", at(2))

    assert record.text == "Call Mom"
    assert record.completed is False
    assert uuid.UUID(record.id)


async def test_list_orders_by_due_date(session):
    await storage.create_reminder(session, "later", at(5))
    await storage.create_reminder(session, "sooner", at(1))

    records = await storage.list_reminders(session, include_completed=False, limit=10)

    assert [r.text for r in records] == ["sooner", "later"]


async def test_list_hides_completed_unless_requested(session):
    done = await storage.create_reminder(session, "done", at(1))
    await storage.complete_reminder(session, uuid.UUID(done.id))

    hidden = await storage.list_reminders(session, include_completed=False, limit=10)
    shown = await storage.list_reminders(session, include_completed=True, limit=10)

    assert hidden == []
    assert [r.text for r in shown] == ["done"]


async def test_list_respects_limit(session):
    for hour in range(5):
        await storage.create_reminder(session, f"r{hour}", at(hour + 1))

    records = await storage.list_reminders(session, include_completed=False, limit=2)

    assert len(records) == 2


async def test_complete_marks_reminder_done(session):
    created = await storage.create_reminder(session, "Call Mom", at(2))

    completed = await storage.complete_reminder(session, uuid.UUID(created.id))

    assert completed.completed is True
    assert completed.id == created.id


async def test_complete_is_idempotent(session):
    created = await storage.create_reminder(session, "Call Mom", at(2))
    first = await storage.complete_reminder(session, uuid.UUID(created.id))

    second = await storage.complete_reminder(session, uuid.UUID(created.id))

    assert second.completed is True
    assert second == first


async def test_complete_unknown_id_raises(session):
    with pytest.raises(ReminderNotFoundError):
        await storage.complete_reminder(session, uuid.uuid4())

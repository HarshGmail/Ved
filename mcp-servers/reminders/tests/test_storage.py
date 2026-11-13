import uuid
from datetime import UTC, datetime, timedelta

import pytest
from ved_db import Reminder

from ved_reminders import storage
from ved_reminders.storage import ReminderNotFoundError

from .conftest import requires_database

pytestmark = requires_database


def at(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


async def test_create_returns_persisted_reminder(session, user):
    record = await storage.create_reminder(session, user.id, "Call Mom", at(2))

    assert record.text == "Call Mom"
    assert record.completed is False
    assert uuid.UUID(record.id)


async def test_list_orders_by_due_date(session, user):
    await storage.create_reminder(session, user.id, "later", at(5))
    await storage.create_reminder(session, user.id, "sooner", at(1))

    records = await storage.list_reminders(
        session, user.id, include_completed=False, limit=10
    )

    assert [r.text for r in records] == ["sooner", "later"]


async def test_list_hides_completed_unless_requested(session, user):
    done = await storage.create_reminder(session, user.id, "done", at(1))
    await storage.complete_reminder(session, user.id, uuid.UUID(done.id))

    hidden = await storage.list_reminders(
        session, user.id, include_completed=False, limit=10
    )
    shown = await storage.list_reminders(
        session, user.id, include_completed=True, limit=10
    )

    assert hidden == []
    assert [r.text for r in shown] == ["done"]


async def test_list_respects_limit(session, user):
    for hour in range(5):
        await storage.create_reminder(session, user.id, f"r{hour}", at(hour + 1))

    records = await storage.list_reminders(
        session, user.id, include_completed=False, limit=2
    )

    assert len(records) == 2


async def test_complete_marks_reminder_done(session, user):
    created = await storage.create_reminder(session, user.id, "Call Mom", at(2))

    completed = await storage.complete_reminder(session, user.id, uuid.UUID(created.id))

    assert completed.completed is True
    assert completed.id == created.id


async def test_complete_is_idempotent(session, user):
    created = await storage.create_reminder(session, user.id, "Call Mom", at(2))
    first = await storage.complete_reminder(session, user.id, uuid.UUID(created.id))

    second = await storage.complete_reminder(session, user.id, uuid.UUID(created.id))

    assert second.completed is True
    assert second == first


async def test_complete_unknown_id_raises(session, user):
    with pytest.raises(ReminderNotFoundError):
        await storage.complete_reminder(session, user.id, uuid.uuid4())


@requires_database
async def test_rescheduling_moves_the_same_reminder(session, user):
    created = await storage.create_reminder(session, user.id, "call Mom", at(2))

    moved = await storage.reschedule_reminder(
        session, user.id, uuid.UUID(created.id), at(3)
    )

    assert moved.id == created.id
    assert moved.completed is False
    assert moved.due_at != created.due_at


@requires_database
async def test_rescheduling_lets_it_fire_again(session, user):
    created = await storage.create_reminder(session, user.id, "call Mom", at(1))
    row = await session.get(Reminder, uuid.UUID(created.id))
    row.notified_at = datetime.now(UTC)
    await session.commit()

    await storage.reschedule_reminder(session, user.id, uuid.UUID(created.id), at(4))

    refreshed = await session.get(Reminder, uuid.UUID(created.id))
    assert refreshed.notified_at is None


@requires_database
async def test_rescheduling_something_unknown_is_reported(session, user):
    with pytest.raises(storage.ReminderNotFoundError):
        await storage.reschedule_reminder(session, user.id, uuid.uuid4(), at(1))


async def test_one_users_reminders_never_show_for_another(session, user, other_user):
    await storage.create_reminder(session, user.id, "mine", at(1))
    await storage.create_reminder(session, other_user.id, "theirs", at(1))

    mine = await storage.list_reminders(
        session, user.id, include_completed=True, limit=10
    )
    theirs = await storage.list_reminders(
        session, other_user.id, include_completed=True, limit=10
    )

    assert [r.text for r in mine] == ["mine"]
    assert [r.text for r in theirs] == ["theirs"]


async def test_another_users_reminder_cannot_be_completed_or_moved(
    session, user, other_user
):
    created = await storage.create_reminder(session, user.id, "mine", at(1))
    reminder_id = uuid.UUID(created.id)

    with pytest.raises(ReminderNotFoundError):
        await storage.complete_reminder(session, other_user.id, reminder_id)
    with pytest.raises(ReminderNotFoundError):
        await storage.reschedule_reminder(session, other_user.id, reminder_id, at(5))

    row = await session.get(Reminder, reminder_id)
    assert row.completed_at is None
    assert row.due_at.isoformat() == created.due_at

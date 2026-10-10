import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from ved_db import Person, Reminder, birthday_in

from ved_backend.birthdays import plan_for, schedule_birthday_reminders
from ved_backend.push import DeliveryReport, Notification
from ved_backend.scheduler import ReminderScheduler

ZONE = ZoneInfo("Asia/Kolkata")
NINE_AM = time(9, 0)

requires_database = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


def local(year: int, month: int, day: int, hour: int = 8) -> datetime:
    return datetime(year, month, day, hour, tzinfo=ZONE)


def mom(notice: int = 15, year: int | None = 1965) -> Person:
    return Person(
        name="Mom",
        birth_month=10,
        birth_day=25,
        birth_year=year,
        birthday_notice_days=notice,
    )


def test_leap_day_birthdays_fall_on_the_28th_in_other_years():
    assert birthday_in(2027, 2, 29) == date(2027, 2, 28)
    assert birthday_in(2028, 2, 29) == date(2028, 2, 29)


def test_next_birthday_rolls_into_next_year_once_passed():
    person = mom()

    assert person.next_birthday(date(2026, 10, 25)) == date(2026, 10, 25)
    assert person.next_birthday(date(2026, 10, 26)) == date(2027, 10, 25)


def test_plan_has_an_early_notice_and_one_on_the_day():
    planned = plan_for(mom(), now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM)

    assert [(p.lead_days, p.due_at) for p in planned] == [
        (15, datetime(2026, 10, 10, 9, tzinfo=ZONE)),
        (0, datetime(2026, 10, 25, 9, tzinfo=ZONE)),
    ]


def test_zero_notice_means_only_on_the_day():
    planned = plan_for(
        mom(notice=0), now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
    )

    assert [p.lead_days for p in planned] == [0]


def test_a_notice_saved_inside_its_window_is_sent_now_with_the_real_countdown():
    now = local(2026, 10, 20)
    early, on_the_day = plan_for(mom(), now=now, zone=ZONE, remind_at=NINE_AM)

    assert early.due_at == now
    assert early.text == "Mom's birthday is in 5 days, on Sunday 25 October"
    assert on_the_day.due_at == datetime(2026, 10, 25, 9, tzinfo=ZONE)


def test_a_notice_landing_the_day_before_says_tomorrow():
    early, _ = plan_for(mom(), now=local(2026, 10, 24), zone=ZONE, remind_at=NINE_AM)

    assert early.text == "Mom's birthday is tomorrow"


def test_on_the_birthday_itself_only_the_day_reminder_is_planned():
    now = local(2026, 10, 25, hour=10)
    planned = plan_for(mom(), now=now, zone=ZONE, remind_at=NINE_AM)

    assert [(p.lead_days, p.due_at) for p in planned] == [(0, now)]


def test_the_day_after_the_birthday_plans_next_year():
    planned = plan_for(mom(), now=local(2026, 10, 26), zone=ZONE, remind_at=NINE_AM)

    assert {p.birthday_on for p in planned} == {date(2027, 10, 25)}


def test_reminder_text_reads_naturally():
    early, on_the_day = plan_for(
        mom(), now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
    )

    assert early.text == "Mom's birthday is in 15 days, on Sunday 25 October"
    assert on_the_day.text == "Mom turns 61 today"


def test_on_the_day_text_without_a_birth_year():
    (on_the_day,) = plan_for(
        mom(notice=0, year=None), now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
    )

    assert on_the_day.text == "It's Mom's birthday today"


def test_people_without_a_birthday_plan_nothing():
    person = Person(name="Rahul", birthday_notice_days=0)

    assert plan_for(person, now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM) == []


class RecordingPush:
    configured = True

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def send(self, notification: Notification) -> DeliveryReport:
        self.sent.append(notification)
        return DeliveryReport(sent=1, expired=0)


@requires_database
async def test_scheduling_creates_reminder_rows(session_factory):
    async with session_factory() as session:
        session.add(mom())
        await session.commit()

    async with session_factory() as session:
        created = await schedule_birthday_reminders(
            session, now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
        )

    assert created == 2
    async with session_factory() as session:
        rows = list(await session.scalars(select(Reminder).order_by(Reminder.due_at)))
    assert [row.lead_days for row in rows] == [15, 0]
    assert all(row.birthday_on == date(2026, 10, 25) for row in rows)


@requires_database
async def test_scheduling_twice_does_not_duplicate(session_factory):
    async with session_factory() as session:
        session.add(mom())
        await session.commit()

    for _ in range(2):
        async with session_factory() as session:
            await schedule_birthday_reminders(
                session, now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
            )

    async with session_factory() as session:
        rows = list(await session.scalars(select(Reminder)))
    assert len(rows) == 2


@requires_database
async def test_a_fired_birthday_is_not_recreated(session_factory):
    async with session_factory() as session:
        session.add(mom(notice=0))
        await session.commit()

    async with session_factory() as session:
        await schedule_birthday_reminders(
            session, now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
        )
        row = await session.scalar(select(Reminder))
        row.notified_at = local(2026, 10, 25, hour=9)
        await session.commit()

    async with session_factory() as session:
        created = await schedule_birthday_reminders(
            session, now=local(2026, 10, 25, hour=8), zone=ZONE, remind_at=NINE_AM
        )

    assert created == 0


@requires_database
async def test_forgetting_a_person_removes_their_reminders(session_factory):
    async with session_factory() as session:
        person = mom()
        session.add(person)
        await session.commit()
        await schedule_birthday_reminders(
            session, now=local(2026, 10, 1), zone=ZONE, remind_at=NINE_AM
        )
        await session.delete(person)
        await session.commit()

    async with session_factory() as session:
        assert list(await session.scalars(select(Reminder))) == []


@requires_database
async def test_a_due_birthday_is_pushed_with_its_own_tag(session_factory):
    async with session_factory() as session:
        person = mom(notice=0)
        session.add(person)
        await session.flush()
        session.add(
            Reminder(
                text="It's Mom's birthday today",
                due_at=local(2020, 1, 2),
                person_id=person.id,
                birthday_on=date(2020, 1, 2),
                lead_days=0,
            )
        )
        await session.commit()

    push = RecordingPush()
    scheduler = ReminderScheduler(
        session_factory, push, timezone="Asia/Kolkata", poll_seconds=30.0
    )
    await scheduler.tick()

    assert [(n.tag, n.body) for n in push.sent] == [
        ("birthday", "It's Mom's birthday today")
    ]

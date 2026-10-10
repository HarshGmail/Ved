from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import Person, Reminder

ON_THE_DAY = 0


@dataclass(frozen=True)
class PlannedBirthdayReminder:
    person: Person
    birthday_on: date
    lead_days: int
    due_at: datetime
    days_left: int

    @property
    def text(self) -> str:
        name = self.person.name
        if self.days_left == 0:
            age = self.person.age_on(self.birthday_on)
            if age is None:
                return f"It's {name}'s birthday today"
            return f"{name} turns {age} today"

        if self.days_left == 1:
            return f"{name}'s birthday is tomorrow"

        weekday_and_date = self.birthday_on.strftime("%A %-d %B")
        return f"{name}'s birthday is in {self.days_left} days, on {weekday_and_date}"


def lead_days_for(person: Person) -> list[int]:
    return sorted({ON_THE_DAY, person.birthday_notice_days}, reverse=True)


def plan_for(
    person: Person, *, now: datetime, zone: ZoneInfo, remind_at: time
) -> list[PlannedBirthdayReminder]:
    today = now.astimezone(zone).date()
    birthday = person.next_birthday(today)
    if birthday is None:
        return []

    planned = []
    for lead in lead_days_for(person):
        intended = datetime.combine(birthday - timedelta(days=lead), remind_at, zone)
        due_at = max(intended, now)
        days_left = (birthday - due_at.astimezone(zone).date()).days
        is_late_notice_on_the_day = lead != ON_THE_DAY and days_left == 0
        if is_late_notice_on_the_day:
            continue
        planned.append(
            PlannedBirthdayReminder(person, birthday, lead, due_at, days_left)
        )
    return planned


async def schedule_birthday_reminders(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, remind_at: time
) -> int:
    people = await session.scalars(
        select(Person).where(Person.birth_month.is_not(None))
    )
    planned = [
        reminder
        for person in people
        for reminder in plan_for(person, now=now, zone=zone, remind_at=remind_at)
    ]
    if not planned:
        return 0

    result = await session.execute(
        insert(Reminder)
        .values(
            [
                {
                    "text": reminder.text,
                    "due_at": reminder.due_at,
                    "person_id": reminder.person.id,
                    "birthday_on": reminder.birthday_on,
                    "lead_days": reminder.lead_days,
                }
                for reminder in planned
            ]
        )
        .on_conflict_do_nothing(constraint="uq_reminders_person_birthday_lead")
        .returning(Reminder.id)
    )
    created = len(result.all())
    await session.commit()
    return created

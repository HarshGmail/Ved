from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import Person, Reminder

UNCHANGED = None


class PersonNotFoundError(LookupError):
    def __init__(self, name: str, known: list[str]) -> None:
        listing = ", ".join(known) if known else "nobody yet"
        super().__init__(f"No person named {name!r}. Known people: {listing}")
        self.name = name


@dataclass(frozen=True)
class Birthday:
    month: int
    day: int
    year: int | None = None

    def as_text(self) -> str:
        if self.year is None:
            return f"--{self.month:02d}-{self.day:02d}"
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


class PersonRecord(BaseModel):
    id: str = Field(description="Stable identifier for this person")
    name: str = Field(description="How the user refers to them, e.g. Mom")
    relation: str | None = Field(description="Who they are to the user")
    birthday: str | None = Field(
        description="YYYY-MM-DD, or --MM-DD when the birth year is unknown"
    )
    birthday_notice_days: int = Field(
        description="How many days before the birthday the user is reminded, "
        "in addition to a reminder on the day itself"
    )
    next_birthday: str | None = Field(description="Next birthday, YYYY-MM-DD")
    days_until_birthday: int | None = Field(description="0 means today")
    turning: int | None = Field(description="Age at the next birthday, if known")

    @classmethod
    def from_row(cls, row: Person, today: date) -> "PersonRecord":
        upcoming = row.next_birthday(today)
        birthday = (
            None
            if row.birth_month is None or row.birth_day is None
            else Birthday(row.birth_month, row.birth_day, row.birth_year)
        )
        return cls(
            id=str(row.id),
            name=row.name,
            relation=row.relation,
            birthday=None if birthday is None else birthday.as_text(),
            birthday_notice_days=row.birthday_notice_days,
            next_birthday=None if upcoming is None else upcoming.isoformat(),
            days_until_birthday=None if upcoming is None else (upcoming - today).days,
            turning=None if upcoming is None else row.age_on(upcoming),
        )


class PersonList(BaseModel):
    people: list[PersonRecord]


class Forgotten(BaseModel):
    name: str = Field(description="The person who was removed")


def soonest_birthday_first(record: PersonRecord) -> tuple[bool, int, str]:
    no_birthday = record.days_until_birthday is None
    return no_birthday, record.days_until_birthday or 0, record.name.lower()


async def find_person(session: AsyncSession, name: str) -> Person | None:
    return await session.scalar(
        select(Person).where(func.lower(Person.name) == name.lower())
    )


async def known_names(session: AsyncSession) -> list[str]:
    rows = await session.scalars(select(Person.name).order_by(Person.name))
    return list(rows)


async def discard_pending_birthday_reminders(
    session: AsyncSession, person: Person
) -> None:
    await session.execute(
        delete(Reminder).where(
            Reminder.person_id == person.id,
            Reminder.notified_at.is_(None),
            Reminder.completed_at.is_(None),
        )
    )


async def save_person(
    session: AsyncSession,
    name: str,
    *,
    today: date,
    relation: str | None = UNCHANGED,
    birthday: Birthday | None = UNCHANGED,
    birthday_notice_days: int | None = UNCHANGED,
) -> PersonRecord:
    person = await find_person(session, name)
    if person is None:
        person = Person(name=name, birthday_notice_days=0)
        session.add(person)

    if relation is not UNCHANGED:
        person.relation = relation

    birthday_changed = False
    if birthday is not UNCHANGED:
        date_changed = (person.birth_month, person.birth_day) != (
            birthday.month,
            birthday.day,
        )
        repeats_known_date_without_year = not date_changed and birthday.year is None
        year = person.birth_year if repeats_known_date_without_year else birthday.year
        birthday_changed = date_changed or year != person.birth_year
        person.birth_month = birthday.month
        person.birth_day = birthday.day
        person.birth_year = year

    notice_changed = False
    if birthday_notice_days is not UNCHANGED:
        notice_changed = person.birthday_notice_days != birthday_notice_days
        person.birthday_notice_days = birthday_notice_days

    await session.flush()
    if birthday_changed or notice_changed:
        await discard_pending_birthday_reminders(session, person)

    await session.commit()
    await session.refresh(person)
    return PersonRecord.from_row(person, today)


async def list_people(session: AsyncSession, *, today: date) -> list[PersonRecord]:
    rows = await session.scalars(select(Person))
    records = [PersonRecord.from_row(row, today) for row in rows]
    return sorted(records, key=soonest_birthday_first)


async def forget_person(session: AsyncSession, name: str) -> Forgotten:
    person = await find_person(session, name)
    if person is None:
        raise PersonNotFoundError(name, await known_names(session))

    forgotten = Forgotten(name=person.name)
    await session.delete(person)
    await session.commit()
    return forgotten

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from ved_db import Reminder

from ved_people import storage
from ved_people.storage import Birthday, PersonNotFoundError

from .conftest import requires_database

pytestmark = requires_database

TODAY = date(2026, 10, 10)
MOM_BIRTHDAY = Birthday(month=10, day=25, year=1965)


async def add_birthday_reminder(session, user, person_id: str, **fields) -> None:
    session.add(
        Reminder(
            user_id=user.id,
            text="Mom's birthday",
            due_at=datetime(2026, 10, 25, 3, 30, tzinfo=UTC),
            person_id=person_id,
            birthday_on=date(2026, 10, 25),
            lead_days=0,
            **fields,
        )
    )
    await session.commit()


async def test_remember_creates_a_person_with_their_next_birthday(session, user):
    record = await storage.save_person(
        session,
        user.id,
        "Mom",
        today=TODAY,
        relation="mother",
        birthday=MOM_BIRTHDAY,
        birthday_notice_days=15,
    )

    assert record.birthday == "1965-10-25"
    assert record.next_birthday == "2026-10-25"
    assert record.days_until_birthday == 15
    assert record.turning == 61
    assert record.birthday_notice_days == 15


async def test_a_birthday_without_a_year_has_no_age(session, user):
    record = await storage.save_person(
        session, user.id, "Rahul", today=TODAY, birthday=Birthday(month=1, day=3)
    )

    assert record.birthday == "--01-03"
    assert record.turning is None
    assert record.next_birthday == "2027-01-03"


async def test_remembering_again_updates_only_what_was_given(session, user):
    await storage.save_person(
        session, user.id, "Mom", today=TODAY, relation="mother", birthday=MOM_BIRTHDAY
    )

    updated = await storage.save_person(
        session, user.id, "mom", today=TODAY, birthday_notice_days=7
    )

    assert updated.name == "Mom"
    assert updated.relation == "mother"
    assert updated.birthday == "1965-10-25"
    assert updated.birthday_notice_days == 7
    assert len(await storage.list_people(session, user.id, today=TODAY)) == 1


async def test_repeating_the_birthday_without_a_year_keeps_the_known_year(
    session, user
):
    await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=MOM_BIRTHDAY
    )

    updated = await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=Birthday(month=10, day=25)
    )

    assert updated.birthday == "1965-10-25"
    assert updated.turning == 61


async def test_a_different_birthday_without_a_year_drops_the_old_year(session, user):
    await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=MOM_BIRTHDAY
    )

    updated = await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=Birthday(month=10, day=26)
    )

    assert updated.birthday == "--10-26"
    assert updated.turning is None


async def test_changing_notice_discards_reminders_not_yet_sent(session, user):
    record = await storage.save_person(
        session,
        user.id,
        "Mom",
        today=TODAY,
        birthday=MOM_BIRTHDAY,
        birthday_notice_days=15,
    )
    await add_birthday_reminder(session, user, record.id)

    await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday_notice_days=3
    )

    assert list(await session.scalars(select(Reminder))) == []


async def test_changing_notice_keeps_reminders_already_sent(session, user):
    record = await storage.save_person(
        session,
        user.id,
        "Mom",
        today=TODAY,
        birthday=MOM_BIRTHDAY,
        birthday_notice_days=15,
    )
    await add_birthday_reminder(session, user, record.id, notified_at=datetime.now(UTC))

    await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday_notice_days=3
    )

    assert len(list(await session.scalars(select(Reminder)))) == 1


async def test_learning_the_birth_year_replans_so_the_age_is_mentioned(session, user):
    record = await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=Birthday(month=10, day=25)
    )
    await add_birthday_reminder(session, user, record.id)

    await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=MOM_BIRTHDAY
    )

    assert list(await session.scalars(select(Reminder))) == []


async def test_repeating_the_same_birthday_keeps_pending_reminders(session, user):
    record = await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=MOM_BIRTHDAY
    )
    await add_birthday_reminder(session, user, record.id)

    await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=Birthday(month=10, day=25)
    )

    assert len(list(await session.scalars(select(Reminder)))) == 1


async def test_changing_only_the_relation_keeps_pending_reminders(session, user):
    record = await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=MOM_BIRTHDAY
    )
    await add_birthday_reminder(session, user, record.id)

    await storage.save_person(session, user.id, "Mom", today=TODAY, relation="mother")

    assert len(list(await session.scalars(select(Reminder)))) == 1


async def test_list_puts_the_soonest_birthday_first(session, user):
    await storage.save_person(session, user.id, "Nobody", today=TODAY)
    await storage.save_person(
        session, user.id, "Later", today=TODAY, birthday=Birthday(month=3, day=1)
    )
    await storage.save_person(
        session, user.id, "Sooner", today=TODAY, birthday=Birthday(month=10, day=12)
    )

    records = await storage.list_people(session, user.id, today=TODAY)

    assert [r.name for r in records] == ["Sooner", "Later", "Nobody"]


async def test_forget_removes_the_person_and_their_reminders(session, user):
    record = await storage.save_person(
        session, user.id, "Mom", today=TODAY, birthday=MOM_BIRTHDAY
    )
    await add_birthday_reminder(session, user, record.id)

    forgotten = await storage.forget_person(session, user.id, "MOM")

    assert forgotten.name == "Mom"
    assert await storage.list_people(session, user.id, today=TODAY) == []
    assert list(await session.scalars(select(Reminder))) == []


async def test_forgetting_someone_unknown_lists_who_is_known(session, user):
    await storage.save_person(session, user.id, "Mom", today=TODAY)

    with pytest.raises(PersonNotFoundError, match="Known people: Mom"):
        await storage.forget_person(session, user.id, "Dad")


async def test_people_are_private_to_their_owner(session, user, other_user):
    await storage.save_person(session, user.id, "Mom", today=TODAY)

    assert await storage.list_people(session, other_user.id, today=TODAY) == []
    assert [
        p.name for p in await storage.list_people(session, user.id, today=TODAY)
    ] == ["Mom"]


async def test_two_users_can_save_the_same_name(session, user, other_user):
    await storage.save_person(session, user.id, "Mom", today=TODAY, relation="mine")
    await storage.save_person(
        session, other_user.id, "Mom", today=TODAY, relation="theirs"
    )

    mine = await storage.list_people(session, user.id, today=TODAY)
    theirs = await storage.list_people(session, other_user.id, today=TODAY)

    assert [p.relation for p in mine] == ["mine"]
    assert [p.relation for p in theirs] == ["theirs"]


async def test_forgetting_never_touches_another_users_person(session, user, other_user):
    await storage.save_person(session, user.id, "Mom", today=TODAY)

    with pytest.raises(PersonNotFoundError, match="nobody yet"):
        await storage.forget_person(session, other_user.id, "Mom")

    assert len(await storage.list_people(session, user.id, today=TODAY)) == 1

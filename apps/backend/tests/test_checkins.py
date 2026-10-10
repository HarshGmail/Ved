import os
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from ved_db import Conversation, ConversationMessage, Person, Reminder

from ved_backend.checkins import CHECK_IN_AUTHOR, draft_check_in
from ved_backend.llm.base import AssistantMessage, UserMessage
from ved_backend.memory import ConversationStore
from ved_backend.push import DeliveryReport, Notification
from ved_backend.scheduler import ReminderScheduler

ZONE = ZoneInfo("Asia/Kolkata")
NOTICE_DAYS = 15

requires_database = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


class RecordingPush:
    def __init__(self, sent: int = 1) -> None:
        self.configured = True
        self.sent: list[Notification] = []
        self._sent_count = sent

    async def send(self, notification: Notification) -> DeliveryReport:
        self.sent.append(notification)
        return DeliveryReport(sent=self._sent_count, expired=0)


def mom(year: int | None = 1965) -> Person:
    return Person(
        name="Mom",
        birth_month=10,
        birth_day=25,
        birth_year=year,
        birthday_notice_days=NOTICE_DAYS,
    )


def scheduler_for(session_factory, push) -> ReminderScheduler:
    return ReminderScheduler(
        session_factory,
        push,
        timezone="Asia/Kolkata",
        poll_seconds=30.0,
        birthday_reminder_time=time(23, 59),
    )


def today() -> date:
    return datetime.now(ZONE).date()


async def add_due_birthday_reminder(session_factory, *, lead_days: int) -> Person:
    birthday_on = today() + timedelta(days=lead_days)
    person = Person(
        name="Mom",
        birth_month=birthday_on.month,
        birth_day=birthday_on.day,
        birth_year=1965,
        birthday_notice_days=NOTICE_DAYS,
    )
    async with session_factory() as session:
        session.add(person)
        await session.flush()
        session.add(
            Reminder(
                text="Mom's birthday",
                due_at=datetime.now(UTC) - timedelta(minutes=1),
                person_id=person.id,
                birthday_on=birthday_on,
                lead_days=lead_days,
            )
        )
        await session.commit()
    return person


EARLY_NOTICE = Reminder.lead_days == NOTICE_DAYS


async def conversation_count(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(Conversation))


def test_the_opening_names_the_day_and_the_age():
    draft = draft_check_in(mom(), date(2026, 10, 25), today=date(2026, 10, 10))

    assert draft.opening == (
        "Mom's birthday is in 15 days (Sun 25 Oct) — turning 61. "
        "Any plans? I can set reminders to buy a gift or book something."
    )
    assert draft.title == "Mom's birthday — 25 Oct"


def test_the_opening_skips_an_unknown_age():
    draft = draft_check_in(mom(year=None), date(2026, 10, 25), today=date(2026, 10, 10))

    assert draft.opening.startswith("Mom's birthday is in 15 days (Sun 25 Oct). ")


def test_a_day_before_reads_as_tomorrow():
    draft = draft_check_in(mom(), date(2026, 10, 25), today=date(2026, 10, 24))

    assert draft.opening.startswith("Mom's birthday is tomorrow (Sun 25 Oct)")


def test_no_check_in_once_the_day_has_come():
    assert draft_check_in(mom(), date(2026, 10, 25), today=date(2026, 10, 25)) is None


@requires_database
async def test_an_early_notice_opens_a_conversation(session_factory):
    await add_due_birthday_reminder(session_factory, lead_days=NOTICE_DAYS)
    push = RecordingPush()

    assert await scheduler_for(session_factory, push).tick() == 1

    async with session_factory() as session:
        reminder = await session.scalar(select(Reminder).where(EARLY_NOTICE))
        conversation = await session.get(Conversation, reminder.conversation_id)
        messages = list(
            await session.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == conversation.id
                )
            )
        )

    assert conversation.title.startswith("Mom's birthday — ")
    assert [(m.role, m.model) for m in messages] == [("assistant", CHECK_IN_AUTHOR)]
    assert messages[0].text.startswith(f"Mom's birthday is in {NOTICE_DAYS} days")
    assert push.sent[0].body == messages[0].text
    assert push.sent[0].url == f"/?c={conversation.id}"
    assert push.sent[0].tag == "birthday"


@requires_database
async def test_on_the_day_stays_a_plain_push(session_factory):
    await add_due_birthday_reminder(session_factory, lead_days=0)
    push = RecordingPush()

    await scheduler_for(session_factory, push).tick()

    assert await conversation_count(session_factory) == 0
    assert push.sent[0].url == "/"
    assert push.sent[0].body == "Mom's birthday"


@requires_database
async def test_ticking_again_does_not_open_another(session_factory):
    await add_due_birthday_reminder(session_factory, lead_days=NOTICE_DAYS)
    push = RecordingPush()
    scheduler = scheduler_for(session_factory, push)

    for _ in range(3):
        await scheduler.tick()

    assert await conversation_count(session_factory) == 1
    assert len(push.sent) == 1


@requires_database
async def test_a_push_retry_reuses_the_same_conversation(session_factory):
    await add_due_birthday_reminder(session_factory, lead_days=NOTICE_DAYS)
    unreachable = RecordingPush(sent=0)
    await scheduler_for(session_factory, unreachable).tick()

    async with session_factory() as session:
        released = await session.scalar(select(Reminder).where(EARLY_NOTICE))
    assert released.notified_at is None, "should be released for another attempt"

    reachable = RecordingPush()
    await scheduler_for(session_factory, reachable).tick()

    assert await conversation_count(session_factory) == 1
    assert reachable.sent[0].url == unreachable.sent[0].url
    assert reachable.sent[0].body == unreachable.sent[0].body


@requires_database
async def test_one_check_in_per_birthday_even_with_two_early_notices(
    session_factory,
):
    person = await add_due_birthday_reminder(session_factory, lead_days=NOTICE_DAYS)
    async with session_factory() as session:
        session.add(
            Reminder(
                text="Mom's birthday",
                due_at=datetime.now(UTC) - timedelta(minutes=1),
                person_id=person.id,
                birthday_on=today() + timedelta(days=NOTICE_DAYS),
                lead_days=NOTICE_DAYS - 5,
            )
        )
        await session.commit()
    push = RecordingPush()

    await scheduler_for(session_factory, push).tick()

    assert await conversation_count(session_factory) == 1
    assert sorted(n.url == "/" for n in push.sent) == [False, True]


@requires_database
async def test_a_check_in_replays_with_ved_speaking_first(session_factory):
    await add_due_birthday_reminder(session_factory, lead_days=NOTICE_DAYS)
    await scheduler_for(session_factory, RecordingPush()).tick()
    async with session_factory() as session:
        conversation_id = await session.scalar(
            select(Reminder.conversation_id).where(EARLY_NOTICE)
        )

    store = ConversationStore(session_factory, history_limit=20)
    await store.record_turn(
        conversation_id,
        prompt="remind me to order a cake a week before",
        answer="Done.",
        model="test-model",
        tool_calls=[],
    )

    history = await store.history(conversation_id)
    transcript = await store.transcript(conversation_id)

    assert [type(m) for m in history] == [
        AssistantMessage,
        UserMessage,
        AssistantMessage,
    ]
    assert history[0].text.startswith("Mom's birthday is in")
    assert [m.role for m in transcript.messages] == ["assistant", "user", "assistant"]
    assert transcript.messages[0].tool_calls == []

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import Conversation, ConversationMessage, Person, Reminder

from ved_backend.birthdays import ON_THE_DAY

CHECK_IN_AUTHOR = "ved-check-in"
CHECK_IN_INVITATION = "Any plans? I can set reminders to buy a gift or book something."
CONVERSATION_URL_TEMPLATE = "/?c={conversation_id}"
TOMORROW = 1


@dataclass(frozen=True)
class CheckInDraft:
    title: str
    opening: str


@dataclass(frozen=True)
class CheckIn:
    conversation_id: uuid.UUID
    opening: str

    @property
    def url(self) -> str:
        return CONVERSATION_URL_TEMPLATE.format(conversation_id=self.conversation_id)


def is_early_birthday_notice(reminder: Reminder) -> bool:
    return reminder.person_id is not None and reminder.lead_days != ON_THE_DAY


def _when(days_left: int, birthday_on: date) -> str:
    weekday_and_date = birthday_on.strftime("%a %-d %b")
    if days_left == TOMORROW:
        return f"tomorrow ({weekday_and_date})"
    return f"in {days_left} days ({weekday_and_date})"


def draft_check_in(
    person: Person, birthday_on: date, today: date
) -> CheckInDraft | None:
    days_left = (birthday_on - today).days
    if days_left < TOMORROW:
        return None

    opening = f"{person.name}'s birthday is {_when(days_left, birthday_on)}"
    age = person.age_on(birthday_on)
    if age is not None:
        opening += f" — turning {age}"
    return CheckInDraft(
        title=f"{person.name}'s birthday — {birthday_on.strftime('%-d %b')}",
        opening=f"{opening}. {CHECK_IN_INVITATION}",
    )


async def _opening_of(session: AsyncSession, conversation_id: uuid.UUID) -> str | None:
    return await session.scalar(
        select(ConversationMessage.text)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.sequence)
        .limit(1)
    )


async def _checked_in_elsewhere(session: AsyncSession, reminder: Reminder) -> bool:
    other = await session.scalar(
        select(Reminder.id)
        .where(
            Reminder.person_id == reminder.person_id,
            Reminder.birthday_on == reminder.birthday_on,
            Reminder.conversation_id.is_not(None),
            Reminder.id != reminder.id,
        )
        .limit(1)
    )
    return other is not None


async def _resume(session: AsyncSession, reminder: Reminder) -> CheckIn | None:
    opening = await _opening_of(session, reminder.conversation_id)
    if opening is None:
        return None
    return CheckIn(conversation_id=reminder.conversation_id, opening=opening)


async def open_check_in(
    session: AsyncSession, reminder: Reminder, *, today: date
) -> CheckIn | None:
    if reminder.conversation_id is not None:
        return await _resume(session, reminder)
    if await _checked_in_elsewhere(session, reminder):
        return None

    person = await session.get(Person, reminder.person_id)
    if person is None or reminder.birthday_on is None:
        return None
    draft = draft_check_in(person, reminder.birthday_on, today)
    if draft is None:
        return None

    conversation = Conversation(title=draft.title)
    conversation.messages.append(
        ConversationMessage(role="assistant", text=draft.opening, model=CHECK_IN_AUTHOR)
    )
    session.add(conversation)
    await session.flush()
    reminder.conversation_id = conversation.id
    return CheckIn(conversation_id=conversation.id, opening=draft.opening)

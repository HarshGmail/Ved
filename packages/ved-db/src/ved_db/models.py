import calendar
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Sequence,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MessageRole = Literal["user", "assistant"]

CONVERSATION_MESSAGE_SEQUENCE = Sequence("conversation_messages_sequence_seq")

EMBEDDING_DIMENSIONS = 768
HNSW_GRAPH_DEGREE = 16
HNSW_BUILD_CANDIDATES = 64

LEAP_DAY = (2, 29)
LEAP_DAY_FALLBACK = 28


def birthday_in(year: int, month: int, day: int) -> date:
    if (month, day) == LEAP_DAY and not calendar.isleap(year):
        return date(year, month, LEAP_DAY_FALLBACK)
    return date(year, month, day)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        Index("uq_people_name_lower", text("lower(name)"), unique=True),
        CheckConstraint(
            "(birth_month IS NULL) = (birth_day IS NULL)",
            name="ck_people_birthday_month_and_day_together",
        ),
        CheckConstraint(
            "birth_month BETWEEN 1 AND 12", name="ck_people_birth_month_range"
        ),
        CheckConstraint("birth_day BETWEEN 1 AND 31", name="ck_people_birth_day_range"),
        CheckConstraint(
            "birthday_notice_days >= 0", name="ck_people_birthday_notice_days_positive"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200))
    relation: Mapped[str | None] = mapped_column(String(100), default=None)
    birth_month: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    birth_day: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    birthday_notice_days: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def next_birthday(self, on_or_after: date) -> date | None:
        if self.birth_month is None or self.birth_day is None:
            return None
        this_year = birthday_in(on_or_after.year, self.birth_month, self.birth_day)
        if this_year >= on_or_after:
            return this_year
        return birthday_in(on_or_after.year + 1, self.birth_month, self.birth_day)

    def age_on(self, day: date) -> int | None:
        if self.birth_year is None:
            return None
        return day.year - self.birth_year


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "birthday_on",
            "lead_days",
            name="uq_reminders_person_birthday_lead",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    text: Mapped[str] = mapped_column(String(500))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "people.id", ondelete="CASCADE", name="fk_reminders_person_id_people"
        ),
        default=None,
    )
    birthday_on: Mapped[date | None] = mapped_column(Date, default=None)
    lead_days: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    keys: Mapped[dict[str, Any]] = mapped_column(JSONB)
    label: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sequence",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("ix_conversation_messages_thread", "conversation_id", "sequence"),
        Index(
            "ix_conversation_messages_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={
                "m": HNSW_GRAPH_DEGREE,
                "ef_construction": HNSW_BUILD_CANDIDATES,
            },
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(
        BigInteger,
        CONVERSATION_MESSAGE_SEQUENCE,
        server_default=CONVERSATION_MESSAGE_SEQUENCE.next_value(),
    )
    role: Mapped[MessageRole] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

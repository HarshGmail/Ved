import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from ved_db import Conversation, ConversationMessage

from ved_backend.llm.base import AssistantMessage, Message, UserMessage
from ved_backend.schemas import ToolInvocation

TITLE_MAX_LENGTH = 60


class ConversationNotFoundError(LookupError):
    def __init__(self, conversation_id: uuid.UUID) -> None:
        super().__init__(f"No conversation with id {conversation_id}")
        self.conversation_id = conversation_id


def summarise_title(prompt: str) -> str:
    collapsed = " ".join(prompt.split())
    if len(collapsed) <= TITLE_MAX_LENGTH:
        return collapsed
    return collapsed[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def to_llm_messages(rows: Sequence[ConversationMessage]) -> list[Message]:
    messages: list[Message] = []
    for row in rows:
        if row.role == "user":
            messages.append(UserMessage(text=row.text))
        else:
            messages.append(AssistantMessage(text=row.text))
    return messages


class ConversationStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        history_limit: int,
    ) -> None:
        self._session_factory = session_factory
        self._history_limit = history_limit

    async def history(self, conversation_id: uuid.UUID) -> list[Message]:
        async with self._session_factory() as session:
            await self._require(session, conversation_id)
            recent = await session.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at.desc())
                .limit(self._history_limit)
            )
            return to_llm_messages(list(reversed(recent.all())))

    async def start(self, prompt: str) -> uuid.UUID:
        async with self._session_factory() as session:
            conversation = Conversation(title=summarise_title(prompt))
            session.add(conversation)
            await session.commit()
            return conversation.id

    async def record_turn(
        self,
        conversation_id: uuid.UUID,
        *,
        prompt: str,
        answer: str,
        model: str,
        tool_calls: Sequence[ToolInvocation],
    ) -> None:
        async with self._session_factory() as session:
            conversation = await self._require(session, conversation_id)
            session.add(
                ConversationMessage(
                    conversation_id=conversation_id, role="user", text=prompt
                )
            )
            session.add(
                ConversationMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    text=answer,
                    model=model,
                    tool_calls=[call.model_dump() for call in tool_calls],
                )
            )
            conversation.last_message_at = func.now()
            await session.commit()

    async def recent_conversations(self, limit: int) -> list[Conversation]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(Conversation)
                .order_by(Conversation.last_message_at.desc())
                .limit(limit)
            )
            return list(rows.all())

    async def transcript(self, conversation_id: uuid.UUID) -> Conversation:
        async with self._session_factory() as session:
            conversation = await session.scalar(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .options(selectinload(Conversation.messages))
            )
            if conversation is None:
                raise ConversationNotFoundError(conversation_id)
            return conversation

    async def _require(
        self, session: AsyncSession, conversation_id: uuid.UUID
    ) -> Conversation:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

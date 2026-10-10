from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import Conversation, ConversationMessage

DISTANCE_TO_SIMILARITY = 1.0


class MemoryHit(BaseModel):
    conversation_title: str | None = Field(
        description="Title of the conversation the message came from"
    )
    role: str = Field(description="Who said it: user or assistant")
    text: str = Field(description="What was said")
    created_at: datetime = Field(description="When it was said")
    similarity: float = Field(
        description="Cosine similarity to the query, 1.0 is identical"
    )


class MemorySearchResult(BaseModel):
    hits: list[MemoryHit] = Field(description="Best match first")


async def search_messages(
    session: AsyncSession, query_vector: list[float], *, limit: int
) -> list[MemoryHit]:
    distance = ConversationMessage.embedding.cosine_distance(query_vector)
    rows = await session.execute(
        select(ConversationMessage, Conversation.title, distance)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(ConversationMessage.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return [
        MemoryHit(
            conversation_title=title,
            role=message.role,
            text=message.text,
            created_at=message.created_at,
            similarity=DISTANCE_TO_SIMILARITY - cosine_distance,
        )
        for message, title, cosine_distance in rows
    ]

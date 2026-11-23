import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import PrivateNote


class SavedPrivateNote(BaseModel):
    id: str = Field(description="Id of the saved note")
    text: str = Field(description="What was saved")


class PrivateNoteEntry(BaseModel):
    text: str = Field(description="What the note says")
    created_at: datetime = Field(description="When it was saved")


class PrivateNotesResult(BaseModel):
    notes: list[PrivateNoteEntry] = Field(description="Newest first")


async def save_note(
    session: AsyncSession, user_id: uuid.UUID, text: str
) -> PrivateNote:
    note = PrivateNote(user_id=user_id, text=text)
    session.add(note)
    await session.commit()
    return note


async def recent_notes(
    session: AsyncSession, user_id: uuid.UUID, query: str, *, limit: int
) -> list[PrivateNoteEntry]:
    statement = (
        select(PrivateNote)
        .where(PrivateNote.user_id == user_id)
        .order_by(PrivateNote.created_at.desc(), PrivateNote.id)
        .limit(limit)
    )
    if query:
        statement = statement.where(PrivateNote.text.icontains(query, autoescape=True))
    rows = await session.scalars(statement)
    return [
        PrivateNoteEntry(text=note.text, created_at=note.created_at) for note in rows
    ]

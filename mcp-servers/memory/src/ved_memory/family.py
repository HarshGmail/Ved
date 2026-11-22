import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ved_db import FamilyNote, User

UNKNOWN_AUTHOR = "Someone"


class SavedFamilyNote(BaseModel):
    id: str = Field(description="Id of the saved note")
    text: str = Field(description="What was saved")


class FamilyNoteEntry(BaseModel):
    text: str = Field(description="What the note says")
    author: str = Field(description="Who told Ved, by name")
    created_at: datetime = Field(description="When it was saved")


class FamilyNotesResult(BaseModel):
    notes: list[FamilyNoteEntry] = Field(description="Newest first")


async def save_note(session: AsyncSession, user_id: uuid.UUID, text: str) -> FamilyNote:
    note = FamilyNote(text=text, author_user_id=user_id)
    session.add(note)
    await session.commit()
    return note


async def recent_notes(
    session: AsyncSession, query: str, *, limit: int
) -> list[FamilyNoteEntry]:
    statement = (
        select(FamilyNote, User.name)
        .outerjoin(User, User.id == FamilyNote.author_user_id)
        .order_by(FamilyNote.created_at.desc(), FamilyNote.id)
        .limit(limit)
    )
    if query:
        statement = statement.where(FamilyNote.text.icontains(query, autoescape=True))
    rows = await session.execute(statement)
    return [
        FamilyNoteEntry(
            text=note.text,
            author=author_name or UNKNOWN_AUTHOR,
            created_at=note.created_at,
        )
        for note, author_name in rows
    ]

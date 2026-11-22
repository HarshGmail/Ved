import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import FamilyNote, User

FAMILY_NOTES_LIMIT = 100


class FamilyNoteNotFoundError(LookupError):
    pass


class NotNoteAuthorError(PermissionError):
    pass


@dataclass(frozen=True)
class NoteEntry:
    id: uuid.UUID
    text: str
    author_user_id: uuid.UUID | None
    author_name: str | None
    created_at: datetime


class FamilyNoteStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def recent(self) -> list[NoteEntry]:
        async with self._session_factory() as session:
            rows = await session.execute(
                select(FamilyNote, User.name)
                .outerjoin(User, User.id == FamilyNote.author_user_id)
                .order_by(FamilyNote.created_at.desc(), FamilyNote.id)
                .limit(FAMILY_NOTES_LIMIT)
            )
            return [
                NoteEntry(
                    id=note.id,
                    text=note.text,
                    author_user_id=note.author_user_id,
                    author_name=author_name or None,
                    created_at=note.created_at,
                )
                for note, author_name in rows
            ]

    async def delete(self, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            note = await session.get(FamilyNote, note_id)
            if note is None:
                raise FamilyNoteNotFoundError(note_id)
            if note.author_user_id != user_id:
                raise NotNoteAuthorError(note_id)
            await session.delete(note)
            await session.commit()

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import PrivateNote

PRIVATE_NOTES_LIMIT = 100


class PrivateNoteNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class PrivateNoteEntry:
    id: uuid.UUID
    text: str
    created_at: datetime


class PrivateNoteStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def recent(self, user_id: uuid.UUID) -> list[PrivateNoteEntry]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(PrivateNote)
                .where(PrivateNote.user_id == user_id)
                .order_by(PrivateNote.created_at.desc(), PrivateNote.id)
                .limit(PRIVATE_NOTES_LIMIT)
            )
            return [
                PrivateNoteEntry(id=note.id, text=note.text, created_at=note.created_at)
                for note in rows
            ]

    async def delete(self, user_id: uuid.UUID, note_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            deleted = await session.scalar(
                delete(PrivateNote)
                .where(PrivateNote.id == note_id, PrivateNote.user_id == user_id)
                .returning(PrivateNote.id)
            )
            if deleted is None:
                raise PrivateNoteNotFoundError(note_id)
            await session.commit()

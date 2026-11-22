import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import User

from ved_backend.access import AccessResult, require_access
from ved_backend.config import settings
from ved_backend.family import FamilyPerson

UNKNOWN_NAME_LINE = (
    "You don't know this person's name yet. Ask for it once, early, "
    "and remember it with people.remember."
)


class UserDirectory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create(self, email: str, name: str | None = None) -> User:
        normalised = email.strip().lower()
        async with self._session_factory() as session:
            user = await self._find(session, normalised)
            if user is None:
                await session.execute(
                    insert(User)
                    .values(email=normalised, name=name)
                    .on_conflict_do_nothing(index_elements=[User.email])
                )
                await session.commit()
                user = await self._find(session, normalised)
            if user.name is None and name is not None:
                user.name = name
                await session.commit()
            return user

    async def adopt_name(self, user_id: uuid.UUID, name: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id, or_(User.name.is_(None), User.name == ""))
                .values(name=name)
            )
            await session.commit()

    @staticmethod
    async def _find(session: AsyncSession, email: str) -> User | None:
        return await session.scalar(select(User).where(User.email == email))


@dataclass(frozen=True)
class Speaker:
    line: str
    language: str | None = None


def speaker_label(user: User, person: FamilyPerson | None = None) -> str:
    if person is not None:
        described = f" ({person.relation_phrase})" if person.relation_phrase else ""
        return f"You are talking with {person.name}{described}."
    if user.name:
        return f"You are talking with {user.name}."
    return UNKNOWN_NAME_LINE


def speaker_for(user: User, person: FamilyPerson | None) -> Speaker:
    if person is None:
        return Speaker(line=speaker_label(user))
    return Speaker(line=speaker_label(user, person), language=person.language)


def is_owner(user: User) -> bool:
    return user.email == settings.owner_email


def users_directory(request: Request) -> UserDirectory:
    return request.app.state.users


async def current_user(
    access: Annotated[AccessResult | None, Depends(require_access)],
    directory: Annotated[UserDirectory, Depends(users_directory)],
) -> User:
    if access is None:
        return await directory.get_or_create(settings.owner_email)
    return await directory.get_or_create(access.email, access.name)


CurrentUser = Annotated[User, Depends(current_user)]

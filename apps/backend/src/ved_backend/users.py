from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import User

from ved_backend.access import AccessResult, require_access
from ved_backend.config import settings


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

    @staticmethod
    async def _find(session: AsyncSession, email: str) -> User | None:
        return await session.scalar(select(User).where(User.email == email))


def speaker_label(user: User) -> str:
    return user.name or user.email


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

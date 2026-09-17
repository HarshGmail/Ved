from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from ved_db import Base, create_engine, create_session_factory

from ved_backend.config import settings

__all__ = ["Base", "engine", "get_session", "session_factory"]

engine: AsyncEngine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_pool_max_overflow,
)

session_factory = create_session_factory(engine)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session

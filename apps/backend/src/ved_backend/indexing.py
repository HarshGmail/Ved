import asyncio
import logging
from collections.abc import Sequence
from contextlib import suppress

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import ConversationMessage

from ved_backend.llm.embeddings import Embedder, EmbeddingRequestError

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_BATCHES = 10
MAX_EMBEDDING_INPUT_CHARS = 4000


def embedding_input(row: ConversationMessage) -> str:
    return row.text.strip()[:MAX_EMBEDDING_INPUT_CHARS]


class MessageIndexer:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_batches: int = DEFAULT_MAX_BATCHES,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._batch_size = batch_size
        self._max_batches = max_batches
        self._task: asyncio.Task | None = None

    def trigger(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="message-indexer")

    async def aclose(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        try:
            await self.embed_pending()
        except Exception:
            logger.exception("Embedding pending messages failed")

    async def embed_pending(self) -> int:
        total = 0
        for _ in range(self._max_batches):
            embedded = await self._embed_batch()
            total += embedded
            if embedded < self._batch_size:
                break
        return total

    async def _embed_batch(self) -> int:
        async with self._session_factory() as session:
            rows = await self._claim_unembedded(session)
            if not rows:
                return 0

            try:
                vectors = await self._embedder.embed_documents(
                    [embedding_input(row) for row in rows]
                )
            except EmbeddingRequestError as error:
                logger.warning("Embedding %d messages failed: %s", len(rows), error)
                return 0

            for row, vector in zip(rows, vectors, strict=True):
                row.embedding = vector
            await session.commit()
            return len(rows)

    async def _claim_unembedded(
        self, session: AsyncSession
    ) -> Sequence[ConversationMessage]:
        result = await session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.embedding.is_(None),
                func.length(func.trim(ConversationMessage.text)) > 0,
            )
            .order_by(ConversationMessage.sequence)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        return result.all()

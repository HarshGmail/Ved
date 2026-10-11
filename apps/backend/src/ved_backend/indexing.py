import asyncio
import logging
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import ConversationMessage, Document, DocumentChunk

from ved_backend.chunking import Page, chunk_pages
from ved_backend.documents import stored_path
from ved_backend.extraction import PDF, ExtractionError, extract_pages
from ved_backend.llm.embeddings import Embedder, EmbeddingRequestError

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_BATCHES = 10
MAX_EMBEDDING_INPUT_CHARS = 4000


def embedding_input(row: ConversationMessage) -> str:
    return row.text.strip()[:MAX_EMBEDDING_INPUT_CHARS]


class BackgroundIndexer:
    task_name = "indexer"

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def trigger(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name=self.task_name)

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
            logger.exception("Background pass of %s failed", self.task_name)

    async def embed_pending(self) -> int:
        raise NotImplementedError


class MessageIndexer(BackgroundIndexer):
    task_name = "message-indexer"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_batches: int = DEFAULT_MAX_BATCHES,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._embedder = embedder
        self._batch_size = batch_size
        self._max_batches = max_batches

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


DEFAULT_DOCUMENTS_PER_PASS = 4
MISSING_ORIGINAL = "The uploaded file is missing from the documents folder."


class DocumentIndexer(BackgroundIndexer):
    task_name = "document-indexer"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        directory: Path,
        embedder: Embedder | None,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_batches: int = DEFAULT_MAX_BATCHES,
        documents_per_pass: int = DEFAULT_DOCUMENTS_PER_PASS,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._directory = directory
        self._embedder = embedder
        self._batch_size = batch_size
        self._max_batches = max_batches
        self._documents_per_pass = documents_per_pass

    async def embed_pending(self) -> int:
        await self.chunk_pending()
        if self._embedder is None:
            return 0
        total = 0
        for _ in range(self._max_batches):
            embedded = await self._embed_batch(self._embedder)
            total += embedded
            if embedded < self._batch_size:
                break
        await self._mark_fully_embedded()
        return total

    async def chunk_pending(self) -> int:
        async with self._session_factory() as session:
            documents = await self._claim_unchunked(session)
            for document in documents:
                await self._chunk(session, document)
            await session.commit()
            return len(documents)

    async def _chunk(self, session: AsyncSession, document: Document) -> None:
        path = stored_path(self._directory, document.sha256)
        if not path.is_file():
            mark_failed(document, MISSING_ORIGINAL)
            return
        try:
            pages = await asyncio.to_thread(extract_pages, path, document.media_type)
        except ExtractionError as error:
            mark_failed(document, str(error))
            return

        document.page_count = page_count(document.media_type, pages)
        for chunk in chunk_pages(pages):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    page_number=chunk.page_number,
                )
            )

    async def _claim_unchunked(self, session: AsyncSession) -> Sequence[Document]:
        has_chunks = exists().where(DocumentChunk.document_id == Document.id)
        result = await session.scalars(
            select(Document)
            .where(Document.status == "pending", ~has_chunks)
            .order_by(Document.created_at)
            .limit(self._documents_per_pass)
            .with_for_update(skip_locked=True)
        )
        return result.all()

    async def _embed_batch(self, embedder: Embedder) -> int:
        async with self._session_factory() as session:
            result = await session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.embedding.is_(None))
                .order_by(DocumentChunk.document_id, DocumentChunk.ordinal)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            chunks = result.all()
            if not chunks:
                return 0

            try:
                vectors = await embedder.embed_documents(
                    [chunk.text for chunk in chunks]
                )
            except EmbeddingRequestError as error:
                logger.warning(
                    "Embedding %d document chunks failed: %s", len(chunks), error
                )
                return 0

            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = vector
            await session.commit()
            return len(chunks)

    async def _mark_fully_embedded(self) -> None:
        has_chunks = exists().where(DocumentChunk.document_id == Document.id)
        has_unembedded = exists().where(
            DocumentChunk.document_id == Document.id,
            DocumentChunk.embedding.is_(None),
        )
        async with self._session_factory() as session:
            await session.execute(
                update(Document)
                .where(Document.status == "pending", has_chunks, ~has_unembedded)
                .values(status="indexed", error=None)
            )
            await session.commit()


def mark_failed(document: Document, reason: str) -> None:
    document.status = "failed"
    document.error = reason


def page_count(media_type: str, pages: Sequence[Page]) -> int | None:
    return len(pages) if media_type == PDF else None

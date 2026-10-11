import os
import tempfile
import uuid
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ved_db import Document

from ved_backend.extraction import sniff_media_type
from ved_backend.uploads import receive_file

UPLOAD_TEMP_PREFIX = ".upload-"


class DocumentNotFoundError(LookupError):
    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(f"No document with id {document_id}")
        self.document_id = document_id


@dataclass(frozen=True)
class StoredUpload:
    document: Document
    created: bool


def stored_path(directory: Path, sha256: str) -> Path:
    return directory / sha256


class DocumentLibrary:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        directory: Path,
        *,
        max_upload_bytes: int,
    ) -> None:
        self._session_factory = session_factory
        self._directory = directory
        self._max_upload_bytes = max_upload_bytes

    @property
    def directory(self) -> Path:
        return self._directory

    def path_for(self, document: Document) -> Path:
        return stored_path(self._directory, document.sha256)

    async def upload(
        self, body: AsyncIterable[bytes], content_type: str | None
    ) -> StoredUpload:
        self._directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=self._directory, prefix=UPLOAD_TEMP_PREFIX, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            try:
                received = await receive_file(
                    body,
                    content_type,
                    temporary,
                    max_bytes=self._max_upload_bytes,
                )
                media_type = sniff_media_type(received.head, received.filename)
            except BaseException:
                temporary.close()
                temporary_path.unlink(missing_ok=True)
                raise

        existing = await self._find_by_hash(received.sha256)
        if existing is not None:
            temporary_path.unlink(missing_ok=True)
            return StoredUpload(document=existing, created=False)

        os.replace(temporary_path, stored_path(self._directory, received.sha256))
        document = Document(
            filename=received.filename,
            media_type=media_type,
            size_bytes=received.size_bytes,
            sha256=received.sha256,
        )
        async with self._session_factory() as session:
            session.add(document)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raced = await self._find_by_hash(received.sha256)
                if raced is None:
                    raise
                return StoredUpload(document=raced, created=False)
            await session.refresh(document)
        return StoredUpload(document=document, created=True)

    async def list(self) -> Sequence[Document]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(Document).order_by(Document.created_at.desc(), Document.id)
            )
            return rows.all()

    async def get(self, document_id: uuid.UUID) -> Document:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    async def delete(self, document_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                raise DocumentNotFoundError(document_id)
            path = self.path_for(document)
            await session.delete(document)
            await session.commit()
        path.unlink(missing_ok=True)

    async def _find_by_hash(self, sha256: str) -> Document | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(Document).where(Document.sha256 == sha256)
            )

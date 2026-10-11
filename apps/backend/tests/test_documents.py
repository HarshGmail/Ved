import hashlib
import os

import pytest
from sqlalchemy import func, select
from ved_db import EMBEDDING_DIMENSIONS, Document, DocumentChunk

from upload_bodies import CONTENT_TYPE, CountingBody, multipart_body
from ved_backend.documents import (
    UPLOAD_TEMP_PREFIX,
    DocumentLibrary,
    DocumentNotFoundError,
)
from ved_backend.extraction import NO_TEXT_LAYER, PDF, UnsupportedDocumentError
from ved_backend.indexing import MISSING_ORIGINAL, DocumentIndexer
from ved_backend.llm.embeddings import EmbeddingRequestError
from ved_backend.uploads import UploadTooLargeError

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

MAX_UPLOAD_BYTES = 100_000
VECTOR = [0.5] * EMBEDDING_DIMENSIONS
LEASE_PAGES = [
    ["Residential lease between the landlord and the tenant."],
    ["Clause 7. The security deposit is INR 85,000, refundable within 30 days."],
]


class RecordingEmbedder:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts):
        self.calls.append(list(texts))
        if self.failing:
            raise EmbeddingRequestError("model down")
        return [VECTOR for _ in texts]


@pytest.fixture
def library(session_factory, tmp_path):
    return DocumentLibrary(
        session_factory, tmp_path / "documents", max_upload_bytes=MAX_UPLOAD_BYTES
    )


def indexer_for(library, session_factory, embedder):
    return DocumentIndexer(session_factory, library.directory, embedder)


async def upload(library, content: bytes, filename: str = "notes.txt"):
    return await library.upload(
        CountingBody(multipart_body(content, filename=filename)), CONTENT_TYPE
    )


def stored_files(library) -> list[str]:
    return sorted(path.name for path in library.directory.iterdir())


async def chunk_rows(session_factory) -> list[DocumentChunk]:
    async with session_factory() as session:
        rows = await session.scalars(
            select(DocumentChunk).order_by(DocumentChunk.ordinal)
        )
        return list(rows)


async def test_an_upload_is_stored_by_content_hash_and_starts_pending(library):
    content = b"the deposit is fifty thousand"

    stored = await upload(library, content, filename="../../lease.txt")

    assert stored.created
    assert stored.document.status == "pending"
    assert stored.document.filename == "lease.txt"
    assert stored_files(library) == [hashlib.sha256(content).hexdigest()]


async def test_the_user_filename_never_reaches_the_disk(library):
    await upload(library, b"notes", filename="../escape.txt")

    assert not (library.directory.parent / "escape.txt").exists()
    assert "escape.txt" not in stored_files(library)


async def test_uploading_the_same_bytes_again_returns_the_same_document(library):
    first = await upload(library, b"same bytes", filename="a.txt")
    second = await upload(library, b"same bytes", filename="b.txt")

    assert not second.created
    assert second.document.id == first.document.id
    assert len(await library.list()) == 1
    assert len(stored_files(library)) == 1


async def test_a_rejected_type_leaves_nothing_behind(library):
    with pytest.raises(UnsupportedDocumentError):
        await upload(library, b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "a.txt")

    assert stored_files(library) == []
    assert await library.list() == []


async def test_an_oversized_upload_leaves_nothing_behind(library):
    with pytest.raises(UploadTooLargeError):
        await upload(library, b"x" * (MAX_UPLOAD_BYTES + 1))

    assert stored_files(library) == []
    assert not any(
        name.startswith(UPLOAD_TEMP_PREFIX) for name in stored_files(library)
    )


async def test_delete_removes_the_rows_and_the_file(library, session_factory, make_pdf):
    stored = await upload(library, make_pdf(LEASE_PAGES), "lease.pdf")
    await indexer_for(library, session_factory, RecordingEmbedder()).embed_pending()

    await library.delete(stored.document.id)

    assert stored_files(library) == []
    assert await library.list() == []
    assert await chunk_rows(session_factory) == []


async def test_deleting_an_unknown_document_says_so(library):
    stored = await upload(library, b"notes")
    await library.delete(stored.document.id)

    with pytest.raises(DocumentNotFoundError):
        await library.delete(stored.document.id)


async def test_a_pdf_is_chunked_per_page_and_embedded(
    library, session_factory, make_pdf
):
    stored = await upload(library, make_pdf(LEASE_PAGES), "lease.pdf")
    embedder = RecordingEmbedder()

    await indexer_for(library, session_factory, embedder).embed_pending()

    document = await library.get(stored.document.id)
    chunks = await chunk_rows(session_factory)
    assert document.status == "indexed"
    assert document.media_type == PDF
    assert document.page_count == 2
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert "INR 85,000" in chunks[1].text
    assert all(chunk.embedding is not None for chunk in chunks)


async def test_a_scanned_pdf_fails_with_a_clear_message(
    library, session_factory, make_pdf
):
    stored = await upload(library, make_pdf([[], []]), "scan.pdf")

    await indexer_for(library, session_factory, RecordingEmbedder()).embed_pending()

    document = await library.get(stored.document.id)
    assert document.status == "failed"
    assert document.error == NO_TEXT_LAYER
    assert await chunk_rows(session_factory) == []


async def test_a_missing_original_fails_instead_of_retrying_forever(
    library, session_factory
):
    stored = await upload(library, b"notes")
    library.path_for(stored.document).unlink()

    await indexer_for(library, session_factory, RecordingEmbedder()).embed_pending()

    document = await library.get(stored.document.id)
    assert document.status == "failed"
    assert document.error == MISSING_ORIGINAL


async def test_a_failing_embedder_leaves_the_document_pending_until_retried(
    library, session_factory
):
    stored = await upload(library, b"the deposit clause")
    embedder = RecordingEmbedder(failing=True)
    indexer = indexer_for(library, session_factory, embedder)

    await indexer.embed_pending()
    assert (await library.get(stored.document.id)).status == "pending"
    assert len(await chunk_rows(session_factory)) == 1

    embedder.failing = False
    await indexer.embed_pending()

    assert (await library.get(stored.document.id)).status == "indexed"
    assert len(await chunk_rows(session_factory)) == 1


async def test_chunks_are_created_once_even_across_passes(library, session_factory):
    await upload(library, b"the deposit clause")
    indexer = indexer_for(library, session_factory, RecordingEmbedder())

    await indexer.embed_pending()
    await indexer.embed_pending()

    async with session_factory() as session:
        assert await session.scalar(select(func.count(DocumentChunk.id))) == 1


async def test_without_an_embedder_documents_are_chunked_but_stay_pending(
    library, session_factory
):
    stored = await upload(library, b"the deposit clause")

    await indexer_for(library, session_factory, None).embed_pending()

    assert (await library.get(stored.document.id)).status == "pending"
    assert len(await chunk_rows(session_factory)) == 1


async def test_trigger_indexes_in_the_background(library, session_factory):
    stored = await upload(library, b"the deposit clause")
    indexer = indexer_for(library, session_factory, RecordingEmbedder())

    indexer.trigger()
    await indexer._task
    await indexer.aclose()

    assert (await library.get(stored.document.id)).status == "indexed"


async def test_documents_are_listed_newest_first(library, session_factory):
    await upload(library, b"older", "old.txt")
    await upload(library, b"newer", "new.md")

    async with session_factory() as session:
        names = (await session.scalars(select(Document.filename))).all()
    listed = [document.filename for document in await library.list()]

    assert sorted(names) == sorted(listed)
    assert listed[0] == "new.md"

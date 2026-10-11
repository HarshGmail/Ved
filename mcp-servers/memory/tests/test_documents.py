from ved_db import EMBEDDING_DIMENSIONS, Document, DocumentChunk

from ved_memory import documents
from ved_memory.documents import UNTRUSTED_NOTICE, DocumentSearchResult

from .conftest import requires_database

pytestmark = requires_database


def direction(axis: int, weight: float = 1.0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[axis] = weight
    return vector


def blend(first_axis: int, second_axis: int, second_weight: float) -> list[float]:
    vector = direction(first_axis)
    vector[second_axis] = second_weight
    return vector


async def add_document(session, filename, chunks, status="indexed", sha="a"):
    document = Document(
        filename=filename,
        media_type="application/pdf",
        size_bytes=100,
        sha256=sha * 64,
        page_count=len(chunks),
        status=status,
    )
    session.add(document)
    await session.flush()
    document_id = document.id
    for ordinal, (text, page, embedding) in enumerate(chunks):
        session.add(
            DocumentChunk(
                document_id=document_id,
                ordinal=ordinal,
                text=text,
                page_number=page,
                embedding=embedding,
            )
        )
    await session.commit()
    return document_id


async def test_the_closest_passage_comes_first_with_file_and_page(session):
    await add_document(
        session,
        "lease.pdf",
        [
            ("unrelated", 1, direction(2)),
            ("close", 3, blend(0, 1, 0.3)),
            ("deposit clause", 2, direction(0)),
        ],
    )

    passages = await documents.search_passages(session, direction(0), limit=3)

    assert [passage.text for passage in passages] == [
        "deposit clause",
        "close",
        "unrelated",
    ]
    assert passages[0].filename == "lease.pdf"
    assert passages[0].page == 2
    assert passages[0].similarity > passages[1].similarity > passages[2].similarity


async def test_limit_caps_the_passages(session):
    await add_document(
        session, "notes.pdf", [(f"p{axis}", 1, direction(axis)) for axis in range(5)]
    )

    passages = await documents.search_passages(session, direction(0), limit=2)

    assert len(passages) == 2


async def test_passages_without_an_embedding_are_skipped(session):
    await add_document(
        session,
        "notes.pdf",
        [("not yet embedded", 1, None), ("embedded", 1, direction(1))],
        status="pending",
    )

    passages = await documents.search_passages(session, direction(0), limit=5)

    assert [passage.text for passage in passages] == ["embedded"]


async def test_search_spans_every_document(session):
    await add_document(session, "a.pdf", [("from a", 1, direction(1))], sha="a")
    await add_document(session, "b.pdf", [("from b", 4, direction(0))], sha="b")

    passages = await documents.search_passages(session, direction(0), limit=5)

    assert [(passage.filename, passage.page) for passage in passages] == [
        ("b.pdf", 4),
        ("a.pdf", 1),
    ]


async def test_list_counts_passages_and_shows_failures(session):
    await add_document(
        session, "lease.pdf", [("one", 1, None), ("two", 2, None)], sha="a"
    )
    await add_document(session, "scan.pdf", [], status="failed", sha="b")

    entries = await documents.list_documents(session, limit=10)

    by_name = {entry.filename: entry for entry in entries}
    assert by_name["lease.pdf"].passages == 2
    assert by_name["scan.pdf"].status == "failed"
    assert by_name["scan.pdf"].passages == 0


def test_search_results_are_marked_untrusted():
    result = DocumentSearchResult(passages=[])

    assert result.untrusted is True
    assert result.notice == UNTRUSTED_NOTICE

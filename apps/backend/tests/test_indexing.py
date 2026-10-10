import os
import uuid

import pytest
from sqlalchemy import select
from ved_db import EMBEDDING_DIMENSIONS, Conversation, ConversationMessage

from ved_backend.indexing import MessageIndexer
from ved_backend.llm.embeddings import EmbeddingRequestError

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

VECTOR = [0.5] * EMBEDDING_DIMENSIONS


class RecordingEmbedder:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts):
        self.calls.append(list(texts))
        if self.failing:
            raise EmbeddingRequestError("model down")
        return [VECTOR for _ in texts]


async def add_messages(session_factory, texts: list[str]) -> uuid.UUID:
    async with session_factory() as session:
        conversation = Conversation(title="thread")
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.id
        for text in texts:
            session.add(
                ConversationMessage(
                    conversation_id=conversation_id, role="user", text=text
                )
            )
        await session.commit()
    return conversation_id


async def embedded_texts(session_factory) -> list[str]:
    async with session_factory() as session:
        rows = await session.scalars(
            select(ConversationMessage.text).where(
                ConversationMessage.embedding.is_not(None)
            )
        )
        return sorted(rows)


async def test_pending_messages_are_embedded(session_factory):
    await add_messages(session_factory, ["first", "second"])
    embedder = RecordingEmbedder()

    embedded = await MessageIndexer(session_factory, embedder).embed_pending()

    assert embedded == 2
    assert await embedded_texts(session_factory) == ["first", "second"]


async def test_already_embedded_messages_are_left_alone(session_factory):
    await add_messages(session_factory, ["first"])
    embedder = RecordingEmbedder()
    indexer = MessageIndexer(session_factory, embedder)
    await indexer.embed_pending()

    assert await indexer.embed_pending() == 0
    assert len(embedder.calls) == 1


async def test_work_is_done_in_batches(session_factory):
    await add_messages(session_factory, [f"message {n}" for n in range(5)])
    embedder = RecordingEmbedder()

    embedded = await MessageIndexer(
        session_factory, embedder, batch_size=2
    ).embed_pending()

    assert embedded == 5
    assert [len(call) for call in embedder.calls] == [2, 2, 1]


async def test_max_batches_bounds_one_pass(session_factory):
    await add_messages(session_factory, [f"message {n}" for n in range(5)])
    indexer = MessageIndexer(
        session_factory, RecordingEmbedder(), batch_size=2, max_batches=2
    )

    assert await indexer.embed_pending() == 4
    assert await indexer.embed_pending() == 1


async def test_a_failing_model_leaves_messages_for_the_next_pass(session_factory):
    await add_messages(session_factory, ["first"])
    embedder = RecordingEmbedder(failing=True)
    indexer = MessageIndexer(session_factory, embedder)

    assert await indexer.embed_pending() == 0
    assert await embedded_texts(session_factory) == []

    embedder.failing = False
    assert await indexer.embed_pending() == 1
    assert await embedded_texts(session_factory) == ["first"]


async def test_blank_messages_are_never_sent_to_the_model(session_factory):
    await add_messages(session_factory, ["   ", "real"])
    embedder = RecordingEmbedder()

    await MessageIndexer(session_factory, embedder).embed_pending()

    assert embedder.calls == [["real"]]


async def test_long_messages_are_truncated(session_factory):
    await add_messages(session_factory, ["x" * 10_000])
    embedder = RecordingEmbedder()

    await MessageIndexer(session_factory, embedder).embed_pending()

    assert len(embedder.calls[0][0]) < 10_000


async def test_trigger_embeds_in_the_background(session_factory):
    await add_messages(session_factory, ["first"])
    indexer = MessageIndexer(session_factory, RecordingEmbedder())

    indexer.trigger()
    await indexer._task
    await indexer.aclose()

    assert await embedded_texts(session_factory) == ["first"]


async def test_a_crashing_background_pass_does_not_raise(session_factory):
    class ExplodingEmbedder:
        async def embed_documents(self, texts):
            raise RuntimeError("boom")

    await add_messages(session_factory, ["first"])
    indexer = MessageIndexer(session_factory, ExplodingEmbedder())

    indexer.trigger()
    await indexer._task
    await indexer.aclose()

from ved_db import EMBEDDING_DIMENSIONS, Conversation, ConversationMessage

from ved_memory import storage

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


async def add_message(session, conversation_id, text, embedding, role="user"):
    session.add(
        ConversationMessage(
            conversation_id=conversation_id, role=role, text=text, embedding=embedding
        )
    )
    await session.commit()


async def new_conversation(session, title):
    conversation = Conversation(title=title)
    session.add(conversation)
    await session.flush()
    conversation_id = conversation.id
    await session.commit()
    return conversation_id


async def test_the_closest_message_comes_first(session):
    thread = await new_conversation(session, "Home lab")
    await add_message(session, thread, "unrelated", direction(2))
    await add_message(session, thread, "close", blend(0, 1, 0.3))
    await add_message(session, thread, "exact", direction(0))

    hits = await storage.search_messages(session, direction(0), limit=3)

    assert [hit.text for hit in hits] == ["exact", "close", "unrelated"]
    assert hits[0].similarity > hits[1].similarity > hits[2].similarity


async def test_similarity_is_one_for_an_identical_vector(session):
    thread = await new_conversation(session, "Home lab")
    await add_message(session, thread, "exact", direction(0))

    hits = await storage.search_messages(session, direction(0), limit=1)

    assert round(hits[0].similarity, 6) == 1.0


async def test_limit_caps_the_results(session):
    thread = await new_conversation(session, "Home lab")
    for axis in range(4):
        await add_message(session, thread, f"message {axis}", direction(axis))

    hits = await storage.search_messages(session, direction(0), limit=2)

    assert len(hits) == 2


async def test_messages_without_an_embedding_are_skipped(session):
    thread = await new_conversation(session, "Home lab")
    await add_message(session, thread, "not yet embedded", None)
    await add_message(session, thread, "embedded", direction(1))

    hits = await storage.search_messages(session, direction(0), limit=5)

    assert [hit.text for hit in hits] == ["embedded"]


async def test_hits_carry_title_role_and_time(session):
    thread = await new_conversation(session, "Home lab")
    await add_message(
        session, thread, "I will run it on an N100", direction(0), role="assistant"
    )

    hit = (await storage.search_messages(session, direction(0), limit=1))[0]

    assert hit.conversation_title == "Home lab"
    assert hit.role == "assistant"
    assert hit.created_at is not None

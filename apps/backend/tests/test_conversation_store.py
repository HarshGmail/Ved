import os
import uuid

import pytest
from sqlalchemy import text

from ved_backend.llm.base import AssistantMessage, UserMessage
from ved_backend.memory import ConversationNotFoundError, ConversationStore
from ved_backend.schemas import ToolInvocation

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

CREATE_CALL = ToolInvocation(
    name="reminders.create", arguments={"text": "call Mom"}, failed=False
)


@pytest.fixture
def store(session_factory):
    return ConversationStore(session_factory, history_limit=20)


async def test_a_new_conversation_starts_empty(store):
    conversation_id = await store.start("remind me at 8 PM")

    assert await store.history(conversation_id) == []


async def test_the_first_prompt_becomes_the_title(store):
    conversation_id = await store.start("remind me at 8 PM to call Mom")

    transcript = await store.transcript(conversation_id)

    assert transcript.title == "remind me at 8 PM to call Mom"


async def test_a_recorded_turn_comes_back_as_history(store):
    conversation_id = await store.start("remind me at 8 PM")
    await store.record_turn(
        conversation_id,
        prompt="remind me at 8 PM",
        answer="Reminder set.",
        model="test-model",
        tool_calls=[CREATE_CALL],
    )

    history = await store.history(conversation_id)

    assert [type(m) for m in history] == [UserMessage, AssistantMessage]
    assert history[0].text == "remind me at 8 PM"
    assert history[1].text == "Reminder set."


async def test_history_is_oldest_first(store):
    conversation_id = await store.start("first")
    for index in range(3):
        await store.record_turn(
            conversation_id,
            prompt=f"prompt {index}",
            answer=f"answer {index}",
            model="test-model",
            tool_calls=[],
        )

    history = await store.history(conversation_id)

    assert [m.text for m in history] == [
        "prompt 0",
        "answer 0",
        "prompt 1",
        "answer 1",
        "prompt 2",
        "answer 2",
    ]


async def test_history_keeps_only_the_most_recent_messages(session_factory):
    store = ConversationStore(session_factory, history_limit=4)
    conversation_id = await store.start("first")
    for index in range(5):
        await store.record_turn(
            conversation_id,
            prompt=f"prompt {index}",
            answer=f"answer {index}",
            model="test-model",
            tool_calls=[],
        )

    history = await store.history(conversation_id)

    assert [m.text for m in history] == [
        "prompt 3",
        "answer 3",
        "prompt 4",
        "answer 4",
    ]


async def test_tool_calls_are_stored_but_never_replayed(store):
    conversation_id = await store.start("remind me")
    await store.record_turn(
        conversation_id,
        prompt="remind me",
        answer="Reminder set.",
        model="test-model",
        tool_calls=[CREATE_CALL],
    )

    transcript = await store.transcript(conversation_id)
    assistant = transcript.messages[1]
    assert assistant.tool_calls == [CREATE_CALL.model_dump()]
    assert assistant.model == "test-model"

    history = await store.history(conversation_id)
    assert history[1].tool_calls == []


async def test_conversations_are_listed_most_recent_first(store):
    older = await store.start("older")
    await store.record_turn(
        older, prompt="older", answer="ok", model="m", tool_calls=[]
    )
    newer = await store.start("newer")
    await store.record_turn(
        newer, prompt="newer", answer="ok", model="m", tool_calls=[]
    )

    listed = await store.recent_conversations(10)

    assert [c.id for c in listed][:2] == [newer, older]


async def test_unknown_conversation_is_reported_not_created(store):
    missing = uuid.uuid4()

    with pytest.raises(ConversationNotFoundError):
        await store.history(missing)

    with pytest.raises(ConversationNotFoundError):
        await store.transcript(missing)

    with pytest.raises(ConversationNotFoundError):
        await store.record_turn(
            missing, prompt="p", answer="a", model="m", tool_calls=[]
        )


async def test_conversations_do_not_leak_into_each_other(store):
    first = await store.start("first")
    second = await store.start("second")
    await store.record_turn(
        first, prompt="about dogs", answer="ok", model="m", tool_calls=[]
    )

    assert await store.history(second) == []
    assert len(await store.history(first)) == 2


async def test_history_replays_the_prompt_before_the_answer(session_factory):
    store = ConversationStore(session_factory, history_limit=20)
    conversations = []
    for index in range(30):
        conversation_id = await store.start(f"prompt {index}")
        await store.record_turn(
            conversation_id,
            prompt=f"prompt {index}",
            answer=f"answer {index}",
            model="m",
            tool_calls=[],
        )
        conversations.append(conversation_id)

    async with session_factory() as session:
        await session.execute(text("ANALYZE conversation_messages"))

    for conversation_id in conversations:
        history = await store.history(conversation_id)
        assert [m.role for m in history] == ["user", "assistant"]

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


async def test_a_new_conversation_starts_empty(store, user):
    conversation_id = await store.start(user.id, "remind me at 8 PM")

    assert await store.history(user.id, conversation_id) == []


async def test_the_first_prompt_becomes_the_title(store, user):
    conversation_id = await store.start(user.id, "remind me at 8 PM to call Mom")

    transcript = await store.transcript(user.id, conversation_id)

    assert transcript.title == "remind me at 8 PM to call Mom"


async def test_a_recorded_turn_comes_back_as_history(store, user):
    conversation_id = await store.start(user.id, "remind me at 8 PM")
    await store.record_turn(
        user.id,
        conversation_id,
        prompt="remind me at 8 PM",
        answer="Reminder set.",
        model="test-model",
        tool_calls=[CREATE_CALL],
    )

    history = await store.history(user.id, conversation_id)

    assert [type(m) for m in history] == [UserMessage, AssistantMessage]
    assert history[0].text == "remind me at 8 PM"
    assert history[1].text == "Reminder set."


async def test_history_is_oldest_first(store, user):
    conversation_id = await store.start(user.id, "first")
    for index in range(3):
        await store.record_turn(
            user.id,
            conversation_id,
            prompt=f"prompt {index}",
            answer=f"answer {index}",
            model="test-model",
            tool_calls=[],
        )

    history = await store.history(user.id, conversation_id)

    assert [m.text for m in history] == [
        "prompt 0",
        "answer 0",
        "prompt 1",
        "answer 1",
        "prompt 2",
        "answer 2",
    ]


async def test_history_keeps_only_the_most_recent_messages(session_factory, user):
    store = ConversationStore(session_factory, history_limit=4)
    conversation_id = await store.start(user.id, "first")
    for index in range(5):
        await store.record_turn(
            user.id,
            conversation_id,
            prompt=f"prompt {index}",
            answer=f"answer {index}",
            model="test-model",
            tool_calls=[],
        )

    history = await store.history(user.id, conversation_id)

    assert [m.text for m in history] == [
        "prompt 3",
        "answer 3",
        "prompt 4",
        "answer 4",
    ]


async def test_tool_calls_are_stored_but_never_replayed(store, user):
    conversation_id = await store.start(user.id, "remind me")
    await store.record_turn(
        user.id,
        conversation_id,
        prompt="remind me",
        answer="Reminder set.",
        model="test-model",
        tool_calls=[CREATE_CALL],
    )

    transcript = await store.transcript(user.id, conversation_id)
    assistant = transcript.messages[1]
    assert assistant.tool_calls == [CREATE_CALL.model_dump()]
    assert assistant.model == "test-model"

    history = await store.history(user.id, conversation_id)
    assert history[1].tool_calls == []


async def test_conversations_are_listed_most_recent_first(store, user):
    older = await store.start(user.id, "older")
    await store.record_turn(
        user.id, older, prompt="older", answer="ok", model="m", tool_calls=[]
    )
    newer = await store.start(user.id, "newer")
    await store.record_turn(
        user.id, newer, prompt="newer", answer="ok", model="m", tool_calls=[]
    )

    listed = await store.recent_conversations(user.id, 10)

    assert [c.id for c in listed][:2] == [newer, older]


async def test_unknown_conversation_is_reported_not_created(store, user):
    missing = uuid.uuid4()

    with pytest.raises(ConversationNotFoundError):
        await store.history(user.id, missing)

    with pytest.raises(ConversationNotFoundError):
        await store.transcript(user.id, missing)

    with pytest.raises(ConversationNotFoundError):
        await store.record_turn(
            user.id, missing, prompt="p", answer="a", model="m", tool_calls=[]
        )


async def test_conversations_do_not_leak_into_each_other(store, user):
    first = await store.start(user.id, "first")
    second = await store.start(user.id, "second")
    await store.record_turn(
        user.id, first, prompt="about dogs", answer="ok", model="m", tool_calls=[]
    )

    assert await store.history(user.id, second) == []
    assert len(await store.history(user.id, first)) == 2


async def test_history_replays_the_prompt_before_the_answer(session_factory, user):
    store = ConversationStore(session_factory, history_limit=20)
    conversations = []
    for index in range(30):
        conversation_id = await store.start(user.id, f"prompt {index}")
        await store.record_turn(
            user.id,
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
        history = await store.history(user.id, conversation_id)
        assert [m.role for m in history] == ["user", "assistant"]


async def test_one_users_conversations_are_invisible_to_another(
    store, user, other_user
):
    mine = await store.start(user.id, "my secret plan")
    await store.record_turn(
        user.id, mine, prompt="p", answer="a", model="m", tool_calls=[]
    )
    theirs = await store.start(other_user.id, "their plan")

    my_list = await store.recent_conversations(user.id, 10)
    their_list = await store.recent_conversations(other_user.id, 10)

    assert [c.id for c in my_list] == [mine]
    assert [c.id for c in their_list] == [theirs]


async def test_another_users_conversation_is_not_found_for_every_operation(
    store, user, other_user
):
    mine = await store.start(user.id, "my secret plan")
    await store.record_turn(
        user.id, mine, prompt="p", answer="a", model="m", tool_calls=[]
    )

    with pytest.raises(ConversationNotFoundError):
        await store.history(other_user.id, mine)
    with pytest.raises(ConversationNotFoundError):
        await store.transcript(other_user.id, mine)
    with pytest.raises(ConversationNotFoundError):
        await store.require_owned(other_user.id, mine)
    with pytest.raises(ConversationNotFoundError):
        await store.record_turn(
            other_user.id, mine, prompt="x", answer="y", model="m", tool_calls=[]
        )

    assert len(await store.history(user.id, mine)) == 2

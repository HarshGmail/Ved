import uuid

import pytest

from ved_backend.llm.base import AssistantMessage, UserMessage
from ved_backend.memory import summarise_title, to_llm_messages


class Row:
    def __init__(self, role: str, text: str) -> None:
        self.role = role
        self.text = text


def test_short_prompts_become_the_title_unchanged():
    assert summarise_title("remind me at 8 PM") == "remind me at 8 PM"


def test_titles_collapse_whitespace():
    assert summarise_title("  remind   me\nat 8 PM  ") == "remind me at 8 PM"


def test_long_prompts_are_truncated_with_an_ellipsis():
    title = summarise_title("x" * 200)

    assert len(title) == 60
    assert title.endswith("…")


def test_history_maps_roles_back_to_message_types():
    messages = to_llm_messages(
        [Row("user", "remind me at 8 PM"), Row("assistant", "Reminder set.")]
    )

    assert isinstance(messages[0], UserMessage)
    assert isinstance(messages[1], AssistantMessage)
    assert messages[0].text == "remind me at 8 PM"
    assert messages[1].text == "Reminder set."


def test_replayed_assistant_turns_carry_no_tool_calls():
    messages = to_llm_messages([Row("assistant", "Reminder set.")])

    assert messages[0].tool_calls == []


@pytest.mark.parametrize("empty", [[], ()])
def test_empty_history_maps_to_no_messages(empty):
    assert to_llm_messages(empty) == []


def test_conversation_not_found_names_the_id():
    from ved_backend.memory import ConversationNotFoundError

    missing = uuid.uuid4()
    error = ConversationNotFoundError(missing)

    assert str(missing) in str(error)
    assert error.conversation_id == missing

import json

import httpx2
import pytest

from ved_backend.llm.base import (
    AssistantMessage,
    ToolCall,
    ToolOutcome,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from ved_backend.llm.openai_compatible import (
    LLMRequestError,
    OpenAICompatibleProvider,
    from_wire_message,
    to_wire_messages,
)

CREATE = ToolSpec(
    name="reminders.create",
    description="Create a reminder.",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
)


def test_system_prompt_leads_the_conversation():
    wire = to_wire_messages("be helpful", [UserMessage(text="hi")])

    assert wire[0] == {"role": "system", "content": "be helpful"}
    assert wire[1] == {"role": "user", "content": "hi"}


def test_assistant_tool_calls_serialise_arguments_as_json():
    message = AssistantMessage(
        tool_calls=[
            ToolCall(id="c1", name="reminders.create", arguments={"text": "call Mom"})
        ]
    )

    wire = to_wire_messages("", [message])[1]

    assert wire["role"] == "assistant"
    call = wire["tool_calls"][0]
    assert call["id"] == "c1"
    assert call["function"]["name"] == "reminders.create"
    assert json.loads(call["function"]["arguments"]) == {"text": "call Mom"}


def test_each_tool_outcome_becomes_its_own_message():
    results = ToolResultMessage(
        outcomes=[
            ToolOutcome(call_id="c1", content="first"),
            ToolOutcome(call_id="c2", content="second"),
        ]
    )

    wire = to_wire_messages("", [results])[1:]

    assert [m["role"] for m in wire] == ["tool", "tool"]
    assert [m["tool_call_id"] for m in wire] == ["c1", "c2"]


def test_tool_errors_travel_as_ordinary_content():
    results = ToolResultMessage(
        outcomes=[ToolOutcome(call_id="c1", content="bad offset", is_error=True)]
    )

    wire = to_wire_messages("", [results])[1]

    assert wire["content"] == "bad offset"


def test_plain_reply_parses():
    reply = from_wire_message({"content": "Reminder set."})

    assert reply.text == "Reminder set."
    assert reply.tool_calls == []


def test_tool_call_reply_parses():
    reply = from_wire_message(
        {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "reminders.create",
                        "arguments": '{"text": "call Mom"}',
                    },
                }
            ],
        }
    )

    assert reply.text == ""
    assert reply.tool_calls[0].name == "reminders.create"
    assert reply.tool_calls[0].arguments == {"text": "call Mom"}


def test_malformed_arguments_do_not_crash_the_turn():
    reply = from_wire_message(
        {
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {"name": "reminders.list", "arguments": "{oops"},
                }
            ]
        }
    )

    assert reply.tool_calls[0].arguments == {}


def test_tool_call_without_a_name_is_dropped():
    reply = from_wire_message({"tool_calls": [{"id": "c1", "function": {}}]})

    assert reply.tool_calls == []


def test_missing_call_id_gets_a_positional_one():
    reply = from_wire_message(
        {"tool_calls": [{"function": {"name": "reminders.list", "arguments": "{}"}}]}
    )

    assert reply.tool_calls[0].id == "call-0"


def build_provider(handler, **kwargs) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(
        base_url="http://model.invalid/v1", model="test-model", **kwargs
    )
    provider._client = httpx2.AsyncClient(
        base_url="http://model.invalid/v1",
        transport=httpx2.MockTransport(handler),
    )
    return provider


async def test_tools_are_sent_in_openai_function_shape():
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = build_provider(handler)
    await provider.complete(
        system="s", messages=[UserMessage(text="hi")], tools=[CREATE]
    )

    tool = seen["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "reminders.create"
    assert tool["function"]["parameters"] == CREATE.input_schema


async def test_no_tools_key_when_there_are_no_tools():
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = build_provider(handler)
    await provider.complete(system="s", messages=[UserMessage(text="hi")], tools=[])

    assert "tools" not in seen


async def test_round_trip_returns_a_tool_call():
    def handler(request):
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "function": {
                                        "name": "reminders.create",
                                        "arguments": '{"text":"call Mom"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    provider = build_provider(handler)
    reply = await provider.complete(
        system="s", messages=[UserMessage(text="remind me")], tools=[CREATE]
    )

    assert reply.tool_calls[0].arguments == {"text": "call Mom"}


async def test_unreachable_model_raises_llm_request_error():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    provider = build_provider(handler)

    with pytest.raises(LLMRequestError, match="Could not reach the model"):
        await provider.complete(system="s", messages=[UserMessage(text="hi")], tools=[])


async def test_error_status_raises_llm_request_error():
    def handler(request):
        return httpx2.Response(404, text="model not found")

    provider = build_provider(handler)

    with pytest.raises(LLMRequestError, match="404"):
        await provider.complete(system="s", messages=[UserMessage(text="hi")], tools=[])


async def test_empty_choices_raises_llm_request_error():
    def handler(request):
        return httpx2.Response(200, json={"choices": []})

    provider = build_provider(handler)

    with pytest.raises(LLMRequestError, match="no choices"):
        await provider.complete(system="s", messages=[UserMessage(text="hi")], tools=[])

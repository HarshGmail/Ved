import json

import httpx2
import pytest

from ved_backend.llm.base import (
    AssistantMessage,
    ReasoningDelta,
    TextDelta,
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


async def test_timeouts_name_the_timeout_setting():
    def handler(request):
        raise httpx2.ReadTimeout("")

    provider = build_provider(handler)

    with pytest.raises(LLMRequestError, match="VED_LLM_TIMEOUT_SECONDS"):
        await provider.complete(system="s", messages=[UserMessage(text="hi")], tools=[])


async def test_a_silent_exception_still_names_its_type():
    def handler(request):
        raise httpx2.ConnectError("")

    provider = build_provider(handler)

    with pytest.raises(LLMRequestError, match="ConnectError"):
        await provider.complete(system="s", messages=[UserMessage(text="hi")], tools=[])


def sse_body(*events: str) -> bytes:
    return "".join(f"{event}\n\n" for event in events).encode()


def delta_event(delta: dict) -> str:
    return "data: " + json.dumps({"choices": [{"index": 0, "delta": delta}]})


async def collect_chunks(provider) -> list:
    return [
        chunk
        async for chunk in provider.stream(
            system="s", messages=[UserMessage(text="hi")], tools=[CREATE]
        )
    ]


async def collect_stream(provider) -> tuple[list[str], AssistantMessage]:
    *deltas, final = await collect_chunks(provider)
    return [delta.text for delta in deltas if isinstance(delta, TextDelta)], final


async def test_stream_requests_streaming_and_yields_text_as_it_arrives():
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx2.Response(
            200,
            content=sse_body(
                delta_event({"role": "assistant", "content": ""}),
                delta_event({"content": "Hel"}),
                delta_event({"content": "lo"}),
                "data: [DONE]",
            ),
            headers={"content-type": "text/event-stream"},
        )

    texts, final = await collect_stream(build_provider(handler))

    assert seen["stream"] is True
    assert texts == ["Hel", "lo"]
    assert final == AssistantMessage(text="Hello")


async def test_stream_assembles_tool_calls_from_fragments():
    def handler(request):
        return httpx2.Response(
            200,
            content=sse_body(
                delta_event(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_a",
                                "function": {
                                    "name": "reminders.create",
                                    "arguments": "",
                                },
                            }
                        ]
                    }
                ),
                delta_event(
                    {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "call_b",
                                "function": {"name": "reminders.list"},
                            }
                        ]
                    }
                ),
                delta_event(
                    {"tool_calls": [{"index": 0, "function": {"arguments": '{"te'}}]}
                ),
                delta_event(
                    {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": 'xt": "call Mom"}'}}
                        ]
                    }
                ),
                delta_event(
                    {"tool_calls": [{"index": 1, "function": {"arguments": "{}"}}]}
                ),
                "data: [DONE]",
            ),
        )

    texts, final = await collect_stream(build_provider(handler))

    assert texts == []
    assert final.tool_calls == [
        ToolCall(id="call_a", name="reminders.create", arguments={"text": "call Mom"}),
        ToolCall(id="call_b", name="reminders.list", arguments={}),
    ]


async def test_stream_joins_multi_line_data_and_skips_comments():
    payload = json.dumps({"choices": [{"delta": {"content": "hi"}}]}, indent=1)
    multi_line = "\n".join(f"data: {line}" for line in payload.splitlines())

    def handler(request):
        return httpx2.Response(
            200, content=sse_body(": keep-alive", multi_line, "data: [DONE]")
        )

    texts, final = await collect_stream(build_provider(handler))

    assert texts == ["hi"]
    assert final.text == "hi"


async def test_stream_without_done_sentinel_still_finishes():
    def handler(request):
        return httpx2.Response(200, content=delta_event({"content": "ok"}).encode())

    texts, final = await collect_stream(build_provider(handler))

    assert texts == ["ok"]
    assert final.text == "ok"


async def test_stream_error_status_raises_llm_request_error():
    def handler(request):
        return httpx2.Response(404, text="model not found")

    with pytest.raises(LLMRequestError, match="404: model not found"):
        await collect_stream(build_provider(handler))


async def test_stream_unreachable_model_raises_llm_request_error():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(LLMRequestError, match="Could not reach the model"):
        await collect_stream(build_provider(handler))


async def test_stream_malformed_event_raises_llm_request_error():
    def handler(request):
        return httpx2.Response(200, content=sse_body("data: {oops"))

    with pytest.raises(LLMRequestError, match="malformed stream"):
        await collect_stream(build_provider(handler))


async def test_stream_error_payload_raises_llm_request_error():
    def handler(request):
        return httpx2.Response(
            200, content=sse_body('data: {"error": {"message": "out of memory"}}')
        )

    with pytest.raises(LLMRequestError, match="out of memory"):
        await collect_stream(build_provider(handler))


async def test_stream_survives_events_split_across_network_reads():
    body = sse_body(
        delta_event({"content": "split "}),
        delta_event({"content": "across reads"}),
        "data: [DONE]",
    )
    read_size = 7

    async def trickle():
        for start in range(0, len(body), read_size):
            yield body[start : start + read_size]

    def handler(request):
        return httpx2.Response(200, content=trickle())

    texts, final = await collect_stream(build_provider(handler))

    assert texts == ["split ", "across reads"]
    assert final.text == "split across reads"


@pytest.mark.parametrize("field", ["reasoning", "reasoning_content"])
async def test_stream_marks_reasoning_without_leaking_it_into_the_reply(field):
    secret = "the user probably wants"

    def handler(request):
        return httpx2.Response(
            200,
            content=sse_body(
                delta_event({"role": "assistant", "content": "", field: "Here"}),
                delta_event({"content": "", field: f" {secret}"}),
                delta_event({"content": "391"}),
                "data: [DONE]",
            ),
        )

    chunks = await collect_chunks(build_provider(handler))

    assert chunks[:2] == [ReasoningDelta(), ReasoningDelta()]
    assert chunks[2:] == [TextDelta(text="391"), AssistantMessage(text="391")]
    assert all(secret not in chunk.model_dump_json() for chunk in chunks)


async def test_stream_reasoning_before_a_tool_call_stays_out_of_the_message():
    def handler(request):
        return httpx2.Response(
            200,
            content=sse_body(
                delta_event({"reasoning": "I should call the tool"}),
                delta_event(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_a",
                                "function": {
                                    "name": "reminders.create",
                                    "arguments": "{}",
                                },
                            }
                        ]
                    }
                ),
                "data: [DONE]",
            ),
        )

    chunks = await collect_chunks(build_provider(handler))

    assert chunks[0] == ReasoningDelta()
    assert chunks[-1].text == ""
    assert chunks[-1].tool_calls[0].name == "reminders.create"


def test_reasoning_in_a_complete_reply_is_ignored():
    reply = from_wire_message({"content": "391", "reasoning": "multiply"})

    assert reply == AssistantMessage(text="391")

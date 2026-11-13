from types import SimpleNamespace

import httpx2
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
)
from anthropic.types import Message as AnthropicMessage

from ved_backend.config import Settings
from ved_backend.llm import MissingAnthropicKeyError, build_embedder, build_provider
from ved_backend.llm.anthropic_provider import (
    AnthropicProvider,
    ToolNameMap,
    to_anthropic_messages,
)
from ved_backend.llm.base import (
    AssistantMessage,
    LLMRequestError,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolOutcome,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from ved_backend.llm.embeddings import OpenAICompatibleEmbedder

SEARCH = ToolSpec(
    name="memory.search",
    description="Search memory.",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
)
REQUEST_URL = "https://api.anthropic.com/v1/messages"
THINKING = {"type": "thinking", "thinking": "", "signature": "sig-1"}
TOOL_USE = {
    "type": "tool_use",
    "id": "tu_1",
    "name": "memory_search",
    "input": {"query": "Ravi"},
}


def test_dotted_tool_names_round_trip_through_safe_names():
    names = ToolNameMap(["memory.search", "plan.create_reminder"])

    assert names.safe("memory.search") == "memory_search"
    assert names.original("memory_search") == "memory.search"
    assert names.original("plan_create_reminder") == "plan.create_reminder"


def test_colliding_safe_names_get_a_numeric_suffix():
    names = ToolNameMap(["a.b", "a_b"])

    assert names.safe("a.b") == "a_b"
    assert names.safe("a_b") == "a_b_2"
    assert names.original("a_b_2") == "a_b"


def test_safe_names_never_exceed_the_length_limit():
    long_name = "x" * 80

    safe = ToolNameMap([long_name]).safe(long_name)

    assert len(safe) <= 64


def test_a_tool_round_trip_alternates_roles_and_keeps_provider_content():
    names = ToolNameMap(["memory.search"])
    reply = AssistantMessage(
        tool_calls=[
            ToolCall(id="tu_1", name="memory.search", arguments={"query": "Ravi"})
        ],
        provider_content=[THINKING, TOOL_USE],
    )
    messages = [
        UserMessage(text="what about Ravi"),
        reply,
        ToolResultMessage(
            outcomes=[ToolOutcome(call_id="tu_1", content="Ravi is a friend")]
        ),
        UserMessage(text="thanks"),
    ]

    converted = to_anthropic_messages(messages, names)

    assert [message["role"] for message in converted] == ["user", "assistant", "user"]
    assert converted[0]["content"] == "what about Ravi"
    assert converted[1]["content"] == [THINKING, TOOL_USE]
    assert converted[2]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "tu_1",
            "content": "Ravi is a friend",
            "is_error": False,
        },
        {"type": "text", "text": "thanks"},
    ]


def test_an_assistant_without_provider_content_is_rebuilt_with_safe_names():
    names = ToolNameMap(["memory.search"])
    message = AssistantMessage(
        text="Looking.",
        tool_calls=[
            ToolCall(id="tu_1", name="memory.search", arguments={"query": "x"})
        ],
    )

    converted = to_anthropic_messages([message], names)

    assert converted == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looking."},
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "memory_search",
                    "input": {"query": "x"},
                },
            ],
        }
    ]


def test_an_empty_assistant_message_is_skipped():
    converted = to_anthropic_messages(
        [UserMessage(text="hi"), AssistantMessage(), UserMessage(text="again")],
        ToolNameMap(),
    )

    assert [message["role"] for message in converted] == ["user"]
    assert converted[0]["content"] == [
        {"type": "text", "text": "hi"},
        {"type": "text", "text": "again"},
    ]


def final_message(
    content: list[dict], stop_reason: str = "end_turn"
) -> AnthropicMessage:
    return AnthropicMessage.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 12, "output_tokens": 4},
        }
    )


class FakeStream:
    def __init__(self, events, final=None, error=None):
        self._events = events
        self._final = final
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def __aiter__(self):
        if self._error is not None:
            raise self._error
        for event in self._events:
            yield event

    async def get_final_message(self):
        return self._final


def provider_with(stream: FakeStream) -> tuple[AnthropicProvider, list[dict]]:
    provider = AnthropicProvider(
        api_key="sk-ant-test", model="claude-haiku-5-5", max_tokens=512
    )
    calls: list[dict] = []

    def open_stream(**kwargs):
        calls.append(kwargs)
        return stream

    provider._client = SimpleNamespace(messages=SimpleNamespace(stream=open_stream))
    return provider, calls


async def collect(provider: AnthropicProvider, tools=(SEARCH,)):
    return [
        chunk
        async for chunk in provider.stream(
            system="be kind", messages=[UserMessage(text="hi")], tools=list(tools)
        )
    ]


async def test_stream_yields_reasoning_text_and_the_final_reply():
    final = final_message(
        [THINKING, {"type": "text", "text": "Hello there", "citations": None}]
    )
    events = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="Hello "),
        SimpleNamespace(type="text", text="there"),
    ]
    provider, _ = provider_with(FakeStream(events, final))

    chunks = await collect(provider)

    assert chunks[0] == ReasoningDelta()
    assert chunks[1:3] == [TextDelta(text="Hello "), TextDelta(text="there")]
    assert chunks[3].text == "Hello there"
    assert chunks[3].provider_content == [
        THINKING,
        {"type": "text", "text": "Hello there"},
    ]


async def test_stream_maps_tool_use_names_back_and_sends_safe_names():
    final = final_message([TOOL_USE], stop_reason="tool_use")
    provider, calls = provider_with(FakeStream([], final))

    chunks = await collect(provider)

    reply = chunks[-1]
    assert reply.tool_calls == [
        ToolCall(id="tu_1", name="memory.search", arguments={"query": "Ravi"})
    ]
    request = calls[0]
    assert request["tools"][0]["name"] == "memory_search"
    assert request["tools"][0]["input_schema"] == SEARCH.input_schema
    assert request["system"] == [
        {"type": "text", "text": "be kind", "cache_control": {"type": "ephemeral"}}
    ]
    assert request["max_tokens"] == 512
    assert "temperature" not in request
    assert "thinking" not in request


async def test_provider_content_is_not_serialised_into_the_reply_dump():
    final = final_message([THINKING, {"type": "text", "text": "ok"}])
    provider, _ = provider_with(FakeStream([], final))

    reply = (await collect(provider))[-1]

    assert reply.provider_content is not None
    assert "provider_content" not in reply.model_dump()


async def test_complete_returns_the_final_reply():
    final = final_message([{"type": "text", "text": "Done."}])
    provider, _ = provider_with(FakeStream([], final))

    reply = await provider.complete(
        system="be kind", messages=[UserMessage(text="hi")], tools=[]
    )

    assert reply.text == "Done."


async def test_a_rejected_key_names_the_setting():
    request = httpx2.Request("POST", REQUEST_URL)
    response = httpx2.Response(401, request=request)
    error = AuthenticationError(
        message="invalid x-api-key", response=response, body=None
    )
    provider, _ = provider_with(FakeStream([], error=error))

    with pytest.raises(LLMRequestError, match="VED_ANTHROPIC_API_KEY"):
        await collect(provider)


async def test_an_exhausted_balance_says_the_credit_ran_out():
    request = httpx2.Request("POST", REQUEST_URL)
    response = httpx2.Response(400, request=request)
    error = BadRequestError(
        message="Your credit balance is too low to access the Anthropic API.",
        response=response,
        body=None,
    )
    provider, _ = provider_with(FakeStream([], error=error))

    with pytest.raises(LLMRequestError, match="credit balance ran out"):
        await collect(provider)


async def test_an_unreachable_api_and_a_timeout_have_plain_messages():
    request = httpx2.Request("POST", REQUEST_URL)
    unreachable, _ = provider_with(
        FakeStream([], error=APIConnectionError(request=request))
    )
    timed_out, _ = provider_with(FakeStream([], error=APITimeoutError(request=request)))

    with pytest.raises(LLMRequestError, match="Could not reach Anthropic"):
        await collect(unreachable)
    with pytest.raises(LLMRequestError, match="did not answer in time"):
        await collect(timed_out)


def anthropic_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "llm_provider": "anthropic",
        "anthropic_api_key": "sk-ant-test",
        "llm_model": "claude-haiku-5-5",
        "llm_max_tokens": 2048,
    }
    return Settings(**{**values, **overrides})


def test_build_provider_returns_the_anthropic_provider():
    provider = build_provider(anthropic_settings())

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-haiku-5-5"


def test_build_provider_refuses_anthropic_without_a_key():
    with pytest.raises(MissingAnthropicKeyError, match="VED_ANTHROPIC_API_KEY"):
        build_provider(anthropic_settings(anthropic_api_key=None))


def test_embeddings_stay_on_the_local_embedder_under_anthropic():
    embedder = build_embedder(
        anthropic_settings(llm_base_url="http://localhost:11434/v1")
    )

    assert isinstance(embedder, OpenAICompatibleEmbedder)

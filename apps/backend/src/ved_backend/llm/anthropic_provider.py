import logging
import re
import time
from collections.abc import AsyncIterator, Iterable, Sequence
from typing import Any

from anthropic import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
)
from anthropic.types import Message as AnthropicMessage

from ved_backend.llm.base import (
    AssistantMessage,
    LLMRequestError,
    Message,
    ReasoningDelta,
    StreamChunk,
    TextDelta,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MAX_TOOL_NAME_LENGTH = 64
UNSAFE_TOOL_NAME_CHARACTERS = re.compile(r"[^a-zA-Z0-9_-]")
SAFE_NAME_REPLACEMENT = "_"
CACHE_CONTROL = {"type": "ephemeral"}
TEXT_BLOCK = "text"
TOOL_USE_BLOCK = "tool_use"
TEXT_EVENT = "text"
THINKING_EVENT = "thinking"
OUTPUT_EVENTS = frozenset({TEXT_EVENT, THINKING_EVENT})
UNAUTHORIZED_STATUS = 401
BAD_REQUEST_STATUS = 400
CREDIT_HINT = "credit"
ERROR_MESSAGE_PREVIEW_CHARS = 400
NO_REPLY_MESSAGE = "Anthropic returned no reply."
LLM_CALL_LOG_FORMAT = (
    "llm_call model=%s messages=%s tools=%s input_tokens=%s "
    "output_tokens=%s cache_read_input_tokens=%s first_token_s=%s total_s=%s"
)


def _with_suffix(base: str, number: int) -> str:
    tail = f"{SAFE_NAME_REPLACEMENT}{number}"
    return base[: MAX_TOOL_NAME_LENGTH - len(tail)] + tail


class ToolNameMap:
    def __init__(self, names: Iterable[str] = ()) -> None:
        self._safe_by_original: dict[str, str] = {}
        self._original_by_safe: dict[str, str] = {}
        for name in names:
            self.safe(name)

    def safe(self, original: str) -> str:
        if original not in self._safe_by_original:
            self._register(original)
        return self._safe_by_original[original]

    def original(self, safe: str) -> str:
        return self._original_by_safe.get(safe, safe)

    def _register(self, original: str) -> None:
        base = UNSAFE_TOOL_NAME_CHARACTERS.sub(SAFE_NAME_REPLACEMENT, original)
        base = base[:MAX_TOOL_NAME_LENGTH]
        candidate = base
        suffix = 1
        while candidate in self._original_by_safe:
            suffix += 1
            candidate = _with_suffix(base, suffix)
        self._safe_by_original[original] = candidate
        self._original_by_safe[candidate] = original


def _text_block(text: str) -> dict[str, Any]:
    return {"type": TEXT_BLOCK, "text": text}


def _as_blocks(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [_text_block(content)]
    return list(content)


def _tool_payload(tool: ToolSpec, names: ToolNameMap) -> dict[str, Any]:
    return {
        "name": names.safe(tool.name),
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _assistant_content(
    message: AssistantMessage, names: ToolNameMap
) -> str | list[dict[str, Any]]:
    if message.provider_content:
        return message.provider_content
    blocks = [_text_block(message.text)] if message.text else []
    blocks.extend(
        {
            "type": TOOL_USE_BLOCK,
            "id": call.id,
            "name": names.safe(call.name),
            "input": call.arguments,
        }
        for call in message.tool_calls
    )
    return blocks


def _tool_results_content(message: ToolResultMessage) -> list[dict[str, Any]]:
    return [
        {
            "type": "tool_result",
            "tool_use_id": outcome.call_id,
            "content": outcome.content,
            "is_error": outcome.is_error,
        }
        for outcome in message.outcomes
    ]


def _role_and_content(
    message: Message, names: ToolNameMap
) -> tuple[str, str | list[dict[str, Any]]]:
    if isinstance(message, UserMessage):
        return "user", message.text
    if isinstance(message, AssistantMessage):
        return "assistant", _assistant_content(message, names)
    return "user", _tool_results_content(message)


def _append_turn(
    converted: list[dict[str, Any]],
    role: str,
    content: str | list[dict[str, Any]],
) -> None:
    if converted and converted[-1]["role"] == role:
        converted[-1]["content"] = _as_blocks(converted[-1]["content"]) + _as_blocks(
            content
        )
        return
    converted.append({"role": role, "content": content})


def to_anthropic_messages(
    messages: Sequence[Message], names: ToolNameMap
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role, content = _role_and_content(message, names)
        if content:
            _append_turn(converted, role, content)
    return converted


def to_assistant_message(
    final: AnthropicMessage, names: ToolNameMap
) -> AssistantMessage:
    text = "".join(block.text for block in final.content if block.type == TEXT_BLOCK)
    calls = [
        ToolCall(
            id=block.id,
            name=names.original(block.name),
            arguments=block.input,
        )
        for block in final.content
        if block.type == TOOL_USE_BLOCK
    ]
    return AssistantMessage(
        text=text,
        tool_calls=calls,
        provider_content=[
            block.model_dump(exclude_none=True) for block in final.content
        ],
    )


def _describe_status(error: APIStatusError) -> str:
    detail = str(error.message)[:ERROR_MESSAGE_PREVIEW_CHARS]
    if error.status_code == UNAUTHORIZED_STATUS:
        return "Anthropic rejected the API key (401). Check VED_ANTHROPIC_API_KEY."
    if error.status_code == BAD_REQUEST_STATUS and CREDIT_HINT in detail.lower():
        return (
            "The Anthropic credit balance ran out, so Ved cannot answer. "
            "Add credit in the Anthropic console."
        )
    return f"Anthropic returned {error.status_code}: {detail}"


def _describe(error: APIError) -> str:
    if isinstance(error, APITimeoutError):
        return (
            "Anthropic did not answer in time. "
            "Raise VED_LLM_TIMEOUT_SECONDS if answers are slow."
        )
    if isinstance(error, APIConnectionError):
        return f"Could not reach Anthropic: {error}"
    if isinstance(error, APIStatusError):
        return _describe_status(error)
    return f"Anthropic request failed: {error}"


def _elapsed_seconds(since: float, until: float | None) -> float | None:
    return None if until is None else round(until - since, 1)


def _log_model_call(
    *,
    model: str,
    request: dict[str, Any],
    final: AnthropicMessage,
    started_at: float,
    first_token_at: float | None,
) -> None:
    usage = final.usage
    logger.info(
        LLM_CALL_LOG_FORMAT,
        model,
        len(request["messages"]),
        len(request.get("tools", [])),
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_input_tokens,
        _elapsed_seconds(started_at, first_token_at),
        _elapsed_seconds(started_at, time.monotonic()),
    )


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = AsyncAnthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=MAX_RETRIES
        )

    @property
    def model(self) -> str:
        return self._model

    def _request(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        names: ToolNameMap,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": [
                {**_text_block(system), "cache_control": CACHE_CONTROL},
            ],
            "messages": to_anthropic_messages(messages, names),
        }
        if tools:
            request["tools"] = [_tool_payload(tool, names) for tool in tools]
        return request

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AssistantMessage:
        reply: AssistantMessage | None = None
        async for chunk in self.stream(system=system, messages=messages, tools=tools):
            if isinstance(chunk, AssistantMessage):
                reply = chunk
        if reply is None:
            raise LLMRequestError(NO_REPLY_MESSAGE)
        return reply

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AsyncIterator[StreamChunk]:
        names = ToolNameMap(tool.name for tool in tools)
        request = self._request(
            system=system, messages=messages, tools=tools, names=names
        )
        started_at = time.monotonic()
        first_token_at: float | None = None
        try:
            async with self._client.messages.stream(**request) as stream:
                async for event in stream:
                    if first_token_at is None and event.type in OUTPUT_EVENTS:
                        first_token_at = time.monotonic()
                    if event.type == TEXT_EVENT:
                        yield TextDelta(text=event.text)
                    elif event.type == THINKING_EVENT:
                        yield ReasoningDelta()
                final = await stream.get_final_message()
        except APIError as error:
            raise LLMRequestError(_describe(error)) from error

        _log_model_call(
            model=self._model,
            request=request,
            final=final,
            started_at=started_at,
            first_token_at=first_token_at,
        )
        yield to_assistant_message(final, names)

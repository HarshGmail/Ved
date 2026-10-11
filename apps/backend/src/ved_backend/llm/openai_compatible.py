import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx2

from ved_backend.llm.base import (
    AssistantMessage,
    LLMRequestError,
    Message,
    ReasoningDelta,
    StreamChunk,
    TextDelta,
    ToolCall,
    ToolOutcome,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_PATH = "/chat/completions"
PLACEHOLDER_API_KEY = "not-needed"
SSE_DATA_PREFIX = "data:"
SSE_DONE_SENTINEL = "[DONE]"
ERROR_BODY_PREVIEW_CHARS = 400
REASONING_FIELDS = ("reasoning", "reasoning_content")


def _describe(error: Exception) -> str:
    detail = str(error) or type(error).__name__
    if isinstance(error, httpx2.TimeoutException):
        return (
            f"The model did not answer in time ({detail}). "
            "A large local model may need a longer VED_LLM_TIMEOUT_SECONDS."
        )
    return f"Could not reach the model: {detail}"


def _tool_payload(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _assistant_payload(message: AssistantMessage) -> dict[str, Any]:
    if not message.tool_calls:
        return {"role": "assistant", "content": message.text}

    return {
        "role": "assistant",
        "content": message.text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in message.tool_calls
        ],
    }


def _outcome_payload(outcome: ToolOutcome) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": outcome.call_id,
        "content": outcome.content,
    }


def to_wire_messages(system: str, messages: Sequence[Message]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        if isinstance(message, UserMessage):
            payload.append({"role": "user", "content": message.text})
        elif isinstance(message, AssistantMessage):
            payload.append(_assistant_payload(message))
        elif isinstance(message, ToolResultMessage):
            payload.extend(_outcome_payload(outcome) for outcome in message.outcomes)
    return payload


def _parse_arguments(raw: str | None, tool_name: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Model sent non-JSON arguments for %s: %r", tool_name, raw)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def from_wire_message(payload: dict[str, Any]) -> AssistantMessage:
    raw_calls = payload.get("tool_calls") or []
    calls = []
    for index, raw in enumerate(raw_calls):
        function = raw.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        calls.append(
            ToolCall(
                id=raw.get("id") or f"call-{index}",
                name=name,
                arguments=_parse_arguments(function.get("arguments"), name),
            )
        )
    return AssistantMessage(text=payload.get("content") or "", tool_calls=calls)


async def iter_sse_data(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    pending: list[str] = []
    async for line in lines:
        if not line:
            if pending:
                yield "\n".join(pending)
                pending = []
            continue
        if line.startswith(SSE_DATA_PREFIX):
            pending.append(line.removeprefix(SSE_DATA_PREFIX).removeprefix(" "))
    if pending:
        yield "\n".join(pending)


@dataclass
class _ToolCallFragments:
    id: str | None = None
    name: str = ""
    arguments: list[str] = field(default_factory=list)


class StreamAssembler:
    def __init__(self) -> None:
        self._text: list[str] = []
        self._calls: dict[int, _ToolCallFragments] = {}

    def absorb(self, delta: dict[str, Any]) -> str:
        for raw in delta.get("tool_calls") or []:
            self._absorb_tool_call(raw)
        content = delta.get("content") or ""
        if content:
            self._text.append(content)
        return content

    def _absorb_tool_call(self, raw: dict[str, Any]) -> None:
        index = raw.get("index", len(self._calls))
        fragments = self._calls.setdefault(index, _ToolCallFragments())
        if raw.get("id"):
            fragments.id = raw["id"]
        function = raw.get("function") or {}
        if function.get("name") and not fragments.name:
            fragments.name = function["name"]
        if function.get("arguments"):
            fragments.arguments.append(function["arguments"])

    def message(self) -> AssistantMessage:
        return from_wire_message(
            {
                "content": "".join(self._text),
                "tool_calls": [
                    {
                        "id": fragments.id,
                        "function": {
                            "name": fragments.name,
                            "arguments": "".join(fragments.arguments),
                        },
                    }
                    for _, fragments in sorted(self._calls.items())
                ],
            }
        )


def carries_reasoning(delta: dict[str, Any]) -> bool:
    return any(delta.get(field) for field in REASONING_FIELDS)


def _first_delta(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("error"):
        raise LLMRequestError(f"Model reported an error: {payload['error']}")
    choices = payload.get("choices") or []
    if not choices:
        return {}
    return choices[0].get("delta") or {}


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        temperature: float | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key or PLACEHOLDER_API_KEY}"},
        )

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._client.aclose()

    def _build_body(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": to_wire_messages(system, messages),
        }
        if tools:
            body["tools"] = [_tool_payload(tool) for tool in tools]
        if self._temperature is not None:
            body["temperature"] = self._temperature
        return body

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AssistantMessage:
        try:
            response = await self._client.post(
                CHAT_COMPLETIONS_PATH,
                json=self._build_body(system, messages, tools),
            )
        except httpx2.HTTPError as error:
            raise LLMRequestError(_describe(error)) from error

        if response.status_code != httpx2.codes.OK:
            raise LLMRequestError(
                f"Model returned {response.status_code}: "
                f"{response.text[:ERROR_BODY_PREVIEW_CHARS]}"
            )

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise LLMRequestError(f"Model returned no choices: {payload}")

        return from_wire_message(choices[0].get("message") or {})

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AsyncIterator[StreamChunk]:
        body = {**self._build_body(system, messages, tools), "stream": True}
        assembler = StreamAssembler()
        try:
            async with self._client.stream(
                "POST", CHAT_COMPLETIONS_PATH, json=body
            ) as response:
                if response.status_code != httpx2.codes.OK:
                    detail = (await response.aread()).decode(errors="replace")
                    raise LLMRequestError(
                        f"Model returned {response.status_code}: "
                        f"{detail[:ERROR_BODY_PREVIEW_CHARS]}"
                    )
                async for data in iter_sse_data(response.aiter_lines()):
                    if data.strip() == SSE_DONE_SENTINEL:
                        break
                    delta = _first_delta(json.loads(data))
                    if carries_reasoning(delta):
                        yield ReasoningDelta()
                    text = assembler.absorb(delta)
                    if text:
                        yield TextDelta(text=text)
        except httpx2.HTTPError as error:
            raise LLMRequestError(_describe(error)) from error
        except json.JSONDecodeError as error:
            raise LLMRequestError(f"Model sent a malformed stream: {error}") from error

        yield assembler.message()

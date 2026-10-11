import json
import re
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ved_backend.llm.base import (
    AssistantMessage,
    Message,
    ReasoningDelta,
    StreamChunk,
    TextDelta,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

STUB_MODEL_NAME = "stub-rules-v1"

CREATE_TOOL = "reminders.create"
LIST_TOOL = "reminders.list"
COMPLETE_TOOL = "reminders.complete"

TIME_PATTERN = re.compile(
    r"\bat\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm)?\b",
    re.IGNORECASE,
)
SUBJECT_PATTERN = re.compile(r"\bto\s+(?P<subject>.+?)\s*[.!?]*$", re.IGNORECASE)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

CREATE_WORDS = ("remind", "reminder")
LIST_WORDS = ("list", "what are my", "show me my", "pending", "due")
COMPLETE_WORDS = ("done", "completed", "finished", "mark")

DEFAULT_HOUR = 9
NOON = 12

STREAM_WORDS_PER_CHUNK = 4
WORD_BOUNDARY = re.compile(r"(?<=\s)(?=\S)")


def _latest_user_text(messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if isinstance(message, UserMessage):
            return message.text
    return ""


def _to_twenty_four_hour(hour: int, meridiem: str | None) -> int:
    lowered = (meridiem or "").lower()
    if lowered == "pm" and hour < NOON:
        return hour + NOON
    if lowered == "am" and hour == NOON:
        return 0
    return hour


def resolve_due_at(text: str, now: datetime) -> datetime:
    match = TIME_PATTERN.search(text)
    if match is None:
        due = now.replace(
            hour=DEFAULT_HOUR, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        return due

    hour = _to_twenty_four_hour(int(match["hour"]), match["meridiem"])
    minute = int(match["minute"] or 0)
    due = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)

    said_tomorrow = "tomorrow" in text.lower()
    already_passed = due <= now
    if said_tomorrow or already_passed:
        due += timedelta(days=1)
    return due


def extract_subject(text: str) -> str:
    match = SUBJECT_PATTERN.search(text)
    return match["subject"].strip() if match else text.strip()


def split_into_chunks(text: str, words_per_chunk: int) -> list[str]:
    if not text:
        return []
    words = WORD_BOUNDARY.split(text)
    return [
        "".join(words[start : start + words_per_chunk])
        for start in range(0, len(words), words_per_chunk)
    ]


def _contains_any(text: str, words: Sequence[str]) -> bool:
    return any(word in text for word in words)


def _format_local(iso_value: str, zone: ZoneInfo) -> str:
    moment = datetime.fromisoformat(iso_value).astimezone(zone)
    return moment.strftime("%a %d %b, %-I:%M %p")


def _describe_reminder(record: dict, zone: ZoneInfo) -> str:
    when = _format_local(record["due_at"], zone)
    state = " (completed)" if record.get("completed") else ""
    return f"{record['text']} — {when}{state}"


def phrase_outcome(content: str, zone: ZoneInfo) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return content

    if isinstance(payload, dict) and "reminders" in payload:
        records = payload["reminders"]
        if not records:
            return "You have no reminders."
        listed = "\n".join(
            f"- {_describe_reminder(record, zone)}" for record in records
        )
        return f"You have {len(records)} reminder(s):\n{listed}"

    if isinstance(payload, dict) and "due_at" in payload:
        verb = "Completed" if payload.get("completed") else "Reminder set"
        return f"{verb}: {_describe_reminder(payload, zone)}"

    return content


class StubProvider:
    def __init__(self, timezone: str) -> None:
        self._zone = ZoneInfo(timezone)
        self._counter = 0

    @property
    def model(self) -> str:
        return STUB_MODEL_NAME

    def _next_call_id(self) -> str:
        self._counter += 1
        return f"stub-call-{self._counter}"

    def _call(self, name: str, arguments: dict[str, object]) -> AssistantMessage:
        return AssistantMessage(
            tool_calls=[
                ToolCall(id=self._next_call_id(), name=name, arguments=arguments)
            ]
        )

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AssistantMessage:
        available = {tool.name for tool in tools}

        if messages and isinstance(messages[-1], ToolResultMessage):
            return self._summarise(messages[-1])

        prompt = _latest_user_text(messages)
        lowered = prompt.lower()

        if COMPLETE_TOOL in available and _contains_any(lowered, COMPLETE_WORDS):
            found = UUID_PATTERN.search(prompt)
            if found:
                return self._call(COMPLETE_TOOL, {"reminder_id": found.group()})

        if LIST_TOOL in available and _contains_any(lowered, LIST_WORDS):
            return self._call(LIST_TOOL, {})

        if CREATE_TOOL in available and _contains_any(lowered, CREATE_WORDS):
            now = datetime.now(self._zone)
            return self._call(
                CREATE_TOOL,
                {
                    "text": extract_subject(prompt),
                    "due_at": resolve_due_at(prompt, now).isoformat(),
                },
            )

        return AssistantMessage(
            text=(
                "I can create, list and complete reminders. "
                'Try "remind me at 8 PM to call Mom".'
            )
        )

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
    ) -> AsyncIterator[StreamChunk]:
        yield ReasoningDelta()
        reply = await self.complete(system=system, messages=messages, tools=tools)
        for chunk in split_into_chunks(reply.text, STREAM_WORDS_PER_CHUNK):
            yield TextDelta(text=chunk)
        yield reply

    def _summarise(self, results: ToolResultMessage) -> AssistantMessage:
        failed = [outcome for outcome in results.outcomes if outcome.is_error]
        if failed:
            return AssistantMessage(text=f"That did not work: {failed[0].content}")

        lines = [
            phrase_outcome(outcome.content, self._zone) for outcome in results.outcomes
        ]
        return AssistantMessage(text="\n".join(lines))

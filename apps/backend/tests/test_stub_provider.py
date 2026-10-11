from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ved_backend.llm.base import (
    ReasoningDelta,
    TextDelta,
    ToolOutcome,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from ved_backend.llm.stub import (
    StubProvider,
    extract_subject,
    phrase_outcome,
    resolve_due_at,
    split_into_chunks,
)

ZONE = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 19, 14, 30, tzinfo=ZONE)

TOOLS = [
    ToolSpec(name="reminders.create", description="", input_schema={}),
    ToolSpec(name="reminders.list", description="", input_schema={}),
    ToolSpec(name="reminders.complete", description="", input_schema={}),
]


@pytest.fixture
def provider():
    return StubProvider(timezone="Asia/Kolkata")


async def complete(provider, text):
    return await provider.complete(
        system="", messages=[UserMessage(text=text)], tools=TOOLS
    )


@pytest.mark.parametrize(
    ("prompt", "expected_hour", "expected_minute"),
    [
        ("remind me at 8 PM to call Mom", 20, 0),
        ("remind me at 8:15 pm to call Mom", 20, 15),
        ("remind me at 9 am to call Mom", 9, 0),
        ("remind me at 12 am to call Mom", 0, 0),
        ("remind me at 12 pm to call Mom", 12, 0),
    ],
)
def test_resolve_due_at_reads_the_clock_time(prompt, expected_hour, expected_minute):
    due = resolve_due_at(prompt, NOW)

    assert (due.hour, due.minute) == (expected_hour, expected_minute)


def test_resolve_due_at_rolls_past_times_to_tomorrow():
    due = resolve_due_at("remind me at 9 am to call Mom", NOW)

    assert due.day == NOW.day + 1


def test_resolve_due_at_honours_tomorrow():
    due = resolve_due_at("remind me tomorrow at 8 pm to call Mom", NOW)

    assert (due.day, due.hour) == (NOW.day + 1, 20)


def test_resolve_due_at_always_carries_an_offset():
    due = resolve_due_at("remind me to call Mom", NOW)

    assert due.tzinfo is not None
    assert "+" in due.isoformat()


def test_extract_subject_drops_the_leading_instruction():
    assert extract_subject("remind me at 8 PM to call Mom") == "call Mom"


async def test_create_prompt_produces_a_create_call(provider):
    reply = await complete(provider, "Ved, remind me at 8 PM to call Mom")

    assert len(reply.tool_calls) == 1
    call = reply.tool_calls[0]
    assert call.name == "reminders.create"
    assert call.arguments["text"] == "call Mom"
    assert call.arguments["due_at"].endswith("+05:30")


async def test_list_prompt_produces_a_list_call(provider):
    reply = await complete(provider, "what are my reminders?")

    assert reply.tool_calls[0].name == "reminders.list"


async def test_complete_prompt_needs_an_identifier(provider):
    identifier = "0b5a1f2e-3c4d-4e5f-8a9b-1c2d3e4f5a6b"

    reply = await complete(provider, f"mark {identifier} as done")

    assert reply.tool_calls[0].name == "reminders.complete"
    assert reply.tool_calls[0].arguments == {"reminder_id": identifier}


async def test_unrelated_prompt_answers_without_tools(provider):
    reply = await complete(provider, "what is the weather")

    assert reply.tool_calls == []
    assert "reminders" in reply.text


async def test_tool_results_end_the_loop(provider):
    reply = await provider.complete(
        system="",
        messages=[
            UserMessage(text="remind me at 8 PM to call Mom"),
            ToolResultMessage(
                outcomes=[
                    ToolOutcome(
                        call_id="stub-call-1",
                        content=(
                            '{"id":"x","text":"call Mom",'
                            '"due_at":"2026-09-19T20:00:00+05:30","completed":false}'
                        ),
                    )
                ]
            ),
        ],
        tools=TOOLS,
    )

    assert reply.tool_calls == []
    assert "Reminder set" in reply.text
    assert "call Mom" in reply.text
    assert "8:00 PM" in reply.text


async def test_tool_errors_are_surfaced(provider):
    reply = await provider.complete(
        system="",
        messages=[
            UserMessage(text="remind me at 8 PM to call Mom"),
            ToolResultMessage(
                outcomes=[
                    ToolOutcome(
                        call_id="stub-call-1",
                        content="due_at must include a UTC offset",
                        is_error=True,
                    )
                ]
            ),
        ],
        tools=TOOLS,
    )

    assert "UTC offset" in reply.text


async def test_tools_the_server_does_not_expose_are_not_called(provider):
    reply = await provider.complete(
        system="",
        messages=[UserMessage(text="remind me at 8 PM to call Mom")],
        tools=[],
    )

    assert reply.tool_calls == []


def test_phrase_outcome_renders_a_created_reminder_in_local_time():
    content = (
        '{"id":"x","text":"call Mom",'
        '"due_at":"2026-09-19T14:30:00+00:00","completed":false}'
    )

    assert (
        phrase_outcome(content, ZONE) == "Reminder set: call Mom — Sat 19 Sep, 8:00 PM"
    )


def test_phrase_outcome_renders_an_empty_list():
    assert phrase_outcome('{"reminders":[]}', ZONE) == "You have no reminders."


def test_phrase_outcome_passes_through_non_json():
    assert phrase_outcome("plain text", ZONE) == "plain text"


async def test_stream_emits_the_reply_in_chunks_then_the_whole_message(provider):
    chunks = [
        chunk
        async for chunk in provider.stream(
            system="", messages=[UserMessage(text="hello there")], tools=TOOLS
        )
    ]
    thinking, *deltas, final = chunks

    assert isinstance(thinking, ReasoningDelta)
    assert len(deltas) > 1
    assert all(isinstance(delta, TextDelta) for delta in deltas)
    assert "".join(delta.text for delta in deltas) == final.text


async def test_stream_of_a_tool_call_carries_no_text(provider):
    chunks = [
        chunk
        async for chunk in provider.stream(
            system="",
            messages=[UserMessage(text="remind me at 8 PM to call Mom")],
            tools=TOOLS,
        )
    ]

    thinking, final = chunks
    assert isinstance(thinking, ReasoningDelta)
    assert final.tool_calls[0].name == "reminders.create"


@pytest.mark.parametrize(
    "text", ["", "one", "a b c d e f g h i", "line one\nline  two   three"]
)
def test_chunks_reassemble_to_the_original_text(text):
    assert "".join(split_into_chunks(text, 2)) == text

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import anyio
import anyio.lowlevel
import pytest

from ved_backend.acknowledgements import DEFAULT_ACKNOWLEDGEMENT, acknowledgement_for
from ved_backend.agent import TOOL_LIMIT_MESSAGE, Agent
from ved_backend.llm.base import (
    AssistantMessage,
    LLMRequestError,
    Message,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from ved_backend.llm.stub import StubProvider
from ved_backend.schemas import (
    AcknowledgementEvent,
    AgentTurn,
    ThinkingEvent,
    TokenEvent,
    ToolFinishedEvent,
    ToolStartedEvent,
)
from ved_backend.tools.toolbox import ToolNotAvailableError

CREATE = ToolSpec(name="reminders.create", description="", input_schema={})
LIST = ToolSpec(name="reminders.list", description="", input_schema={})
SEARCH = ToolSpec(name="memory.search", description="", input_schema={})


class FakeToolbox:
    def __init__(self, results=None, tools=(CREATE,)):
        self.tools = list(tools)
        self.calls: list[tuple[str, dict]] = []
        self._results = results or {}

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name not in {tool.name for tool in self.tools}:
            raise ToolNotAvailableError(name)
        return self._results.get(name, ('{"id":"r1"}', False))


class ScriptedProvider:
    model = "scripted"

    def __init__(self, replies: list[AssistantMessage]):
        self._replies = list(replies)
        self.seen: list[list[Message]] = []
        self.systems: list[str] = []

    async def complete(self, *, system, messages, tools):
        self.seen.append(list(messages))
        self.systems.append(system)
        return self._replies.pop(0)

    async def stream(self, *, system, messages, tools):
        await anyio.lowlevel.checkpoint()
        reply = await self.complete(system=system, messages=messages, tools=tools)
        for word in reply.text.split(" "):
            yield TextDelta(text=word + " ")
        yield reply


class FailingMidStreamProvider:
    model = "failing"

    async def stream(self, *, system, messages, tools):
        yield TextDelta(text="Partial ")
        raise LLMRequestError("connection dropped")


def create_call(**arguments):
    return AssistantMessage(
        tool_calls=[ToolCall(id="c1", name="reminders.create", arguments=arguments)]
    )


@pytest.fixture
def toolbox():
    return FakeToolbox()


async def test_plain_reply_skips_the_toolbox(toolbox):
    agent = Agent(
        ScriptedProvider([AssistantMessage(text="hello")]),
        toolbox,
        max_tool_rounds=4,
        timezone="Asia/Kolkata",
    )

    reply = await agent.run("hi")

    assert reply.text == "hello"
    assert reply.tool_calls == []
    assert toolbox.calls == []


async def test_tool_call_is_executed_then_summarised(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="Reminder set.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    reply = await agent.run("remind me to call Mom")

    assert reply.text == "Reminder set."
    assert toolbox.calls == [("reminders.create", {"text": "call Mom"})]
    assert reply.tool_calls[0].name == "reminders.create"
    assert reply.tool_calls[0].failed is False


async def test_the_model_sees_the_tool_result(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="done")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    await agent.run("remind me to call Mom")

    final_turn = provider.seen[-1]
    assert final_turn[-1].outcomes[0].content == '{"id":"r1"}'


async def test_tool_errors_are_returned_to_the_model_not_raised():
    toolbox = FakeToolbox(
        results={"reminders.create": ("due_at must include a UTC offset", True)}
    )
    provider = ScriptedProvider(
        [create_call(due_at="8pm"), AssistantMessage(text="Let me fix that.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    reply = await agent.run("remind me at 8pm")

    assert reply.tool_calls[0].failed is True
    assert provider.seen[-1][-1].outcomes[0].is_error is True


async def test_unknown_tools_do_not_crash_the_turn():
    toolbox = FakeToolbox(tools=[])
    provider = ScriptedProvider([create_call(), AssistantMessage(text="sorry")])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    reply = await agent.run("remind me")

    assert reply.text == "sorry"
    assert reply.tool_calls[0].failed is True


async def test_a_looping_model_is_cut_off(toolbox):
    provider = ScriptedProvider([create_call(text="again") for _ in range(4)])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    reply = await agent.run("remind me")

    assert reply.text == TOOL_LIMIT_MESSAGE
    assert len(toolbox.calls) == 4


async def test_system_prompt_tells_the_model_the_current_time(toolbox):
    provider = ScriptedProvider([AssistantMessage(text="hi")])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    await agent.run("hello")

    prompt = provider.systems[0]
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    assert str(now.year) in prompt
    assert now.strftime("%B") in prompt
    assert "Asia/Kolkata" in prompt
    assert "+0530" in prompt


async def collect(agent, prompt):
    return [event async for event in agent.stream(prompt)]


async def test_stream_yields_tokens_in_order_then_the_turn(toolbox):
    provider = ScriptedProvider([AssistantMessage(text="Good morning to you")])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "hi")

    *tokens, final = events
    assert all(isinstance(token, TokenEvent) for token in tokens)
    assert "".join(token.text for token in tokens).strip() == "Good morning to you"
    assert final == AgentTurn(text="Good morning to you", model="scripted")


async def test_stream_announces_each_tool_around_its_execution(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="Reminder set.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me to call Mom")

    kinds = [type(event) for event in events]
    started = kinds.index(ToolStartedEvent)
    assert kinds[started + 1] is ToolFinishedEvent
    assert all(kind is TokenEvent for kind in kinds[started + 2 : -1])
    assert events[started] == ToolStartedEvent(
        name="reminders.create", arguments={"text": "call Mom"}
    )
    assert events[-1].tool_calls[0].name == "reminders.create"


async def test_stream_reports_a_failed_tool_and_feeds_the_error_back():
    toolbox = FakeToolbox(
        results={"reminders.create": ("due_at must include a UTC offset", True)}
    )
    provider = ScriptedProvider(
        [create_call(due_at="8pm"), AssistantMessage(text="Let me fix that.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me at 8pm")

    finished = next(e for e in events if isinstance(e, ToolFinishedEvent))
    assert finished.failed is True
    assert provider.seen[-1][-1].outcomes[0].is_error is True


async def test_stream_stops_a_looping_model(toolbox):
    provider = ScriptedProvider([create_call(text="again") for _ in range(3)])
    agent = Agent(provider, toolbox, max_tool_rounds=3, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me")

    assert events[-1].text == TOOL_LIMIT_MESSAGE
    assert sum(isinstance(e, ToolStartedEvent) for e in events) == 3


async def test_stream_raises_when_the_model_fails_mid_reply(toolbox):
    agent = Agent(
        FailingMidStreamProvider(),
        toolbox,
        max_tool_rounds=4,
        timezone="Asia/Kolkata",
    )
    received = []

    with pytest.raises(LLMRequestError, match="connection dropped"):
        async for event in agent.stream("hi"):
            received.append(event)

    assert received == [TokenEvent(text="Partial ")]


async def test_stream_sends_the_current_time_every_round(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="done")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    await collect(agent, "remind me")

    assert len(provider.systems) == 2
    assert all("Asia/Kolkata" in system for system in provider.systems)


class SlowToolbox(FakeToolbox):
    def __init__(self):
        super().__init__()
        self.started = anyio.Event()
        self.release = anyio.Event()
        self.finished = False

    async def call(self, name, arguments):
        self.started.set()
        await self.release.wait()
        self.finished = True
        return await super().call(name, arguments)


async def test_a_cancelled_stream_lets_a_running_tool_finish():
    toolbox = SlowToolbox()
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="done")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")
    received = []

    async def consume():
        async for event in agent.stream("remind me"):
            received.append(event)

    async with anyio.create_task_group() as group:
        group.start_soon(consume)
        await toolbox.started.wait()
        group.cancel_scope.cancel()
        toolbox.release.set()

    assert toolbox.finished is True
    assert not any(isinstance(event, AgentTurn) for event in received)


class ReasoningProvider(ScriptedProvider):
    def __init__(self, replies, reasoning_chunks=3):
        super().__init__(replies)
        self._reasoning_chunks = reasoning_chunks

    async def stream(self, *, system, messages, tools):
        for _ in range(self._reasoning_chunks):
            yield ReasoningDelta()
        async for chunk in super().stream(
            system=system, messages=messages, tools=tools
        ):
            yield chunk


async def test_thinking_is_announced_once_before_the_first_token(toolbox):
    provider = ReasoningProvider([AssistantMessage(text="Good morning")])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "hi")

    assert isinstance(events[0], ThinkingEvent)
    assert sum(isinstance(event, ThinkingEvent) for event in events) == 1
    assert isinstance(events[1], TokenEvent)
    assert events[-1].text == "Good morning"


async def test_thinking_is_announced_again_in_each_round_that_reasons(toolbox):
    provider = ReasoningProvider(
        [create_call(text="call Mom"), AssistantMessage(text="Reminder set.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me to call Mom")

    kinds = [type(event) for event in events]
    assert kinds.count(ThinkingEvent) == 2
    assert kinds.index(ThinkingEvent, 1) > kinds.index(ToolFinishedEvent)


async def test_run_ignores_thinking_and_returns_only_the_answer(toolbox):
    provider = ReasoningProvider([AssistantMessage(text="hello")])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    reply = await agent.run("hi")

    assert reply.text == "hello"


async def test_a_tool_call_first_round_is_acknowledged_from_its_domain(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="Reminder set.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me to call Mom")

    kinds = [type(event) for event in events]
    assert kinds.count(AcknowledgementEvent) == 1
    assert kinds.index(AcknowledgementEvent) < kinds.index(ToolStartedEvent)
    acknowledgement = events[kinds.index(AcknowledgementEvent)]
    assert acknowledgement.text == acknowledgement_for("reminders.create")


async def test_a_direct_answer_is_not_acknowledged(toolbox):
    agent = Agent(
        ScriptedProvider([AssistantMessage(text="hello there")]),
        toolbox,
        max_tool_rounds=4,
        timezone="Asia/Kolkata",
    )

    events = await collect(agent, "hi")

    assert not any(isinstance(event, AcknowledgementEvent) for event in events)


async def test_only_the_opening_round_is_acknowledged(toolbox):
    provider = ScriptedProvider(
        [create_call(text="a"), create_call(text="b"), AssistantMessage(text="ok")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me twice")

    assert sum(isinstance(event, AcknowledgementEvent) for event in events) == 1


async def test_a_tool_call_that_already_spoke_is_not_acknowledged(toolbox):
    spoken_call = AssistantMessage(
        text="Let me set that up.",
        tool_calls=[ToolCall(id="c1", name="reminders.create", arguments={})],
    )
    provider = ScriptedProvider([spoken_call, AssistantMessage(text="Done.")])
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "remind me")

    assert not any(isinstance(event, AcknowledgementEvent) for event in events)


@pytest.mark.parametrize(
    ("tool", "expected"),
    [
        ("reminders.create", "Setting that up…"),
        ("reminders.reschedule", "Setting that up…"),
        ("memory.search", "Let me look back…"),
        ("web.search", "Let me check that…"),
        ("web.fetch", "Let me check that…"),
        ("weather.today", DEFAULT_ACKNOWLEDGEMENT),
        ("undotted", DEFAULT_ACKNOWLEDGEMENT),
    ],
)
def test_acknowledgement_is_chosen_by_tool_then_domain(tool, expected):
    assert acknowledgement_for(tool) == expected


class StaggeredToolbox(FakeToolbox):
    def __init__(self, delays, failures=(), crashes=()):
        super().__init__(tools=[CREATE, LIST, SEARCH])
        self._delays = delays
        self._failures = set(failures)
        self._crashes = set(crashes)
        self.finish_order: list[str] = []

    async def call(self, name, arguments):
        await anyio.sleep(self._delays[name])
        self.finish_order.append(name)
        if name in self._crashes:
            raise RuntimeError("server went away")
        if name in self._failures:
            return f"{name} rejected its arguments", True
        return f"{name} result", False


def several_calls(*names):
    return AssistantMessage(
        tool_calls=[
            ToolCall(id=f"c{index}", name=name, arguments={})
            for index, name in enumerate(names)
        ]
    )


SLOW_SECONDS = 0.3
FAST_SECONDS = 0.05
MIDDLE_SECONDS = 0.15


async def test_calls_in_one_round_run_concurrently_and_keep_call_order():
    toolbox = StaggeredToolbox(
        {
            "reminders.create": SLOW_SECONDS,
            "reminders.list": FAST_SECONDS,
            "memory.search": MIDDLE_SECONDS,
        }
    )
    provider = ScriptedProvider(
        [
            several_calls("reminders.create", "reminders.list", "memory.search"),
            AssistantMessage(text="done"),
        ]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    started_at = time.perf_counter()
    events = await collect(agent, "do three things")
    elapsed = time.perf_counter() - started_at

    assert elapsed < SLOW_SECONDS + FAST_SECONDS + MIDDLE_SECONDS
    assert toolbox.finish_order == [
        "reminders.list",
        "memory.search",
        "reminders.create",
    ]
    outcomes = provider.seen[-1][-1].outcomes
    assert [outcome.call_id for outcome in outcomes] == ["c0", "c1", "c2"]
    assert [outcome.content for outcome in outcomes] == [
        "reminders.create result",
        "reminders.list result",
        "memory.search result",
    ]
    assert [call.name for call in events[-1].tool_calls] == [
        "reminders.create",
        "reminders.list",
        "memory.search",
    ]


async def test_every_call_is_started_before_any_finishes_and_finishes_as_it_completes():
    toolbox = StaggeredToolbox(
        {"reminders.create": SLOW_SECONDS, "reminders.list": FAST_SECONDS}
    )
    provider = ScriptedProvider(
        [
            several_calls("reminders.create", "reminders.list"),
            AssistantMessage(text="done"),
        ]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "two things")

    tool_events = [
        event
        for event in events
        if isinstance(event, ToolStartedEvent | ToolFinishedEvent)
    ]
    assert tool_events == [
        ToolStartedEvent(name="reminders.create", arguments={}),
        ToolStartedEvent(name="reminders.list", arguments={}),
        ToolFinishedEvent(name="reminders.list", failed=False),
        ToolFinishedEvent(name="reminders.create", failed=False),
    ]


async def test_a_failing_call_does_not_affect_its_siblings():
    toolbox = StaggeredToolbox(
        {
            "reminders.create": FAST_SECONDS,
            "reminders.list": MIDDLE_SECONDS,
            "memory.search": FAST_SECONDS,
        },
        failures={"reminders.create"},
        crashes={"memory.search"},
    )
    provider = ScriptedProvider(
        [
            several_calls("reminders.create", "reminders.list", "memory.search"),
            AssistantMessage(text="partly"),
        ]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    events = await collect(agent, "three things")

    outcomes = provider.seen[-1][-1].outcomes
    assert [outcome.is_error for outcome in outcomes] == [True, False, True]
    assert outcomes[1].content == "reminders.list result"
    assert outcomes[2].content == "memory.search failed unexpectedly"
    finished = {
        event.name: event.failed
        for event in events
        if isinstance(event, ToolFinishedEvent)
    }
    assert finished == {
        "reminders.create": True,
        "reminders.list": False,
        "memory.search": True,
    }
    assert events[-1].text == "partly"


class BlockingToolbox(FakeToolbox):
    def __init__(self):
        super().__init__(tools=[CREATE, LIST])
        self.release = anyio.Event()
        self.started: set[str] = set()
        self.finished: set[str] = set()

    async def call(self, name, arguments):
        self.started.add(name)
        await self.release.wait()
        self.finished.add(name)
        return "ok", False


async def test_a_cancelled_stream_lets_every_running_call_finish():
    toolbox = BlockingToolbox()
    provider = ScriptedProvider(
        [
            several_calls("reminders.create", "reminders.list"),
            AssistantMessage(text="done"),
        ]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4, timezone="Asia/Kolkata")

    async def consume():
        async for _ in agent.stream("two things"):
            pass

    async with anyio.create_task_group() as group:
        group.start_soon(consume)
        while len(toolbox.started) < 2:
            await anyio.sleep(0)
        group.cancel_scope.cancel()
        toolbox.release.set()

    assert toolbox.finished == {"reminders.create", "reminders.list"}


async def test_the_stub_exercises_thinking_and_acknowledgement():
    toolbox = FakeToolbox(
        results={
            "reminders.create": (
                '{"id":"x","text":"call Mom",'
                '"due_at":"2026-09-19T20:00:00+05:30","completed":false}',
                False,
            )
        }
    )
    agent = Agent(
        StubProvider(timezone="Asia/Kolkata"),
        toolbox,
        max_tool_rounds=4,
        timezone="Asia/Kolkata",
    )

    events = await collect(agent, "remind me at 8 PM to call Mom")

    kinds = [type(event) for event in events]
    assert kinds[:3] == [ThinkingEvent, AcknowledgementEvent, ToolStartedEvent]
    assert "Reminder set" in events[-1].text

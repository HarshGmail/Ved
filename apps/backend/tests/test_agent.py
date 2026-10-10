from datetime import datetime
from zoneinfo import ZoneInfo

import anyio
import anyio.lowlevel
import pytest

from ved_backend.agent import TOOL_LIMIT_MESSAGE, Agent
from ved_backend.llm.base import (
    AssistantMessage,
    LLMRequestError,
    Message,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from ved_backend.schemas import (
    AgentTurn,
    TokenEvent,
    ToolFinishedEvent,
    ToolStartedEvent,
)
from ved_backend.tools.toolbox import ToolNotAvailableError

CREATE = ToolSpec(name="reminders.create", description="", input_schema={})


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

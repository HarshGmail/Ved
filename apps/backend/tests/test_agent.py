import pytest

from ved_backend.agent import TOOL_LIMIT_MESSAGE, Agent
from ved_backend.llm.base import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolSpec,
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

    async def complete(self, *, system, messages, tools):
        self.seen.append(list(messages))
        return self._replies.pop(0)


def create_call(**arguments):
    return AssistantMessage(
        tool_calls=[ToolCall(id="c1", name="reminders.create", arguments=arguments)]
    )


@pytest.fixture
def toolbox():
    return FakeToolbox()


async def test_plain_reply_skips_the_toolbox(toolbox):
    agent = Agent(
        ScriptedProvider([AssistantMessage(text="hello")]), toolbox, max_tool_rounds=4
    )

    reply = await agent.run("hi")

    assert reply.text == "hello"
    assert reply.tool_calls == []
    assert toolbox.calls == []


async def test_tool_call_is_executed_then_summarised(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="Reminder set.")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4)

    reply = await agent.run("remind me to call Mom")

    assert reply.text == "Reminder set."
    assert toolbox.calls == [("reminders.create", {"text": "call Mom"})]
    assert reply.tool_calls[0].name == "reminders.create"
    assert reply.tool_calls[0].failed is False


async def test_the_model_sees_the_tool_result(toolbox):
    provider = ScriptedProvider(
        [create_call(text="call Mom"), AssistantMessage(text="done")]
    )
    agent = Agent(provider, toolbox, max_tool_rounds=4)

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
    agent = Agent(provider, toolbox, max_tool_rounds=4)

    reply = await agent.run("remind me at 8pm")

    assert reply.tool_calls[0].failed is True
    assert provider.seen[-1][-1].outcomes[0].is_error is True


async def test_unknown_tools_do_not_crash_the_turn():
    toolbox = FakeToolbox(tools=[])
    provider = ScriptedProvider([create_call(), AssistantMessage(text="sorry")])
    agent = Agent(provider, toolbox, max_tool_rounds=4)

    reply = await agent.run("remind me")

    assert reply.text == "sorry"
    assert reply.tool_calls[0].failed is True


async def test_a_looping_model_is_cut_off(toolbox):
    provider = ScriptedProvider([create_call(text="again") for _ in range(4)])
    agent = Agent(provider, toolbox, max_tool_rounds=4)

    reply = await agent.run("remind me")

    assert reply.text == TOOL_LIMIT_MESSAGE
    assert len(toolbox.calls) == 4

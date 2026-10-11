import json
import uuid

import pytest
from fastapi.testclient import TestClient

from ved_backend.llm.base import LLMRequestError, ToolSpec
from ved_backend.main import agent_message_stream, app
from ved_backend.memory import ConversationNotFoundError
from ved_backend.schemas import (
    AcknowledgementEvent,
    AgentReply,
    AgentRequest,
    AgentTurn,
    ThinkingEvent,
    TokenEvent,
    ToolFinishedEvent,
    ToolInvocation,
    ToolStartedEvent,
)

CREATE = ToolSpec(name="reminders.create", description="", input_schema={})
CONVERSATION_ID = uuid.uuid4()

client = TestClient(app)


class FakeAgent:
    def __init__(self, turn: AgentTurn):
        self._turn = turn
        self.prompts: list[str] = []
        self.histories: list[list] = []

    async def run(self, prompt: str, history=()):
        self.prompts.append(prompt)
        self.histories.append(list(history))
        return self._turn

    async def stream(self, prompt: str, history=()):
        self.prompts.append(prompt)
        self.histories.append(list(history))
        for call in self._turn.tool_calls:
            yield ToolStartedEvent(name=call.name, arguments=call.arguments)
            yield ToolFinishedEvent(name=call.name, failed=call.failed)
        for word in self._turn.text.split(" "):
            yield TokenEvent(text=word + " ")
        yield self._turn


class FakeToolbox:
    def __init__(self, tools):
        self.tools = list(tools)


class FakeStore:
    def __init__(self, known=(), history=()):
        self._known = set(known)
        self._history = list(history)
        self.started: list[str] = []
        self.recorded: list[dict] = []

    async def start(self, prompt: str) -> uuid.UUID:
        self.started.append(prompt)
        self._known.add(CONVERSATION_ID)
        return CONVERSATION_ID

    async def history(self, conversation_id: uuid.UUID):
        if conversation_id not in self._known:
            raise ConversationNotFoundError(conversation_id)
        return list(self._history)

    async def record_turn(self, conversation_id, **kwargs):
        if conversation_id not in self._known:
            raise ConversationNotFoundError(conversation_id)
        self.recorded.append({"conversation_id": conversation_id, **kwargs})


@pytest.fixture
def wired():
    def _wire(turn=None, tools=(CREATE,), store=None):
        agent = FakeAgent(turn or AgentTurn(text="ok", model="stub-rules-v1"))
        app.state.agent = agent
        app.state.toolbox = FakeToolbox(tools)
        app.state.conversations = store or FakeStore()
        app.state.indexer = None
        return agent, app.state.conversations

    yield _wire
    app.state.agent = None
    app.state.toolbox = None
    app.state.conversations = None


def post(prompt: str, conversation_id: uuid.UUID | None = None):
    body: dict = {"prompt": prompt}
    if conversation_id is not None:
        body["conversation_id"] = str(conversation_id)
    return client.post("/agent/message", json=body)


def test_message_returns_the_agent_reply(wired):
    wired(
        AgentTurn(
            text="Reminder set for 8 PM.",
            model="stub-rules-v1",
            tool_calls=[
                ToolInvocation(
                    name="reminders.create",
                    arguments={"text": "call Mom"},
                    failed=False,
                )
            ],
        )
    )

    response = post("remind me at 8 PM")

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Reminder set for 8 PM."
    assert body["model"] == "stub-rules-v1"
    assert body["tool_calls"][0]["name"] == "reminders.create"


class RecordingIndexer:
    def __init__(self) -> None:
        self.triggered = 0

    def trigger(self) -> None:
        self.triggered += 1


def test_a_recorded_turn_nudges_the_indexer(wired):
    wired()
    indexer = RecordingIndexer()
    app.state.indexer = indexer

    post("remind me at 8 PM")

    assert indexer.triggered == 1


def test_prompt_reaches_the_agent_unchanged(wired):
    agent, _ = wired()

    post("  remind me at 8 PM  ")

    assert agent.prompts == ["  remind me at 8 PM  "]


def test_empty_prompt_is_rejected(wired):
    wired()

    assert post("").status_code == 422


def test_unavailable_tools_return_service_unavailable(wired):
    wired(tools=[])

    assert post("remind me").status_code == 503


def test_a_first_message_starts_a_conversation_and_returns_its_id(wired):
    _, store = wired()

    response = post("remind me at 8 PM")

    assert response.json()["conversation_id"] == str(CONVERSATION_ID)
    assert store.started == ["remind me at 8 PM"]


def test_a_follow_up_replays_history_into_the_agent(wired):
    from ved_backend.llm.base import AssistantMessage, UserMessage

    history = [UserMessage(text="remind me at 8 PM"), AssistantMessage(text="Done.")]
    agent, store = wired(store=FakeStore(known=[CONVERSATION_ID], history=history))

    response = post("actually make it 9", CONVERSATION_ID)

    assert response.status_code == 200
    assert [m.text for m in agent.histories[0]] == ["remind me at 8 PM", "Done."]
    assert store.started == []


def test_every_turn_is_recorded(wired):
    turn = AgentTurn(text="Reminder set.", model="stub-rules-v1")
    _, store = wired(turn)

    post("remind me at 8 PM")

    assert store.recorded[0]["prompt"] == "remind me at 8 PM"
    assert store.recorded[0]["answer"] == "Reminder set."
    assert store.recorded[0]["model"] == "stub-rules-v1"


def test_an_unknown_conversation_is_a_404(wired):
    wired(store=FakeStore(known=[]))

    assert post("hello", uuid.uuid4()).status_code == 404


def test_a_malformed_conversation_id_is_rejected(wired):
    wired()

    response = client.post(
        "/agent/message", json={"prompt": "hi", "conversation_id": "not-a-uuid"}
    )

    assert response.status_code == 422


def test_a_failed_turn_leaves_no_empty_conversation(wired):
    class FailingAgent:
        async def run(self, prompt, history=()):
            raise LLMRequestError("model is down")

    _, store = wired()
    app.state.agent = FailingAgent()

    response = post("remind me at 8 PM")

    assert response.status_code == 503
    assert store.started == []
    assert store.recorded == []


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(
            line.removeprefix("event: ") for line in lines if line.startswith("event:")
        )
        data = "\n".join(
            line.removeprefix("data: ") for line in lines if line.startswith("data:")
        )
        events.append((name, json.loads(data)))
    return events


def post_stream(prompt: str, conversation_id: uuid.UUID | None = None):
    body: dict = {"prompt": prompt}
    if conversation_id is not None:
        body["conversation_id"] = str(conversation_id)
    return client.post("/agent/message/stream", json=body)


REMINDER_TURN = AgentTurn(
    text="Reminder set for 8 PM.",
    model="stub-rules-v1",
    tool_calls=[
        ToolInvocation(
            name="reminders.create", arguments={"text": "call Mom"}, failed=False
        )
    ],
)


def test_stream_sends_tool_events_tokens_then_a_done_reply(wired):
    wired(REMINDER_TURN)

    response = post_stream("remind me at 8 PM")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[:2] == ["tool", "tool_result"]
    assert set(names[2:-1]) == {"token"}
    assert names[-1] == "done"
    assert events[0][1] == {
        "name": "reminders.create",
        "arguments": {"text": "call Mom"},
    }
    assert events[1][1] == {"name": "reminders.create", "failed": False}
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens.strip() == "Reminder set for 8 PM."


def test_stream_done_payload_is_an_agent_reply(wired):
    wired(REMINDER_TURN)

    _, done = parse_sse(post_stream("remind me at 8 PM").text)[-1]

    reply = AgentReply.model_validate(done)
    assert reply.text == "Reminder set for 8 PM."
    assert reply.conversation_id == CONVERSATION_ID
    assert reply.tool_calls == REMINDER_TURN.tool_calls


def test_stream_records_the_turn_once_and_nudges_the_indexer(wired):
    _, store = wired(REMINDER_TURN)
    indexer = RecordingIndexer()
    app.state.indexer = indexer

    post_stream("remind me at 8 PM")

    assert store.started == ["remind me at 8 PM"]
    assert len(store.recorded) == 1
    assert store.recorded[0]["answer"] == "Reminder set for 8 PM."
    assert indexer.triggered == 1


def test_stream_follow_up_replays_history(wired):
    from ved_backend.llm.base import AssistantMessage, UserMessage

    history = [UserMessage(text="remind me at 8 PM"), AssistantMessage(text="Done.")]
    agent, store = wired(store=FakeStore(known=[CONVERSATION_ID], history=history))

    post_stream("actually make it 9", CONVERSATION_ID)

    assert [m.text for m in agent.histories[0]] == ["remind me at 8 PM", "Done."]
    assert store.started == []


def test_stream_rejects_an_unknown_conversation_before_streaming(wired):
    wired(store=FakeStore(known=[]))

    response = post_stream("hello", uuid.uuid4())

    assert response.status_code == 404
    assert "No conversation" in response.json()["detail"]


def test_stream_without_tools_is_service_unavailable(wired):
    wired(tools=[])

    assert post_stream("remind me").status_code == 503


class FailingMidStreamAgent:
    async def stream(self, prompt, history=()):
        yield TokenEvent(text="Partial ")
        raise LLMRequestError("model is down")


def test_stream_failure_sends_an_error_event_and_records_nothing(wired):
    _, store = wired()
    app.state.agent = FailingMidStreamAgent()

    events = parse_sse(post_stream("remind me at 8 PM").text)

    assert events[-1] == ("error", {"detail": "model is down"})
    assert "done" not in [name for name, _ in events]
    assert store.started == []
    assert store.recorded == []


async def test_a_client_leaving_mid_stream_records_nothing(wired):
    _, store = wired(REMINDER_TURN)
    stream = agent_message_stream(AgentRequest(prompt="remind me at 8 PM"), [])

    first = await anext(stream)
    await stream.aclose()

    assert first.event == "tool"
    assert store.started == []
    assert store.recorded == []


class ThinkingAgent:
    async def stream(self, prompt, history=()):
        yield ThinkingEvent()
        yield AcknowledgementEvent(text="Setting that up…")
        yield ToolStartedEvent(name="reminders.create", arguments={})
        yield ToolFinishedEvent(name="reminders.create", failed=False)
        yield TokenEvent(text="Done.")
        yield AgentTurn(text="Done.", model="stub-rules-v1")


def test_stream_names_thinking_and_acknowledgement_events(wired):
    wired()
    app.state.agent = ThinkingAgent()

    events = parse_sse(post_stream("remind me").text)

    assert [name for name, _ in events] == [
        "thinking",
        "ack",
        "tool",
        "tool_result",
        "token",
        "done",
    ]
    assert events[0][1] == {}
    assert events[1][1] == {"text": "Setting that up…"}

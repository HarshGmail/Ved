import uuid

import pytest
from fastapi.testclient import TestClient

from ved_backend.llm.base import ToolSpec
from ved_backend.llm.openai_compatible import LLMRequestError
from ved_backend.main import app
from ved_backend.memory import ConversationNotFoundError
from ved_backend.schemas import AgentTurn, ToolInvocation

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

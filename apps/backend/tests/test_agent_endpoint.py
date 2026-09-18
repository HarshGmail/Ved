import pytest
from fastapi.testclient import TestClient

from ved_backend.llm.base import ToolSpec
from ved_backend.main import app
from ved_backend.schemas import AgentReply, ToolInvocation

CREATE = ToolSpec(name="reminders.create", description="", input_schema={})

client = TestClient(app)


class FakeAgent:
    def __init__(self, reply: AgentReply):
        self._reply = reply
        self.prompts: list[str] = []

    async def run(self, prompt: str) -> AgentReply:
        self.prompts.append(prompt)
        return self._reply


class FakeToolbox:
    def __init__(self, tools):
        self.tools = list(tools)


@pytest.fixture
def wired():
    def _wire(reply, tools=(CREATE,)):
        agent = FakeAgent(reply)
        app.state.agent = agent
        app.state.toolbox = FakeToolbox(tools)
        return agent

    yield _wire
    app.state.agent = None
    app.state.toolbox = None


def test_message_returns_the_agent_reply(wired):
    wired(
        AgentReply(
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

    response = client.post("/agent/message", json={"prompt": "remind me at 8 PM"})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Reminder set for 8 PM."
    assert body["model"] == "stub-rules-v1"
    assert body["tool_calls"][0]["name"] == "reminders.create"


def test_prompt_reaches_the_agent_unchanged(wired):
    agent = wired(AgentReply(text="ok", model="stub-rules-v1"))

    client.post("/agent/message", json={"prompt": "  remind me at 8 PM  "})

    assert agent.prompts == ["  remind me at 8 PM  "]


def test_empty_prompt_is_rejected(wired):
    wired(AgentReply(text="ok", model="stub-rules-v1"))

    response = client.post("/agent/message", json={"prompt": ""})

    assert response.status_code == 422


def test_unavailable_tools_return_service_unavailable(wired):
    wired(AgentReply(text="ok", model="stub-rules-v1"), tools=[])

    response = client.post("/agent/message", json={"prompt": "remind me"})

    assert response.status_code == 503

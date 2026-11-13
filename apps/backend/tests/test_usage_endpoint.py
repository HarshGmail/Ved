import os

import pytest
from fastapi.testclient import TestClient

from ved_backend.config import settings
from ved_backend.llm.anthropic_provider import AnthropicProvider
from ved_backend.main import app
from ved_backend.usage import UsageStore
from ved_backend.users import current_user

pytestmark = pytest.mark.skipif(
    not os.environ.get("VED_TEST_DATABASE_URL"),
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)

OWNER_EMAIL = "first@example.com"
HAIKU = "claude-haiku-5-5"


@pytest.fixture
def owner_is_first(monkeypatch):
    monkeypatch.setattr(settings, "owner_email", OWNER_EMAIL)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")


def client_as(session_factory, user) -> TestClient:
    app.dependency_overrides[current_user] = lambda: user
    app.state.usage = UsageStore(session_factory, timezone=settings.timezone)
    app.state.llm = AnthropicProvider(
        api_key="sk-ant-test", model=HAIKU, max_tokens=512
    )
    return TestClient(app)


@pytest.fixture
def owner_api(session_factory, user, owner_is_first):
    yield client_as(session_factory, user)
    app.dependency_overrides.pop(current_user, None)


@pytest.fixture
def guest_api(session_factory, other_user, owner_is_first):
    yield client_as(session_factory, other_user)
    app.dependency_overrides.pop(current_user, None)


def test_the_owner_sets_the_balance_and_sees_what_is_left(owner_api):
    response = owner_api.put("/usage/claude/balance", json={"balance_usd": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["balance_usd"] == 5.0
    assert body["remaining_usd"] == 5.0
    assert body["spent_since_balance_usd"] == 0.0
    assert body["tracking"] is True
    assert body["model"] == HAIKU
    assert body["can_edit"] is True
    assert body["balance_set_at"] is not None


def test_a_guest_cannot_set_the_balance(guest_api):
    response = guest_api.put("/usage/claude/balance", json={"balance_usd": 5})

    assert response.status_code == 403
    assert "owner" in response.json()["detail"]


def test_a_guest_can_read_usage_but_not_edit_it(guest_api):
    response = guest_api.get("/usage/claude")

    assert response.status_code == 200
    body = response.json()
    assert body["can_edit"] is False
    assert body["balance_usd"] is None
    assert body["remaining_usd"] is None


def test_a_guest_put_does_not_change_the_stored_balance(
    session_factory, user, other_user, owner_is_first
):
    api = client_as(session_factory, user)
    api.put("/usage/claude/balance", json={"balance_usd": 8})
    app.dependency_overrides[current_user] = lambda: other_user

    guest_response = api.put("/usage/claude/balance", json={"balance_usd": 1})
    app.dependency_overrides[current_user] = lambda: user

    assert guest_response.status_code == 403
    assert api.get("/usage/claude").json()["balance_usd"] == 8.0
    app.dependency_overrides.pop(current_user, None)


@pytest.mark.parametrize("amount", [-1, 10_001])
def test_a_balance_outside_the_allowed_range_is_rejected(owner_api, amount):
    response = owner_api.put("/usage/claude/balance", json={"balance_usd": amount})

    assert response.status_code == 422


def test_usage_reports_tracking_off_for_the_local_model(owner_api, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")

    body = owner_api.get("/usage/claude").json()

    assert body["tracking"] is False

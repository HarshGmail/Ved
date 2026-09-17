import pytest
from fastapi.testclient import TestClient

from ved_backend import main
from ved_backend.config import settings
from ved_backend.main import app

client = TestClient(app)


@pytest.fixture
def database_state(monkeypatch):
    def _set(state):
        async def fake_check():
            return state

        monkeypatch.setattr(main, "check_database", fake_check)

    return _set


def test_health_reports_ok_when_database_reachable(database_state):
    database_state("ok")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": settings.version,
        "database": "ok",
    }


def test_health_degrades_when_database_unreachable(database_state):
    database_state("down")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "down"


def test_health_allows_web_client_origin(database_state):
    database_state("ok")
    origin = "http://localhost:3000"

    response = client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin

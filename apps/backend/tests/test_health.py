from fastapi.testclient import TestClient

from ved_backend.config import settings
from ved_backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.version}


def test_health_allows_web_client_origin():
    origin = "http://localhost:3000"
    response = client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin

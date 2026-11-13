import httpx2
import pytest

from ved_snappy.auth import BearerTokenMiddleware, bearer_token
from ved_snappy.server import create_app


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc123", "abc123"),
        ("bearer   abc123  ", "abc123"),
        ("BEARER abc123", "abc123"),
        ("Basic abc123", None),
        ("Bearer", None),
        ("Bearer    ", None),
        ("", None),
        (None, None),
    ],
)
def test_bearer_token_is_read_only_from_a_bearer_header(header, expected):
    assert bearer_token(header) == expected


async def test_requests_without_a_token_never_reach_the_app():
    reached = []

    async def inner(scope, receive, send):
        reached.append(scope)

    responses = []

    async def send(message):
        responses.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "headers": [(b"authorization", b"Basic nope")]}
    await BearerTokenMiddleware(inner)(scope, receive, send)

    assert reached == []
    assert responses[0]["status"] == 401


async def test_requests_with_a_token_pass_through():
    reached = []

    async def inner(scope, receive, send):
        reached.append(scope)

    async def send(message):
        pass

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "headers": [(b"authorization", b"Bearer key")]}
    await BearerTokenMiddleware(inner)(scope, receive, send)

    assert reached == [scope]


async def test_the_mcp_endpoint_answers_401_without_a_key():
    transport = httpx2.ASGITransport(app=create_app())
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://snappy.test"
    ) as client:
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "Bearer token" in response.text

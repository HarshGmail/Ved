import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ved_backend import access, main
from ved_backend.access import ACCESS_HEADER, check_access, require_access
from ved_backend.config import Settings

TEAM = "family.cloudflareaccess.com"
AUDIENCE = "aud-tag"
ADMIN = "harsh@example.com"
ISSUER = f"https://{TEAM}"
FIVE_MINUTES = 300


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def resolver(private_key):
    public_key = private_key.public_key()
    return lambda token: public_key


@pytest.fixture
def sign(private_key):
    def _sign(claims, audience=AUDIENCE, issuer=ISSUER):
        now = int(time.time())
        payload = {
            "aud": audience,
            "iss": issuer,
            "iat": now,
            "exp": now + FIVE_MINUTES,
            **claims,
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    return _sign


@pytest.fixture
def admin_settings():
    return Settings(
        auth="cloudflare-access",
        access_team_domain=TEAM,
        access_aud=AUDIENCE,
        admin_emails=[ADMIN],
    )


@pytest.fixture
def protected_client(monkeypatch, admin_settings, resolver):
    monkeypatch.setattr(access, "settings", admin_settings)
    monkeypatch.setattr(access, "cloudflare_signing_key", resolver)
    app = FastAPI(dependencies=[Depends(require_access)])

    @app.get("/protected")
    def protected():
        return {"ok": True}

    return TestClient(app)


def test_accepts_admin_email_case_insensitively(admin_settings, resolver, sign):
    result = check_access(
        sign({"email": "Harsh@Example.com"}), admin_settings, resolver
    )

    assert result.email == ADMIN
    assert result.reason is None


def test_refuses_email_not_on_list(admin_settings, resolver, sign):
    result = check_access(sign({"email": "dad@example.com"}), admin_settings, resolver)

    assert result.email is None
    assert "dad@example.com" in result.reason
    assert "not on the admin list" in result.reason


def test_refuses_wrong_audience(admin_settings, resolver, sign):
    result = check_access(
        sign({"email": ADMIN}, audience="other-app"), admin_settings, resolver
    )

    assert result.email is None
    assert "AUD tag does not match" in result.reason


def test_refuses_wrong_issuer(admin_settings, resolver, sign):
    result = check_access(
        sign({"email": ADMIN}, issuer="https://evil.example"), admin_settings, resolver
    )

    assert result.email is None
    assert "did not check out" in result.reason


def test_refuses_missing_token(admin_settings, resolver):
    result = check_access(None, admin_settings, resolver)

    assert result.email is None
    assert "No Cloudflare Access sign-in" in result.reason


def test_refuses_when_audience_is_unset(resolver, sign):
    unset = Settings(
        auth="cloudflare-access", access_team_domain=TEAM, admin_emails=[ADMIN]
    )

    result = check_access(sign({"email": ADMIN}), unset, resolver)

    assert result.email is None
    assert "no Access AUD tag" in result.reason


def test_refuses_when_no_admin_emails(resolver, sign):
    nobody = Settings(
        auth="cloudflare-access", access_team_domain=TEAM, access_aud=AUDIENCE
    )

    result = check_access(sign({"email": ADMIN}), nobody, resolver)

    assert result.email is None
    assert "No admin emails are set" in result.reason


def test_dependency_lets_requests_through_when_auth_is_off(monkeypatch):
    monkeypatch.setattr(access, "settings", Settings(auth="off"))
    app = FastAPI(dependencies=[Depends(require_access)])

    @app.get("/open")
    def open_route():
        return {"ok": True}

    response = TestClient(app).get("/open")

    assert response.status_code == 200


def test_dependency_accepts_valid_admin_token(protected_client, sign):
    response = protected_client.get(
        "/protected", headers={ACCESS_HEADER: sign({"email": ADMIN})}
    )

    assert response.status_code == 200


def test_dependency_returns_401_with_reason_when_token_missing(protected_client):
    response = protected_client.get("/protected")

    assert response.status_code == 401
    assert "No Cloudflare Access sign-in" in response.json()["detail"]


def test_health_stays_open_when_auth_is_on(monkeypatch, admin_settings):
    monkeypatch.setattr(access, "settings", admin_settings)

    async def database_up():
        return "ok"

    monkeypatch.setattr(main, "check_database", database_up)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_app_routes_refuse_requests_without_sign_in(monkeypatch, admin_settings):
    monkeypatch.setattr(access, "settings", admin_settings)

    response = TestClient(main.app).get("/conversations")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("a@x.com", ["a@x.com"]),
        ("a@x.com, b@x.com", ["a@x.com", "b@x.com"]),
        ('["a@x.com"]', ["a@x.com"]),
    ],
)
def test_admin_emails_accept_empty_comma_and_json(monkeypatch, raw, expected):
    monkeypatch.setenv("VED_ADMIN_EMAILS", raw)
    assert Settings().admin_emails == expected

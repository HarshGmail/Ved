from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

AUTHORIZATION_HEADER = b"authorization"
BEARER_SCHEME = "bearer"


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, credential = authorization.strip().partition(" ")
    token = credential.strip()
    if scheme.casefold() != BEARER_SCHEME or not token:
        return None
    return token


def authorization_of(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == AUTHORIZATION_HEADER:
            return value.decode("latin-1")
    return None


class BearerTokenMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or bearer_token(authorization_of(scope)):
            await self._app(scope, receive, send)
            return
        response = JSONResponse(
            {"error": "send the snappy API key as a Bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)

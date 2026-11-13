from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status

from ved_backend.config import Settings, settings

ACCESS_HEADER = "cf-access-jwt-assertion"
ACCESS_ALGORITHM = "RS256"
PUBLIC_PATHS = frozenset({"/health"})
NO_AUDIENCE_REASON = "Ved has no Access AUD tag yet (set VED_ACCESS_AUD)."
ANYONE_SIGNED_IN = "*"
NO_ADMINS_REASON = "No admin emails are set (set VED_ADMIN_EMAILS)."
NO_TOKEN_REASON = (
    "No Cloudflare Access sign-in reached Ved. "
    "Is the Access application on this hostname saved?"
)
WRONG_AUDIENCE_REASON = (
    "The sign-in is for a different Access application: the AUD tag does not match."
)
NO_EMAIL_LABEL = "an account without an email"

KeyResolver = Callable[[str], Any]


@dataclass(frozen=True)
class AccessResult:
    email: str | None
    reason: str | None
    name: str | None = None


@lru_cache
def jwks_client(team_domain: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs")


def cloudflare_signing_key(token: str) -> Any:
    return jwks_client(settings.access_team_domain).get_signing_key_from_jwt(token).key


def denied(reason: str) -> AccessResult:
    return AccessResult(email=None, reason=reason)


def check_access(
    token: str | None, settings: Settings, key_resolver: KeyResolver
) -> AccessResult:
    if not settings.access_aud:
        return denied(NO_AUDIENCE_REASON)
    if not settings.admin_emails:
        return denied(NO_ADMINS_REASON)
    if not token:
        return denied(NO_TOKEN_REASON)
    try:
        claims = jwt.decode(
            token,
            key_resolver(token),
            algorithms=[ACCESS_ALGORITHM],
            audience=settings.access_aud,
            issuer=f"https://{settings.access_team_domain}",
        )
    except jwt.InvalidAudienceError:
        return denied(WRONG_AUDIENCE_REASON)
    except jwt.PyJWTError as error:
        return denied(f"The sign-in token did not check out ({error}).")

    email = str(claims.get("email") or "").lower()
    admin_emails = {admin.lower() for admin in settings.admin_emails}
    if email and (ANYONE_SIGNED_IN in admin_emails or email in admin_emails):
        return AccessResult(
            email=email, reason=None, name=str(claims.get("name") or "") or None
        )
    return denied(
        f"Signed in as {email or NO_EMAIL_LABEL}, which is not on the admin list."
    )


def require_access(request: Request) -> AccessResult | None:
    if settings.auth == "off" or request.url.path in PUBLIC_PATHS:
        return None
    result = check_access(
        request.headers.get(ACCESS_HEADER), settings, cloudflare_signing_key
    )
    if result.reason is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=result.reason
        )
    return result

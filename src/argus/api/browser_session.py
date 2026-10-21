"""Request-local cookie renewal; Supabase alone validates refresh credentials."""

from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Request

REFRESH_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def renew_browser_token(request: Request, gateway: Any, token: str | None) -> str | None:
    if request.headers.get("Authorization") is not None:
        return token
    refresh = request.cookies.get("sb-refresh-token")
    if not refresh:
        return token
    old_subject = None
    if token:
        try:
            # These claims only select renewal. They never authorize a request.
            claims = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["HS256", "RS256", "ES256"],
            )
            expiry = claims.get("exp")
            if not isinstance(expiry, (int, float)) or expiry > time.time():
                return token
            old_subject = claims.get("sub")
        except jwt.PyJWTError:
            return token
    payload = gateway.refresh_browser_session(refresh)
    session = payload.get("session")
    if not isinstance(session, dict):
        raise ValueError("Missing renewed session")
    access = session.get("access_token")
    rotated = session.get("refresh_token")
    lifetime = session.get("expires_in")
    if (
        not isinstance(access, str)
        or not access
        or not isinstance(rotated, str)
        or not rotated
        or not isinstance(lifetime, int)
        or lifetime <= 0
    ):
        raise ValueError("Incomplete renewed session")
    if old_subject:
        new_claims = jwt.decode(
            access,
            options={"verify_signature": False},
            algorithms=["HS256", "RS256", "ES256"],
        )
        if new_claims.get("sub") != old_subject:
            raise ValueError("Renewed session identity mismatch")
    request.state.renewed_browser_session = payload
    request.state.access_token = access
    return access

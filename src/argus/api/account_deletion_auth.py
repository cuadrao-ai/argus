"""Who may call ``POST /api/v1/account/delete`` (Lane 6).

Every other route refuses a person whose deletion run is in flight: the account
is locked from the run's start until the auth user is gone (``auth_sessions``).
This route alone accepts that person, so a retry resumes their own run instead
of ending in a 401.

GoTrue answers ``user_banned`` for a locked account's token (the run bans it so
no refresh or sign-in works), so the token is verified here instead: its
signature against the project's signing key (the JWKS for an asymmetric key,
``SUPABASE_JWT_SECRET`` for HS256), its expiry (``exp``, ``sub`` and
``session_id`` are required), a live ``auth.sessions`` row
for its session, a deletion run in flight for its subject, and a subject that
is not a placeholder. Anything else goes through ``current_user`` unchanged.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi import Request
from loguru import logger

from argus.api import state as api_state
from argus.api.auth_sessions import (
    AuthSessionVerificationUnavailable,
    deletion_in_flight,
)
from argus.api.dependencies import current_user, problem, request_access_token
from argus.api.schemas import User

_AUDIENCE = "authenticated"
# A token without an expiry would never lapse; one without a subject or a
# session can't be tied to the live session the lock check found.
_REQUIRED = ("exp", "sub", "session_id")


class _Unverified(Exception):
    pass


def _unverified_subject(token: str) -> str | None:
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=["HS256", "RS256", "ES256"],
        )
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return str(sub) if sub else None


def verify_access_token(token: str) -> dict[str, Any]:
    """The token's claims once its signature and expiry check out, without
    asking GoTrue's /user (which refuses a banned account)."""

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise _Unverified("malformed") from exc
    alg = str(header.get("alg") or "")
    if alg == "HS256":
        secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
        if not secret:
            raise _Unverified("no_hs256_secret")
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=_AUDIENCE,
                options={"require": list(_REQUIRED)},
            )
        except jwt.PyJWTError as exc:
            raise _Unverified("hs256") from exc
    if alg not in {"RS256", "ES256"} or not header.get("kid"):
        raise _Unverified("algorithm")
    gateway = api_state.supabase_gateway
    if gateway is None:
        raise _Unverified("no_gateway")
    try:
        # supabase-py verifies an asymmetric token against the project's JWKS
        # (and its expiry) locally; it calls /user only for HS256.
        response = gateway.client.auth.get_claims(token)
    except Exception as exc:  # noqa: BLE001
        raise _Unverified("jwks") from exc
    claims = dict((response or {}).get("claims") or {})
    if claims.get("aud") not in (_AUDIENCE, [_AUDIENCE]):
        raise _Unverified("audience")
    if any(not claims.get(name) for name in _REQUIRED):
        raise _Unverified("claims")
    return claims


def _unauthorized(request: Request) -> Exception:
    return problem(
        request,
        status_code=401,
        code="unauthorized",
        title="Unauthorized",
        detail="Invalid or expired access token.",
    )


def deletion_requester(request: Request) -> User:
    """The signed-in person asking to delete their account, locked or not."""

    if any(
        os.getenv(name, "").strip().lower() == "true"
        for name in ("NEXT_PUBLIC_MOCK_AUTH", "CUADRAO_MOCK_AUTH")
    ):
        return current_user(request)
    token = request_access_token(request)
    subject = _unverified_subject(token) if token else None
    if (
        token is None
        or subject is None
        or api_state.supabase_gateway is None
        or not api_state.DATABASE_URL
    ):
        return current_user(request)
    try:
        locked = deletion_in_flight(
            database_url=api_state.DATABASE_URL, token=token, user_id=subject
        )
    except AuthSessionVerificationUnavailable:
        raise problem(
            request,
            status_code=503,
            code="auth_session_verification_unavailable",
            title="Session Verification Unavailable",
            detail="Argus could not verify this session. Please try again.",
        ) from None
    if not locked:
        return current_user(request)
    try:
        claims = verify_access_token(token)
    except _Unverified as exc:
        logger.warning("Locked deletion retry not verified", reason=str(exc))
        raise _unauthorized(request) from None
    if str(claims.get("sub") or "") != subject:
        raise _unauthorized(request)
    request.state.account_deletion_started = True
    # Only the id is used: the run already holds everything else it needs.
    now = datetime.now(timezone.utc)
    return User(id=subject, email=None, created_at=now, updated_at=now)

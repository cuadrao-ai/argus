from __future__ import annotations

import atexit
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from loguru import logger
from psycopg_pool import ConnectionPool

_AUTH_SESSION_CONNECT_TIMEOUT_SECONDS = 2
_AUTH_SESSION_ACQUIRE_TIMEOUT_SECONDS = 2.0
_AUTH_SESSION_STATEMENT_TIMEOUT_MS = 2_000
_AUTH_SESSION_POOL_SIZE = 5


class AuthSessionVerificationUnavailable(RuntimeError):
    """Raised when Argus cannot safely determine whether a session is active."""


@dataclass(frozen=True)
class AuthSessionVerifier:
    pool: Any

    def is_active(self, *, token: str, user_id: str) -> bool:
        """True for a live session of a real person. An account-deletion
        placeholder (Lane 6) is never active, whatever its sessions, and
        neither is a person whose deletion run is in flight: the account is
        locked from the moment deletion starts until the auth user is gone."""
        identity = _session_identity(token=token, user_id=user_id)
        if identity is None:
            return False
        session_id, auth_user_id = identity

        with self.pool.connection(
            timeout=_AUTH_SESSION_ACQUIRE_TIMEOUT_SECONDS
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select exists (
                        select 1
                        from auth.sessions
                        where id = %s and user_id = %s
                    )
                    and not exists (
                        select 1
                        from argus_private.account_placeholders
                        where id = %s
                    )
                    and not exists (
                        select 1
                        from argus_private.account_deletion_runs
                        where user_id = %s
                    )
                    """,
                    (session_id, auth_user_id, auth_user_id, auth_user_id),
                )
                row = cursor.fetchone()
        return bool(row and row[0])

    def deletion_in_flight(self, *, token: str, user_id: str) -> bool:
        """True when this live session's person has a deletion run in flight:
        the one case POST /account/delete accepts a locked account, so the
        person can resume their own run. Never true for a placeholder.

        Live means the session row exists and has not passed ``not_after``
        (GoTrue's session time-box; null when none is configured). This door
        is verified here rather than by GoTrue's /user, so it enforces the
        session end GoTrue would (Priya #801 note 6)."""
        identity = _session_identity(token=token, user_id=user_id)
        if identity is None:
            return False
        session_id, auth_user_id = identity

        with self.pool.connection(
            timeout=_AUTH_SESSION_ACQUIRE_TIMEOUT_SECONDS
        ) as connection:
            row = connection.execute(
                """
                select exists (
                    select 1 from auth.sessions
                    where id = %s and user_id = %s
                      and (not_after is null or not_after > now())
                )
                and not exists (
                    select 1 from argus_private.account_placeholders where id = %s
                )
                and exists (
                    select 1 from argus_private.account_deletion_runs
                    where user_id = %s and status <> 'done'
                )
                """,
                (session_id, auth_user_id, auth_user_id, auth_user_id),
            ).fetchone()
        return bool(row and row[0])


def deletion_in_flight(*, database_url: str, token: str, user_id: str) -> bool:
    if not database_url:
        raise AuthSessionVerificationUnavailable
    try:
        return _auth_session_verifier(database_url).deletion_in_flight(
            token=token, user_id=user_id
        )
    except Exception as exc:
        logger.warning("Deletion session check failed: {}", type(exc).__name__)
        raise AuthSessionVerificationUnavailable from exc


def auth_session_is_active(*, database_url: str, token: str, user_id: str) -> bool:
    if not database_url:
        raise AuthSessionVerificationUnavailable
    try:
        return _auth_session_verifier(database_url).is_active(
            token=token,
            user_id=user_id,
        )
    except AuthSessionVerificationUnavailable:
        raise
    except Exception as exc:
        logger.warning("Auth session verification failed: {}", type(exc).__name__)
        raise AuthSessionVerificationUnavailable from exc


def _session_identity(*, token: str, user_id: str) -> tuple[UUID, UUID] | None:
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=["HS256", "RS256", "ES256"],
        )
        session_id = UUID(str(claims.get("session_id") or ""))
        token_user_id = UUID(str(claims.get("sub") or ""))
        expected_user_id = UUID(user_id)
    except (TypeError, ValueError, jwt.PyJWTError):
        return None
    if token_user_id != expected_user_id:
        return None
    return session_id, expected_user_id


@lru_cache(maxsize=2)
def _auth_session_verifier(database_url: str) -> AuthSessionVerifier:
    pool = ConnectionPool(
        conninfo=database_url,
        kwargs={
            "autocommit": True,
            "connect_timeout": _AUTH_SESSION_CONNECT_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={_AUTH_SESSION_STATEMENT_TIMEOUT_MS}",
        },
        min_size=0,
        max_size=_AUTH_SESSION_POOL_SIZE,
        open=True,
        timeout=_AUTH_SESSION_ACQUIRE_TIMEOUT_SECONDS,
        name="argus-auth-sessions",
    )
    atexit.register(pool.close)
    return AuthSessionVerifier(pool)

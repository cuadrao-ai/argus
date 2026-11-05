from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest


class _FakeCursor:
    def __init__(self, *, active: bool) -> None:
        self.active = active
        self.query: str | None = None
        self.params: tuple[UUID, ...] | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[UUID, ...]) -> None:
        self.query = query
        self.params = params

    def fetchone(self) -> tuple[bool]:
        return (self.active,)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakePool:
    def __init__(self, *, active: bool) -> None:
        self.cursor = _FakeCursor(active=active)

    @contextmanager
    def connection(self, *, timeout: float):
        assert timeout > 0
        yield _FakeConnection(self.cursor)


def _token(*, session_id: UUID, user_id: UUID) -> str:
    return jwt.encode(
        {"session_id": str(session_id), "sub": str(user_id)},
        "test-secret",
        algorithm="HS256",
    )


def test_auth_session_verifier_accepts_matching_active_session() -> None:
    from argus.api.auth_sessions import AuthSessionVerifier

    session_id = uuid4()
    user_id = uuid4()
    pool = _FakePool(active=True)

    assert AuthSessionVerifier(pool).is_active(
        token=_token(session_id=session_id, user_id=user_id),
        user_id=str(user_id),
    )
    assert "auth.sessions" in str(pool.cursor.query)
    assert "argus_private.account_placeholders" in str(pool.cursor.query)
    # A person whose deletion run is in flight is locked out too.
    assert "argus_private.account_deletion_runs" in str(pool.cursor.query)
    assert pool.cursor.params == (session_id, user_id, user_id, user_id)


def test_auth_session_verifier_rejects_revoked_session() -> None:
    from argus.api.auth_sessions import AuthSessionVerifier

    user_id = uuid4()

    assert not AuthSessionVerifier(_FakePool(active=False)).is_active(
        token=_token(session_id=uuid4(), user_id=user_id),
        user_id=str(user_id),
    )


def test_auth_session_verifier_rejects_missing_or_mismatched_claims() -> None:
    from argus.api.auth_sessions import AuthSessionVerifier

    user_id = uuid4()
    verifier = AuthSessionVerifier(_FakePool(active=True))
    missing_session = jwt.encode({"sub": str(user_id)}, "test-secret", algorithm="HS256")

    assert not verifier.is_active(token=missing_session, user_id=str(user_id))
    assert not verifier.is_active(
        token=_token(session_id=uuid4(), user_id=uuid4()),
        user_id=str(user_id),
    )


def test_auth_session_pool_bounds_connect_acquire_and_statement_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import auth_sessions

    captured: dict[str, Any] = {}

    class _Pool:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def close(self) -> None:
            return None

    auth_sessions._auth_session_verifier.cache_clear()
    monkeypatch.setattr(auth_sessions, "ConnectionPool", _Pool)

    auth_sessions._auth_session_verifier("postgresql://auth-pool/argus")

    assert captured["timeout"] == auth_sessions._AUTH_SESSION_ACQUIRE_TIMEOUT_SECONDS
    assert captured["kwargs"]["connect_timeout"] == (
        auth_sessions._AUTH_SESSION_CONNECT_TIMEOUT_SECONDS
    )
    assert (
        f"statement_timeout={auth_sessions._AUTH_SESSION_STATEMENT_TIMEOUT_MS}"
        in captured["kwargs"]["options"]
    )
    auth_sessions._auth_session_verifier.cache_clear()


def test_auth_session_timeout_maps_to_verification_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import auth_sessions

    class _TimeoutPool:
        def connection(self, *, timeout: float):
            assert timeout == auth_sessions._AUTH_SESSION_ACQUIRE_TIMEOUT_SECONDS
            raise TimeoutError("pool acquisition timed out")

    monkeypatch.setattr(
        auth_sessions,
        "_auth_session_verifier",
        lambda _database_url: auth_sessions.AuthSessionVerifier(_TimeoutPool()),
    )
    user_id = uuid4()

    with pytest.raises(auth_sessions.AuthSessionVerificationUnavailable):
        auth_sessions.auth_session_is_active(
            database_url="postgresql://auth-pool/argus",
            token=_token(session_id=uuid4(), user_id=user_id),
            user_id=str(user_id),
        )

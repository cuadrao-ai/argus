"""Who may call POST /account/delete (Lane 6): a locked person resumes their
own run; everyone else goes through current_user unchanged."""

from __future__ import annotations

import time
import uuid
from unittest.mock import MagicMock

import jwt
import pytest
from argus.api import account_deletion_auth as auth
from argus.api import state as api_state
from argus.api.schemas import User
from fastapi import HTTPException

SECRET = "test-only-jwt-secret-0123456789abcdef"
SUB = str(uuid.uuid4())
SESSION = str(uuid.uuid4())


def _token(secret: str = SECRET, drop: tuple[str, ...] = (), **claims) -> str:  # noqa: ANN003
    body = {
        "sub": SUB,
        "session_id": SESSION,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 600,
        **claims,
    }
    for name in drop:
        body.pop(name)
    return jwt.encode(body, secret, algorithm="HS256")


class _Request:
    def __init__(self, token: str | None) -> None:
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.cookies: dict[str, str] = {}
        self.url = MagicMock(path="/api/v1/account/delete")
        self.state = MagicMock()
        self.scope = {"path": "/api/v1/account/delete"}


@pytest.fixture
def wired(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.delenv("CUADRAO_MOCK_AUTH", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(api_state, "DATABASE_URL", "postgresql://x@db/argus")
    gateway = MagicMock()
    gateway.get_auth_user_from_token.side_effect = AssertionError(
        "GoTrue refuses a banned user"
    )
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    fallback = MagicMock(
        return_value=User(id="someone", email=None, created_at=_now(), updated_at=_now())
    )
    monkeypatch.setattr(auth, "current_user", fallback)
    problems: list[int] = []

    def problem(request, *, status_code, **_):  # noqa: ANN001, ANN003, ANN202
        problems.append(status_code)
        return HTTPException(status_code=status_code)

    monkeypatch.setattr(auth, "problem", problem)
    return {"gateway": gateway, "fallback": fallback}


def _now():  # noqa: ANN202
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _in_flight(monkeypatch, value: bool) -> list[tuple[str, str]]:  # noqa: ANN001
    seen: list[tuple[str, str]] = []

    def check(*, database_url, token, user_id):  # noqa: ANN001, ANN202
        seen.append((token, user_id))
        return value

    monkeypatch.setattr(auth, "deletion_in_flight", check)
    return seen


def test_a_locked_person_is_verified_locally_and_resumes(wired, monkeypatch) -> None:  # noqa: ANN001
    seen = _in_flight(monkeypatch, True)
    user = auth.deletion_requester(_Request(_token()))
    assert user.id == SUB and seen and seen[0][1] == SUB
    wired["gateway"].get_auth_user_from_token.assert_not_called()
    wired["fallback"].assert_not_called()


def test_anyone_not_locked_goes_through_current_user(wired, monkeypatch) -> None:  # noqa: ANN001
    _in_flight(monkeypatch, False)
    request = _Request(_token())
    assert auth.deletion_requester(request).id == "someone"
    wired["fallback"].assert_called_once_with(request)


@pytest.mark.parametrize(
    "token",
    [
        _token(secret="another-projects-secret-0123456789abcdef"),
        _token(exp=int(time.time()) - 5),
        _token(aud="anon"),
        # Marcus #801 N1: a token with no expiry would never lapse.
        _token(drop=("exp",)),
        _token(drop=("session_id",)),
    ],
    ids=["forged", "expired", "wrong_audience", "no_exp", "no_session_id"],
)
def test_a_locked_token_that_does_not_verify_is_refused(
    wired, monkeypatch, token
) -> None:  # noqa: ANN001
    _in_flight(monkeypatch, True)
    with pytest.raises(HTTPException) as refused:
        auth.deletion_requester(_Request(token))
    assert refused.value.status_code == 401


def test_without_the_hs256_secret_a_locked_token_is_refused(wired, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("SUPABASE_JWT_SECRET")
    _in_flight(monkeypatch, True)
    with pytest.raises(HTTPException) as refused:
        auth.deletion_requester(_Request(_token()))
    assert refused.value.status_code == 401


def test_an_asymmetric_token_is_checked_against_the_projects_keys(
    wired, monkeypatch
) -> None:  # noqa: ANN001
    _in_flight(monkeypatch, True)
    monkeypatch.setattr(
        auth.jwt, "get_unverified_header", lambda token: {"alg": "ES256", "kid": "k1"}
    )
    good = {
        "sub": SUB,
        "session_id": SESSION,
        "aud": "authenticated",
        "exp": int(time.time()) + 600,
    }
    claims = MagicMock(return_value={"claims": good})
    wired["gateway"].client.auth.get_claims = claims
    assert auth.deletion_requester(_Request(_token())).id == SUB
    claims.assert_called_once()
    # No expiry: refused even though the keys verified it.
    claims.return_value = {"claims": {k: v for k, v in good.items() if k != "exp"}}
    with pytest.raises(HTTPException) as refused:
        auth.deletion_requester(_Request(_token()))
    assert refused.value.status_code == 401
    claims.side_effect = RuntimeError("Invalid JWT signature")
    with pytest.raises(HTTPException):
        auth.deletion_requester(_Request(_token()))


def test_no_token_goes_through_current_user(wired, monkeypatch) -> None:  # noqa: ANN001
    seen = _in_flight(monkeypatch, True)
    auth.deletion_requester(_Request(None))
    assert seen == []
    wired["fallback"].assert_called_once()

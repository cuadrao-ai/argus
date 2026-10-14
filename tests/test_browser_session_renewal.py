from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from argus.api import dependencies as deps
from argus.api import state as api_state
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient


def token(subject="user-1", expired=False):
    return jwt.encode(
        {"sub": subject, "exp": 1 if expired else 4102444800},
        "synthetic-unit-test-secret-32-bytes",
        algorithm="HS256",
    )


def app():
    instance = FastAPI()
    instance.middleware("http")(deps.request_id_middleware)

    @instance.post("/login")
    def login(request: Request):
        return deps.auth_response(
            request,
            {
                "session": {
                    "access_token": token(),
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                }
            },
        )

    @instance.get("/me")
    def me(user=Depends(deps.current_user)):  # noqa: B008
        return {"id": user.id}

    return instance


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    monkeypatch.setenv("APP_ENV", "staging")
    gateway = Mock()
    gateway.get_auth_user_from_token.return_value = {
        "id": "user-1",
        "email": "person@example.com",
    }
    gateway.get_or_create_profile_for_auth_user.return_value = SimpleNamespace(
        id="user-1"
    )
    gateway.refresh_browser_session.return_value = {
        "session": {
            "access_token": token(),
            "refresh_token": "refresh-2",
            "expires_in": 3600,
        }
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(deps, "auth_session_is_active", lambda **kwargs: True)
    monkeypatch.setattr(deps, "permanent_account_access_allowed", lambda *args: True)
    return gateway


def test_login_refresh_cookie_outlives_access_cookie(gateway):
    response = TestClient(app(), base_url="https://app.example").post("/login")
    cookies = response.headers.get_list("set-cookie")
    assert any(v.startswith("sb-auth-token=") and "Max-Age=3600" in v for v in cookies)
    assert any(
        v.startswith("sb-refresh-token=") and "Max-Age=2592000" in v for v in cookies
    )
    assert all(
        "HttpOnly" in v and "Secure" in v and "SameSite=lax" in v and "Path=/" in v
        for v in cookies
    )


@pytest.mark.parametrize("access", [None, token(expired=True)])
def test_expired_session_survives_client_and_app_restart(gateway, access):
    before = TestClient(app(), base_url="https://app.example")
    before.post("/login")
    persisted = dict(before.cookies)
    if access is None:
        persisted.pop("sb-auth-token")  # Browser removed its expired one-hour cookie.
    else:
        persisted["sb-auth-token"] = access
    before.close()
    after = TestClient(app(), base_url="https://app.example", cookies=persisted)
    response = after.get("/me")
    assert response.status_code == 200
    assert response.json() == {"id": "user-1"}
    gateway.refresh_browser_session.assert_called_once_with("refresh-1")
    assert response.cookies.get("sb-refresh-token") == "refresh-2"
    assert response.cookies.get("sb-auth-token") == token()
    assert "Max-Age=2592000" in response.headers["set-cookie"]
    gateway.get_auth_user_from_token.assert_called_with(token())
    after.get("/me")
    assert gateway.refresh_browser_session.call_count == 1


@pytest.mark.parametrize("header", ["Bearer expired", "Bearer "])
def test_bearer_never_falls_back_to_refresh_cookie(gateway, header):
    gateway.get_auth_user_from_token.side_effect = RuntimeError("expired")
    response = TestClient(app()).get(
        "/me", headers={"Authorization": header, "Cookie": "sb-refresh-token=refresh-1"}
    )
    assert response.status_code == 401
    gateway.refresh_browser_session.assert_not_called()


def test_invalid_refresh_fails_closed(gateway):
    gateway.refresh_browser_session.side_effect = RuntimeError("invalid refresh")
    response = TestClient(app()).get("/me", headers={"Cookie": "sb-refresh-token=wrong"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    gateway.get_or_create_profile_for_auth_user.assert_not_called()


def test_refresh_cannot_switch_cookie_identity(gateway):
    gateway.refresh_browser_session.return_value["session"]["access_token"] = token(
        "other-user"
    )
    response = TestClient(app()).get(
        "/me",
        headers={
            "Cookie": f"sb-auth-token={token(expired=True)}; sb-refresh-token=refresh-1"
        },
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_renewed_session_still_checks_revocation(gateway, monkeypatch):
    monkeypatch.setattr(deps, "auth_session_is_active", lambda **kwargs: False)
    response = TestClient(app()).get(
        "/me", headers={"Cookie": "sb-refresh-token=refresh-1"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "session",
    [None, {}, {"access_token": token(), "refresh_token": "", "expires_in": 3600}],
)
def test_incomplete_renewal_fails_closed(gateway, session):
    gateway.refresh_browser_session.return_value = {"session": session}
    response = TestClient(app()).get(
        "/me", headers={"Cookie": "sb-refresh-token=refresh-1"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_valid_access_does_not_rotate_refresh(gateway):
    response = TestClient(app()).get(
        "/me", headers={"Cookie": f"sb-auth-token={token()}; sb-refresh-token=refresh-1"}
    )
    assert response.status_code == 200
    gateway.refresh_browser_session.assert_not_called()


def test_renewal_still_checks_account_access(gateway, monkeypatch):
    monkeypatch.setattr(deps, "permanent_account_access_allowed", lambda *args: False)
    response = TestClient(app()).get(
        "/me", headers={"Cookie": "sb-refresh-token=refresh-1"}
    )
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_renewed_token_is_available_to_downstream_tools(gateway):
    instance = app()

    @instance.get("/token")
    def downstream(request: Request, user=Depends(deps.current_user)):  # noqa: B008
        return {"renewed": deps.request_access_token(request) == token()}

    response = TestClient(instance).get(
        "/token", headers={"Cookie": "sb-refresh-token=refresh-1"}
    )
    assert response.status_code == 200
    assert response.json() == {"renewed": True}

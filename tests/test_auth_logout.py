from __future__ import annotations

from datetime import datetime, timezone
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest
from argus.api import dependencies
from argus.api import state as api_state
from argus.api.app_setup import http_exception_handler
from argus.api.routers.auth import router
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from loguru import logger

LOGOUT = "/api/v1/auth/logout"
SESSION = "/api/v1/auth/session"


@pytest.fixture
def auth(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    profile = api_state.store.get_or_create_dev_user()

    def access(session: str, expiry: int = 4102444800) -> str:
        return jwt.encode(
            {"sub": profile.id, "session_id": session, "exp": expiry},
            "synthetic-logout-secret-at-least-32-bytes",
            algorithm="HS256",
        )

    tokens = {"a": access("a"), "b": access("b"), "expired": access("a", 1)}
    active = {"a", "b"}
    gateway = MagicMock()
    gateway.private_alpha_email_disabled.return_value = False

    def session_id(token: str) -> str:
        return jwt.decode(token, options={"verify_signature": False})["session_id"]

    def sign_out(token: str, *, scope: str) -> None:
        assert scope == "local"
        active.discard(session_id(token))

    def refresh(token: str) -> dict:
        session = {"refresh-a": "a", "refresh-b": "b"}[token]
        if session not in active:
            raise ValueError("Fake provider rejected revoked refresh")
        return {
            "session": {
                "access_token": tokens[session],
                "refresh_token": f"rotated-{session}",
                "expires_in": 3600,
            }
        }

    gateway.client.auth.admin.sign_out.side_effect = sign_out
    gateway.refresh_browser_session.side_effect = refresh
    gateway.get_auth_user_from_token.return_value = {
        "id": profile.id,
        "email": "logout@example.test",
        "is_anonymous": False,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = profile
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(
        dependencies,
        "auth_session_is_active",
        lambda *, database_url, token, user_id: session_id(token) in active,
    )
    app = FastAPI()
    app.include_router(router)
    app.middleware("http")(dependencies.request_id_middleware)
    app.add_exception_handler(HTTPException, http_exception_handler)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, gateway=gateway, tokens=tokens)


def _cookies(access: str | None = None, refresh: str | None = None) -> dict[str, str]:
    values = {"sb-auth-token": access, "sb-refresh-token": refresh}
    return {
        "Cookie": "; ".join(f"{key}={value}" for key, value in values.items() if value)
    }


def _assert_cleanup(response) -> None:
    assert response.status_code == 200
    assert response.json() == {"success": True}
    headers = response.headers.get_list("set-cookie")
    assert len(headers) == 2
    cleared = set()
    for header in headers:
        cookie = SimpleCookie()
        cookie.load(header)
        for name, value in cookie.items():
            cleared.add(name)
            assert value.value == ""
            assert value["max-age"] == "0"
            assert value["path"] == "/"
            expires = datetime.strptime(value["expires"], "%a, %d %b %Y %H:%M:%S GMT")
            assert expires.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)
    assert cleared == {"sb-auth-token", "sb-refresh-token"}


def test_logout_revokes_access_cookie_session(auth) -> None:
    response = auth.client.post(LOGOUT, headers=_cookies(auth.tokens["a"], "refresh-a"))
    _assert_cleanup(response)
    auth.gateway.client.auth.admin.sign_out.assert_called_once_with(
        auth.tokens["a"], scope="local"
    )
    auth.gateway.refresh_browser_session.assert_called_once_with("refresh-a")


@pytest.mark.parametrize("header", ["Bearer", "Basic synthetic", "", "Bearer invalid"])
def test_authorization_never_falls_back_to_cookie_session(auth, header: str) -> None:
    headers = {**_cookies(auth.tokens["a"], "refresh-a"), "Authorization": header}
    _assert_cleanup(auth.client.post(LOGOUT, headers=headers))
    auth.gateway.refresh_browser_session.assert_not_called()
    calls = auth.gateway.client.auth.admin.sign_out.call_args_list
    assert all(call.args[0] != auth.tokens["a"] for call in calls)
    assert (
        auth.client.get(
            SESSION, headers={"Authorization": f"Bearer {auth.tokens['a']}"}
        ).status_code
        == 200
    )


def test_authorization_selects_its_session_over_cookie(auth) -> None:
    headers = {
        **_cookies(auth.tokens["a"], "refresh-a"),
        "Authorization": f"Bearer {auth.tokens['b']}",
    }
    _assert_cleanup(auth.client.post(LOGOUT, headers=headers))
    auth.gateway.client.auth.admin.sign_out.assert_called_once_with(
        auth.tokens["b"], scope="local"
    )
    auth.gateway.refresh_browser_session.assert_not_called()


@pytest.mark.parametrize("access_kind", [None, "expired"])
def test_refresh_cookie_resolves_session_without_replacing_cleared_cookies(
    auth, access_kind
) -> None:
    access = auth.tokens[access_kind] if access_kind else None
    _assert_cleanup(auth.client.post(LOGOUT, headers=_cookies(access, "refresh-a")))
    auth.gateway.refresh_browser_session.assert_called_once_with("refresh-a")
    auth.gateway.client.auth.admin.sign_out.assert_called_once_with(
        auth.tokens["a"], scope="local"
    )


def test_fake_provider_boundary_rejects_replays_and_preserves_other_session(auth) -> None:
    def bearer(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    assert auth.client.get(SESSION, headers=bearer(auth.tokens["a"])).status_code == 200
    assert auth.client.get(SESSION, headers=bearer(auth.tokens["b"])).status_code == 200
    _assert_cleanup(auth.client.post(LOGOUT, headers=bearer(auth.tokens["a"])))
    assert auth.client.get(SESSION, headers=bearer(auth.tokens["a"])).status_code == 401
    assert (
        auth.client.get(SESSION, headers=_cookies(refresh="refresh-a")).status_code == 401
    )
    assert auth.client.get(SESSION, headers=bearer(auth.tokens["b"])).status_code == 200
    assert (
        auth.client.get(SESSION, headers=_cookies(refresh="refresh-b")).status_code == 200
    )


@pytest.mark.parametrize("failure", ["refresh", "revoke"])
def test_provider_failure_warns_without_secrets_and_still_clears_cookies(
    auth, failure
) -> None:
    secret = f"sensitive-provider-error-{auth.tokens['a']}-refresh-a"
    operation = (
        auth.gateway.refresh_browser_session
        if failure == "refresh"
        else auth.gateway.client.auth.admin.sign_out
    )
    operation.side_effect = RuntimeError(secret)
    records = []
    sink = logger.add(lambda message: records.append(message.record))
    try:
        response = auth.client.post(LOGOUT, headers=_cookies(refresh="refresh-a"))
    finally:
        logger.remove(sink)
    _assert_cleanup(response)
    warnings = [record for record in records if record["level"].name == "WARNING"]
    assert warnings
    assert all(secret not in str(record) for record in warnings)
    assert all(auth.tokens["a"] not in str(record) for record in warnings)
    assert all("refresh-a" not in str(record) for record in warnings)
    if failure == "refresh":
        auth.gateway.client.auth.admin.sign_out.assert_not_called()


def test_untrusted_origin_does_not_revoke_refresh_or_mutate_cookies(auth) -> None:
    response = auth.client.post(
        LOGOUT,
        headers={
            **_cookies(auth.tokens["a"], "refresh-a"),
            "Origin": "https://untrusted.example",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin_rejected"
    assert response.headers.get_list("set-cookie") == []
    auth.gateway.client.auth.admin.sign_out.assert_not_called()
    auth.gateway.refresh_browser_session.assert_not_called()


def test_no_credentials_and_repeated_logout_are_cleanup_only(auth) -> None:
    for _ in range(2):
        _assert_cleanup(auth.client.post(LOGOUT))
    auth.gateway.client.auth.admin.sign_out.assert_not_called()
    auth.gateway.refresh_browser_session.assert_not_called()


@pytest.mark.parametrize(
    "access_cookie",
    [
        "not-a-jwt",
        jwt.encode(
            {"sub": "stale-user", "session_id": "stale", "exp": 1},
            "synthetic-logout-secret",
            algorithm="HS256",
        ),
    ],
)
def test_stale_access_cookie_cannot_preserve_valid_refresh_session(
    auth, access_cookie
) -> None:
    _assert_cleanup(
        auth.client.post(LOGOUT, headers=_cookies(access_cookie, "refresh-a"))
    )
    auth.gateway.client.auth.admin.sign_out.assert_called_once_with(
        auth.tokens["a"], scope="local"
    )
    assert (
        auth.client.get(SESSION, headers=_cookies(refresh="refresh-a")).status_code == 401
    )


def test_failed_refresh_still_revokes_access_cookie_session(auth) -> None:
    _assert_cleanup(
        auth.client.post(LOGOUT, headers=_cookies(auth.tokens["a"], "invalid-refresh"))
    )
    auth.gateway.client.auth.admin.sign_out.assert_called_once_with(
        auth.tokens["a"], scope="local"
    )
    assert (
        auth.client.get(SESSION, headers=_cookies(refresh="refresh-a")).status_code == 401
    )

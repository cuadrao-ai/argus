import time
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.login_browser_check import CaptchaVerificationError
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

client = TestClient(app)

_LOGIN_PAYLOAD = {
    "email": "mama@example.com",
    "password": "password123",
    "captcha_token": "captcha-proof",
}
_EXPECTED_UNAUTHORIZED = {
    "title": "Unauthorized",
    "status": 401,
    "detail": "Invalid email or password.",
    "code": "unauthorized",
}
_PUBLIC_HEADER_KEYS = (
    "content-type",
    "cache-control",
    "www-authenticate",
    "set-cookie",
)


class _CaptchaRejected(Exception):
    def __init__(self) -> None:
        super().__init__("captcha verification process failed")
        self.code = "captcha_failed"


class _Session:
    session = object()

    def model_dump(self, mode: str) -> dict[str, object]:
        return {"user": {"id": "user-1"}, "session": {"access_token": "issued"}}


def _gateway(auth: object) -> SupabaseGateway:
    return SupabaseGateway(client=MagicMock(), auth_client_factory=lambda: auth)


def _configure_login_route(
    monkeypatch: pytest.MonkeyPatch,
    *,
    allowed: bool = True,
    disabled: bool = False,
    login_side_effect: object | None = None,
) -> MagicMock:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.delenv("CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED", raising=False)
    gateway = MagicMock()
    gateway.private_alpha_email_allowed.return_value = allowed
    gateway.private_alpha_email_disabled.return_value = disabled
    if login_side_effect is not None:
        gateway.login.side_effect = login_side_effect
    monkeypatch.setattr("argus.api.state.supabase_gateway", gateway)
    return gateway


def _public_problem_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in payload if key != "request_id"}


def _public_headers(response: httpx.Response) -> dict[str, str | None]:
    lowered = {key.lower(): value for key, value in response.headers.items()}
    return {key: lowered.get(key) for key in _PUBLIC_HEADER_KEYS}


def _post_login() -> httpx.Response:
    return client.post("/api/v1/auth/login", json=_LOGIN_PAYLOAD)


def test_login_returns_the_provider_session() -> None:
    class Auth:
        def sign_in_with_password(self, payload: dict[str, object]) -> _Session:
            assert payload["options"] == {"captcha_token": "token"}
            return _Session()

    issued = _gateway(Auth()).login(
        email="mama@example.com",
        password="password123",
        captcha_token="token",
    )

    assert issued == {
        "user": {"id": "user-1"},
        "session": {"access_token": "issued"},
    }


def test_captcha_rejection_is_a_verification_error_not_a_login_failure() -> None:
    class Auth:
        def sign_in_with_password(self, _payload: dict[str, object]) -> None:
            raise _CaptchaRejected()

    with pytest.raises(CaptchaVerificationError):
        _gateway(Auth()).login(
            email="mama@example.com",
            password="password123",
            captcha_token="token",
        )


def test_provider_timeout_is_a_verification_error_not_a_session() -> None:
    class Auth:
        def sign_in_with_password(self, _payload: dict[str, object]) -> None:
            raise httpx.ReadTimeout("timed out")

    with pytest.raises(CaptchaVerificationError):
        _gateway(Auth()).login(
            email="mama@example.com",
            password="password123",
            captcha_token="token",
        )


def test_a_stalled_provider_does_not_wait_out_the_client_and_returns_no_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Auth:
        def sign_in_with_password(self, _payload: dict[str, object]) -> _Session:
            time.sleep(1)
            return _Session()

    monkeypatch.setattr(
        "argus.domain.supabase_gateway.LOGIN_PROVIDER_TIMEOUT_SECONDS",
        0.05,
    )
    started = time.monotonic()
    with pytest.raises(CaptchaVerificationError):
        _gateway(Auth()).login(
            email="mama@example.com",
            password="password123",
            captcha_token="token",
        )
    assert time.monotonic() - started < 0.5


def test_wrong_password_stays_a_login_failure() -> None:
    class Auth:
        def sign_in_with_password(self, _payload: dict[str, object]) -> None:
            raise RuntimeError("Invalid login credentials")

    with pytest.raises(RuntimeError, match="Login failed") as caught:
        _gateway(Auth()).login(
            email="mama@example.com",
            password="password123",
            captcha_token="token",
        )
    assert not isinstance(caught.value, CaptchaVerificationError)


@pytest.mark.parametrize(
    "login_side_effect",
    [
        CaptchaVerificationError("captcha_failed"),
        RuntimeError("invalid provider password"),
    ],
)
def test_login_route_maps_server_failures_to_one_public_contract(
    monkeypatch: pytest.MonkeyPatch,
    login_side_effect: Exception,
) -> None:
    gateway = _configure_login_route(
        monkeypatch,
        login_side_effect=login_side_effect,
    )

    response = _post_login()

    assert response.status_code == 401
    assert _public_problem_body(response.json()) == {
        **_EXPECTED_UNAUTHORIZED,
        "type": "https://api.argus.app/problems/unauthorized",
    }
    assert response.headers.get("set-cookie") is None
    gateway.login.assert_called_once()


def test_login_route_denied_admission_matches_provider_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = _configure_login_route(monkeypatch, allowed=False)
    denied_response = _post_login()

    gateway = _configure_login_route(
        monkeypatch,
        login_side_effect=RuntimeError("invalid provider password"),
    )
    provider_response = _post_login()

    assert denied_response.status_code == provider_response.status_code == 401
    assert _public_problem_body(denied_response.json()) == _public_problem_body(
        provider_response.json()
    )
    assert _public_headers(denied_response) == _public_headers(provider_response)
    denied.login.assert_not_called()
    gateway.login.assert_called_once()


def test_login_route_maps_captcha_deadline_like_captcha_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejection = _configure_login_route(
        monkeypatch,
        login_side_effect=CaptchaVerificationError("captcha_failed"),
    )
    rejected = _post_login()

    deadline = _configure_login_route(
        monkeypatch,
        login_side_effect=CaptchaVerificationError("deadline"),
    )
    timed_out = _post_login()

    assert rejected.status_code == timed_out.status_code == 401
    assert _public_problem_body(rejected.json()) == _public_problem_body(
        timed_out.json()
    )
    rejection.login.assert_called_once()
    deadline.login.assert_called_once()

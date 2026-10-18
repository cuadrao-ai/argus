import time
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.supabase_gateway import (
    CaptchaVerificationError,
    SupabaseGateway,
)

client = TestClient(app)


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


def test_login_route_returns_captcha_unavailable_instead_of_a_wrong_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    monkeypatch.delenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", raising=False)
    gateway = MagicMock()
    gateway.private_alpha_email_allowed.return_value = True
    gateway.private_alpha_email_disabled.return_value = False
    gateway.login.side_effect = CaptchaVerificationError("captcha_failed")
    monkeypatch.setattr("argus.api.state.supabase_gateway", gateway)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "mama@example.com",
            "password": "password123",
            "captcha_token": "captcha-proof",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "captcha_unavailable"
    assert "password" not in response.json()["detail"].lower()
    gateway.login.assert_called_once()

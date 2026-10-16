from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.api.routers import auth
from argus.api.schemas import SignupRequest
from argus.domain.username_signup import UsernameSignupPrevalidation
from faker import Faker
from fastapi import HTTPException, Request
from loguru import logger

fake = Faker()


@pytest.fixture
def signup_context(monkeypatch):
    monkeypatch.delenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", raising=False)
    gateway = MagicMock()
    gateway.private_alpha_email_allowed.return_value = False
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    auth.reset_auth_attempt_limiter_for_tests()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/signup",
            "headers": [],
            "client": ("127.0.0.1", 5000),
            "state": {"request_id": "signup-diagnostics-test"},
        }
    )
    body = SignupRequest(
        email=fake.email(),
        password=fake.password(length=16),
        captcha_token=fake.uuid4(),
    )
    return request, body, gateway


def test_closed_admission_reports_internal_reason_without_provider_call(signup_context):
    request, body, gateway = signup_context
    records = []
    sink = logger.add(lambda message: records.append(message.record))
    try:
        with pytest.raises(HTTPException) as caught:
            auth.signup(request, body)
    finally:
        logger.remove(sink)

    assert caught.value.status_code == 400
    assert caught.value.detail["code"] == "auth_signup_failed"
    gateway.signup.assert_not_called()
    rejections = [
        record for record in records if record["message"].startswith("Signup rejected:")
    ]
    assert len(rejections) == 1
    assert rejections[0]["extra"] == {
        "request_id": request.state.request_id,
        "surface": "direct_signup",
        "reason": "access_denied",
    }
    serialized = json.dumps(rejections, default=str)
    assert body.email not in serialized
    assert body.password not in serialized
    assert body.captcha_token not in serialized


@pytest.mark.parametrize("surface", ["direct_signup", "guest_conversion"])
def test_admission_denial_stays_private_on_both_signup_routes(
    signup_context, monkeypatch, surface
):
    request, body, gateway = signup_context
    monkeypatch.setattr(auth, "_enforce_browser_auth_origin", lambda request: None)
    monkeypatch.setattr(
        auth, "account_context", lambda request: SimpleNamespace(kind="guest")
    )
    with pytest.raises(HTTPException) as caught:
        if surface == "direct_signup":
            auth.signup(request, body)
        else:
            auth.signup_guest_account(request, body, user=MagicMock())
    assert caught.value.detail["code"] == "auth_signup_failed"
    assert "access_denied" not in json.dumps(caught.value.detail)
    gateway.signup.assert_not_called()


@pytest.mark.parametrize("failure", ["provider", "username"])
def test_known_rejection_stage_preserves_public_error_and_redacts_input(
    signup_context, monkeypatch, failure
):
    request, body, gateway = signup_context
    gateway.private_alpha_email_allowed.return_value = True
    sensitive_detail = (
        f"provider rejected {body.email} {body.password} {body.captcha_token}"
    )
    gateway.signup.side_effect = RuntimeError(sensitive_detail)
    if failure == "username":
        body = body.model_copy(update={"username": "already-taken"})
        monkeypatch.setattr(
            auth,
            "serialized_username_signup",
            lambda *args: nullcontext(UsernameSignupPrevalidation(False, False)),
        )
    records = []
    sink = logger.add(lambda message: records.append(message.record))
    try:
        with pytest.raises(HTTPException) as caught:
            auth.signup(request, body)
    finally:
        logger.remove(sink)
    assert caught.value.detail == {
        "type": "https://api.argus.app/problems/auth-signup-failed",
        "title": "Signup Failed",
        "status": 400,
        "detail": "Signup failed. Please try again.",
        "code": "auth_signup_failed",
        "request_id": request.state.request_id,
    }
    rejections = [
        record for record in records if record["message"].startswith("Signup rejected:")
    ]
    assert len(rejections) == 1
    reason = "signup_failed" if failure == "provider" else "username_unavailable"
    assert rejections[0]["extra"]["reason"] == reason
    assert f"reason={reason}" in rejections[0]["message"]
    serialized = json.dumps(rejections, default=str) + json.dumps(caught.value.detail)
    assert sensitive_detail not in serialized
    assert body.email not in serialized
    assert body.password not in serialized
    assert body.captcha_token not in serialized
    assert rejections[0]["exception"] is None
    assert gateway.signup.call_count == (1 if failure == "provider" else 0)

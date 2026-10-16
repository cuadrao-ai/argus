from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.api.routers import auth
from argus.api.schemas import SignupRequest
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
    rejections = [record for record in records if record["message"] == "Signup rejected"]
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

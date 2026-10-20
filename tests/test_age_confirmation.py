from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.schemas import GuestAccountSignupRequest, SignupRequest
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.mark.parametrize("schema", [SignupRequest, GuestAccountSignupRequest])
@pytest.mark.parametrize(
    "confirmation",
    [False, True, 12345, "2026-10-17", "2026-10-17T10:00:00", "nonsense"],
)
def test_signup_rejects_unusable_confirmation(schema, confirmation):
    with pytest.raises(ValidationError):
        schema.model_validate(
            dict(
                email="adult@example.com",
                password="strong-password",
                captcha_token="proof",
                age_confirmed_at=confirmation,
            )
        )


@pytest.mark.parametrize("schema", [SignupRequest, GuestAccountSignupRequest])
@pytest.mark.parametrize("age_field", ["absent", "null"])
def test_signup_stores_null_when_confirmation_is_absent_or_null(schema, age_field):
    payload = dict(
        email="adult@example.com", password="strong-password", captcha_token="proof"
    )
    if age_field == "null":
        payload["age_confirmed_at"] = None
    body = schema.model_validate(payload)
    assert body.age_confirmed_at is None


@pytest.mark.parametrize("schema", [SignupRequest, GuestAccountSignupRequest])
def test_confirmation_normalizes_offset_and_keeps_the_original_instant(schema):
    confirmed = datetime.now(timezone.utc) - timedelta(days=2)
    body = schema.model_validate(
        dict(
            email="adult@example.com",
            password="strong-password",
            captcha_token="proof",
            age_confirmed_at=confirmed.astimezone(
                timezone(timedelta(hours=-4))
            ).isoformat(),
        )
    )
    assert body.age_confirmed_at == confirmed
    assert body.age_confirmed_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("schema", [SignupRequest, GuestAccountSignupRequest])
def test_confirmation_refuses_future_clock_values(schema):
    with pytest.raises(ValidationError):
        schema.model_validate(
            dict(
                email="adult@example.com",
                password="strong-password",
                captcha_token="proof",
                age_confirmed_at=(
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
            )
        )


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/signup", "/api/v1/auth/guest/signup"],
)
@pytest.mark.parametrize("age_field", ["present", "absent", "null"])
def test_signup_routes_never_return_age_confirmation_required(
    path, age_field, monkeypatch
):
    from argus.api.routers import auth as auth_router
    from argus.api.schemas import User
    from argus.domain.store import utcnow

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    gateway = MagicMock()
    gateway.private_alpha_email_disabled.return_value = False
    gateway.signup.return_value = {
        "user": {"id": "user-1", "email": "adult@example.com", "identities": [{"id": "1"}]},
        "session": None,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = User(
        id="user-1",
        email="adult@example.com",
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    instant = datetime.now(timezone.utc) - timedelta(days=1)
    payload = {
        "email": "adult@example.com",
        "password": "strong-password",
        "captcha_token": "proof",
    }
    if age_field == "present":
        payload["age_confirmed_at"] = instant.isoformat()
    elif age_field == "null":
        payload["age_confirmed_at"] = None
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(path, json=payload)
    assert response.status_code != 422
    assert response.json().get("code") != "age_confirmation_required"
    if path != "/api/v1/auth/signup":
        return
    assert response.status_code == 200
    assert gateway.signup.call_args.kwargs["age_confirmed_at"] == (
        instant if age_field == "present" else None
    )
    if age_field == "present":
        gateway.record_age_confirmation.assert_called_once_with("user-1", instant)
    else:
        gateway.record_age_confirmation.assert_not_called()


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/signup", "/api/v1/auth/guest/signup"],
)
@pytest.mark.parametrize(
    "confirmation",
    ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00", "not-a-timestamp"],
)
def test_invalid_confirmation_is_422_before_provider(path, confirmation):
    gateway = MagicMock()
    payload = {
        "email": "adult@example.com",
        "password": "strong-password",
        "captcha_token": "proof",
        "age_confirmed_at": confirmation,
    }
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "age_confirmation_invalid"
    assert "Confirmo que tengo 18 años o más." not in response.text
    gateway.signup.assert_not_called()
    gateway.sign_in_anonymously.assert_not_called()


def test_guest_bootstrap_does_not_accept_age_confirmation(monkeypatch):
    from argus.api.routers import auth as auth_router
    from fastapi import HTTPException

    gateway = MagicMock()
    gateway.sign_in_anonymously.side_effect = RuntimeError("stop after the call")
    monkeypatch.setenv("ARGUS_GUEST_ACCESS_ENABLED", "true")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch.object(auth_router, "current_user", side_effect=HTTPException(401)),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        missing = client.post("/api/v1/auth/guest", json={"captcha_token": "proof"})
        invalid = client.post(
            "/api/v1/auth/guest",
            json={"captcha_token": "proof", "age_confirmed_at": "not-a-timestamp"},
        )
    assert missing.json().get("code") != "age_confirmation_required"
    assert invalid.json().get("code") != "age_confirmation_invalid"
    assert gateway.sign_in_anonymously.call_count == 2
    for call in gateway.sign_in_anonymously.call_args_list:
        assert call.kwargs == {"captcha_token": "proof", "language": "en"}


def test_provider_metadata_recovers_sessionless_profile_without_reconfirming():
    from argus.api.schemas import User
    from argus.domain.supabase_gateway import SupabaseGateway

    instant = datetime.now(timezone.utc) - timedelta(days=1)
    auth_user = {
        "id": "00000000-0000-0000-0000-000000000181",
        "email": "adult@example.com",
        "user_metadata": {"age_confirmed_at": instant.isoformat()},
    }
    gateway = SupabaseGateway.__new__(SupabaseGateway)
    gateway.client = MagicMock()
    gateway._auth = MagicMock()
    gateway._auth.return_value.sign_up.return_value.user = object()
    gateway._auth.return_value.sign_up.return_value.model_dump.return_value = {
        "user": auth_user,
        "session": None,
    }
    result = gateway.signup(
        email=auth_user["email"],
        password="strong-password",
        captcha_token="proof",
        age_confirmed_at=instant,
    )
    assert result["session"] is None
    metadata = gateway._auth.return_value.sign_up.call_args.args[0]["options"]["data"]
    assert metadata["age_confirmed_at"] == instant.isoformat()
    profile = User(
        id=auth_user["id"],
        email=auth_user["email"],
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        created_at=instant,
        updated_at=instant,
    )
    gateway.private_alpha_role_for_email = MagicMock(return_value=None)
    gateway.get_user = MagicMock(return_value=None)
    gateway.client.table.return_value.upsert.return_value.execute.return_value.data = [
        profile.model_dump(mode="json")
    ]
    gateway.get_or_create_profile_for_auth_user(auth_user)
    inserted = gateway.client.table.return_value.upsert.call_args.args[0]
    assert datetime.fromisoformat(inserted["age_confirmed_at"]) == instant
    gateway.get_user.return_value = profile
    gateway.client.table.reset_mock()
    gateway.get_or_create_profile_for_auth_user(
        {
            **auth_user,
            "user_metadata": {"age_confirmed_at": datetime.now(timezone.utc).isoformat()},
        }
    )
    gateway.client.table.assert_not_called()


def test_direct_signup_initializes_a_legacy_null_attestation_from_the_validated_request(
    monkeypatch,
):
    from argus.api.routers import auth as auth_router
    from argus.api.schemas import User
    from argus.domain.store import utcnow

    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    gateway = MagicMock()
    gateway.private_alpha_email_disabled.return_value = False
    gateway.signup.return_value = {
        "user": {"id": "user-1", "email": "adult@example.com"},
        "session": None,
    }
    gateway.get_or_create_profile_for_auth_user.return_value = User(
        id="user-1",
        email="adult@example.com",
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    instant = datetime.now(timezone.utc) - timedelta(days=1)
    with patch.object(api_state, "supabase_gateway", gateway), TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/signup",
            json=dict(
                email="adult@example.com",
                password="strong-password",
                captcha_token="proof",
                age_confirmed_at=instant.isoformat(),
            ),
        )
    assert response.status_code == 200
    gateway.record_age_confirmation.assert_called_once_with("user-1", instant)

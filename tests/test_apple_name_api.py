from __future__ import annotations

from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.apple_sign_in import FLAG
from argus.api.main import app
from argus.api.routers import profile
from argus.api.routers.profile_apple_name import AppleDisplayNameRequest
from argus.domain.apple_sign_in.credentials import AppleIdentityMissing
from argus.domain.apple_sign_in.identity import (
    AppleIdentityUnavailable,
    LinkedAppleIdentity,
)
from argus.domain.apple_sign_in.name import AppleNameAccountUnavailable
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests.apple_sign_in_support import SUBJECT
from tests.financial_accounts.conftest import (  # noqa: F401
    ALICE,
    GUEST,
    gateway,
    identities,
    surface_env,
)

URL = "/api/v1/me/apple-name"
COMMAND = "argus.api.routers.profile_apple_name.initialize_apple_display_name"


@pytest.mark.parametrize("name", [" ", "\t\n", "a" * 201, None, 12])
def test_name_boundary_rejects_invalid_input(name):
    with pytest.raises(ValidationError):
        AppleDisplayNameRequest(display_name=name)


def test_name_boundary_preserves_unicode_and_interior_spelling():
    assert (
        AppleDisplayNameRequest(display_name="  María  de la Cruz 李  ").display_name
        == "María  de la Cruz 李"
    )


@pytest.fixture
def client(surface_env, gateway, monkeypatch):  # noqa: F811
    monkeypatch.setenv(FLAG, "true")
    monkeypatch.setattr(profile, "_apple_identity", lambda *_: LinkedAppleIdentity(SUBJECT))
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch.object(api_state, "DATABASE_URL", "local-test"),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        patch("argus.api.routers.profile_apple_name.deletion_pool"),
        TestClient(app) as client,
    ):
        yield client


@pytest.mark.parametrize(
    "data",
    [
        {"display_name": " "},
        {"display_name": "a" * 201},
        {"display_name": "Name", "user_id": "other"},
    ],
)
def test_invalid_request_has_no_command_side_effect(client, data):
    with patch(COMMAND) as command:
        response = client.post(
            URL, json=data, headers={"Authorization": f"Bearer {ALICE}"}
        )
    assert response.status_code == 422
    command.assert_not_called()


@pytest.mark.parametrize("payload", [b"not-json", b"{}", b'{"display_name":"Name"}'])
def test_flag_off_is_404_before_auth_or_body(client, monkeypatch, payload):
    monkeypatch.setenv(FLAG, "false")
    with patch(COMMAND) as command:
        response = client.post(
            URL, content=payload, headers={"content-type": "application/json"}
        )
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    command.assert_not_called()


@pytest.mark.parametrize("token,status", [(None, 401), (GUEST, 403)])
def test_denied_session_does_not_dispatch(client, token, status):
    with patch(COMMAND) as command:
        response = client.post(
            URL,
            json={"display_name": "Name"},
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
    assert response.status_code == status
    command.assert_not_called()


@pytest.mark.parametrize(
    "error,status,code",
    [
        (AppleIdentityMissing(), 409, "apple_identity_missing"),
        (AppleIdentityUnavailable(), 503, "apple_name_unavailable"),
        (AppleNameAccountUnavailable(), 403, "account_unavailable"),
        (RuntimeError("unavailable"), 503, "apple_name_unavailable"),
    ],
)
def test_failures_keep_accurate_errors(client, error, status, code):
    with patch(COMMAND, side_effect=error):
        response = client.post(
            URL,
            json={"display_name": "Name"},
            headers={"Authorization": f"Bearer {ALICE}"},
        )
    assert response.status_code == status
    assert response.json()["code"] == code


def test_saved_name_returns_current_identity_envelope(client, request):
    fixture_gateway = request.getfixturevalue("gateway")
    fixture_identities = request.getfixturevalue("identities")
    saved = fixture_gateway.get_or_create_profile_for_auth_user(
        fixture_identities[ALICE]
    ).model_dump()
    with patch(COMMAND, return_value=saved):
        response = client.post(
            URL,
            json={"display_name": "Name"},
            headers={"Authorization": f"Bearer {ALICE}"},
        )
    assert response.status_code == 200
    assert response.json()["apple_identity"] == {"subject": SUBJECT}


def test_name_identity_failure_has_no_command_side_effect(client, monkeypatch):
    from fastapi import HTTPException

    def unavailable(*args):
        raise HTTPException(status_code=503)

    monkeypatch.setattr(profile, "_apple_identity", unavailable)
    with patch(COMMAND) as command:
        response = client.post(
            URL,
            json={"display_name": "Name"},
            headers={"Authorization": f"Bearer {ALICE}"},
        )
    assert response.status_code == 503
    assert response.json()["code"] == "apple_name_unavailable"
    command.assert_not_called()

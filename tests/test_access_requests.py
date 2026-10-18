from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from argus.api import state as api_state
from argus.api.main import app
from argus.domain.supabase_gateway import SupabaseGateway
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_access_request_limiter() -> None:
    from argus.api.routers import auth

    auth.reset_auth_attempt_limiter_for_tests()


@pytest.fixture
def access_gateway(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    gateway = MagicMock()
    gateway.request_private_alpha_access.return_value = None
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    return gateway


@pytest.mark.parametrize(
    ("stored_role", "expected"),
    [
        ("admin", "admin"),
        ("developer", "developer"),
        ("user", "user"),
        ("requested", None),
        ("unexpected-role", None),
    ],
)
def test_private_alpha_role_lookup_fails_closed_for_non_access_roles(
    stored_role: str,
    expected: str | None,
) -> None:
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = [
        {
            "email": "person@example.com",
            "role": stored_role,
            "disabled_at": None,
        }
    ]
    gateway = SupabaseGateway(client=MagicMock())
    gateway.client.table.return_value = query

    assert gateway.private_alpha_role_for_email("person@example.com") == expected
    assert gateway.private_alpha_email_allowed("person@example.com") is (
        expected is not None
    )


def test_gateway_records_only_a_missing_requested_row() -> None:
    query = MagicMock()
    query.upsert.return_value = query
    query.execute.return_value.data = []
    gateway = SupabaseGateway(client=MagicMock())
    gateway.client.table.return_value = query

    gateway.request_private_alpha_access(
        email=" PERSON@Example.COM ",
        language="es-419",
    )

    gateway.client.table.assert_called_once_with("private_alpha_allowlist")
    query.upsert.assert_called_once_with(
        {
            "email": "person@example.com",
            "role": "requested",
            "language": "es-419",
        },
        on_conflict="email",
        ignore_duplicates=True,
    )


def test_gateway_loads_only_active_requested_access() -> None:
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.is_.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = [
        {
            "email": "person@example.com",
            "role": "requested",
            "language": "es-419",
            "disabled_at": None,
        }
    ]
    gateway = SupabaseGateway(client=MagicMock())
    gateway.client.table.return_value = query

    row = gateway.get_requested_private_alpha_access(" Person@Example.COM ")

    assert row == {
        "email": "person@example.com",
        "role": "requested",
        "language": "es-419",
        "disabled_at": None,
    }
    query.select.assert_called_once_with("email,role,language,disabled_at")
    assert query.eq.call_args_list[0].args == ("email", "person@example.com")
    assert query.eq.call_args_list[1].args == ("role", "requested")
    query.is_.assert_called_once_with("disabled_at", "null")


def test_gateway_loads_access_welcome_delivery_with_normalized_email() -> None:
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = [
        {
            "recipient_email": "person@example.com",
            "language": "es-419",
            "content_version": "private-alpha-access-welcome/v1",
            "subject": "Bienvenido a Argus",
            "provider_receipt": "synthetic-provider-receipt",
            "sent_at": "2026-08-12T14:27:17Z",
        }
    ]
    gateway = SupabaseGateway(client=MagicMock())
    gateway.client.table.return_value = query

    row = gateway.get_private_alpha_access_welcome_delivery(" Person@Example.COM ")

    assert row == query.execute.return_value.data[0]
    gateway.client.table.assert_called_once_with(
        "private_alpha_access_welcome_deliveries"
    )
    query.select.assert_called_once_with(
        "recipient_email,language,content_version,subject,provider_receipt,sent_at"
    )
    query.eq.assert_called_once_with("recipient_email", "person@example.com")
    query.limit.assert_called_once_with(1)


@pytest.mark.parametrize("send_allowed", [True, False])
def test_gateway_claims_access_welcome_before_send(
    send_allowed: bool,
) -> None:
    claim = {
        "recipient_email": "person@example.com",
        "language": "es-419",
        "content_version": "private-alpha-access-welcome/v1",
        "subject": "Bienvenido a Argus",
        "claim_token": "11111111-1111-4111-8111-111111111111",
        "claimed_at": "2026-08-12T14:27:17Z",
        "send_allowed": send_allowed,
    }
    rpc = MagicMock()
    rpc.execute.return_value.data = [claim]
    client = MagicMock()
    client.rpc.return_value = rpc
    gateway = SupabaseGateway(client=client)

    result = gateway.claim_private_alpha_access_welcome(
        email=" Person@Example.COM ",
        language="es-419",
        content_version="private-alpha-access-welcome/v1",
        subject="Bienvenido a Argus",
    )

    assert result == claim
    client.rpc.assert_called_once_with(
        "claim_private_alpha_access_welcome",
        {
            "p_email": "person@example.com",
            "p_language": "es-419",
            "p_content_version": "private-alpha-access-welcome/v1",
            "p_subject": "Bienvenido a Argus",
        },
    )
    rpc.execute.assert_called_once_with()


@pytest.mark.parametrize(("database_result", "expected"), [(True, True), (False, False)])
def test_gateway_completes_access_welcome_through_rpc(
    database_result: bool,
    expected: bool,
) -> None:
    rpc = MagicMock()
    rpc.execute.return_value.data = database_result
    client = MagicMock()
    client.rpc.return_value = rpc
    gateway = SupabaseGateway(client=client)

    completed = gateway.complete_private_alpha_access_welcome(
        email=" Person@Example.COM ",
        language="es-419",
        content_version="private-alpha-access-welcome/v1",
        subject="Bienvenido a Argus",
        provider_receipt="synthetic-provider-receipt",
        claim_token="11111111-1111-4111-8111-111111111111",
    )

    assert completed is expected
    client.rpc.assert_called_once_with(
        "complete_private_alpha_access_welcome",
        {
            "p_email": "person@example.com",
            "p_language": "es-419",
            "p_content_version": "private-alpha-access-welcome/v1",
            "p_subject": "Bienvenido a Argus",
            "p_provider_receipt": "synthetic-provider-receipt",
            "p_claim_token": "11111111-1111-4111-8111-111111111111",
        },
    )


def test_gateway_releases_expired_access_welcome_claims_through_rpc() -> None:
    rpc = MagicMock()
    rpc.execute.return_value.data = 3
    client = MagicMock()
    client.rpc.return_value = rpc
    gateway = SupabaseGateway(client=client)

    released = gateway.release_expired_private_alpha_access_welcome_claims()

    assert released == 3
    client.rpc.assert_called_once_with(
        "release_expired_private_alpha_access_welcome_claims",
        {},
    )

    rpc.execute.assert_called_once_with()


def test_public_access_request_normalizes_and_returns_non_enumerating_202(
    access_gateway: MagicMock,
) -> None:
    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": " Person@Example.COM ", "language": "es-419"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    access_gateway.request_private_alpha_access.assert_called_once_with(
        email="person@example.com",
        language="es-419",
    )


@pytest.mark.parametrize(
    "existing_state",
    ["requested", "user", "admin", "developer", "disabled"],
)
def test_public_access_request_response_never_reveals_existing_state(
    access_gateway: MagicMock,
    existing_state: str,
) -> None:
    access_gateway.request_private_alpha_access.return_value = existing_state

    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": "person@example.com", "language": "en"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}


def test_public_access_request_rejects_untrusted_origin_before_persistence(
    access_gateway: MagicMock,
) -> None:
    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": "person@example.com", "language": "en"},
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin_rejected"
    access_gateway.request_private_alpha_access.assert_not_called()


def test_public_access_request_uses_bounded_auth_attempt_limiter(
    access_gateway: MagicMock,
) -> None:
    from argus.api.routers import auth

    headers = {"CF-Connecting-IP": "203.0.113.19"}
    payload = {"email": "person@example.com", "language": "en"}
    for _ in range(auth.AUTH_ACCESS_REQUEST_ATTEMPT_LIMIT):
        response = client.post(
            "/api/v1/auth/access-requests",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 202

    blocked = client.post(
        "/api/v1/auth/access-requests",
        json=payload,
        headers=headers,
    )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"
    assert blocked.headers["Retry-After"]
    assert (
        access_gateway.request_private_alpha_access.call_count
        == auth.AUTH_ACCESS_REQUEST_ATTEMPT_LIMIT
    )


def test_public_access_request_missing_gateway_is_problem_details_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)

    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": "person@example.com", "language": "en"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "access_request_unavailable"


def test_public_access_request_persistence_failure_is_problem_details_503(
    access_gateway: MagicMock,
) -> None:
    access_gateway.request_private_alpha_access.side_effect = RuntimeError(
        "persistence unavailable"
    )

    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": "person@example.com", "language": "en"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "access_request_unavailable"


def test_public_access_request_rejects_invalid_language_before_persistence(
    access_gateway: MagicMock,
) -> None:
    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": "person@example.com", "language": "fr"},
    )

    assert response.status_code == 422
    access_gateway.request_private_alpha_access.assert_not_called()


def test_public_access_request_requires_language(
    access_gateway: MagicMock,
) -> None:
    response = client.post(
        "/api/v1/auth/access-requests",
        json={"email": "person@example.com"},
    )

    assert response.status_code == 422
    access_gateway.request_private_alpha_access.assert_not_called()


def test_access_request_environment_contract_is_value_free() -> None:
    render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    api = next(
        service for service in render["services"] if service["name"] == "argus-api"
    )
    api_env = {entry["key"]: entry for entry in api["envVars"]}

    assert api_env["ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD"] == {
        "key": "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD",
        "sync": False,
    }
    assert api_env["ARGUS_APP_ORIGIN"] == {
        "key": "ARGUS_APP_ORIGIN",
        "value": "https://arguschat.ai",
    }
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert (
        "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD="
        "your_resend_smtp_password_here" in env_example
    )
    assert "ARGUS_APP_ORIGIN=http://localhost:3000" in env_example

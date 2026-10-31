"""The account deletion route (Lane 6, part B): flag, auth order, mapping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from argus.api.guest_access import (
    AccountContext,
    guest_capabilities,
    registered_account_context,
    store_account_context,
)
from argus.api.main import app
from argus.api.routers import account as account_route
from argus.api.schemas import User
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionRejected,
    DeletionOutcome,
)
from fastapi.testclient import TestClient

client = TestClient(app)
USER_ID = "00000000-0000-0000-0000-0000000000d1"
URL = "/api/v1/account/delete"


_NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def _user(email: str | None) -> User:
    return User(id=USER_ID, email=email, created_at=_NOW, updated_at=_NOW)


def _registered(request):  # noqa: ANN001, ANN202
    store_account_context(request, registered_account_context(USER_ID))
    return _user("person@example.com")


def _guest(request):  # noqa: ANN001, ANN202
    store_account_context(
        request,
        AccountContext(
            kind="guest",
            user_id=USER_ID,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            capabilities=guest_capabilities(),
        ),
    )
    return _user(None)


@pytest.fixture
def enabled(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setenv(account_route.FLAG, "true")


@pytest.fixture(autouse=True)
def _fresh_rate_limit():  # noqa: ANN202
    account_route._per_account.reset()
    yield
    account_route._per_account.reset()


def test_off_by_default_answers_404_before_auth(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv(account_route.FLAG, raising=False)
    auth = MagicMock(side_effect=AssertionError("auth must not run"))
    with patch.object(account_route, "deletion_requester", auth):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 404
    auth.assert_not_called()


def test_requires_a_session(enabled) -> None:  # noqa: ANN001
    response = client.post(URL, json={"confirm": True})
    # No credentials: refused by authentication (401, or 5xx where this
    # process has no auth backend). Never reaches the command.
    assert response.status_code in {401, 500, 503}


def test_deletes_the_session_user_only(enabled) -> None:  # noqa: ANN001
    service = MagicMock()
    service.delete_account.return_value = DeletionOutcome(status="done")
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 200
    assert response.json() == {"status": "done", "pending": []}
    service.delete_account.assert_called_once_with(user_id=USER_ID)


@pytest.mark.parametrize(
    "body",
    [{}, {"confirm": False}, {"confirm": True, "user_id": "someone-else"}],
)
def test_body_is_only_a_confirmation(enabled, body) -> None:  # noqa: ANN001
    service = MagicMock()
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json=body)
    assert response.status_code == 422
    service.delete_account.assert_not_called()


def test_form_post_is_refused(enabled) -> None:  # noqa: ANN001
    service = MagicMock()
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, data={"confirm": "true"})
    assert response.status_code == 422
    service.delete_account.assert_not_called()


def test_a_guest_is_deleted_by_the_same_command(enabled) -> None:  # noqa: ANN001
    service = MagicMock()
    service.delete_account.return_value = DeletionOutcome(status="done", pending=[])
    with (
        patch.object(account_route, "deletion_requester", _guest),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 200
    assert response.json() == {"status": "done", "pending": []}
    service.delete_account.assert_called_once_with(user_id=USER_ID)


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (AccountDeletionRejected("placeholder"), 403, "account_deletion_not_allowed"),
        (
            AccountDeletionRejected("business_owner_must_exit"),
            403,
            "account_deletion_not_allowed",
        ),
        (RuntimeError("boom"), 503, "account_deletion_incomplete"),
    ],
)
def test_failures_map_to_problems(enabled, error, status, code) -> None:  # noqa: ANN001
    service = MagicMock()
    service.delete_account.side_effect = error
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert USER_ID not in response.text


@pytest.mark.parametrize("construction_error", [None, RuntimeError("unavailable")])
@pytest.mark.parametrize("started", [False, True])
def test_service_unavailability_preserves_deletion_state(
    enabled, construction_error, started
) -> None:  # noqa: ANN001
    def requester(request):
        request.state.account_deletion_started = started
        return _registered(request)

    with (
        patch.object(account_route, "deletion_requester", requester),
        patch.object(
            account_route,
            "account_deletion_service",
            return_value=None,
            side_effect=construction_error,
        ),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 503
    assert response.json()["code"] == (
        "account_deletion_incomplete" if started else "account_deletion_unavailable"
    )
    assert response.headers.get("Retry-After") == ("5" if started else None)


def test_feedback_still_takes_deletion_requests_while_the_command_is_off() -> None:
    """Marcus S4: with the flag off the route is 404 and the web files the old
    support ticket instead (tests/test_alpha_api_supabase.py covers the
    enrichment)."""
    from argus.api.schemas import FeedbackRequest

    assert FeedbackRequest(type="account_deletion_request", message="delete me")


def test_another_request_holding_the_run_is_in_progress(enabled) -> None:  # noqa: ANN001
    service = MagicMock()
    service.delete_account.side_effect = AccountDeletionIncomplete("in_progress")
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 202
    assert response.json() == {"status": "in_progress", "pending": []}


def test_a_run_finished_by_another_request_is_done(enabled) -> None:  # noqa: ANN001
    """The session was verified, so the person existed a moment ago: a run
    that no longer knows them was finished in between."""
    service = MagicMock()
    service.delete_account.side_effect = AccountDeletionRejected("unknown_user")
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 200
    assert response.json() == {"status": "done", "pending": []}


def test_the_route_is_rate_limited_per_account(enabled) -> None:  # noqa: ANN001
    service = MagicMock()
    service.delete_account.side_effect = AccountDeletionIncomplete(
        "third_party_pending", ["apple"]
    )
    limit = account_route._PER_ACCOUNT[0]
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        codes = [
            client.post(URL, json={"confirm": True}).status_code for _ in range(limit + 1)
        ]
    assert codes == [202] * limit + [429]
    assert service.delete_account.call_count == limit


@pytest.mark.parametrize(
    ("error", "pending"),
    [
        (
            AccountDeletionIncomplete("third_party_pending", ["plaid", "apple"]),
            ["apple", "plaid"],
        ),
        (AccountDeletionIncomplete("units_changed"), []),
    ],
)
def test_a_pending_third_party_is_in_progress_not_done(enabled, error, pending) -> None:  # noqa: ANN001
    """The account is locked and the sweep finishes it: 202, never success."""
    service = MagicMock()
    service.delete_account.side_effect = error
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == 202
    assert response.json() == {"status": "in_progress", "pending": pending}


def test_deletion_does_not_need_the_households_surface(enabled, monkeypatch) -> None:  # noqa: ANN001
    """Households (and accounts, ingestion, Apple capture) off, deletion on:
    the command is still built, from deletion's own pool."""
    from argus.api import account_deletion_runtime as runtime
    from argus.api import households as households_api
    from argus.api import state as api_state

    monkeypatch.delenv("CUADRAO_HOUSEHOLDS_ENABLED", raising=False)
    monkeypatch.setattr(households_api, "_service", None)
    monkeypatch.setattr(api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(api_state, "DATABASE_URL", "postgresql://deletion@db/argus")
    monkeypatch.setattr(api_state, "supabase_gateway", MagicMock())
    built = {}

    def fake_build(**kwargs):  # noqa: ANN003, ANN202
        built.update(kwargs)
        service = MagicMock()
        service.delete_account.return_value = DeletionOutcome(status="done")
        return service

    monkeypatch.setattr(runtime, "build_service", fake_build)
    with patch.object(account_route, "deletion_requester", _registered):
        response = client.post(URL, json={"confirm": True})
    assert households_api.households_service() is None
    assert response.status_code == 200, response.text
    assert built["database_url"] == "postgresql://deletion@db/argus"


def test_the_deletion_repository_is_built_without_any_feature_service() -> None:
    from argus.api.account_deletion_runtime import household_repository
    from argus.domain.household.postgres import PostgresHouseholdRepository

    repository = household_repository(MagicMock())
    assert isinstance(repository, PostgresHouseholdRepository)


def test_fresh_apple_code_uses_current_session(enabled):
    service = MagicMock()
    service.delete_account.return_value = DeletionOutcome(status="done")
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(
            URL, json={"confirm": True, "apple_authorization_code": "fresh"}
        )
    assert response.status_code == 200
    service.delete_account.assert_called_once_with(
        user_id=USER_ID, apple_authorization_code="fresh"
    )


@pytest.mark.parametrize("code", ["", "x" * 513, "é"])
def test_fresh_code_bounds(enabled, code):
    service = MagicMock()
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(
            URL, json={"confirm": True, "apple_authorization_code": code}
        )
    assert response.status_code == 422
    service.delete_account.assert_not_called()


@pytest.mark.parametrize(
    "code,status",
    [
        ("apple_reauthorization_required", 409),
        ("apple_identity_mismatch", 409),
        ("apple_authorization_invalid", 400),
        ("account_deletion_unavailable", 503),
    ],
)
def test_admission_refusal_is_distinct_from_started_failure(enabled, code, status):
    from argus.domain.account_deletion.apple import AccountDeletionAdmissionError

    service = MagicMock()
    service.delete_account.side_effect = AccountDeletionAdmissionError(code, status)
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json={"confirm": True})
    assert response.status_code == status
    assert response.json()["code"] == code


@pytest.mark.parametrize("code", [None, "fresh-apple-code"])
def test_unreadable_admission_state_is_unavailable_not_accepted(enabled, code):
    from argus.domain.account_deletion.service import AccountDeletionService

    households = MagicMock()
    households.connection.side_effect = RuntimeError("database unavailable")
    admin = MagicMock()
    service = AccountDeletionService(
        households=households, auth_admin=admin, revoker=None, analytics=MagicMock()
    )
    body = {"confirm": True}
    if code is not None:
        body["apple_authorization_code"] = code
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.post(URL, json=body)
    assert response.status_code == 503
    assert response.json()["code"] == "account_deletion_incomplete"
    assert response.headers["Retry-After"] == "5"
    admin.lock_user.assert_not_called()
    admin.delete_user.assert_not_called()

"""The support request from an owner the delete command refuses (#1495)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from argus.api.guest_access import registered_account_context, store_account_context
from argus.api.main import app
from argus.api.routers import account as account_route
from argus.api.schemas import User
from argus.domain.account_deletion.support_request import SupportRequest
from faker import Faker
from fastapi.testclient import TestClient

client = TestClient(app)
fake = Faker()
URL = "/api/v1/account/deletion/request"
USER_ID = fake.uuid4()
EMAIL = fake.email()
_NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def _registered(request):  # noqa: ANN001, ANN202
    store_account_context(request, registered_account_context(USER_ID))
    return User(id=USER_ID, email=EMAIL, created_at=_NOW, updated_at=_NOW)


@pytest.fixture
def enabled(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setenv(account_route.FLAG, "true")


@pytest.fixture(autouse=True)
def _fresh_rate_limit():  # noqa: ANN202
    account_route._per_account_request.reset()
    yield
    account_route._per_account_request.reset()


@pytest.fixture
def notified():  # noqa: ANN201
    with patch.object(account_route, "notify_feedback_submitted") as notify:
        yield notify


def _post(service: MagicMock | None):  # noqa: ANN202
    with (
        patch.object(account_route, "deletion_requester", _registered),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        return client.post(URL)


def test_off_answers_404_before_auth(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv(account_route.FLAG, raising=False)
    auth = MagicMock(side_effect=AssertionError("auth must not run"))
    with patch.object(account_route, "deletion_requester", auth):
        response = client.post(URL)
    assert response.status_code == 404
    auth.assert_not_called()


@pytest.mark.parametrize("filed", [True, False])
def test_a_blocked_owner_gets_requested_every_time(enabled, notified, filed) -> None:  # noqa: ANN001
    business_id = fake.uuid4()
    service = MagicMock()
    service.request_support_deletion.return_value = SupportRequest(
        [business_id], filed=filed
    )

    response = _post(service)

    assert response.status_code == 200
    assert response.json() == {"status": "requested"}
    service.delete_account.assert_not_called()
    (user_id, context), _ = service.request_support_deletion.call_args
    assert user_id == USER_ID
    assert context["account_email"] == EMAIL
    assert context["request_user_id"] == USER_ID
    # Support hears once: a repeat files nothing and sends nothing.
    assert notified.call_count == (1 if filed else 0)


def test_a_person_who_can_delete_in_the_app_is_refused(enabled, notified) -> None:  # noqa: ANN001
    service = MagicMock()
    service.request_support_deletion.return_value = None

    response = _post(service)

    assert response.status_code == 409
    assert response.json()["code"] == "account_deletion_request_not_needed"
    notified.assert_not_called()


@pytest.mark.parametrize("broken", ["no_service", "raises"])
def test_a_request_that_cannot_be_filed_is_unavailable(enabled, notified, broken) -> None:  # noqa: ANN001
    service = MagicMock()
    service.request_support_deletion.side_effect = RuntimeError("database down")

    response = _post(None if broken == "no_service" else service)

    assert response.status_code == 503
    assert response.json()["code"] == "account_deletion_unavailable"
    notified.assert_not_called()


def test_the_request_is_rate_limited_per_account(enabled, notified) -> None:  # noqa: ANN001
    service = MagicMock()
    service.request_support_deletion.return_value = SupportRequest([], filed=False)
    statuses = [_post(service).status_code for _ in range(7)]
    assert statuses == [200] * 6 + [429]

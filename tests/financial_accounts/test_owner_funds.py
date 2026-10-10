from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.business import ledger
from argus.domain.owner_scope import PERSONAL, BusinessSpace
from argus.domain.recording.errors import AccountNotFound, IdempotencyConflict
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_schemas import MoneyRequest, OwnerFunds
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.service import FinancialAccountService
from pydantic import ValidationError

from tests.financial_accounts.test_loop_commands import NOW


@pytest.fixture
def funded_scene():
    repository = InMemoryFinancialAccountRepository(lambda: NOW)
    accounts = FinancialAccountService(repository, lambda: NOW)
    return MoneyService(accounts), str(uuid4()), BusinessSpace(str(uuid4()))


def entered(scope, **changes):
    return MoneyRequest(
        **{
            "kind": "expense",
            "amount": "850",
            "occurred_at": NOW - timedelta(days=1),
            "note": "Materials",
            "owner_funding": OwnerFunds(owner_space_id=scope.space_id, currency="DOP"),
            **changes,
        }
    )


def reviewed(money, user, scope, request):
    preview = money.preview(user_id=user, scope=scope, request=request)
    assert preview["affected_accounts"] == []
    return MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )


def test_accountless_expense_is_canonical_and_replays(funded_scene):
    money, user, scope = funded_scene
    request = reviewed(money, user, scope, entered(scope))
    first = money.write(user_id=user, scope=scope, request=request, idempotency_key="one")
    again = money.write(user_id=user, scope=scope, request=request, idempotency_key="one")
    assert again["replayed"] and again["activity"] == first["activity"]
    assert first["accounts"] == []
    assert first["activity"]["legs"] == []
    assert first["activity"]["funding"] == "owner_funds"
    assert first["activity"]["amount_minor"] == 85000
    rows = current_activities(money.accounts.list_accounts(user_id=user, scope=scope))
    assert rows == [first["activity"]]
    assert ledger.totals(
        ledger.expenses(rows, {}, NOW.date() - timedelta(days=2), NOW.date())
    ) == [{"currency": "DOP", "amount": "850.00", "count": 1}]
    assert (
        money.detail(
            user_id=user, scope=scope, activity_id=first["activity"]["activity_id"]
        )
        == first["activity"]
    )
    with pytest.raises(IdempotencyConflict):
        money.write(
            user_id=user,
            scope=scope,
            request=request.model_copy(update={"amount": "851"}),
            idempotency_key="one",
        )


@pytest.mark.parametrize("scope", [PERSONAL, BusinessSpace(str(uuid4()))])
def test_owner_funds_cannot_cross_scope(funded_scene, scope):
    money, user, own_scope = funded_scene
    with pytest.raises(AccountNotFound):
        money.preview(user_id=user, scope=scope, request=entered(own_scope))
    assert (
        current_activities(money.accounts.list_accounts(user_id=user, scope=scope)) == []
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "income"},
        {"account_id": str(uuid4())},
        {"source_account_id": str(uuid4())},
        {"source_id": "salary"},
        {"expected_revision": 1},
    ],
)
def test_owner_funds_forbids_account_or_other_kind(changes, funded_scene):
    with pytest.raises(ValidationError):
        entered(funded_scene[2], **changes)


def test_recorded_owner_funds_cannot_be_corrected_into_bank_debit(funded_scene):
    from argus.domain.recording.errors import RecordingInputError

    money, user, scope = funded_scene
    request = reviewed(money, user, scope, entered(scope))
    saved = money.write(
        user_id=user, scope=scope, request=request, idempotency_key="approved"
    )
    change = MoneyRequest(
        kind="expense",
        account_id=str(uuid4()),
        amount="850",
        occurred_at=NOW,
        expected_revision=1,
        reason="change payer",
    )
    with pytest.raises(RecordingInputError, match="recorded_correction_unsupported"):
        money.preview(
            user_id=user,
            scope=scope,
            request=change,
            activity_id=saved["activity"]["activity_id"],
        )


def test_durable_direct_business_expense_requires_approval():
    from types import SimpleNamespace

    from argus.domain.business.service import BusinessService
    from argus.domain.ingestion.reconcile.model import ReconcileError

    service = BusinessService(
        None,
        SimpleNamespace(
            money=SimpleNamespace(accounts=SimpleNamespace(_repository=object()))
        ),
        lambda _: frozenset(),
    )
    with pytest.raises(ReconcileError, match="human_approval_required"):
        service.record_expense(None, {}, "creator-is-not-authority")


@pytest.mark.parametrize("path", ["/preview", ""])
def test_personal_money_http_cannot_submit_owner_funds(client, path):
    from tests.financial_accounts.conftest import ALICE

    response = client.post(
        "/api/v1/financial-activities" + path,
        headers={
            "Authorization": f"Bearer {ALICE}",
            "Idempotency-Key": "browser-owner-funds",
        },
        json=entered(BusinessSpace(str(uuid4()))).model_dump(mode="json"),
    )
    assert response.status_code == 404

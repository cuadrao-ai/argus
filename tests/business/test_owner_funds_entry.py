from types import SimpleNamespace

from argus.api.financial_accounts import financial_accounts_service

from tests.business import test_business_api as shared

alice = shared.alice


def test_creator_cannot_use_direct_expense_route_for_durable_money(alice, monkeypatch):
    account = alice.account()
    service = financial_accounts_service()
    monkeypatch.setattr(
        service,
        "_repository",
        SimpleNamespace(list_accounts=service._repository.list_accounts),
    )
    response = alice.post(
        "/expenses",
        {
            "account_id": account,
            "amount": "850",
            "merchant": "Materials",
            "category_id": "other",
            "occurred_on": "2026-10-07",
        },
        key="direct-money-bypass",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "human_approval_required"


def test_owner_funded_expense_is_visible_without_account_or_balance(alice):
    from argus.domain.recording.money_service import MoneyService

    from tests.financial_accounts.test_owner_funds import entered, reviewed

    scope = alice.scope()
    money = MoneyService(financial_accounts_service())
    request = reviewed(money, scope.person_id, scope.owner, entered(scope.owner))
    receipt = money.write(
        user_id=scope.person_id,
        scope=scope.owner,
        request=request,
        idempotency_key="approved-owner-funds",
    )
    response = alice.get("/expenses", **{"from": "2026-09-01", "to": "2026-09-30"})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "id": receipt["activity"]["activity_id"],
            "merchant": "Materials",
            "amount": "850.00",
            "currency": "DOP",
            "category_id": None,
            "account_id": None,
            "funding": "owner_funds",
            "occurred_on": "2026-09-19",
            "receipt_id": None,
            "fiscal_known": True,
        }
    ]
    assert alice.get("/workspace").json()["accounts"] == []
    overview = alice.get("/overview", **{"from": "2026-09-01", "to": "2026-09-30"})
    assert overview.json()["totals"] == [
        {"currency": "DOP", "amount": "850.00", "count": 1}
    ]

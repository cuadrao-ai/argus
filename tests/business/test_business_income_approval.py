from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.actions.approval import _money_request
from argus.domain.business.actions.dossier import blockers
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dossier import AccountChoice
from argus.domain.business.contracts.facts import BusinessFacts


def _known(value):
    return {
        "state": "known",
        "value": value,
        "origin": "owner_stated",
        "source_ids": [uuid4()],
    }


def _facts(kind: str = "income", funding: dict | None = None) -> BusinessFacts:
    return BusinessFacts.model_validate(
        {
            "kind": _known(kind),
            "amount": _known("5000"),
            "currency": {
                "state": "known",
                "value": "DOP",
                "origin": "default",
                "source_ids": [],
            },
            "occurred_on": _known("2026-10-09"),
            "funding": _known(
                funding or {"kind": "business_account", "account_id": uuid4()}
            ),
            "business_share": _known({"kind": "all"}),
        }
    )


def _blockers(facts: BusinessFacts, account_type: str = "cash", currency: str = "DOP"):
    account = (
        (
            AccountChoice(
                id=facts.funding.value.account_id,
                nickname=None,
                type=account_type,
                currency=currency,
            ),
        )
        if facts.funding.state == "known"
        and facts.funding.value.kind == "business_account"
        else ()
    )
    return blockers(facts, account)


def test_income_draft_requires_receiving_account_and_exact_business_share() -> None:
    ready = _facts()
    assert _blockers(ready) == []
    assert _blockers(_facts("expense")) == []
    assert {
        (item.code, item.field)
        for item in _blockers(_facts("income", {"kind": "owner_funds"}))
    } == {("business_funding_unsupported", "funding")}
    partial = ready.model_dump(mode="json")
    partial["business_share"] = _known({"kind": "partial", "amount": "100"})
    assert any(
        item.code == "business_allocation_unsupported"
        for item in _blockers(BusinessFacts.model_validate(partial))
    )
    missing = ready.model_dump(mode="json")
    missing["amount"] = {"state": "unknown", "value": None}
    assert any(
        item.field == "amount"
        for item in _blockers(BusinessFacts.model_validate(missing))
    )
    assert any(
        item.code == "activity_kind_unsupported"
        for item in _blockers(_facts("loan_received"))
    )
    categorized = ready.model_dump(mode="json")
    categorized["category_id"] = _known("groceries")
    assert {
        (item.code, item.field)
        for item in _blockers(BusinessFacts.model_validate(categorized))
    } == {("business_category_unsupported", "category_id")}


def test_income_readiness_requires_scoped_liquid_matching_currency_account() -> None:
    income = _facts()
    assert _blockers(income) == []
    for account_type in ("credit_card", "other_debt"):
        assert {(item.code, item.field) for item in _blockers(income, account_type)} == {
            ("account_ineligible", "funding")
        }
    assert {(item.code, item.field) for item in _blockers(income, currency="USD")} == {
        ("import_currency_mismatch", "funding")
    }
    assert {(item.code, item.field) for item in blockers(income, ())} == {
        ("business_record_not_found", "funding")
    }
    expense = _facts("expense")
    assert _blockers(expense, "credit_card") == []


def test_income_money_request_uses_receiving_business_account_only() -> None:
    facts = _facts()
    request = _money_request(facts, uuid4(), "income")
    assert request.kind == "income"
    assert request.account_id == str(facts.funding.value.account_id)
    assert request.amount == "5000"
    assert request.occurred_at.date().isoformat() == "2026-10-09"
    assert request.owner_funding is None
    assert request.source_id is None
    assert request.category_id is None
    assert request.preview_token is None
    with pytest.raises(ActionError, match="activity_kind_unsupported"):
        _money_request(facts, uuid4(), "expense")
    with pytest.raises(ActionError, match="business_funding_unsupported"):
        _money_request(_facts("income", {"kind": "owner_funds"}), uuid4(), "income")


def test_expense_money_request_keeps_owner_funds_path() -> None:
    facts = _facts("expense", {"kind": "owner_funds"})
    request = _money_request(facts, uuid4(), "expense")
    assert request.kind == "expense"
    assert request.account_id is None
    assert request.owner_funding is not None

"""Confirm records one expense per receipt whatever order retries arrive in."""

from __future__ import annotations

import pytest
from argus.api.documents import documents_service
from argus.api.ingestion import ingestion_hub
from argus.domain.business.service import BusinessService
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.recording.money_service import MoneyService

from tests.business.receipt_stub import PURCHASE
from tests.business.test_business_api import Owner, alice, prepared  # noqa: F401

WINDOW = {"from": "2026-10-01", "to": "2026-10-31"}


def _reviewed(alice: Owner) -> tuple[str, int]:  # noqa: F811
    receipt_id = prepared(alice)
    version = alice.review(
        receipt_id, alice.detail(receipt_id)["version"], account_id=alice.account()
    ).json()["version"]
    return receipt_id, version


def _expense_ids(alice: Owner) -> list[str]:  # noqa: F811
    return [e["id"] for e in alice.get("/expenses", **WINDOW).json()["items"]]


def test_an_interrupted_claim_is_finished_by_the_next_confirm(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_id, version = _reviewed(alice)
    write = MoneyService.write

    def crash_after_claim(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
        raise RuntimeError("process died after the claim")

    monkeypatch.setattr(MoneyService, "write", crash_after_claim)
    assert alice.confirm(receipt_id, version, "tab-a").status_code == 500
    assert alice.detail(receipt_id)["status"] == "review_ready"
    assert _expense_ids(alice) == []

    monkeypatch.setattr(MoneyService, "write", write)
    other_tab = alice.confirm(receipt_id, version, "tab-b")
    assert other_tab.status_code == 200, other_tab.text
    assert other_tab.json()["status"] == "confirmed"
    [expense_id] = _expense_ids(alice)
    assert other_tab.json()["expense_id"] == expense_id
    retried = alice.confirm(receipt_id, version, "tab-a").json()
    assert (retried["status"], retried["expense_id"]) == ("confirmed", expense_id)
    assert _expense_ids(alice) == [expense_id]


def test_a_stale_confirm_is_409_even_with_fields_missing(alice: Owner) -> None:  # noqa: F811
    receipt_id = prepared(alice)
    seen = alice.detail(receipt_id)["version"]
    alice.review(receipt_id, seen, merchant="Ferretería La Esquina")
    stale = alice.confirm(receipt_id, seen, "k-1")
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    current = alice.detail(receipt_id)["version"]
    version = alice.review(receipt_id, current, account_id=alice.account()).json()[
        "version"
    ]
    stale = alice.confirm(receipt_id, current, "k-2")
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert alice.confirm(receipt_id, version, "k-3").json()["status"] == "confirmed"


def test_a_same_key_confirm_inside_another_records_one_expense(
    alice: Owner,  # noqa: F811
    stub,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirm changes nothing before it claims, so a same-key confirm that
    lands first leaves the outer one a replay rather than a stale version."""

    stub.rows = [{**PURCHASE, "direction": "unknown", "kind_hint": "unknown"}]
    receipt_id = prepared(alice)
    account = alice.account()
    service = BusinessService(documents_service(), ingestion_hub().sink, frozenset)
    scope = alice.scope()
    event_id = service.receipt(scope, receipt_id).review.event_id
    # The account is known without a Business review, as a remembered account
    # link would make it; the import's own kind is still undecided.
    version = ingestion_hub().sink.resolve(
        user_id=scope.person_id,
        event_id=event_id,
        version=alice.detail(receipt_id)["version"],
        changes={"account_id": account},
        scope=scope.owner,
    )["version"]
    assert alice.detail(receipt_id)["missing_fields"] == []
    accept = ReconciliationService.accept_reviewed
    inner = []

    def interleaved(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
        if not inner:
            inner.append(None)
            inner[0] = service.confirm(scope, receipt_id, version, "double-click")
        return accept(self, **kwargs)

    monkeypatch.setattr(ReconciliationService, "accept_reviewed", interleaved)
    outer = service.confirm(scope, receipt_id, version, "double-click")
    assert inner[0].status == outer.status == "confirmed"
    assert inner[0].review.expense_id == outer.review.expense_id
    assert _expense_ids(alice) == [outer.review.expense_id]
    [activity] = ingestion_hub().sink.money.purchases(
        user_id=scope.person_id, scope=scope.owner
    )["items"]
    assert activity["kind"] == "expense"


def test_a_replayed_key_that_is_not_an_expense_is_a_conflict(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = alice.account()
    body = {"account_id": account, "amount": "10.00", "occurred_on": "2026-10-02"}
    recorded = MoneyService.write_entered(
        ingestion_hub().sink.money,
        user_id=alice.person,
        request=_income(account),
        idempotency_key="exp-1",
        scope=alice.scope().owner,
    )
    assert recorded["activity"]["kind"] == "income"

    def replay(self, **_):  # noqa: ANN001, ANN003, ANN202
        return recorded

    monkeypatch.setattr(MoneyService, "write_entered", replay)
    conflict = alice.post("/expenses", body, key="exp-1")
    assert (conflict.status_code, conflict.json()["code"]) == (
        409,
        "idempotency_conflict",
    )


def _income(account: str):  # noqa: ANN202
    from datetime import datetime, timezone

    from argus.domain.recording.money_schemas import MoneyRequest

    return MoneyRequest(
        kind="income",
        account_id=account,
        amount="10.00",
        occurred_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        source_id="other",
    )

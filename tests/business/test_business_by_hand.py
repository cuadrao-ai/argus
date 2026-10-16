"""A receipt nobody read is completed by hand, saved once, and linked to its source."""

from __future__ import annotations

import pytest
from argus.api.ingestion import ingestion_hub
from argus.domain.ingestion.reconcile.service import ReconciliationService
from fastapi.testclient import TestClient

from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401

WINDOW = {"from": "2026-10-01", "to": "2026-10-31"}
UNREAD = ["account_id", "amount", "currency", "occurred_on"]


def _saved(alice: Owner) -> str:  # noqa: F811
    uploaded = alice.upload(consent=False)
    assert uploaded.json()["status"] == "saved"
    return uploaded.json()["id"]


def _imports(alice: Owner) -> list[dict]:  # noqa: F811
    """The Business space's imports; Personal review never lists them."""

    for state in ("open", "accepted"):
        personal = alice.client.get(
            f"/api/v1/financial-imports?state={state}", headers=alice.auth
        )
        assert personal.json()["items"] == []
    scope = alice.scope()
    return ingestion_hub().sink.list(
        user_id=scope.person_id, states=("open", "accepted"), scope=scope.owner
    )


def test_declined_ai_receipt_is_entered_by_hand_and_saved_once(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
    client: TestClient,
) -> None:
    receipt_id = _saved(alice)
    account = alice.account()
    unread = alice.detail(receipt_id)
    assert (unread["version"], unread["missing_fields"], unread["evidence"]) == (
        0,
        UNREAD,
        None,
    )
    refused = alice.confirm(receipt_id, 0, "too-early")
    assert (refused.status_code, refused.json()["code"]) == (422, "missing_fields")

    entered = alice.review(
        receipt_id,
        0,
        merchant="Colmado Don Pedro",
        occurred_on="2026-10-07",
        amount="706.10",
        currency="DOP",
        category_id="groceries",
        account_id=account,
    )
    assert entered.status_code == 200, entered.text
    body = entered.json()
    assert {
        key: body[key]
        for key in (
            "status",
            "merchant",
            "occurred_on",
            "amount",
            "currency",
            "category_id",
            "account_id",
            "missing_fields",
            "evidence",
            "expense_id",
        )
    } == {
        "status": "review_ready",
        "merchant": "Colmado Don Pedro",
        "occurred_on": "2026-10-07",
        "amount": "706.1",
        "currency": "DOP",
        "category_id": "groceries",
        "account_id": account,
        "missing_fields": [],
        "evidence": None,
        "expense_id": None,
    }
    again = alice.review(receipt_id, 0, merchant="Otra vez")
    assert (again.status_code, again.json()["code"]) == (409, "stale_version")
    assert len(_imports(alice)) == 1

    confirmed = alice.confirm(receipt_id, body["version"], "by-hand").json()
    replay = alice.confirm(receipt_id, body["version"], "by-hand").json()
    assert confirmed["status"] == replay["status"] == "confirmed"
    assert confirmed["expense_id"] == replay["expense_id"]
    assert alice.get("/expenses", **WINDOW).json()["items"] == [
        {
            "id": confirmed["expense_id"],
            "merchant": "Colmado Don Pedro",
            "amount": "706.10",
            "currency": "DOP",
            "category_id": "groceries",
            "account_id": account,
            "occurred_on": "2026-10-07",
            "receipt_id": receipt_id,
            "fiscal_known": True,
        }
    ]
    assert alice.get(f"/receipts/{receipt_id}/source").json()["code"] == "document_source_unavailable"

    prepare = alice.post(
        f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}
    )
    generic = client.post(
        f"/api/v1/financial-documents/{receipt_id}/prepare",
        headers={**alice.auth, "X-Extraction-Consent": "true"},
    )
    assert [(r.status_code, r.json()["code"]) for r in (prepare, generic)] == [
        (409, "document_entered_by_owner"),
        (404, "financial_document_not_found"),
    ]
    assert stub.calls == []
    assert len(_imports(alice)) == 1


def test_unknown_fields_stay_unknown_until_the_owner_supplies_them(
    alice: Owner,  # noqa: F811
) -> None:
    receipt_id = _saved(alice)
    stale = alice.review(receipt_id, 3, merchant="Colmado")
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    partial = alice.review(receipt_id, 0, merchant="Colmado").json()
    assert (partial["merchant"], partial["amount"], partial["missing_fields"]) == (
        "Colmado",
        None,
        UNREAD,
    )
    assert partial["status"] == "review_ready"
    refused = alice.confirm(receipt_id, partial["version"], "k")
    assert (refused.status_code, refused.json()["code"]) == (422, "missing_fields")


def test_an_interrupted_entry_is_finished_by_the_next_review(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_id = _saved(alice)
    submit = ReconciliationService.submit

    def down(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
        raise RuntimeError("review queue unavailable")

    monkeypatch.setattr(ReconciliationService, "submit", down)
    failed = alice.review(receipt_id, 0, merchant="Colmado")
    assert (failed.status_code, failed.json()["code"]) == (
        503,
        "document_delivery_failed",
    )
    interrupted = alice.detail(receipt_id)
    assert (interrupted["version"], interrupted["missing_fields"]) == (0, UNREAD)

    monkeypatch.setattr(ReconciliationService, "submit", submit)
    finished = alice.review(receipt_id, 0, merchant="Colmado").json()
    assert (finished["status"], finished["merchant"]) == ("review_ready", "Colmado")
    assert len(_imports(alice)) == 1

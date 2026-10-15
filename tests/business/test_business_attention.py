"""Every receipt that needs attention names its next step, and each step works."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from argus.api.documents import documents_service
from argus.api.ingestion import ingestion_hub
from argus.domain.ingestion.documents.jobs import OUTCOME_UNKNOWN
from argus.domain.ingestion.reconcile.service import ReconciliationService

from tests.business.receipt_stub import PURCHASE, ReceiptStub
from tests.business.test_business_api import (  # noqa: F401
    EVIDENCE,
    Owner,
    alice,
    bob,
    prepared,
)

SECOND = (
    Path(__file__).parents[1] / "document_extraction_fixtures/unreadable.png"
).read_bytes()
WINDOW = {"from": "2026-10-01", "to": "2026-10-31"}
UNREAD = ["account_id", "amount", "currency", "occurred_on"]
CONSENT = {"X-Extraction-Consent": "true"}
NEXT = ("status", "attention", "preparable", "enterable")


def _next(receipt: dict) -> tuple:
    return tuple(receipt[key] for key in NEXT)


def _events(alice: Owner) -> list[tuple[str, str | None]]:  # noqa: F811
    scope = alice.scope()
    return sorted(
        (event["state"], event["activity_id"] and "expense")
        for event in ingestion_hub().sink.list(
            user_id=scope.person_id,
            states=("open", "accepting", "accepted", "dismissed"),
            scope=scope.owner,
        )
    )


def _enter_and_confirm(alice: Owner, receipt_id: str) -> dict:  # noqa: F811
    account = alice.account()
    fields = {
        "merchant": "Ferretería La Esquina",
        "occurred_on": "2026-10-06",
        "amount": "3450.00",
        "currency": "DOP",
        "account_id": account,
    }
    entered = alice.review(receipt_id, 0, **fields)
    assert entered.status_code == 200, entered.text
    body = entered.json()
    assert (_next(body), body["missing_fields"]) == (
        ("review_ready", None, False, False),
        [],
    )
    replayed = alice.review(receipt_id, 0, merchant="Otra")
    assert (replayed.status_code, replayed.json()["code"]) == (409, "stale_version")
    first = alice.confirm(receipt_id, body["version"], "by-hand").json()
    second = alice.confirm(receipt_id, body["version"], "other-tab").json()
    assert first["status"] == second["status"] == "confirmed"
    assert first["expense_id"] == second["expense_id"]
    [expense] = alice.get("/expenses", **WINDOW).json()["items"]
    assert (expense["id"], expense["receipt_id"], expense["amount"]) == (
        first["expense_id"],
        receipt_id,
        "3450.00",
    )
    return body


def test_a_failed_read_offers_a_consented_retry_and_entry_by_hand(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.failure = "extraction_provider_failed"
    receipt_id = prepared(alice)
    failed = alice.detail(receipt_id)
    assert (_next(failed), failed["error_code"], failed["version"]) == (
        ("needs_attention", "ai_unavailable", True, True),
        "extraction_provider_failed",
        0,
    )
    [listed] = alice.get("/receipts").json()["items"]
    assert _next(listed) == _next(failed)
    assert alice.get("/updates").json()["items"][0]["attention"] == "ai_unavailable"
    refused = alice.post(f"/receipts/{receipt_id}/prepare")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "document_extraction_consent_required",
    )
    assert stub.calls == [receipt_id]

    retried = alice.post(f"/receipts/{receipt_id}/prepare", **CONSENT)
    assert retried.status_code == 200, retried.text
    ready = alice.detail(receipt_id)
    assert (_next(ready), ready["evidence"]) == (
        ("review_ready", None, False, False),
        EVIDENCE,
    )
    assert stub.calls == [receipt_id, receipt_id]


def test_an_unknown_outcome_is_retried_only_with_the_owners_consent(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    receipt_id = alice.upload(consent=False).json()["id"]
    documents, person = documents_service(), alice.scope().person_id
    draft = documents.store.draft(user_id=person, connection_id=receipt_id)
    documents._update(person, draft, status="needs_attention", error_code=OUTCOME_UNKNOWN)
    unknown = alice.detail(receipt_id)
    assert (_next(unknown), unknown["error_code"]) == (
        ("needs_attention", "outcome_unknown", True, True),
        OUTCOME_UNKNOWN,
    )
    alice.get("/receipts")
    alice.get("/overview", **WINDOW)
    assert stub.calls == []

    assert alice.reading(True).status_code == 200
    assert stub.calls == []
    assert alice.post(f"/receipts/{receipt_id}/prepare", **CONSENT).status_code == 200
    assert _next(alice.detail(receipt_id)) == ("review_ready", None, False, False)
    assert stub.calls == [receipt_id]


def test_a_file_the_ai_cannot_open_is_entered_by_hand_without_a_retry(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.failure = "encrypted_document"
    receipt_id = prepared(alice)
    assert _next(alice.detail(receipt_id)) == (
        "needs_attention",
        "unreadable",
        False,
        True,
    )
    _enter_and_confirm(alice, receipt_id)
    assert _events(alice) == [("accepted", "expense")]


def test_an_unreadable_read_is_finished_by_hand_and_keeps_what_was_read(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.readable = False
    receipt_id = prepared(alice)
    read = alice.detail(receipt_id)
    assert (
        _next(read),
        read["error_code"],
        read["version"],
        read["missing_fields"],
        read["evidence"],
    ) == (
        ("needs_attention", "unreadable", False, True),
        "unreadable_document",
        0,
        UNREAD,
        EVIDENCE,
    )
    entered = _enter_and_confirm(alice, receipt_id)
    assert entered["evidence"] == EVIDENCE
    assert _events(alice) == [("accepted", "expense")]
    assert alice.post(f"/receipts/{receipt_id}/prepare", **CONSENT).status_code == 200
    assert stub.calls == [receipt_id]
    assert alice.detail(receipt_id)["status"] == "confirmed"
    assert len(alice.get("/expenses", **WINDOW).json()["items"]) == 1


def test_a_document_with_no_receipt_purchase_sets_the_reading_aside(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.details = None
    receipt_id = prepared(alice)
    read = alice.detail(receipt_id)
    assert (_next(read), read["evidence"]) == (
        ("needs_attention", "no_purchase_found", False, True),
        None,
    )
    assert _events(alice) == [("open", None)]
    _enter_and_confirm(alice, receipt_id)
    assert _events(alice) == [("accepted", "expense"), ("dismissed", None)]


def test_receipt_details_with_no_purchase_row_say_no_purchase_was_found(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.rows = []
    receipt_id = prepared(alice)
    read = alice.detail(receipt_id)
    assert _next(read) == ("needs_attention", "no_purchase_found", False, True)
    assert read["evidence"] is not None
    _enter_and_confirm(alice, receipt_id)
    assert _events(alice) == [("accepted", "expense")]


def test_several_purchases_are_set_aside_for_the_owners_one_purchase(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.rows = [
        PURCHASE,
        {**PURCHASE, "row": 2, "evidence": "payment_notice", "amount": "100.00"},
    ]
    receipt_id = prepared(alice)
    assert _next(alice.detail(receipt_id)) == (
        "needs_attention",
        "several_purchases",
        False,
        True,
    )
    assert _events(alice) == [("open", None), ("open", None)]
    _enter_and_confirm(alice, receipt_id)
    assert _events(alice) == [
        ("accepted", "expense"),
        ("dismissed", None),
        ("dismissed", None),
    ]


def test_an_ambiguous_purchase_is_entered_by_hand(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.rows = [{**PURCHASE, "amount": "3000.00"}]
    receipt_id = prepared(alice)
    read = alice.detail(receipt_id)
    assert (_next(read), read["evidence"]) == (
        ("needs_attention", "several_purchases", False, True),
        EVIDENCE,
    )
    _enter_and_confirm(alice, receipt_id)
    assert _events(alice) == [("accepted", "expense")]


def test_review_with_an_account_outside_this_space_is_404(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    receipt_id = prepared(alice)
    version = alice.detail(receipt_id)["version"]
    personal = alice.client.post(
        "/api/v1/financial-accounts",
        json={"type": "checking", "currency": "DOP", "nickname": "Casa"},
        headers={**alice.auth, "Idempotency-Key": str(uuid4())},
    ).json()["id"]
    elsewhere = bob.account()
    refused = [
        alice.review(receipt_id, version, account_id=account)
        for account in (personal, elsewhere)
    ]
    assert [(r.status_code, r.json()["code"]) for r in refused] == [
        (404, "financial_account_not_found")
    ] * 2
    saved = alice.upload(content=SECOND, consent=False)
    assert saved.status_code == 200, saved.text
    saved_id = saved.json()["id"]
    by_hand = alice.review(saved_id, 0, account_id=personal)
    assert (by_hand.status_code, by_hand.json()["code"]) == (
        404,
        "financial_account_not_found",
    )
    untouched = alice.detail(saved_id)
    assert (_next(untouched), untouched["version"]) == (
        ("saved", None, True, True),
        0,
    )
    assert _events(alice) == [("open", None)]


def test_an_entry_interrupted_before_the_reads_are_set_aside_finishes_next_time(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub.rows = [
        PURCHASE,
        {**PURCHASE, "row": 2, "evidence": "payment_notice", "amount": "100.00"},
    ]
    receipt_id = prepared(alice)
    dismiss = ReconciliationService.dismiss

    def down(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
        raise RuntimeError("review queue unavailable")

    monkeypatch.setattr(ReconciliationService, "dismiss", down)
    failed = alice.review(receipt_id, 0, merchant="Ferretería")
    assert failed.status_code >= 500
    entered = alice.detail(receipt_id)
    assert (_next(entered), entered["merchant"]) == (
        ("review_ready", None, False, False),
        None,
    )
    assert _events(alice) == [("open", None)] * 3

    monkeypatch.setattr(ReconciliationService, "dismiss", dismiss)
    healed = alice.review(receipt_id, entered["version"], merchant="Ferretería")
    assert healed.status_code == 200, healed.text
    assert _events(alice) == [("dismissed", None), ("dismissed", None), ("open", None)]

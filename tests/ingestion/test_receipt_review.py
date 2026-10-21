"""A receipt's review composed from its draft, evidence and import event."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from argus.api.documents import documents_service
from argus.domain.ingestion.documents import extractor as provider
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.domain.ingestion.receipt_review import (
    RECEIPT_EVENT_STATES,
    receipt_ids,
    receipt_review,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest

from tests.ingestion.conftest import ALICE, bearer

DOCUMENTS = "/api/v1/financial-documents"
IMPORTS = "/api/v1/financial-imports"
RECEIPT = Path(__file__).parents[1] / "document_extraction_fixtures/receipt-dop.png"

PURCHASE = {
    "page": 1,
    "row": 1,
    "evidence": "transaction",
    "status": "posted",
    "amount": "1180.00",
    "currency": "DOP",
    "occurred_on": "2026-10-03",
    "direction": "outflow",
    "kind_hint": "expense",
    "merchant": "Ferreteria Ochoa",
}
DETAILS = {
    "payment_status": "paid",
    "merchant": "Ferreteria Ochoa",
    "occurred_on": "2026-10-03",
    "currency": "DOP",
    "items": [
        {"id": "1", "description": "Tornillos", "quantity": "2", "total": "300.00"},
        {"id": "2", "description": "Pintura", "quantity": "1", "total": "700.00"},
    ],
    "subtotal": "1000.00",
    "tax": "180.00",
    "total": "1180.00",
}


def _extract(monkeypatch, observations, receipt=DETAILS):
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("ARGUS_VISION_MODEL", "test/vision")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key")
    result = ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "observations": observations,
            "receipt": receipt,
        }
    )
    monkeypatch.setattr(
        provider, "invoke_openrouter_json_schema", AsyncMock(return_value=result)
    )
    monkeypatch.setattr(
        documents_service(),
        "extractor",
        provider.DocumentExtractor(DocumentExtractionSettings(enabled=True)),
    )


def _upload(client, consent="true"):
    response = client.post(
        DOCUMENTS,
        content=RECEIPT.read_bytes(),
        headers={
            **bearer(ALICE),
            "Content-Type": "image/png",
            "X-Extraction-Consent": consent,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["connection_id"]


def _review(identities, receipt_id):
    service = documents_service()
    user = identities[ALICE]["id"]
    draft = service.get(user_id=user, connection_id=receipt_id, scope=PERSONAL)
    batch = service.store.get(user_id=user, connection_id=receipt_id)
    events = service.hub.sink.list(
        user_id=user, states=RECEIPT_EVENT_STATES, scope=PERSONAL
    )
    return receipt_review(draft, batch, events)


def _receipt_ids(identities, activity_ids):
    service = documents_service()
    user = identities[ALICE]["id"]
    with service.hub.sink.store.transaction(user, scope=PERSONAL) as tx:
        return receipt_ids(tx, service.store, user, activity_ids)


def _account(client):
    return client.post(
        "/api/v1/financial-accounts",
        json={"type": "checking", "currency": "DOP", "nickname": "Caja"},
        headers={**bearer(ALICE), "Idempotency-Key": str(uuid4())},
    ).json()["id"]


def _resolve(client, event_id, version, changes):
    response = client.patch(
        f"{IMPORTS}/{event_id}",
        headers=bearer(ALICE),
        json={"version": version, "changes": changes},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _accept(client, event_id, version):
    preview = client.post(
        f"{IMPORTS}/{event_id}/preview", json={}, headers=bearer(ALICE)
    ).json()["preview"]
    accepted = client.post(
        f"{IMPORTS}/{event_id}/accept",
        json={
            "version": version,
            "request": {
                **preview["reviewed_request"],
                "preview_token": preview["preview_token"],
            },
        },
        headers={**bearer(ALICE), "Idempotency-Key": str(uuid4())},
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()["activity"]


def _only_import(client):
    [event] = client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]
    return event


def test_line_items_make_one_purchase_at_the_receipt_total(
    client, monkeypatch, identities
):
    _extract(monkeypatch, [PURCHASE])
    receipt_id = _upload(client)
    review = _review(identities, receipt_id)
    assert (review.status, review.blocker, review.missing) == (
        "review_ready",
        None,
        ("account_id",),
    )
    assert review.event_id == _only_import(client)["id"]
    assert Decimal(review.fields.amount) == Decimal("1180.00")
    assert (review.fields.note, review.fields.currency) == ("Ferreteria Ochoa", "DOP")
    assert [item["total"] for item in review.evidence["receipt"]["items"]] == [
        "300.00",
        "700.00",
    ]


def test_line_items_reported_as_purchases_are_ambiguous(client, monkeypatch, identities):
    rows = [
        {**PURCHASE, "row": 1, "amount": "300.00"},
        {**PURCHASE, "row": 2, "amount": "700.00"},
        {**PURCHASE, "row": 3, "amount": "1180.00"},
    ]
    _extract(monkeypatch, rows)
    receipt_id = _upload(client)
    review = _review(identities, receipt_id)
    assert client.get(IMPORTS, headers=bearer(ALICE)).json()["items"] == []
    assert (review.status, review.error_code, review.blocker) == (
        "needs_attention",
        "receipt_purchase_ambiguous",
        "receipt_purchase_ambiguous",
    )
    assert review.evidence["issues"] == ["receipt_purchase_ambiguous"]
    assert review.fields is None
    assert review.evidence["receipt"]["total"] == "1180.00"


@pytest.mark.parametrize(
    "mismatch",
    [{"amount": "1000.00"}, {"currency": "USD"}, {"occurred_on": "2026-10-04"}],
    ids=["total", "currency", "date"],
)
def test_one_row_that_disagrees_with_the_receipt_is_ambiguous(
    client, monkeypatch, identities, mismatch
):
    _extract(monkeypatch, [{**PURCHASE, **mismatch}])
    receipt_id = _upload(client)
    review = _review(identities, receipt_id)
    assert client.get(IMPORTS, headers=bearer(ALICE)).json()["items"] == []
    assert review.evidence["issues"] == ["receipt_purchase_ambiguous"]
    assert (review.error_code, review.blocker, review.fields) == (
        "receipt_purchase_ambiguous",
        "receipt_purchase_ambiguous",
        None,
    )


def test_a_receipt_with_two_activity_rows_has_several_purchases(
    client, monkeypatch, identities
):
    notice = {
        **PURCHASE,
        "row": 2,
        "evidence": "payment_notice",
        "amount": "50.00",
        "kind_hint": "fee",
        "merchant": "Banco",
    }
    _extract(monkeypatch, [PURCHASE, notice])
    receipt_id = _upload(client)
    assert len(client.get(IMPORTS, headers=bearer(ALICE)).json()["items"]) == 2
    review = _review(identities, receipt_id)
    assert (review.blocker, review.error_code, review.fields) == (
        "several_purchases_found",
        None,
        None,
    )


def test_saved_without_consent_is_not_prepared(client, monkeypatch, identities):
    _extract(monkeypatch, [PURCHASE])
    receipt_id = _upload(client, consent="false")
    review = _review(identities, receipt_id)
    assert (review.status, review.blocker, review.evidence, review.fields) == (
        "saved",
        "not_prepared",
        None,
        None,
    )


def test_review_corrects_and_confirms_without_rewriting_evidence(
    client, monkeypatch, identities
):
    _extract(monkeypatch, [PURCHASE])
    receipt_id = _upload(client)
    review = _review(identities, receipt_id)
    assert review.expense_id is None

    corrected_event = _resolve(
        client,
        review.event_id,
        review.event_version,
        {"account_id": _account(client), "note": "Ochoa Hardware", "amount": "1100.00"},
    )
    corrected = _review(identities, receipt_id)
    assert corrected.fields.note == "Ochoa Hardware"
    assert Decimal(corrected.fields.amount) == Decimal("1100.00")
    assert corrected.missing == ()
    assert corrected.evidence == review.evidence
    assert corrected.evidence["receipt"]["merchant"] == "Ferreteria Ochoa"
    assert corrected.evidence["receipt"]["total"] == "1180.00"

    activity = _accept(client, review.event_id, corrected_event["version"])
    assert activity["note"] == "Ochoa Hardware"
    assert Decimal(activity["amount"]) == Decimal("1100.00")

    confirmed = _review(identities, receipt_id)
    assert (confirmed.status, confirmed.expense_id) == (
        "confirmed",
        activity["activity_id"],
    )
    assert _receipt_ids(identities, [activity["activity_id"], str(uuid4())]) == {
        activity["activity_id"]: receipt_id
    }

    documents_service().hub.disconnect(
        user_id=identities[ALICE]["id"], connection_id=receipt_id, scope=PERSONAL
    )
    assert _receipt_ids(identities, [activity["activity_id"]]) == {}


def test_a_statement_row_is_not_a_receipt(client, monkeypatch, identities):
    _extract(monkeypatch, [PURCHASE], receipt=None)
    statement_id = _upload(client)
    event = _only_import(client)
    event = _resolve(
        client, event["id"], event["version"], {"account_id": _account(client)}
    )
    activity = _accept(client, event["id"], event["version"])
    assert _receipt_ids(identities, [activity["activity_id"]]) == {}
    assert _review(identities, statement_id).blocker == "no_purchase_found"


def test_activity_recorded_by_hand_has_a_receipt_only_once_linked(
    client, monkeypatch, identities
):
    """An expense recorded by hand has no receipt until an import of a receipt
    is linked to it."""

    user = identities[ALICE]["id"]
    account = _account(client)
    money = documents_service().hub.sink.money
    preview = money.preview(
        user_id=user,
        request=MoneyRequest(
            kind="expense",
            account_id=account,
            amount="1180.00",
            occurred_at=datetime(2026, 10, 3, 15, tzinfo=timezone.utc),
        ),
        scope=PERSONAL,
    )
    manual = money.write(
        user_id=user,
        request=MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        ),
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )["activity"]["activity_id"]
    assert _receipt_ids(identities, [manual]) == {}

    _extract(monkeypatch, [PURCHASE])
    receipt_id = _upload(client)
    event = _only_import(client)
    linked = client.post(
        f"{IMPORTS}/{event['id']}/link-activity",
        json={"version": event["version"], "activity_id": manual},
        headers=bearer(ALICE),
    )
    assert linked.status_code == 200, linked.text
    assert _receipt_ids(identities, [manual]) == {manual: receipt_id}
    assert _review(identities, receipt_id).expense_id == manual


@pytest.fixture(autouse=True)
def _surface(client):
    assert documents_service() is not None

"""A fake Dominican hotel e-CF, as the email with the rendered body and the
XML attached, as the XML alone, or as a PDF render, is one receipt whose
amount is the DOP total paid. The USD total is never the expense: a read
that picks it on a document that names DOP is held with the basis recorded."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from argus.api.documents import documents_service

from tests.business.receipt_stub import PURCHASE, ReceiptStub
from tests.business.test_business_api import Owner, alice  # noqa: F401

FIXTURES = Path(__file__).parents[1] / "document_extraction_fixtures"
ECF = "E320000001234"
HOTEL = "Hotel Brisa del Este SRL"
READ = {
    **PURCHASE,
    "amount": "33254.91",
    "occurred_on": "2026-10-09",
    "merchant": HOTEL,
}
DETAILS = {
    "merchant": HOTEL,
    "occurred_on": "2026-10-09",
    "currency": "DOP",
    "items": [
        {"id": "1", "description": "Room Charge", "total": "24620.40"},
        {"id": "2", "description": "Minibar", "total": "1360.00"},
    ],
    "subtotal": "25980.40",
    "tax": "4676.47",
    "tip": "2598.04",
    "total": "33254.91",
    "rnc": "131111222",
    "ecf": ECF,
    "itbis": "4676.47",
}
FILES = [
    ("hotel-ecf.eml", "message/rfc822"),
    ("hotel-ecf.xml", "text/xml"),
    ("hotel-ecf.pdf", "application/pdf"),
]


@pytest.mark.parametrize("filename,media_type", FILES)
def test_each_hotel_invoice_file_is_one_receipt_at_the_dop_total(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
    filename: str,
    media_type: str,
) -> None:
    stub.rows = [READ]
    stub.details = DETAILS
    content = (FIXTURES / filename).read_bytes()
    uploaded = alice.upload(content=content, name=filename, media_type=media_type)
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    detail = alice.detail(receipt_id)
    assert (detail["status"], detail["media_type"], detail["filename"]) == (
        "review_ready",
        media_type,
        filename,
    )
    assert (detail["amount"], detail["currency"]) == ("33254.91", "DOP")
    assert (detail["merchant"], detail["occurred_on"]) == (HOTEL, "2026-10-09")
    evidence = detail["evidence"]
    assert (evidence["total"], evidence["currency"]) == ("33254.91", "DOP")
    assert (evidence["tax"], evidence["tip"]) == ("4676.47", "2598.04")
    assert [line["amount"] for line in evidence["lines"]] == ["24620.40", "1360.00"]
    # The e-NCF, RNC and ITBIS stay with the saved read, as the bridge's fiscal facts.
    batch = documents_service().store.get(
        user_id=alice.scope().person_id, connection_id=receipt_id
    )
    assert (batch.receipt.ecf, batch.receipt.rnc, batch.receipt.itbis) == (
        ECF,
        "131111222",
        "4676.47",
    )
    assert batch.metadata.get("document_currency") == (
        "DOP" if media_type != "application/pdf" else None
    )
    assert stub.calls == [receipt_id]
    assert alice.get(f"/receipts/{receipt_id}/source").json()["code"] == "document_source_unavailable"
    # The XML, alone or attached, is checked locally; the PDF render cannot be.
    if media_type == "application/pdf":
        assert batch.ecf_checks is None
    else:
        states = {c.name: (c.state, c.code) for c in batch.ecf_checks.checks}
        assert states["signature_integrity"] == ("not_checked", "no_signature")
        assert states["totals_arithmetic"] == ("verified", None)
        assert states["read_matches_xml"] == ("verified", None)
        assert states["dgii_accepted"] == ("not_checked", "network_not_in_tier_a")
        assert (batch.ecf_checks.encf, batch.ecf_checks.tipo_ecf) == (ECF, "32")


def test_a_usd_read_of_the_xml_invoice_is_held_and_recorded(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    stub.rows = [{**READ, "amount": "567.30", "currency": "USD"}]
    stub.details = {**DETAILS, "currency": "USD", "total": "567.30"}
    content = (FIXTURES / "hotel-ecf.xml").read_bytes()
    uploaded = alice.upload(content=content, name="hotel-ecf.xml", media_type="text/xml")
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    detail = alice.detail(receipt_id)
    assert detail["status"] == "needs_attention"
    assert detail["error_code"] == "receipt_purchase_ambiguous"
    batch = documents_service().store.get(
        user_id=alice.scope().person_id, connection_id=receipt_id
    )
    assert batch.candidates == ()
    assert {issue.code for issue in batch.issues} >= {
        "receipt_currency_conflict",
        "receipt_purchase_ambiguous",
    }
    assert [row.amount for row in batch.observations] == ["567.30"]
    assert batch.metadata["document_currency"] == "DOP"
    assert alice.get(
        "/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}
    ).json() == {"items": []}


def test_a_usd_read_of_the_pdf_render_is_not_held_by_the_guard(
    alice: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    # A PDF names no currency for itself; only a person can know. The read stands.
    stub.rows = [{**READ, "amount": "567.30", "currency": "USD"}]
    stub.details = {**DETAILS, "currency": "USD", "total": "567.30"}
    content = (FIXTURES / "hotel-ecf.pdf").read_bytes()
    uploaded = alice.upload(
        content=content, name="hotel-ecf.pdf", media_type="application/pdf"
    )
    assert uploaded.status_code == 200, uploaded.text
    detail = alice.detail(uploaded.json()["id"])
    assert (detail["status"], Decimal(detail["amount"]), detail["currency"]) == (
        "review_ready",
        Decimal("567.30"),
        "USD",
    )

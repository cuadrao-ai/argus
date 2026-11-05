"""Orders and estimated charges remain source evidence, not paid purchases."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import ExtractionBatch, ExtractionResult


def read_receipt(**receipt_fields: object) -> ExtractionResult:
    return ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "receipt": {
                "merchant": "Synthetic Shop",
                "subtotal": "40.00",
                "total": "43.20",
                **receipt_fields,
            },
            "observations": [
                {
                    "page": 1,
                    "row": 1,
                    "evidence": "transaction",
                    "status": "posted",
                    "amount": "43.20",
                    "currency": "USD",
                    "occurred_on": "2026-10-10",
                    "direction": "outflow",
                    "kind_hint": "expense",
                }
            ],
        }
    )


def project(parsed: ExtractionResult) -> ExtractionBatch:
    return batch_from_result(
        parsed, "a" * 64, "synthetic-connection", datetime.now(timezone.utc), 1
    )


@pytest.mark.parametrize("payment_status", ["unknown", "pending"])
def test_unpaid_read_keeps_its_purchase_and_payment_evidence(payment_status):
    parsed = read_receipt(payment_status=payment_status, estimated_tax="3.20")
    batch = project(parsed)
    assert len(batch.candidates) == 1
    assert Decimal(batch.candidates[0].amount) == Decimal("43.20")
    assert not batch.issues
    assert batch.observations == parsed.observations
    assert batch.receipt == parsed.receipt
    assert batch.receipt.payment_status == payment_status
    assert batch.receipt.estimated_tax == "3.20"
    assert batch.receipt.tax is None


def test_missing_payment_evidence_is_unknown_for_a_fresh_read():
    batch = project(read_receipt())
    assert batch.receipt.payment_status == "unknown"
    assert len(batch.candidates) == 1
    assert not batch.issues


def test_paid_receipt_still_projects_one_purchase_and_final_tax():
    batch = project(read_receipt(payment_status="paid", tax="3.20"))
    assert len(batch.candidates) == 1
    assert batch.candidates[0].status == "posted"
    assert batch.receipt.tax == "3.20"
    assert batch.receipt.estimated_tax is None
    assert not batch.issues


def test_saved_legacy_batch_keeps_its_existing_candidate():
    parsed = read_receipt()
    observed = project(parsed.model_copy(update={"receipt": None}))
    legacy = observed.model_copy(update={"receipt": parsed.receipt}).model_dump(
        mode="json"
    )
    legacy["receipt"].pop("payment_status", None)
    legacy["receipt"].pop("estimated_tax", None)
    saved = ExtractionBatch.model_validate(legacy)
    assert len(saved.candidates) == 1
    assert saved.candidates[0].amount == observed.candidates[0].amount
    assert saved.receipt.tax is None

"""The projection compares two typed fields of one document: the currency the
source names for itself (a DGII e-CF is paid in DOP) and the currency the read
chose for the receipt. A mismatch is recorded as a projection issue and the
read is held for a person; a document that names no currency never fires it."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import (
    RECEIPT_CURRENCY_CONFLICT,
    RECEIPT_PURCHASE_AMBIGUOUS,
    ExtractionResult,
)

NOW = datetime(2026, 10, 9, 18, 30, tzinfo=timezone.utc)


def read(currency: str, amount: str = "33254.91") -> ExtractionResult:
    return ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[
                dict(
                    page=1,
                    row=1,
                    evidence="transaction",
                    amount=amount,
                    currency=currency,
                    occurred_on="2026-10-09",
                    direction="outflow",
                    kind_hint="expense",
                    merchant="Hotel Brisa del Este SRL",
                )
            ],
            receipt=dict(
                payment_status="paid",
                total=amount,
                currency=currency,
                merchant="Hotel Brisa del Este SRL",
            ),
        )
    )


def codes(batch) -> list[str]:  # noqa: ANN001
    return [issue.code for issue in batch.issues]


def test_a_usd_read_of_a_dop_invoice_is_held_with_the_basis_recorded():
    batch = batch_from_result(
        read("USD", "567.30"), "a" * 64, "c1", NOW, 1, document_currency="DOP"
    )
    conflict = [i for i in batch.issues if i.code == RECEIPT_CURRENCY_CONFLICT]
    assert conflict and conflict[0].fields == ("currency",)
    assert RECEIPT_PURCHASE_AMBIGUOUS in codes(batch)
    assert batch.candidates == ()
    assert [row.amount for row in batch.observations] == ["567.30"]


def test_a_dop_read_of_a_dop_invoice_passes():
    batch = batch_from_result(
        read("DOP"), "a" * 64, "c1", NOW, 1, document_currency="DOP"
    )
    assert RECEIPT_CURRENCY_CONFLICT not in codes(batch)
    assert len(batch.candidates) == 1 and batch.candidates[0].currency == "DOP"


@pytest.mark.parametrize("currency", ["USD", "DOP"])
def test_a_document_that_names_no_currency_never_fires_the_guard(currency):
    batch = batch_from_result(read(currency), "a" * 64, "c1", NOW, 1)
    assert RECEIPT_CURRENCY_CONFLICT not in codes(batch)
    assert len(batch.candidates) == 1


def test_an_unreadable_read_currency_counts_as_a_conflict():
    batch = batch_from_result(
        read("pesos"), "a" * 64, "c1", NOW, 1, document_currency="DOP"
    )
    assert RECEIPT_CURRENCY_CONFLICT in codes(batch)

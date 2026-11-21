"""Model amount text reaches a saved draft through the receipt amount owner."""

from decimal import Decimal

import pytest
from argus.domain.business.receipt_amounts import read_amount
from argus.domain.ingestion.documents.models import DocumentDraft

from tests.business.receipt_stub import DETAILS, PURCHASE
from tests.business.test_amount_due_review import _prepare, _stored
from tests.test_business_attachment_preparation import checked  # noqa: F401


@pytest.mark.parametrize("field", ["itbis", "subtotal", "service", "tip"])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,180.00", None), ("0538.50", "538.5"), ("garbage", None), ("0.00", "0")],
)
def test_model_amount_handoff_saves_a_reviewable_draft(
    checked, monkeypatch, field, raw, expected  # noqa: F811
):
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    receipt = {**DETAILS, "service": None, "tip": None, field: raw}
    batch = _stored(draft, [PURCHASE], receipt=receipt)
    original = batch.model_dump_json()

    # Pin the owner's actual behavior, including its rejection of separators.
    assert read_amount(raw) == expected
    result, resolution, saved = _prepare(checked, monkeypatch, batch, draft)

    assert result.outcome == "applied"
    assert str(result.draft_id) == saved.id
    assert saved.state == "open"
    facts = resolution.facts
    fact = (
        facts.fiscal.itbis
        if field == "itbis"
        else facts.net_amount if field == "subtotal" else facts.legal_tip
    )
    assert fact.state == ("unknown" if expected is None else "known")
    assert fact.value == expected
    if raw == "0538.50":
        assert Decimal(fact.value) == Decimal("538.50")
    assert fact.origin == "extracted"
    assert fact.verified is False
    assert fact.source_ids == facts.amount.source_ids
    assert fact.source_ids
    assert batch.model_dump_json() == original
    assert getattr(batch.receipt, field) == raw

# ruff: noqa: F811
"""An unpaid read prefills its amount unverified; payment status stays evidence."""

from decimal import Decimal

import pytest
from argus.domain.ingestion.documents.models import DocumentDraft

from tests.dgii_qr_support import URL
from tests.ingestion.test_receipt_payment_truth import project, read_receipt
from tests.test_business_attachment_preparation import checked  # noqa: F401
from tests.test_business_multi_purchase import _prepared


@pytest.mark.parametrize("with_qr", [False, True])
def test_unpaid_read_prefills_an_unverified_amount(checked, monkeypatch, with_qr):  # noqa: F811
    from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url
    from argus.domain.ingestion.documents.extractor import batch_from_result

    _, tx, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    parsed = read_receipt(payment_status="unknown", estimated_tax="3.20")
    batch = batch_from_result(
        parsed,
        draft.sha256,
        draft.connection_id,
        draft.created_at,
        1,
        dgii_qr=parse_dgii_url(URL) if with_qr else None,
    )
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    saved = tx.imports.put_event.call_args.args[0]
    assert saved.state == "open"
    assert resolution.facts.amount.state == "known"
    assert resolution.facts.amount.verified is False
    assert Decimal(resolution.facts.amount.value) == Decimal("43.20")
    assert resolution.facts.kind.value == "expense"
    assert resolution.dgii_qr == batch.dgii_qr
    assert batch.receipt.estimated_tax == "3.20"


def test_legacy_saved_business_batch_keeps_its_frozen_candidates(checked, monkeypatch):  # noqa: F811
    from argus.domain.ingestion.documents.models import ExtractionBatch

    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    parsed = read_receipt()
    projected = project(parsed.model_copy(update={"receipt": None}))
    candidate = projected.candidates[0]
    candidate = candidate.model_copy(
        update={
            "source": candidate.source.model_copy(
                update={"connection_id": draft.connection_id}
            )
        }
    )
    frozen = projected.model_copy(
        update={"candidates": (candidate,), "receipt": parsed.receipt}
    ).model_dump(mode="json")
    frozen["receipt"].pop("payment_status", None)
    frozen["receipt"].pop("estimated_tax", None)
    batch = ExtractionBatch.model_validate(frozen)
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    assert resolution.facts.amount.value == "43.2"
    assert resolution.facts.kind.value == "expense"
    assert not batch.issues


def test_unpaid_reread_prefills_the_existing_draft_like_a_paid_one(checked, monkeypatch):  # noqa: F811
    from uuid import UUID

    from argus.domain.business.actions import mutations
    from argus.domain.business.contracts.actions import ExistingDraft
    from argus.domain.business.contracts.facts import BusinessResolution
    from argus.domain.ingestion.documents.extractor import batch_from_result

    _, tx, binding, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    paid = read_receipt(payment_status="paid")
    paid = paid.model_copy(
        update={
            "observations": (
                paid.observations[0],
                paid.observations[0].model_copy(update={"row": 2, "amount": "10.00"}),
            )
        }
    )
    initial = batch_from_result(
        paid, draft.sha256, draft.connection_id, draft.created_at, 1
    )
    _prepared(checked, monkeypatch, initial)
    event = tx.imports.put_event.call_args.args[0]
    monkeypatch.setattr(mutations, "event_at", lambda *args: event)

    def reread(payment_status: str) -> tuple:
        batch = batch_from_result(
            read_receipt(payment_status=payment_status, estimated_tax="3.20"),
            draft.sha256,
            draft.connection_id,
            draft.created_at,
            1,
        )
        mutations.prepare_attachment(
            tx,
            ExistingDraft(draft_id=UUID(event.id), version=event.version),
            batch,
            draft,
            binding.actor,
        )
        saved = tx.imports.put_event.call_args.args[0]
        return saved, BusinessResolution.model_validate(saved.resolution["business"])

    saved, pending = reread("pending")
    _, settled = reread("paid")
    assert saved.state == "open"
    assert saved.version == event.version + 1
    assert pending.facts.amount.verified is False
    assert Decimal(pending.facts.amount.value) == Decimal("43.20")
    assert pending.read_purchases == settled.read_purchases
    assert pending.read_total == settled.read_total
    for name in ("amount", "currency", "kind"):
        unpaid, paid_fact = getattr(pending.facts, name), getattr(settled.facts, name)
        assert (unpaid.state, unpaid.value, unpaid.verified) == (
            paid_fact.state,
            paid_fact.value,
            paid_fact.verified,
        )

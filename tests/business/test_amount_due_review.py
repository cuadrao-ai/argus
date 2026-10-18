"""Stored amount-due reads replay into a review draft, or stay refused.

The five shapes mirror the October reads: two zero totals stayed refused,
a 0.50 and a 32.03 notice should become unverified review drafts, and a
32.08 receipt that already passed stays as it was. No model is called on
replay. Merchants, ids, and files here are synthetic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, sources
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.business.receipts import compose
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    ExtractionResult,
)
from argus.domain.owner_scope import BusinessSpace

from tests.business.test_business_handoff_retry import reading_on
from tests.ingestion.test_business_document_bridge import document_bridge  # noqa: F401
from tests.test_business_attachment_preparation import checked  # noqa: F401

NOW = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
MERCHANT = "Example Cloud Inc"


def _row(amount: str | None, *, currency: str | None, evidence: str, row: int) -> dict:
    return {
        "page": 1,
        "row": row,
        "evidence": evidence,
        "status": "posted",
        "amount": amount,
        "currency": currency,
        "occurred_on": "2026-10-18",
        "direction": "unknown" if evidence == "due_notice" else "outflow",
        "kind_hint": "unknown" if evidence == "due_notice" else "expense",
        "merchant": MERCHANT,
    }


def _stored(
    draft: DocumentDraft,
    rows: list[dict],
    *,
    receipt: dict | None,
    complete: bool = True,
    readable: bool = True,
) -> ExtractionBatch:
    """The batch the document store would hand back on a later prepare."""

    result = ExtractionResult.model_validate(
        {
            "complete": complete,
            "readable": readable,
            "pages_read": [1],
            "observations": rows,
            "receipt": receipt,
        }
    )
    batch = batch_from_result(result, draft.sha256, draft.connection_id, NOW, 1)
    return ExtractionBatch.model_validate_json(batch.model_dump_json())


def _refused(draft: DocumentDraft) -> DocumentDraft:
    return draft.model_copy(
        update={"status": "needs_attention", "error_code": "not_a_receipt"}
    )


def _prepare(checked, monkeypatch, batch, draft):  # noqa: ANN001, F811
    _, tx, binding, _ = checked
    event = mutations.new_candidate(str(binding.owner_id), draft.created_at)
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
    tx.imports = Mock()
    tx.rows = Mock(return_value=[])
    tx.context = Mock(actor=Mock(space_id=binding.space_id))
    monkeypatch.setattr(mutations, "new_candidate", lambda *args: event)
    result = mutations.prepare_attachment(tx, None, batch, draft, binding.actor)
    saved = tx.imports.put_event.call_args.args[0]
    resolution = BusinessResolution.model_validate(saved.resolution["business"])
    return result, resolution, saved


def _assert_refused(checked, monkeypatch, draft, batch) -> None:  # noqa: ANN001, F811
    with pytest.raises(ActionError, match="not_a_receipt"):
        _prepare(checked, monkeypatch, batch, draft)
    shown = compose(_refused(draft), batch, [], "web")
    assert (shown.attention, shown.preparable) == ("not_a_receipt", False)


def _assert_unverified_draft(checked, monkeypatch, draft, batch, amount: str) -> None:  # noqa: ANN001, F811
    shown = compose(_refused(draft), batch, [], "web")
    assert shown.attention != "not_a_receipt"
    assert shown.preparable is True
    result, resolution, saved = _prepare(checked, monkeypatch, batch, draft)
    amount_fact = resolution.facts.amount
    assert result.outcome == "applied"
    assert saved.state == "open"
    assert amount_fact.state == "known"
    assert amount_fact.verified is False
    assert Decimal(amount_fact.value) == Decimal(amount)
    assert resolution.facts.currency.value == "USD"
    assert resolution.facts.currency.verified is False
    assert resolution.facts.kind.value == "expense"
    assert resolution.facts.counterparty.value == MERCHANT


def test_replay_of_the_five_stored_reads(checked, monkeypatch) -> None:  # noqa: ANN001, F811
    """(a) zeros stay refused, (b) 0.50 and (c) 32.03 become unverified
    drafts, (d) the 32.08 receipt that already passed is unchanged."""

    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])

    def due(amount: str, *, currency: str | None = "USD", copies: int = 1) -> ExtractionBatch:
        rows = [
            _row(amount, currency=currency, evidence="due_notice", row=index)
            for index in range(1, copies + 1)
        ]
        return _stored(draft, rows, receipt=None)

    _assert_refused(checked, monkeypatch, draft, due("0"))
    _assert_refused(checked, monkeypatch, draft, due("0.00"))
    _assert_unverified_draft(checked, monkeypatch, draft, due("0.50"), "0.50")
    _assert_unverified_draft(checked, monkeypatch, draft, due("32.03"), "32.03")

    passed = _stored(
        draft,
        [_row("32.08", currency="USD", evidence="transaction", row=1)],
        receipt={
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "total": "32.08",
        },
    )
    _, resolution, saved = _prepare(checked, monkeypatch, passed, draft)
    assert saved.state == "open"
    assert resolution.facts.amount.state == "known"
    assert resolution.facts.amount.verified is False
    assert Decimal(resolution.facts.amount.value) == Decimal("32.08")
    assert resolution.facts.currency.value == "USD"
    assert resolution.facts.kind.value == "expense"
    assert resolution.read_purchases == ()


@pytest.mark.parametrize(
    ("amount", "currency", "copies"),
    [
        ("12.00", None, 1),
        ("12.00", "USD", 2),
        ("-3.25", "USD", 1),
    ],
)
def test_amount_due_without_one_positive_currency_row_stays_refused(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
    amount: str,
    currency: str | None,
    copies: int,
) -> None:
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = _stored(
        draft,
        [
            _row(amount, currency=currency, evidence="due_notice", row=index)
            for index in range(1, copies + 1)
        ],
        receipt=None,
    )
    _assert_refused(checked, monkeypatch, draft, batch)


@pytest.mark.asyncio
async def test_reprepare_of_a_stored_refusal_builds_the_draft_without_a_new_read(
    document_bridge,  # noqa: F811
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    """The first prepare stored the refusal. The replay reads that batch
    again and does not ask the model for another read."""

    service, bridge, extractor, _ = document_bridge
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    reading_on(service, scope, owner)
    calls: list[str] = []

    async def extract(**kwargs):  # noqa: ANN003
        calls.append(kwargs["connection_id"])
        draft = service.get(
            user_id=owner, connection_id=kwargs["connection_id"], scope=scope
        )
        return _stored(
            draft,
            [_row("32.03", currency="USD", evidence="due_notice", row=1)],
            receipt=None,
        )

    extractor.extract.side_effect = extract
    produced: dict[str, BusinessResolution] = {}

    def replay(**kwargs):  # noqa: ANN003
        del kwargs
        batch = service.store.get(user_id=owner, connection_id=calls[0])
        assert batch is not None
        _, resolution, _ = _prepare(
            checked,
            monkeypatch,
            batch,
            service.get(user_id=owner, connection_id=calls[0], scope=scope),
        )
        produced["resolution"] = resolution

    seen = {"count": 0}

    def on_prepare(**kwargs):  # noqa: ANN003
        seen["count"] += 1
        if seen["count"] == 1:
            raise ActionError("invalid_input", "not_a_receipt")
        replay(**kwargs)

    bridge.prepare_attachment.side_effect = on_prepare
    uploaded = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="invoice.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    with pytest.raises(ActionError, match="not_a_receipt"):
        await service.resume(
            user_id=owner, connection_id=uploaded.connection_id, scope=scope
        )
    assert calls == [uploaded.connection_id]
    stored = service.store.get(user_id=owner, connection_id=uploaded.connection_id)
    held = service.get(user_id=owner, connection_id=uploaded.connection_id, scope=scope)
    shown = compose(held, stored, [], "web")
    assert shown.attention != "not_a_receipt"
    assert shown.preparable is True
    outcome = await service.resume(
        user_id=owner, connection_id=uploaded.connection_id, scope=scope
    )
    assert calls == [uploaded.connection_id]
    assert outcome.replayed is True
    assert outcome.status == "review_ready"
    assert produced["resolution"].facts.amount.verified is False
    assert Decimal(produced["resolution"].facts.amount.value) == Decimal("32.03")
    assert produced["resolution"].facts.amount.state == "known"

"""A read with several purchases, or one it cannot settle, still becomes one
draft a person can finish: shared facts known, the amount left open, and
every read purchase kept on the draft as evidence. Never a refusal."""

from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, sources
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    ProjectionIssue,
    ReceiptDetails,
)

from tests.test_business_attachment_preparation import checked  # noqa: F401


def _candidate(
    draft: DocumentDraft, amount: str, merchant: str, occurred_on: str, **extra
) -> ImportCandidate:  # noqa: ANN003
    return ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=draft.sha256,
            observed_at=draft.created_at,
        ),
        evidence="transaction",
        direction="outflow",
        amount=amount,
        currency="DOP",
        occurred_on=occurred_on,
        kind_hint="expense",
        merchant=merchant,
        **extra,
    )


def _prepared(checked, monkeypatch, batch):  # noqa: ANN001, F811
    _, tx, binding, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
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
    return result, BusinessResolution.model_validate(saved.resolution["business"]), draft


def test_two_purchases_become_one_open_draft_with_both_kept(checked, monkeypatch) -> None:  # noqa: ANN001, F811
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(
            _candidate(draft, "245.00", "Colmado La Esquina", "2026-10-11"),
            _candidate(draft, "95.00", "Colmado La Esquina", "2026-10-11"),
        ),
        receipt=ReceiptDetails(total="340.00", currency="DOP"),
    )
    result, resolution, _ = _prepared(checked, monkeypatch, batch)
    assert result.outcome == "applied"
    facts = resolution.facts
    assert facts.amount.state == "unknown"
    assert (
        facts.counterparty.value,
        facts.occurred_on.value.isoformat(),
        facts.currency.value,
    ) == (
        "Colmado La Esquina",
        "2026-10-11",
        "DOP",
    )
    assert [(p.index, p.amount, p.merchant) for p in resolution.read_purchases] == [
        (1, "245", "Colmado La Esquina"),
        (2, "95", "Colmado La Esquina"),
    ]


def test_purchases_that_disagree_leave_those_facts_open(checked, monkeypatch) -> None:  # noqa: ANN001, F811
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(
            _candidate(draft, "245.00", "Colmado", "2026-10-11"),
            _candidate(
                draft,
                "95.00",
                "Farmacia",
                "2026-10-12",
                uncertain=frozenset({"merchant"}),
            ),
        ),
        receipt=ReceiptDetails(total="340.00", currency="DOP"),
    )
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    facts = resolution.facts
    assert (facts.amount.state, facts.counterparty.state, facts.occurred_on.state) == (
        "unknown",
    ) * 3
    assert facts.currency.value == "DOP"
    assert len(resolution.read_purchases) == 2


def test_an_ambiguous_single_read_keeps_its_purchase_as_evidence(
    checked, monkeypatch
) -> None:  # noqa: ANN001, F811
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(_candidate(draft, "3000.00", "Ferretería", "2026-10-10"),),
        receipt=ReceiptDetails(total="3000.00", currency="DOP"),
        issues=(ProjectionIssue(code="receipt_purchase_ambiguous", row=1),),
    )
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    assert resolution.facts.amount.state == "unknown"
    assert resolution.facts.counterparty.value == "Ferretería"
    assert [p.amount for p in resolution.read_purchases] == ["3000"]


def test_a_single_clean_purchase_is_unchanged(checked, monkeypatch) -> None:  # noqa: ANN001, F811
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(_candidate(draft, "250.50", "Owner named shop", "2026-10-09"),),
        receipt=ReceiptDetails(total="250.50", currency="DOP"),
    )
    _, resolution, _ = _prepared(checked, monkeypatch, batch)
    assert resolution.facts.amount.value in ("250.50", "250.5")
    assert resolution.read_purchases == ()


def test_an_unreadable_read_is_still_refused_to_the_document_layer(
    checked, monkeypatch
) -> None:  # noqa: ANN001, F811
    _, _, _, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = ExtractionBatch(complete=True, readable=False, candidates=(), receipt=None)
    with pytest.raises(ActionError, match="receipt_requires_review"):
        _prepared(checked, monkeypatch, batch)

"""The reviewed document beside the one it may repeat: the main data of
both, which of it differs, and what the fiscal numbers recommend."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from argus.domain.business.actions.facts import facts_of
from argus.domain.business.contracts.dossier import (
    ComparedDocument,
    ComparedField,
    ComparedFile,
    DuplicateComparison,
)
from argus.domain.business.contracts.facts import FiscalFacts, Known
from argus.domain.business.duplicates import recommendation, same_value
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.model import ImportEvent

_VALUES: tuple[ComparedField, ...] = (
    "counterparty",
    "occurred_on",
    "amount",
    "currency",
    "fiscal_number",
)


def fiscal_repeats(
    tx: ActionTransaction, draft_ids: Sequence[UUID]
) -> dict[UUID, tuple[UUID, ...]]:
    """For each draft, the other purchases, open or recorded, that share its
    supplier RNC and comprobante, read from the columns the database's own
    index is built on."""

    rows = tx.rows(
        "select distinct me.id, other.id as other_id from public.financial_import_events me"
        " join public.financial_import_events other on other.owner_space_id=me.owner_space_id"
        " and other.business_rnc=me.business_rnc"
        " and other.business_fiscal_number=me.business_fiscal_number"
        " where me.owner_space_id=%s and me.id=any(%s) and other.id<>me.id"
        " and other.state in ('open','accepting','accepted')"
        " and me.business_kind is distinct from 'income'"
        " and other.business_kind is distinct from 'income'"
        " order by me.id, other.id",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    found: dict[UUID, tuple[UUID, ...]] = {}
    for row in rows:
        found[row["id"]] = (*found.get(row["id"], ()), row["other_id"])
    return found


def _known(fact: object) -> Any:
    return fact.value if isinstance(fact, Known) else None


def _document(
    tx: ActionTransaction, event: ImportEvent, approvals: list[dict[str, Any]]
) -> tuple[ComparedDocument, Any]:
    """The document and the digest of its file, which never leaves the server."""

    facts = facts_of(event)
    files = tx.rows(
        "select s.connection_id,s.received_at,d.draft->>'filename' as filename,"
        "d.draft->>'media_type' as media_type,"
        "coalesce(d.source_sha256,d.draft->>'sha256') as sha256"
        " from public.business_draft_sources l join public.business_sources s"
        " on s.id=l.source_id and s.space_id=l.space_id"
        " join public.financial_document_extractions d on d.connection_id=s.connection_id"
        " where l.space_id=%s and l.draft_id=%s and s.kind='attachment'"
        " order by s.received_at,s.id limit 1",
        (tx.context.actor.space_id, event.id),
    )
    received = tx.rows(
        "select min(s.received_at) as at from public.business_draft_sources l"
        " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
        " where l.space_id=%s and l.draft_id=%s",
        (tx.context.actor.space_id, event.id),
    )
    file = files[0] if files else None
    amount = _known(facts.amount)
    fiscal = facts.fiscal or FiscalFacts()
    return (
        ComparedDocument(
            draft_id=event.id,
            counterparty=_known(facts.counterparty),
            occurred_on=_known(facts.occurred_on),
            amount=None if amount is None else str(amount),
            currency=_known(facts.currency),
            fiscal_number=_known(fiscal.ncf) or _known(fiscal.ecf),
            file=file
            and ComparedFile(
                connection_id=file["connection_id"],
                filename=file["filename"],
                media_type=file["media_type"],
            ),
            received_at=received[0]["at"],
            approved_at=approvals[0]["created_at"] if approvals else None,
        ),
        file and file["sha256"],
    )


def compare(
    tx: ActionTransaction,
    event: ImportEvent,
    other: ImportEvent,
    other_approvals: list[dict[str, Any]],
) -> DuplicateComparison:
    """``other_approvals`` is the other draft's approval receipt when it is
    recorded; the reviewed draft is open and has none."""

    document, digest = _document(tx, event, [])
    counterpart, other_digest = _document(tx, other, other_approvals)
    differences = [
        name
        for name in _VALUES
        if not same_value(name, getattr(document, name), getattr(counterpart, name))
    ]
    if digest != other_digest:
        differences.append("file")
    return DuplicateComparison(
        document=document,
        other=counterpart,
        differences=tuple(differences),
        recommendation=recommendation(
            document.fiscal_number, counterpart.fiscal_number
        ),
    )

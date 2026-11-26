"""The reviewed document beside the one it may repeat: the main data of
both, which of it differs, and what the fiscal numbers recommend."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from argus.domain.business.actions.facts import facts_of
from argus.domain.business.contracts.actions import ResolveDuplicateCommand
from argus.domain.business.contracts.dossier import (
    ComparedDocument,
    ComparedField,
    ComparedFile,
    DuplicateComparison,
    DuplicateRevision,
    SourceEvidence,
    WebActionSource,
)
from argus.domain.business.contracts.facts import FiscalFacts, Known
from argus.domain.business.duplicates import recommendation, same_value
from argus.domain.business.record_origin import DraftArrival, draft_arrivals
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent

_VALUES: tuple[ComparedField, ...] = (
    "counterparty",
    "occurred_on",
    "amount",
    "currency",
    "fiscal_number",
)


def _known(fact: object) -> Any:
    return fact.value if isinstance(fact, Known) else None


def _comparison_file(tx: ActionTransaction, arrival: DraftArrival | None) -> dict[str, Any] | None:
    if arrival is None or arrival.file_source_id is None:
        return None
    files = tx.rows(
        "select s.connection_id,s.channel,(d.draft->>'created_at')::timestamptz as received_at,"
        " d.draft->>'filename' as filename,d.draft->>'media_type' as media_type,"
        " coalesce(d.source_sha256,d.draft->>'sha256') as sha256"
        " from public.business_sources s join public.financial_document_extractions d"
        " on d.connection_id=s.connection_id where s.space_id=%s and s.id=%s",
        (tx.context.actor.space_id, arrival.file_source_id),
    )
    return files[0] if files else None


def duplicate_revisions(
    tx: ActionTransaction, sources: Sequence[SourceEvidence]
) -> dict[UUID, DuplicateRevision]:
    """By web action source, the different-purchase decisions it recorded, each
    naming the other document by its merchant and file as they read now."""

    found: dict[UUID, DuplicateRevision] = {}
    for source in sources:
        if not isinstance(source, WebActionSource):
            continue
        command = json.loads(source.text)
        if command.get("action") != "resolve_duplicate":
            continue
        request = ResolveDuplicateCommand.model_validate(command).request
        if request.decision != "different_purchase":
            continue
        other_id = str(request.other_draft_id)
        try:
            counterparty = _known(facts_of(tx.imports.event(other_id)).counterparty)
        except EventNotFound:
            counterparty = None
        arrival = draft_arrivals(tx, [request.other_draft_id]).get(request.other_draft_id)
        found[source.id] = DuplicateRevision(
            decision=request.decision,
            other_draft_id=request.other_draft_id,
            other_counterparty=counterparty,
            other_filename=arrival.filename if arrival else None,
        )
    return found


def _document(
    tx: ActionTransaction, event: ImportEvent, approvals: list[dict[str, Any]],
    arrival: DraftArrival | None,
) -> tuple[ComparedDocument, Any]:
    """The document and the digest of its file, which never leaves the server."""

    facts = facts_of(event)
    file = _comparison_file(tx, arrival)
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
                channel=file["channel"],
                received_at=file["received_at"],
            ),
            received_at=arrival.received_at if arrival else None,
            approved_at=approvals[0]["created_at"] if approvals else None,
            state=event.state,
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

    here, there = UUID(event.id), UUID(other.id)
    arrivals = draft_arrivals(tx, [here, there])
    document, digest = _document(tx, event, [], arrivals.get(here))
    counterpart, other_digest = _document(tx, other, other_approvals, arrivals.get(there))
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

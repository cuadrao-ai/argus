"""What the Listos rule reads of open drafts. One read serves the receipt list
and the recheck at approval, so what was listed and what is approved are judged
on the same facts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from argus.domain.business.actions.document_deletion import reading_uploads
from argus.domain.business.actions.dossier import (
    record_context,
    review_questions,
    rnc_registry,
    workflow_blockers,
)
from argus.domain.business.actions.fiscal import repeated_comprobantes
from argus.domain.business.actions.refunds import refund_shaped
from argus.domain.business.annotations import OWN_SOURCE_SQL
from argus.domain.business.bandeja_group import (
    DraftStanding,
    ReadState,
    listo_reason,
    upload_year,
)
from argus.domain.business.contracts.dossier import Blocker, ReviewFlag
from argus.domain.business.contracts.facts import BusinessResolution, fiscal_value
from argus.domain.business.receipts import read_attention
from argus.domain.business.record_origin import DraftArrival, first_draft_sources
from argus.domain.business.review_flags import review_flags
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.email_intake.store import email_draft_standing
from argus.domain.ingestion.reconcile.model import ImportEvent


def attachment_reads(
    tx: ActionTransaction,
    draft_ids: Sequence[UUID],
    *,
    live_siblings: bool = False,
) -> dict[UUID, ReadState]:
    """A listed draft waits for every original receipt. The worker stamping
    the completed read still holds its lease and needs the settled standing."""

    rows = tx.rows(
        "select l.draft_id,s.connection_id,d.draft->>'status' as status,"
        " exists (select 1 from public.business_draft_sources o"
        "   where o.space_id=l.space_id and o.source_id=l.source_id"
        "   and o.draft_id<>l.draft_id) as shared"
        " from public.business_draft_sources l"
        " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
        " left join public.financial_document_extractions d on d.connection_id=s.connection_id"
        " where l.space_id=%s and l.draft_id=any(%s) and s.kind='attachment'"
        f" and {OWN_SOURCE_SQL}",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        found.setdefault(row["draft_id"], []).append(row)
    reads = {draft_id: _read_state(rows) for draft_id, rows in found.items()}
    if not live_siblings:
        return reads
    siblings = {
        draft_id: {row["connection_id"] for row in rows}
        for draft_id, rows in found.items()
        if len(rows) > 1
    }
    if not siblings:
        return reads
    uploads = tx.rows(
        "select c.id as connection_id,c.lease_until,d.draft"
        " from public.financial_source_connections c"
        " join public.financial_document_extractions d on d.connection_id=c.id and d.user_id=c.user_id"
        " where c.owner_space_id=%s and c.user_id=%s and c.id=any(%s)",
        (
            tx.context.actor.space_id, tx.context.owner_id,
            list(set.union(*siblings.values())),
        ),
    )
    pending = reading_uploads(tx, uploads)
    for draft_id, ids in siblings.items():
        if ids & pending:
            reads[draft_id] = "reading"
    return reads


def _upload_years(
    tx: ActionTransaction, draft_ids: Sequence[UUID]
) -> dict[UUID, int | None]:
    return {
        draft_id: upload_year(first["received_at"])
        for draft_id, (first, _) in first_draft_sources(tx, draft_ids).items()
    }


def _read_state(attachments: list[dict[str, Any]]) -> ReadState:
    """A read that finished clean on the one attachment this draft owns."""

    if not attachments:
        return "none"
    if len(attachments) > 1 or attachments[0]["shared"]:
        return "unclear"
    return "finished" if attachments[0]["status"] == "review_ready" else "unclear"


def _ecf_failed(resolution: BusinessResolution) -> bool:
    """A check on the e-CF or its QR failed, or the file names an e-CF and the
    record holds another kind of number."""

    verification = resolution.ecf_checks
    if verification is None:
        return False
    return any(check.state == "failed" for check in verification.checks) or (
        verification.encf is not None and fiscal_value(resolution.facts) != "ecf"
    )


def draft_standing(
    tx: ActionTransaction,
    event: ImportEvent,
    resolution: BusinessResolution,
    *,
    blocked: Sequence[Blocker],
    flags: tuple[ReviewFlag, ...],
    read: ReadState,
    repeated: bool,
    uploaded: int | None,
    every_gap: bool,
) -> DraftStanding:
    standing = DraftStanding(
        draft_id=event.id,
        version=event.version,
        facts=resolution.facts,
        read=read,
        read_attention=read_attention(event).get("attention"),
        credit_note=refund_shaped(resolution.facts),
        ecf_failed=_ecf_failed(resolution),
        repeated=repeated,
        # RULE already reports these missing facts individually.
        blockers=tuple(
            blocker.code
            for blocker in blocked
            if not (
                blocker.code == "fact_required"
                and blocker.field in {"occurred_on", "amount", "currency"}
            )
        ),
        flags=flags,
        upload_year=uploaded,
    )
    if every_gap or listo_reason(standing) is None:
        standing = replace(
            standing,
            sender=email_draft_standing(
                tx.connection, str(tx.context.actor.space_id), event.id
            ),
        )
    return standing


def draft_standings(
    tx: ActionTransaction,
    events: Iterable[ImportEvent],
    *,
    every_gap: bool = False,
    live_siblings: bool = False,
    arrivals: Mapping[UUID, DraftArrival] | None = None,
) -> dict[str, DraftStanding]:
    """The standing of each open Business draft, by id. The sender costs the
    most, so it is read last and only for a draft nothing else keeps out: that
    answers the first reason. ``every_gap`` reads it for every draft, for a
    caller that names every gap."""

    drafts = {UUID(event.id): event for event in events if "business" in event.resolution}
    if not drafts:
        return {}
    ids = list(drafts)
    questions = review_questions(tx, ids)
    reads = attachment_reads(tx, ids, live_siblings=live_siblings)
    uploaded = _upload_years(tx, ids) if arrivals is None else {
        key: upload_year(arrival.received_at) for key, arrival in arrivals.items()
    }
    repeated = repeated_comprobantes(tx, drafts.values())
    accounts = record_context(tx).accounts
    registry = rnc_registry(tx)
    found = {}
    for draft_id, event in drafts.items():
        resolution = BusinessResolution.model_validate(event.resolution["business"])
        facts = resolution.facts
        blocked, _ = workflow_blockers(
            tx, event, facts, accounts, questions.get(event.id, ())
        )
        found[event.id] = draft_standing(
            tx, event, resolution,
            blocked=blocked,
            flags=review_flags(facts, registry, declaration=resolution.dgii),
            read=reads.get(draft_id, "none"),
            repeated=draft_id in repeated,
            uploaded=uploaded.get(draft_id),
            every_gap=every_gap,
        )
    return found


def linked_standings(
    tx: ActionTransaction, drafts: Mapping[str, list[dict[str, Any]]]
) -> dict[str, DraftStanding]:
    """The standings of the open drafts these receipt rows link."""

    wanted = {
        str(row["id"])
        for linked in drafts.values()
        for row in linked
        if row["state"] == "open"
    }
    if not wanted:
        return {}
    return draft_standings(
        tx,
        (event for event in tx.imports.events(("open",)) if event.id in wanted),
        live_siblings=True,
        arrivals={
            row["id"]: row["arrival"]
            for linked in drafts.values() for row in linked if row.get("arrival")
        },
    )

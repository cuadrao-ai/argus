"""What the Listos rule reads of open drafts. One read serves the receipt list
and the recheck at approval, so what was listed and what is approved are judged
on the same facts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from argus.domain.business.actions.dossier import (
    record_context,
    review_questions,
    rnc_registry,
    workflow_blockers,
)
from argus.domain.business.actions.fiscal import repeated_comprobantes
from argus.domain.business.actions.refunds import refund_shaped
from argus.domain.business.bandeja_group import (
    DraftStanding,
    ReadState,
    listo_reason,
    upload_year,
)
from argus.domain.business.contracts.facts import BusinessResolution, fiscal_value
from argus.domain.business.receipts import read_attention
from argus.domain.business.review_flags import review_flags
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.email_intake.store import email_draft_standing
from argus.domain.ingestion.reconcile.model import ImportEvent


def _attachments(
    tx: ActionTransaction, draft_ids: Sequence[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    """Each draft's attachments, with the status of their read and whether
    another draft shares them."""

    rows = tx.rows(
        "select l.draft_id,d.draft->>'status' as status,"
        " exists (select 1 from public.business_draft_sources o"
        "   where o.space_id=l.space_id and o.source_id=l.source_id"
        "   and o.draft_id<>l.draft_id) as shared"
        " from public.business_draft_sources l"
        " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
        " left join public.financial_document_extractions d on d.connection_id=s.connection_id"
        " where l.space_id=%s and l.draft_id=any(%s) and s.kind='attachment'",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        found.setdefault(row["draft_id"], []).append(row)
    return found


def _upload_years(
    tx: ActionTransaction, draft_ids: Sequence[UUID]
) -> dict[UUID, int | None]:
    """Each draft's upload year, from its first source as the dossier orders them."""

    rows = tx.rows(
        "select l.draft_id,min(s.received_at) as received_at"
        " from public.business_draft_sources l"
        " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
        " where l.space_id=%s and l.draft_id=any(%s) group by l.draft_id",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    return {row["draft_id"]: upload_year(row["received_at"]) for row in rows}


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


def draft_standings(
    tx: ActionTransaction, events: Iterable[ImportEvent], *, every_gap: bool = False
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
    attachments = _attachments(tx, ids)
    uploaded = _upload_years(tx, ids)
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
        standing = DraftStanding(
            draft_id=event.id,
            version=event.version,
            facts=facts,
            read=_read_state(attachments.get(draft_id, [])),
            read_attention=read_attention(event).get("attention"),
            credit_note=refund_shaped(facts),
            ecf_failed=_ecf_failed(resolution),
            repeated=draft_id in repeated,
            # RULE already reports these missing facts individually.
            blockers=tuple(
                blocker.code
                for blocker in blocked
                if not (
                    blocker.code == "fact_required"
                    and blocker.field in {"occurred_on", "amount", "currency"}
                )
            ),
            flags=review_flags(facts, registry, declaration=resolution.dgii),
            upload_year=uploaded.get(draft_id),
        )
        if every_gap or listo_reason(standing) is None:
            standing = replace(
                standing,
                sender=email_draft_standing(
                    tx.connection, str(tx.context.actor.space_id), event.id
                ),
            )
        found[event.id] = standing
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
        tx, (event for event in tx.imports.events(("open",)) if event.id in wanted)
    )

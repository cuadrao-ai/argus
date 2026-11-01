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
from argus.domain.business.actions.refunds import refund_shaped
from argus.domain.business.bandeja_group import (
    DraftStanding,
    ReadState,
    listo_reason,
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
        "select l.draft_id,d.draft->>'status' as status,d.draft->>'error_code' as error_code,"
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


def _read_state(attachments: list[dict[str, Any]]) -> ReadState:
    """A read that finished clean on the one attachment this draft owns."""

    if not attachments:
        return "none"
    if len(attachments) > 1 or attachments[0]["shared"]:
        return "unclear"
    read = attachments[0]
    if read["status"] in ("queued", "preparing"):
        return "reading"
    return (
        "finished"
        if read["status"] == "review_ready" and read["error_code"] is None
        else "unclear"
    )


def _ecf_failed(resolution: BusinessResolution) -> bool:
    """A check on the e-CF or its QR failed, or the file names an e-CF and the
    record holds another kind of number."""

    verification = resolution.ecf_checks
    if verification is None:
        return False
    return any(check.state == "failed" for check in verification.checks) or (
        verification.encf is not None and fiscal_value(resolution.facts) != "ecf"
    )


def _repeated(tx: ActionTransaction, draft_ids: Sequence[UUID]) -> set[UUID]:
    """Drafts that share a supplier RNC and comprobante with another purchase,
    open or recorded, read from the columns the database's own index is built on."""

    rows = tx.rows(
        "select distinct me.id from public.financial_import_events me"
        " join public.financial_import_events other on other.owner_space_id=me.owner_space_id"
        " and other.business_rnc=me.business_rnc"
        " and other.business_fiscal_number=me.business_fiscal_number"
        " where me.owner_space_id=%s and me.id=any(%s) and other.id<>me.id"
        " and other.state in ('open','accepting','accepted')"
        " and other.business_kind is distinct from 'income'",
        (tx.context.actor.space_id, list(draft_ids)),
    )
    return {row["id"] for row in rows}


def draft_standings(
    tx: ActionTransaction, events: Iterable[ImportEvent]
) -> dict[str, DraftStanding]:
    """The standing of each open Business draft, by id. The sender is read last
    and only for a draft nothing else keeps out, since it costs the most."""

    drafts = {UUID(event.id): event for event in events if "business" in event.resolution}
    if not drafts:
        return {}
    ids = list(drafts)
    questions = review_questions(tx, ids)
    attachments = _attachments(tx, ids)
    repeated = _repeated(tx, ids)
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
            document_type=resolution.document_type,
            credit_note=refund_shaped(facts),
            ecf_failed=_ecf_failed(resolution),
            repeated=draft_id in repeated,
            blockers=tuple(blocker.code for blocker in blocked),
            flags=review_flags(facts, registry),
        )
        if listo_reason(standing) is None:
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

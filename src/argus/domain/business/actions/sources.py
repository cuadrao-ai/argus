from __future__ import annotations

from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dossier import AttachmentSource, SourceEvidence
from argus.domain.business.transactions import ActionTransaction


def require_sources(tx: ActionTransaction, source_ids: tuple[UUID, ...]) -> None:
    found = tx.rows(
        "select id from public.business_sources where space_id=%s and id=any(%s::uuid[])",
        (tx.context.actor.space_id, list(source_ids)),
    )
    if {row["id"] for row in found} != set(source_ids):
        raise ActionError("not_found", "business_record_not_found")


def record_source(tx: ActionTransaction, key: str, evidence: SourceEvidence) -> UUID:
    if not 1 <= len(key) <= 200:
        raise ActionError("invalid_input", "source_key_invalid")
    attachment = isinstance(evidence, AttachmentSource)
    connection_id = evidence.connection_id if attachment else None
    text = None if attachment else evidence.text
    if attachment and not tx.rows(
        "select id from public.financial_source_connections"
        " where id=%s and owner_space_id=%s and user_id=%s and status<>'disconnected'",
        (connection_id, tx.context.actor.space_id, tx.context.owner_id),
    ):
        raise ActionError("not_found", "business_record_not_found")
    existing = tx.rows(
        "select id,kind,channel,text_content,connection_id,received_at"
        " from public.business_sources where space_id=%s and source_key=%s",
        (tx.context.actor.space_id, key),
    )
    if existing:
        row = existing[0]
        if (row["kind"], row["channel"], row["text_content"], row["connection_id"]) != (
            evidence.kind,
            evidence.channel,
            text,
            connection_id,
        ):
            raise ActionError("idempotency_conflict", "source_identity_conflict")
        return row["id"]
    tx.rows(
        "insert into public.business_sources"
        " (id,space_id,kind,channel,source_key,text_content,connection_id,received_at)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            evidence.id,
            tx.context.actor.space_id,
            evidence.kind,
            evidence.channel,
            key,
            text,
            connection_id,
            evidence.received_at,
        ),
    )
    return evidence.id


def attach(tx: ActionTransaction, draft_id: str, sources: tuple[UUID, ...]) -> None:
    require_sources(tx, sources)
    for source_id in sources:
        if tx.rows(
            "select e.id from public.business_sources s"
            " join public.financial_import_observations o on o.connection_id=s.connection_id"
            " join public.financial_import_events e on e.id=o.event_id and e.owner_space_id=s.space_id"
            " where s.id=%s and s.space_id=%s and e.user_id=%s and e.id<>%s"
            " and not (e.resolution ? 'business') limit 1",
            (source_id, tx.context.actor.space_id, tx.context.owner_id, draft_id),
        ):
            raise ActionError("invalid_input", "business_legacy_conversion_unsupported")
        tx.rows(
            "insert into public.business_draft_sources(space_id,draft_id,source_id)"
            " values (%s,%s,%s) on conflict (draft_id,source_id) do nothing",
            (tx.context.actor.space_id, draft_id, source_id),
        )

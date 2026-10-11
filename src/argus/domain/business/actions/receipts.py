from __future__ import annotations

from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.transactions import ActionTransaction
from argus.domain.ingestion.reconcile.model import EventNotFound


def draft_for_receipt(
    tx: ActionTransaction, connection_id: UUID, legacy_id: UUID | None
) -> tuple[UUID | None, bool]:
    if not tx.rows(
        "select id from public.financial_source_connections"
        " where id=%s and user_id=%s and owner_space_id=%s and status<>'disconnected'",
        (connection_id, tx.context.owner_id, tx.context.actor.space_id),
    ):
        raise ActionError("not_found", "business_record_not_found")
    if legacy_id is not None:
        try:
            tx.imports.event(str(legacy_id))
        except EventNotFound:
            raise ActionError("not_found", "business_record_not_found") from None
    rows = tx.rows(
        "select distinct e.id from public.business_sources s"
        " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
        " join public.financial_import_events e on e.id=l.draft_id and e.owner_space_id=l.space_id"
        " where s.space_id=%s and s.connection_id=%s and e.user_id=%s"
        " and e.resolution ? 'business' order by e.id limit 2",
        (tx.context.actor.space_id, connection_id, tx.context.owner_id),
    )
    candidates = {row["id"] for row in rows}
    if legacy_id is not None:
        candidates.add(legacy_id)
    if len(candidates) > 1:
        return None, True
    return (next(iter(candidates)) if candidates else None), False

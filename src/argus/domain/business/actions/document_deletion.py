from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from psycopg.types.json import Jsonb

from argus.domain.business.actions import plans
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import ActionOutcome, Applied
from argus.domain.business.contracts.deletion import (
    DeletedDocument,
    DeletingActor,
    DocumentCommand,
    PreviousDocumentState,
    deletion,
)
from argus.domain.business.duplicates import flag_receipt_duplicates
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.documents.models import DocumentDraft
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent

if TYPE_CHECKING:
    from argus.domain.business.actions.service import BusinessActions


def change_document(
    service: BusinessActions, context: ActionContext, command: DocumentCommand, key: str
) -> ActionOutcome:
    try:
        with transaction(service.authority, context, "approve") as tx:
            if context.actor.actor_kind != "member":
                raise ActionError("permission_denied", "business_human_command_required")
            saved = plans.receipt(tx, key, command)
            if saved is not None:
                return plans.replay(saved)
            plans.start_receipt(tx, key, command)
            try:
                with tx.connection.transaction():
                    result = _change(tx, command, key)
            except ActionError as error:
                result = error.result
            return plans.finish_receipt(tx, key, result)
    except ActionError as error:
        return error.result


def _target(
    tx: ActionTransaction, document_id: UUID
) -> tuple[ImportEvent | None, list[dict], tuple[ImportEvent, ...]]:
    candidates = ()
    try:
        event = tx.imports.event(str(document_id))
    except EventNotFound:
        event = None
    if event is None:
        rows = tx.rows(
            "select distinct e.id from public.financial_import_events e"
            " left join public.business_draft_sources l on l.draft_id=e.id and l.space_id=e.owner_space_id"
            " left join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
            " left join public.financial_import_observations o on o.event_id=e.id and o.user_id=e.user_id"
            " where e.owner_space_id=%s and e.user_id=%s"
            " and (s.connection_id=%s or o.connection_id=%s) order by e.id",
            (tx.context.actor.space_id, tx.context.owner_id, document_id, document_id),
        )
        if len(rows) > 1:
            candidates = tuple(tx.imports.event(str(row["id"])) for row in rows)
            if any("business" in candidate.resolution for candidate in candidates):
                raise ActionError("invalid_input", "business_document_ambiguous")
        elif rows:
            event = tx.imports.event(str(rows[0]["id"]))
    attachments = tx.rows(
        "select d.connection_id,d.draft,c.lease_until from public.financial_document_extractions d"
        " join public.financial_source_connections c on c.id=d.connection_id and c.user_id=d.user_id"
        " where c.owner_space_id=%s and c.user_id=%s and c.status<>'disconnected'"
        " and (c.id=%s or c.id in ("
        " select s.connection_id from public.business_sources s"
        " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
        " where l.draft_id=%s and l.space_id=%s"
        " union select o.connection_id from public.financial_import_observations o"
        " where o.event_id=%s and o.user_id=%s)) for update of c,d",
        (
            tx.context.actor.space_id,
            tx.context.owner_id,
            document_id,
            event.id if event else None,
            tx.context.actor.space_id,
            event.id if event else None,
            tx.context.owner_id,
        ),
    )
    if (
        event is not None
        and attachments
        and tx.rows(
            "select 1 from public.business_draft_sources l"
            " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
            " where l.space_id=%s and s.connection_id=any(%s) and l.draft_id<>%s"
            " union select 1 from public.financial_import_observations o"
            " join public.financial_import_events e on e.id=o.event_id and e.user_id=o.user_id"
            " where e.owner_space_id=%s and e.user_id=%s and o.connection_id=any(%s) and e.id<>%s limit 1",
            (
                tx.context.actor.space_id,
                [row["connection_id"] for row in attachments],
                event.id,
                tx.context.actor.space_id,
                tx.context.owner_id,
                [row["connection_id"] for row in attachments],
                event.id,
            ),
        )
    ):
        raise ActionError("invalid_input", "business_document_ambiguous")
    if event is None and not attachments:
        raise ActionError("not_found", "business_record_not_found")
    return event, attachments, candidates


def is_reading(tx: ActionTransaction, attachments: list[dict]) -> bool:
    now = datetime.now(timezone.utc)
    permission = BusinessReceiptConsentStore().status_on_connection(
        tx.connection, str(tx.context.actor.space_id), tx.context.owner_id
    )
    return any(
        DocumentDraft.model_validate(row["draft"]).read_pending(
            permission["enabled"]
            and permission["consent_id"]
            == row["draft"].get("business_reading_consent_id")
        )
        or (row.get("lease_until") is not None and row["lease_until"] > now)
        for row in attachments
        if row.get("draft")
    )


def _change(tx: ActionTransaction, command: DocumentCommand, key: str) -> Applied:
    event, attachments, candidates = _target(tx, command.document_id)
    document = attachments[0]["draft"] if attachments else None
    state = event.state if event else document["status"]
    resolution = dict(event.resolution if event else document.get("resolution", {}))
    marker = deletion(state, resolution)
    deleting = command.action == "delete_document"
    if deleting and marker is None:
        if (
            (event is not None and state != "open")
            or state == "dismissed"
            or any(
                candidate.state not in ("open", "dismissed") for candidate in candidates
            )
        ):
            raise ActionError("invalid_input", "business_document_not_open")
        if is_reading(tx, attachments):
            raise ActionError("invalid_input", "business_document_reading")
        group = "attention"
        if event is not None and "business" in event.resolution:
            from argus.domain.business.actions.listos import draft_standings
            from argus.domain.business.bandeja_group import listo_reason

            standing = draft_standings(tx, (event,))[event.id]
            group = "attention" if listo_reason(standing) else "listo"
        marker = DeletedDocument(
            actor=DeletingActor(
                id=tx.context.actor.actor_id,
                display_name=tx.authorization.provenance.display_name,
            ),
            at=datetime.now(timezone.utc),
            key=key,
            previous_state=PreviousDocumentState(
                state=state,
                group=group,
                events={candidate.id: candidate.state for candidate in candidates},
            ),
        )
        resolution["deleted"] = marker.model_dump(mode="json")
        state = "dismissed"
    elif not deleting:
        if marker is None:
            raise ActionError("invalid_input", "business_document_not_deleted")
        state = marker.previous_state.state
        resolution.pop("deleted")
    else:
        return Applied(outcome="applied", draft_id=event.id if event else None)
    if event is not None:
        tx.imports.put_event(
            replace(
                event,
                state=state,
                resolution=resolution,
                version=event.version + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if not deleting:
            _recheck_duplicates(tx, (event.id,))
        return Applied(
            outcome="applied",
            draft_id=event.id,
            version=tx.imports.event(event.id).version,
        )
    for candidate in candidates:
        candidate_state = (
            "dismissed" if deleting else marker.previous_state.events[candidate.id]
        )
        if candidate.state != candidate_state:
            tx.imports.put_event(
                replace(
                    candidate,
                    state=candidate_state,
                    version=candidate.version + 1,
                    updated_at=datetime.now(timezone.utc),
                )
            )
    updated = {
        **document,
        "status": state,
        "resolution": resolution,
        "version": document["version"] + 1,
    }
    tx.rows(
        "update public.financial_document_extractions set draft=%s"
        " where user_id=%s and connection_id=%s",
        (Jsonb(updated), tx.context.owner_id, command.document_id),
    )
    if not deleting:
        _recheck_duplicates(tx, tuple(candidate.id for candidate in candidates))
    return Applied(outcome="applied")


def _recheck_duplicates(tx: ActionTransaction, event_ids: tuple[str, ...]) -> None:
    from argus.domain.business.actions.duplicate_resolution import attachment_signature

    for event_id in event_ids:
        if tx.imports.event(event_id).state == "open":
            flag_receipt_duplicates(
                tx.imports,
                event_id,
                lambda draft_id: attachment_signature(tx, draft_id),
                symmetric=True,
            )

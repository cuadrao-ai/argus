"""Durable device-file append without extraction or changes to financial facts."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from psycopg import Connection
from pydantic import Field

from argus.domain.business.actions import plans, sources
from argus.domain.business.annotations import (
    eligible,
    finish,
    save_annotation,
    supporting_source_key,
)
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    BusinessAuthority,
    authorize,
)
from argus.domain.business.contracts.dossier import AttachmentSource
from argus.domain.business.reporting_query import Contract
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.documents.service import DocumentsService, stored_filename
from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx


class SupportingCommand(Contract):
    action: Literal["append_supporting_file"] = "append_supporting_file"
    draft_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    filename: str
    filename_input_hash: str
    media_type: str
    sha256: str


class SupportingResult(Contract):
    draft_id: UUID
    version: int
    outcome: Literal["appended", "duplicate"]
    source_id: UUID
    receipt_id: UUID
    sha256: str


def _replay(
    tx: ActionTransaction, command: SupportingCommand, key: str
) -> SupportingResult | None:
    eligible(tx, command.draft_id)
    saved = plans.receipt(tx, key, command)
    if not saved or saved["outcome"] is None:
        return None
    result = SupportingResult.model_validate(saved["outcome"]["annotation_result"])
    available = tx.rows(
        "select 1 from public.business_draft_sources l "
        "join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id "
        "join public.financial_source_connections c on c.id=s.connection_id and c.owner_space_id=s.space_id "
        "join public.financial_document_extractions d on d.connection_id=c.id and d.user_id=c.user_id "
        "where l.space_id=%s and l.draft_id=%s and s.id=%s and c.id=%s and c.user_id=%s and c.status<>'disconnected' and d.source_sha256=%s and (d.draft->>'source_available')::boolean",
        (
            tx.context.actor.space_id,
            command.draft_id,
            result.source_id,
            result.receipt_id,
            tx.context.owner_id,
            result.sha256,
        ),
    )
    if not available:
        raise ActionError("invalid_input", "document_source_unavailable")
    return result


def _attach(
    tx: ActionTransaction, command: SupportingCommand, key: str, receipt_id: UUID
) -> SupportingResult:
    replay = _replay(tx, command, key)
    if replay:
        return replay
    event = eligible(tx, command.draft_id, command.expected_version)
    conflicts = tx.rows(
        "select 1 from public.business_sources s join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id "
        "where s.space_id=%s and s.connection_id=%s and l.draft_id<>%s limit 1",
        (tx.context.actor.space_id, receipt_id, command.draft_id),
    )
    observed_elsewhere = tx.rows(
        "select 1 from public.financial_import_observations o "
        "join public.financial_import_events e on e.id=o.event_id "
        "where o.connection_id=%s and e.owner_space_id=%s and e.user_id=%s and e.id<>%s limit 1",
        (receipt_id, tx.context.actor.space_id, tx.context.owner_id, command.draft_id),
    )
    if conflicts or observed_elsewhere:
        raise ActionError("invalid_input", "supporting_file_already_linked")
    existing = tx.rows(
        "select s.id from public.business_sources s join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id "
        "where s.space_id=%s and s.connection_id=%s and l.draft_id=%s order by s.id limit 1",
        (tx.context.actor.space_id, receipt_id, command.draft_id),
    )
    if existing:
        source_id = existing[0]["id"]
        outcome = "duplicate"
    else:
        evidence = AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=datetime.now(timezone.utc),
            connection_id=receipt_id,
            filename=command.filename,
            media_type=command.media_type,
        )
        source_id = sources.record_source(tx, supporting_source_key(receipt_id), evidence)
        sources.attach(tx, event.id, (source_id,))
        event = save_annotation(tx, event, source_ids=(source_id,))
        outcome = "appended"
    result = SupportingResult(
        draft_id=command.draft_id,
        version=event.version,
        outcome=outcome,
        source_id=source_id,
        receipt_id=receipt_id,
        sha256=command.sha256,
    )
    finish(tx, key, result)
    return result


def append_file(
    authority: BusinessAuthority,
    documents: DocumentsService,
    context: ActionContext,
    draft_id: UUID,
    expected_version: int,
    filename: str,
    media_type: str,
    content: bytes,
    key: str,
) -> SupportingResult:
    command = SupportingCommand(
        draft_id=draft_id,
        expected_version=expected_version,
        filename=stored_filename(filename),
        filename_input_hash=hashlib.sha256(filename.encode("utf-8")).hexdigest(),
        media_type=media_type,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    with transaction(authority, context, "prepare") as tx:
        replay = _replay(tx, command, key)
        if replay:
            return replay
        eligible(tx, draft_id, expected_version)
        if plans.receipt(tx, key, command) is None:
            plans.start_receipt(tx, key, command)

    result: SupportingResult | None = None

    def captured(connection: Connection, connection_id: str) -> None:
        nonlocal result
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"financial_import:{context.owner_id}",),
        )
        live = authorize(connection, context.actor, context.grant_id)
        live.require("prepare")
        if live.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        tx = ActionTransaction(
            connection, live, _PostgresTx(connection, context.owner_id, context.scope)
        )
        result = _attach(tx, command, key, UUID(connection_id))
        authorize(connection, context.actor, context.grant_id).require("prepare")

    # This capture primitive validates/stores bytes only. It never reads consent,
    # dispatches preparation, or creates an activity. The hook commits with custody.
    documents._upload(
        user_id=context.owner_id,
        content=content,
        filename=command.filename,
        media_type=media_type,
        consent=False,
        proposal=None,
        source_text=None,
        scope=context.scope,
        on_capture=captured,
    )
    if result is None:
        raise ActionError("invalid_input", "supporting_file_capture_unsettled")
    return result

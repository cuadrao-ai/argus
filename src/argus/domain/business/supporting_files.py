"""A record's supporting files: append without extraction, take one off, put
it back. None of these changes a financial fact."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import Connection
from pydantic import Field

from argus.domain.business.actions import plans, sources
from argus.domain.business.annotations import (
    SUPPORTING_SOURCE_SQL,
    SUPPORTING_UPLOAD_NAMESPACE,
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
from argus.domain.business.contracts.actions import SUPPORTING_FILE_LIMIT
from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.contracts.dossier import AttachmentSource, SupportingFile
from argus.domain.business.reporting_query import Contract
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.documents.service import (
    DocumentsService,
    document_ref,
    stored_filename,
)
from argus.domain.ingestion.reconcile.model import ImportEvent
from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx

SupportingAction = Literal[
    "append_supporting_file", "unlink_supporting_file", "restore_supporting_file"
]


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


class SupportingLinkCommand(Contract):
    action: Literal["unlink_supporting_file", "restore_supporting_file"]
    draft_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    source_id: UUID


class SupportingLinkResult(Contract):
    draft_id: UUID
    version: int
    outcome: Literal["unlinked", "restored"]
    source_id: UUID
    #: On ``unlinked``: when the file's bytes are erased and restore ends.
    purge_at: datetime | None = None


def _files(tx: ActionTransaction, draft_id: UUID | str) -> list[dict[str, Any]]:
    """The record's supporting files, oldest first: each one linked to it now,
    and each one whose newest change here is an unlink and that no record
    holds. ``unlinked_at`` is that unlink's time."""

    return tx.rows(
        "select s.id as source_id,s.connection_id as receipt_id,"
        " d.draft->>'filename' as filename,d.draft->>'media_type' as media_type,"
        " (d.draft->>'size_bytes')::bigint as size_bytes,d.source_sha256 as sha256,"
        " l.draft_id is not null as linked,u.created_at as unlinked_at"
        " from public.business_sources s"
        " left join public.business_draft_sources l"
        " on l.source_id=s.id and l.space_id=s.space_id and l.draft_id=%s"
        " left join public.financial_document_extractions d"
        " on d.connection_id=s.connection_id and d.user_id=%s"
        " left join lateral (select r.created_at,r.supporting_change"
        " from public.business_draft_revisions r"
        " where r.space_id=s.space_id and r.draft_id=%s and r.source_ids=array[s.id]"
        " and r.supporting_change is not null order by r.version desc limit 1) u on true"
        f" where s.space_id=%s and {SUPPORTING_SOURCE_SQL}"
        " and (l.draft_id is not null or (u.supporting_change='unlinked'"
        " and not exists (select 1 from public.business_draft_sources o"
        " where o.source_id=s.id and o.space_id=s.space_id)))"
        " order by s.received_at,s.id",
        (draft_id, tx.context.owner_id, draft_id, tx.context.actor.space_id),
    )


def _full(files: list[dict[str, Any]]) -> bool:
    return sum(row["linked"] for row in files) >= SUPPORTING_FILE_LIMIT


def supporting_state(
    tx: ActionTransaction, draft_id: UUID, can_annotate: bool
) -> dict[str, Any]:
    """The dossier's supporting-file fields. An unlinked file past its restore
    window is not listed, erased or not. An action is offered only when
    ``_refusal`` has no reason against it."""

    now = datetime.now(timezone.utc)
    files = _files(tx, draft_id)

    def offered(action: SupportingAction, file: dict[str, Any] | None = None) -> bool:
        return can_annotate and _refusal(tx, draft_id, files, action, file) is None

    shown = []
    for row in files:
        purge_at = None if row["linked"] else row["unlinked_at"] + PURGE_AFTER
        if purge_at is not None and purge_at <= now:
            continue
        shown.append(
            SupportingFile(
                source_id=row["source_id"],
                receipt_id=row["receipt_id"],
                filename=row["filename"],
                media_type=row["media_type"],
                size_bytes=row["size_bytes"],
                state="linked" if row["linked"] else "unlinked",
                purge_at=purge_at,
                unlink_available=offered("unlink_supporting_file", row),
                restore_available=offered("restore_supporting_file", row),
            )
        )
    return {
        "supporting_files": tuple(shown),
        "supporting_limit_reached": _full(files),
        "supporting_append_available": offered("append_supporting_file"),
    }


def _same_bytes(tx: ActionTransaction, sha256: str) -> list[UUID]:
    """The Business's live uploads of these bytes: the receipt, the supporting
    file, or both."""

    context = tx.context
    refs = [
        document_ref(context.owner_id, context.scope, sha256, namespace)
        for namespace in (None, SUPPORTING_UPLOAD_NAMESPACE)
    ]
    return [
        row["id"]
        for row in tx.rows(
            "select id from public.financial_source_connections"
            " where source='statement' and external_ref=any(%s) and owner_space_id=%s"
            " and user_id=%s and status<>'disconnected'",
            (refs, context.actor.space_id, context.owner_id),
        )
    ]


def _linked_elsewhere(tx: ActionTransaction, uploads: list[UUID], draft_id: UUID) -> bool:
    """Another record holds these bytes, as a source or as what it was read from."""

    return bool(
        tx.rows(
            "select 1 from public.business_sources s join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id "
            "where s.space_id=%s and s.connection_id=any(%s) and l.draft_id<>%s limit 1",
            (tx.context.actor.space_id, uploads, draft_id),
        )
        or tx.rows(
            "select 1 from public.financial_import_observations o "
            "join public.financial_import_events e on e.id=o.event_id "
            "where o.connection_id=any(%s) and e.owner_space_id=%s and e.user_id=%s and e.id<>%s limit 1",
            (uploads, tx.context.actor.space_id, tx.context.owner_id, draft_id),
        )
    )


def _refusal(
    tx: ActionTransaction,
    draft_id: UUID,
    files: list[dict[str, Any]],
    action: SupportingAction,
    file: dict[str, Any] | None = None,
) -> str | None:
    """Why the record refuses this command now, or None when it takes it. The
    command raises this code and the dossier offers the action only without
    one. ``file`` is the listed file an unlink or a restore names. An append
    is asked for bytes that would add a file."""

    if action == "append_supporting_file":
        return "supporting_file_limit_reached" if _full(files) else None
    assert file is not None
    if action == "unlink_supporting_file":
        return None if file["linked"] else "supporting_file_not_linked"
    if file["linked"] or _linked_elsewhere(
        tx, [file["receipt_id"], *_same_bytes(tx, file["sha256"])], draft_id
    ):
        return "supporting_file_already_linked"
    if file["unlinked_at"] + PURGE_AFTER <= datetime.now(timezone.utc):
        return "supporting_file_restore_expired"
    return "supporting_file_limit_reached" if _full(files) else None


def _require(
    tx: ActionTransaction,
    draft_id: UUID,
    files: list[dict[str, Any]],
    action: SupportingAction,
    file: dict[str, Any] | None = None,
) -> None:
    code = _refusal(tx, draft_id, files, action, file)
    if code:
        raise ActionError("invalid_input", code)


def _settled(
    tx: ActionTransaction, command: SupportingCommand, key: str, event: ImportEvent
) -> SupportingResult | None:
    """Bytes this record already holds, as its document or as a file, add
    nothing. Bytes another record holds are refused. Only bytes that would
    add a file meet the limit, so the limit is checked last."""

    uploads = _same_bytes(tx, command.sha256)
    if _linked_elsewhere(tx, uploads, command.draft_id):
        raise ActionError("invalid_input", "supporting_file_already_linked")
    existing = tx.rows(
        "select s.id,s.connection_id from public.business_sources s join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id "
        "where s.space_id=%s and s.connection_id=any(%s) and l.draft_id=%s order by s.id limit 1",
        (tx.context.actor.space_id, uploads, command.draft_id),
    )
    if not existing:
        _require(tx, command.draft_id, _files(tx, command.draft_id), command.action)
        return None
    result = SupportingResult(
        draft_id=command.draft_id,
        version=event.version,
        outcome="duplicate",
        source_id=existing[0]["id"],
        receipt_id=existing[0]["connection_id"],
        sha256=command.sha256,
    )
    finish(tx, key, result)
    return result


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
    settled = _settled(tx, command, key, event)
    if settled:
        return settled
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
    event = save_annotation(
        tx, event, source_ids=(source_id,), supporting=("appended", command.filename)
    )
    result = SupportingResult(
        draft_id=command.draft_id,
        version=event.version,
        outcome="appended",
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
        event = eligible(tx, draft_id, expected_version)
        if plans.receipt(tx, key, command) is None:
            plans.start_receipt(tx, key, command)
        # Settled or refused here, before any byte is stored. The capture checks again.
        settled = _settled(tx, command, key, event)
        if settled:
            return settled

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
        namespace=SUPPORTING_UPLOAD_NAMESPACE,
    )
    if result is None:
        raise ActionError("invalid_input", "supporting_file_capture_unsettled")
    return result


def _unlink(
    tx: ActionTransaction,
    event: ImportEvent,
    files: list[dict[str, Any]],
    file: dict[str, Any] | None,
    source_id: UUID,
) -> SupportingLinkResult:
    if file is None:
        raise ActionError("not_found", "supporting_file_not_found")
    _require(tx, UUID(event.id), files, "unlink_supporting_file", file)
    tx.rows(
        "delete from public.business_draft_sources"
        " where space_id=%s and draft_id=%s and source_id=%s",
        (tx.context.actor.space_id, event.id, source_id),
    )
    event = save_annotation(
        tx, event, source_ids=(source_id,), supporting=("unlinked", file["filename"])
    )
    [revision] = tx.rows(
        "select created_at from public.business_draft_revisions"
        " where draft_id=%s and version=%s",
        (event.id, event.version),
    )
    return SupportingLinkResult(
        draft_id=UUID(event.id),
        version=event.version,
        outcome="unlinked",
        source_id=source_id,
        purge_at=revision["created_at"] + PURGE_AFTER,
    )


def _gone(tx: ActionTransaction, draft_id: UUID, source_id: UUID) -> ActionError:
    """Why a file this record does not list cannot come back."""

    space_id = tx.context.actor.space_id
    if not tx.rows(
        "select 1 from public.business_draft_revisions where space_id=%s and draft_id=%s"
        " and source_ids=array[%s]::uuid[] and supporting_change='unlinked' limit 1",
        (space_id, draft_id, source_id),
    ):
        return ActionError("not_found", "supporting_file_not_found")
    if tx.rows(
        "select 1 from public.business_draft_sources where space_id=%s and source_id=%s limit 1",
        (space_id, source_id),
    ):
        return ActionError("invalid_input", "supporting_file_already_linked")
    return ActionError("invalid_input", "supporting_file_restore_expired")


def _restore(
    tx: ActionTransaction,
    event: ImportEvent,
    files: list[dict[str, Any]],
    file: dict[str, Any] | None,
    source_id: UUID,
) -> SupportingLinkResult:
    draft_id = UUID(event.id)
    if file is None:
        raise _gone(tx, draft_id, source_id)
    _require(tx, draft_id, files, "restore_supporting_file", file)
    sources.attach(tx, event.id, (source_id,))
    event = save_annotation(
        tx, event, source_ids=(source_id,), supporting=("restored", file["filename"])
    )
    return SupportingLinkResult(
        draft_id=draft_id, version=event.version, outcome="restored", source_id=source_id
    )


def change_file_link(
    authority: BusinessAuthority,
    context: ActionContext,
    command: SupportingLinkCommand,
    key: str,
) -> SupportingLinkResult:
    """Take a supporting file off its record, or put it back within
    ``PURGE_AFTER``. The same key answers with the first result."""

    with transaction(authority, context, "prepare") as tx:
        eligible(tx, command.draft_id)
        saved = plans.receipt(tx, key, command)
        if saved:
            return SupportingLinkResult.model_validate(
                saved["outcome"]["annotation_result"]
            )
        event = eligible(tx, command.draft_id, command.expected_version)
        files = _files(tx, command.draft_id)
        file = next((row for row in files if row["source_id"] == command.source_id), None)
        plans.start_receipt(tx, key, command)
        if command.action == "unlink_supporting_file":
            result = _unlink(tx, event, files, file, command.source_id)
        else:
            result = _restore(tx, event, files, file, command.source_id)
        finish(tx, key, result)
        return result

"""Human annotations preserve approved facts and use the existing Activity history."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import Field, field_validator

from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    Authorization,
    BusinessAuthority,
)
from argus.domain.business.reporting_query import Contract
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent


class EditCurrentNote(Contract):
    expected_version: int = Field(ge=1, strict=True)
    note: str = Field(max_length=500)

    @field_validator("note")
    @classmethod
    def valid_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("null characters are not permitted")
        return value


class NoteCommand(EditCurrentNote):
    action: Literal["edit_current_note"] = "edit_current_note"
    draft_id: UUID


class NoteResult(Contract):
    draft_id: UUID
    version: int
    note: str


def supporting_source_key(connection_id: UUID | str) -> str:
    return f"supporting:{connection_id}"


def annotation_available(authorization: Authorization, event: ImportEvent | None) -> bool:
    return bool(
        event
        and "business" in event.resolution
        and event.state in ("open", "accepted")
        and authorization.context.actor.actor_kind == "member"
        and "prepare" in authorization.permissions
    )


def eligible(
    tx: ActionTransaction, draft_id: UUID, expected_version: int | None = None
) -> ImportEvent:
    if tx.context.actor.actor_kind != "member":
        raise ActionError("permission_denied", "business_human_command_required")
    try:
        event = tx.imports.event(str(draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    if "business" not in event.resolution:
        raise ActionError("invalid_input", "business_annotation_unsupported")
    if not annotation_available(tx.authorization, event):
        raise ActionError("invalid_input", "business_annotation_unavailable")
    if expected_version is not None and event.version != expected_version:
        raise ActionError("stale_version", "stale_version")
    return event


def current_note(event: ImportEvent) -> str | None:
    return event.resolution.get("current_note", event.resolution.get("note"))


def save_annotation(
    tx: ActionTransaction,
    event: ImportEvent,
    *,
    source_ids: tuple[UUID, ...] = (),
    note: str | None = None,
) -> ImportEvent:
    from argus.domain.business.actions.facts import facts_of

    before_note = current_note(event)
    resolution = dict(event.resolution)
    if note is not None:
        resolution["current_note"] = note
    event = replace(
        event,
        version=event.version + 1,
        updated_at=datetime.now(timezone.utc),
        resolution=resolution,
    )
    tx.imports.put_event(event)
    facts = facts_of(event).model_dump(mode="json")
    business = resolution["business"]
    tx.rows(
        "insert into public.business_draft_revisions "
        "(space_id,draft_id,version,actor,before_facts,after_facts,source_ids,before_dgii,after_dgii,before_due_on,after_due_on,before_current_note,after_current_note) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            tx.context.actor.space_id,
            event.id,
            event.version,
            Jsonb(tx.authorization.provenance.model_dump(mode="json")),
            Jsonb(facts),
            Jsonb(facts),
            list(source_ids),
            Jsonb(business.get("dgii")) if business.get("dgii") else None,
            Jsonb(business.get("dgii")) if business.get("dgii") else None,
            business.get("due_on"),
            business.get("due_on"),
            before_note if note is not None else None,
            note,
        ),
    )
    return event


def finish(tx: ActionTransaction, key: str, result: Contract) -> None:
    tx.rows(
        "update public.business_action_receipts set outcome=%s where space_id=%s and actor_id=%s and idempotency_key=%s",
        (
            Jsonb(
                {
                    "outcome": "applied",
                    "draft_id": str(result.draft_id),
                    "version": result.version,
                    "annotation_result": result.model_dump(mode="json"),
                }
            ),
            tx.context.actor.space_id,
            tx.context.actor.actor_id,
            key,
        ),
    )


def edit_note(
    authority: BusinessAuthority,
    context: ActionContext,
    draft_id: UUID,
    body: EditCurrentNote,
    key: str,
) -> NoteResult:
    from argus.domain.business.actions import plans

    command = NoteCommand(draft_id=draft_id, **body.model_dump())
    with transaction(authority, context, "prepare") as tx:
        eligible(tx, draft_id)
        saved = plans.receipt(tx, key, command)
        if saved:
            return NoteResult.model_validate(saved["outcome"]["annotation_result"])
        event = eligible(tx, draft_id, body.expected_version)
        plans.start_receipt(tx, key, command)
        event = save_annotation(tx, event, note=body.note)
        result = NoteResult(draft_id=draft_id, version=event.version, note=body.note)
        finish(tx, key, result)
        return result

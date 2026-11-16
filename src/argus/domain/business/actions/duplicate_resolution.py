from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from argus.domain.business.actions import document_deletion, mutations, plans, sources
from argus.domain.business.actions.duplicate_comparison import fiscal_repeats
from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    Applied,
    ExistingDraft,
    ResolveDuplicate,
    ResolveDuplicateCommand,
)
from argus.domain.business.contracts.deletion import deletion
from argus.domain.business.contracts.dossier import WebActionSource, web_action_text
from argus.domain.business.duplicates import (
    different_purchase,
    event_key,
    evidence_signature,
    pending_duplicates,
)
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent


def attachment_signature(tx: ActionTransaction, draft_id: str) -> str:
    evidence = tx.rows(
        "select s.id,s.connection_id,coalesce(d.source_sha256,d.draft->>'sha256') as source_sha256,d.batch"
        " from public.business_draft_sources l join public.business_sources s"
        " on s.id=l.source_id and s.space_id=l.space_id"
        " join public.financial_document_extractions d on d.connection_id=s.connection_id"
        " join public.financial_source_connections c on c.id=s.connection_id"
        " and c.owner_space_id=s.space_id"
        " where l.space_id=%s and l.draft_id=%s and s.kind='attachment' and c.user_id=%s"
        " order by s.id",
        (tx.context.actor.space_id, draft_id, tx.context.owner_id),
    )
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"] or "") for row in evidence
    ):
        raise ActionError("invalid_input", "duplicate_evidence_unavailable")
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _other_at(tx: ActionTransaction, request: ResolveDuplicate) -> ImportEvent:
    """The other draft the request names, at the version the person saw."""

    try:
        other = tx.imports.event(str(request.other_draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    if other.version != request.other_version:
        raise ActionError("stale_version", "stale_version")
    if other.state not in ("open", "accepted") or "business" not in other.resolution:
        raise ActionError("invalid_input", "duplicate_pair_not_available")
    return other


def _read_pair(
    tx: ActionTransaction,
    event: ImportEvent,
    other: ImportEvent,
    source_signature: Callable[[str], str],
) -> bool:
    """Whether the read-facts warning between the two still waits for a decision."""

    key = event_key(event, tx.imports.observations)
    return (
        other.id != event.id
        and other.id in pending_duplicates(tx.imports, event, source_signature)
        and event.attention in (None, "possible_duplicate")
        and (
            (event.attention_detail or {}).get("basis") == "read_facts"
            or bool(event.resolution.get("different_purchases"))
        )
        and key is not None
        and key == event_key(other, tx.imports.observations)
    )


def _delete_as_duplicate(
    tx: ActionTransaction,
    draft_id: UUID,
    request: ResolveDuplicate,
    key: str,
    source_signature: Callable[[str], str],
) -> Applied:
    try:
        event = tx.imports.event(str(draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    marker = deletion(event.state, event.resolution)
    if marker is not None and marker.reason == "duplicate":
        # Already in Eliminados for this reason: a repeat ends in the same
        # state and writes nothing.
        return Applied(outcome="replayed", draft_id=event.id, version=event.version)
    event = mutations.event_at(
        tx, ExistingDraft(draft_id=draft_id, version=request.version)
    )
    other = _other_at(tx, request)
    if UUID(other.id) not in fiscal_repeats(tx, [draft_id]).get(
        draft_id, ()
    ) and not _read_pair(tx, event, other, source_signature):
        raise ActionError("invalid_input", "duplicate_pair_not_available")
    return document_deletion.delete(tx, draft_id, key, "duplicate")


def resolve(
    authority: BusinessAuthority,
    context: ActionContext,
    draft_id: UUID,
    request: ResolveDuplicate,
    key: str,
) -> ActionOutcome:
    command = ResolveDuplicateCommand(draft_id=draft_id, request=request)
    deleting = request.decision == "same_purchase"
    try:
        # Deleting a document is the owner's alone, whatever names the delete.
        with transaction(authority, context, "approve" if deleting else "prepare") as tx:
            if context.actor.actor_kind != "member":
                raise ActionError("permission_denied", "business_human_command_required")
            def source_signature(event_id: str) -> str:
                return attachment_signature(tx, event_id)
            saved = plans.receipt(tx, key, command)
            if saved is not None:
                if not deleting and (saved.get("outcome") or {}).get("outcome") == "applied":
                    try:
                        event = tx.imports.event(str(draft_id))
                        other = tx.imports.event(str(request.other_draft_id))
                    except EventNotFound:
                        raise ActionError(
                            "not_found", "business_record_not_found"
                        ) from None
                    if not different_purchase(tx.imports, event, other, source_signature):
                        raise ActionError("stale_version", "duplicate_evidence_changed")
                return plans.replay(saved)
            plans.start_receipt(tx, key, command)
            try:
                with tx.connection.transaction():
                    if deleting:
                        result = _delete_as_duplicate(
                            tx, draft_id, request, key, source_signature
                        )
                    else:
                        result = _keep_as_different(
                            tx, draft_id, command, key, source_signature
                        )
            except ActionError as error:
                result = error.result
            return plans.finish_receipt(tx, key, result)
    except ActionError as error:
        return error.result


def _keep_as_different(
    tx: ActionTransaction,
    draft_id: UUID,
    command: ResolveDuplicateCommand,
    key: str,
    source_signature: Callable[[str], str],
) -> ActionOutcome:
    request = command.request
    event = mutations.event_at(
        tx, ExistingDraft(draft_id=draft_id, version=request.version)
    )
    other = _other_at(tx, request)
    if not _read_pair(tx, event, other, source_signature):
        raise ActionError("invalid_input", "duplicate_pair_not_available")
    resolution = dict(event.resolution)
    decisions = dict(resolution.get("different_purchases", {}))
    decisions[other.id] = {
        "self": evidence_signature(tx.imports, event),
        "other": evidence_signature(tx.imports, other),
        "source_self": source_signature(event.id),
        "source_other": source_signature(other.id),
    }
    resolution["different_purchases"] = decisions
    remaining = tuple(
        i
        for i in pending_duplicates(tx.imports, event, source_signature)
        if i != other.id
    )
    event = replace(
        event,
        resolution=resolution,
        possible_duplicates=remaining,
        attention="possible_duplicate" if remaining else None,
        attention_detail=event.attention_detail if remaining else None,
        version=event.version + 1,
        updated_at=datetime.now(timezone.utc),
    )
    evidence = WebActionSource(
        id=uuid4(),
        received_at=datetime.now(timezone.utc),
        text=web_action_text(command.model_dump(mode="json")),
    )
    source_id = sources.record_source(
        tx, f"web:{tx.context.actor.actor_id}:{key}", evidence
    )
    facts = mutations.facts_of(event)
    return mutations.save_revision(
        tx,
        event,
        facts,
        facts,
        (source_id,),
        tx.authorization.provenance,
        None,
    )

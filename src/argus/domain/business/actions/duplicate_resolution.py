from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from argus.domain.business.actions import mutations, plans, sources
from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    ExistingDraft,
    ResolveDuplicate,
    ResolveDuplicateCommand,
)
from argus.domain.business.contracts.dossier import WebActionSource, web_action_text
from argus.domain.business.duplicates import (
    different_purchase,
    event_key,
    evidence_signature,
    pending_duplicates,
)
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.reconcile.model import EventNotFound


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


def resolve(
    authority: BusinessAuthority,
    context: ActionContext,
    draft_id: UUID,
    request: ResolveDuplicate,
    key: str,
) -> ActionOutcome:
    command = ResolveDuplicateCommand(draft_id=draft_id, request=request)
    try:
        with transaction(authority, context, "prepare") as tx:
            if context.actor.actor_kind != "member":
                raise ActionError("permission_denied", "business_human_command_required")
            def source_signature(event_id: str) -> str:
                return attachment_signature(tx, event_id)
            saved = plans.receipt(tx, key, command)
            if saved is not None:
                if (saved.get("outcome") or {}).get("outcome") == "applied":
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
                    event = mutations.event_at(
                        tx, ExistingDraft(draft_id=draft_id, version=request.version)
                    )
                    try:
                        other = tx.imports.event(str(request.other_draft_id))
                    except EventNotFound:
                        raise ActionError(
                            "not_found", "business_record_not_found"
                        ) from None
                    if other.version != request.other_version:
                        raise ActionError("stale_version", "stale_version")
                    if (
                        other.id == event.id
                        or other.state not in ("open", "accepted")
                        or "business" not in other.resolution
                        or other.id
                        not in pending_duplicates(tx.imports, event, source_signature)
                        or event.attention not in (None, "possible_duplicate")
                        or (
                            (event.attention_detail or {}).get("basis") != "read_facts"
                            and not event.resolution.get("different_purchases")
                        )
                        or event_key(event, tx.imports.observations) is None
                        or event_key(event, tx.imports.observations)
                        != event_key(other, tx.imports.observations)
                    ):
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
                        tx, f"web:{context.actor.actor_id}:{key}", evidence
                    )
                    facts = mutations.facts_of(event)
                    result = mutations.save_revision(
                        tx,
                        event,
                        facts,
                        facts,
                        (source_id,),
                        tx.authorization.provenance,
                        None,
                    )
            except ActionError as error:
                result = error.result
            return plans.finish_receipt(tx, key, result)
    except ActionError as error:
        return error.result

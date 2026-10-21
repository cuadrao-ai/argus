from __future__ import annotations

import hashlib
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter, ValidationError

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    Applied,
    BoundDraft,
    Command,
    DraftReference,
    ExistingDraft,
    OutcomeUnknown,
    PlannedDraft,
    TurnPlan,
    canonical_input_hash,
)
from argus.domain.business.contracts.authority import ActorProvenance
from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.business.transactions import ActionTransaction

OUTCOME = TypeAdapter(ActionOutcome)


def same_authority(tx: ActionTransaction, actor: ActorProvenance) -> bool:
    live = tx.authorization.provenance
    return (actor.actor_id, actor.actor_kind, actor.grant_id, actor.issuer_id) == (
        live.actor_id,
        live.actor_kind,
        live.grant_id,
        live.issuer_id,
    )


def turn(tx: ActionTransaction, key: str, lease: SenderLease | None) -> dict:
    rows = tx.rows(
        "select * from public.business_turns where turn_key=%s and space_id=%s"
        " and actor_id=%s for update",
        (key, tx.context.actor.space_id, tx.context.actor.actor_id),
    )
    if not rows:
        raise ActionError("not_found", "business_record_not_found")
    row = rows[0]
    if (
        lease is None
        or row["sender_hash"] != lease.sender_hash
        or row["lease_fence"] != lease.fence
    ):
        raise ActionError("permission_denied", "business_sender_lease_lost")
    return row


def persist(
    tx: ActionTransaction, key: str, plan: TurnPlan, lease: SenderLease | None
) -> TurnPlan:
    row = turn(tx, key, lease)
    if row["plan"] is not None:
        saved = TurnPlan.model_validate(row["plan"])
        actor = ActorProvenance.model_validate(row["plan_actor"])
        if saved != plan or not same_authority(tx, actor):
            raise ActionError("idempotency_conflict", "business_plan_conflict")
        return saved
    if row["model_state"] == "unknown":
        raise ActionError("invalid_input", "business_model_outcome_unknown")
    tx.rows(
        "update public.business_turns set plan=%s,plan_actor=%s,model_state='completed',"
        " updated_at=clock_timestamp() where turn_key=%s",
        (
            Jsonb(plan.model_dump(mode="json", exclude_none=True)),
            Jsonb(tx.authorization.provenance.model_dump(mode="json")),
            key,
        ),
    )
    return plan


def action_key(turn_key: str, index: int) -> str:
    return f"{hashlib.sha256(turn_key.encode()).hexdigest()}:{index}"


def receipt(tx: ActionTransaction, key: str, command: Command) -> dict | None:
    if not 1 <= len(key) <= 80:
        raise ActionError("invalid_input", "idempotency_key_invalid")
    rows = tx.rows(
        "select * from public.business_action_receipts"
        " where space_id=%s and actor_id=%s and idempotency_key=%s",
        (tx.context.actor.space_id, tx.context.actor.actor_id, key),
    )
    if not rows:
        return None
    row = rows[0]
    actor = ActorProvenance.model_validate(row["actor"])
    if row["input_hash"] != canonical_input_hash(command) or not same_authority(
        tx, actor
    ):
        raise ActionError("idempotency_conflict", "business_action_conflict")
    return row


def start_receipt(
    tx: ActionTransaction,
    key: str,
    command: Command,
    *,
    actor: ActorProvenance | None = None,
    turn_key: str | None = None,
    index: int | None = None,
) -> None:
    tx.rows(
        "insert into public.business_action_receipts"
        " (space_id,actor_id,actor,idempotency_key,input_hash,command,turn_key,action_index)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            tx.context.actor.space_id,
            tx.context.actor.actor_id,
            Jsonb((actor or tx.authorization.provenance).model_dump(mode="json")),
            key,
            canonical_input_hash(command),
            Jsonb(command.model_dump(mode="json", exclude_none=True)),
            turn_key,
            index,
        ),
    )


def finish_receipt(
    tx: ActionTransaction, key: str, outcome: ActionOutcome
) -> ActionOutcome:
    tx.rows(
        "update public.business_action_receipts set outcome=%s"
        " where space_id=%s and actor_id=%s and idempotency_key=%s",
        (
            Jsonb(outcome.model_dump(mode="json")),
            tx.context.actor.space_id,
            tx.context.actor.actor_id,
            key,
        ),
    )
    return outcome


def replay(row: dict) -> ActionOutcome:
    return (
        OUTCOME.validate_python(row["outcome"])
        if row["outcome"]
        else OutcomeUnknown(code="business_action_unsettled")
    )


def reference(
    tx: ActionTransaction, ref: DraftReference, key: str | None, index: int | None
) -> ExistingDraft:
    if isinstance(ref, BoundDraft):
        return bound_reference(tx, ref, key, index)
    if not isinstance(ref, PlannedDraft):
        return ref
    if key is None or index is None or ref.from_action >= index:
        raise ActionError("invalid_input", "business_draft_reference_invalid")
    rows = tx.rows(
        "select action_index,outcome from public.business_action_receipts"
        " where turn_key=%s and action_index >= %s and action_index < %s"
        " and space_id=%s and actor_id=%s order by action_index",
        (
            key,
            ref.from_action,
            index,
            tx.context.actor.space_id,
            tx.context.actor.actor_id,
        ),
    )
    if not rows or rows[0]["action_index"] != ref.from_action:
        raise ActionError("invalid_input", "business_prior_action_missing")
    created = OUTCOME.validate_python(rows[0]["outcome"]) if rows[0]["outcome"] else None
    if (
        not isinstance(created, Applied)
        or created.draft_id is None
        or created.version is None
    ):
        raise ActionError("invalid_input", "business_prior_action_not_applied")
    version = created.version
    for row in rows[1:]:
        outcome = OUTCOME.validate_python(row["outcome"]) if row["outcome"] else None
        if (
            isinstance(outcome, Applied)
            and outcome.draft_id == created.draft_id
            and outcome.version is not None
        ):
            version = outcome.version
    return ExistingDraft(draft_id=UUID(str(created.draft_id)), version=version)


def bound_reference(
    tx: ActionTransaction, ref: BoundDraft, key: str | None, index: int | None
) -> ExistingDraft:
    if key is None or index is None or index < 0:
        raise ActionError("invalid_input", "business_draft_reference_invalid")
    rows = tx.rows(
        "select outcome from public.business_action_receipts"
        " where turn_key=%s and action_index<%s and space_id=%s and actor_id=%s"
        " and command->'draft'=%s order by action_index",
        (
            key,
            index,
            tx.context.actor.space_id,
            tx.context.actor.actor_id,
            Jsonb(ref.model_dump(mode="json")),
        ),
    )
    version = ref.base_version
    for row in rows:
        try:
            outcome = OUTCOME.validate_python(row["outcome"]) if row["outcome"] else None
        except ValidationError:
            raise ActionError(
                "invalid_input", "business_prior_action_not_applied"
            ) from None
        if (
            not isinstance(outcome, Applied)
            or outcome.draft_id != ref.draft_id
            or outcome.version is None
            or outcome.version < version
        ):
            raise ActionError("invalid_input", "business_prior_action_not_applied")
        version = outcome.version
    return ExistingDraft(draft_id=ref.draft_id, version=version)

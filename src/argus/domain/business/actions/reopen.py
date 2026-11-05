"""Reabrir: an approved record returns to the Bandeja for correction.

The draft goes back to ``open`` at a new version with its facts, sources,
revisions, marks and 606 or 607 data as they stand. Its money row stays in the
ledger with every revision and receipt, and ``reversed_at`` takes it out of
every read: period totals, the month close, the 606 and 607, Registros and the
account it debited. The reopen's own ledger row says who and when, and names
the row it reversed. A later approval writes one new money row.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from argus.domain.business.actions import plans
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    Applied,
    ReopenCommand,
    ReopenDraft,
)
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.reconcile.model import EventNotFound

if TYPE_CHECKING:
    from argus.domain.business.actions.service import BusinessActions

#: What the approval left on the draft for its own recovery. A reopened draft
#: has nothing to recover, and ``approval_receipt`` left behind would read as
#: a failed approval's revision on the next one.
_APPROVAL_KEYS = ("approval_receipt", "accepted", "accepted_request", "pending_request")


def linked_reason(tx: ActionTransaction, activity_id: str) -> str | None:
    """Why this recorded row cannot be reopened now, or None. A live bank
    match points at it, so the person unmatches first; a credit note or refund
    names it as the purchase it returns, whether recorded or still a draft, so
    that one is dealt with first."""

    space_id = tx.context.actor.space_id
    if tx.rows(
        "select 1 from public.business_bank_line_outcomes"
        " where space_id=%s and target_id=%s and kind='match' and ended_at is null"
        " limit 1",
        (space_id, activity_id),
    ):
        return "business_record_matched"
    refunded = tx.rows(
        "select 1 from public.financial_record_revisions v"
        " join public.financial_activity_memberships m on m.record_id=v.record_id"
        " and m.record_revision=v.revision"
        " and coalesce(m.record_owner_id,m.user_id)=v.user_id"
        " join public.financial_activity_groups g on g.id=m.activity_id"
        " and g.user_id=m.user_id and g.current_revision=m.activity_revision"
        " where v.user_id=%s and v.purchase_activity_id=%s and g.reversed_at is null"
        " limit 1",
        (tx.context.owner_id, activity_id),
    ) or tx.rows(
        "select 1 from public.financial_import_events"
        " where owner_space_id=%s and state in ('open','accepting','accepted')"
        " and resolution->'business'->'dgii'->>'purchase_activity_id'=%s limit 1",
        (space_id, activity_id),
    )
    return "business_refund_linked" if refunded else None


def reopen(
    service: BusinessActions,
    context: ActionContext,
    draft_id: UUID,
    request: ReopenDraft,
    key: str,
) -> ActionOutcome:
    """One ledger row under the key, on the approval permission. The owner
    lock every approval, 606 write and export takes serializes it with them,
    so a reopen never crosses a recording or a TXT build."""

    command = ReopenCommand(draft_id=draft_id, request=request)
    try:
        with transaction(service.authority, context, "approve") as tx:
            saved = plans.receipt(tx, key, command)
            if saved is not None:
                return plans.replay(saved)
            plans.start_receipt(tx, key, command)
            try:
                with tx.connection.transaction():
                    result = _reopen(tx, context, draft_id, request.version, key)
            except ActionError as error:
                result = error.result
            return plans.finish_receipt(tx, key, result)
    except ActionError as error:
        return error.result


def _reopen(
    tx: ActionTransaction, context: ActionContext, draft_id: UUID, version: int, key: str
) -> Applied:
    tx.authorization.require("approve")
    if context.actor.actor_kind != "member":
        raise ActionError("permission_denied", "business_human_command_required")
    try:
        event = tx.imports.event(str(draft_id))
    except EventNotFound:
        raise ActionError("not_found", "business_record_not_found") from None
    if event.version != version:
        raise ActionError("stale_version", "stale_version")
    if event.state != "accepted":
        raise ActionError("invalid_input", "business_draft_not_recorded")
    activity_id = event.activity_id
    reason = linked_reason(tx, activity_id)
    if reason is not None:
        raise ActionError("invalid_input", reason)
    reversed_rows = tx.rows(
        "update public.financial_activity_groups"
        " set reversed_at=coalesce(reversed_at, clock_timestamp())"
        " where id=%s and user_id=%s returning id",
        (activity_id, tx.context.owner_id),
    )
    if not reversed_rows:
        raise ActionError("invalid_input", "business_record_not_found")
    now = datetime.now(timezone.utc)
    resolution = {
        name: value
        for name, value in event.resolution.items()
        if name not in _APPROVAL_KEYS
    }
    resolution["reopened"] = [
        *event.resolution.get("reopened", ()),
        {
            "activity_id": activity_id,
            "version": event.version,
            "actor_id": str(context.actor.actor_id),
            "key": key,
            "at": now.isoformat(),
        },
    ]
    tx.imports.put_event(
        replace(
            event,
            state="open",
            activity_id=None,
            accept_key=None,
            version=event.version + 1,
            updated_at=now,
            resolution=resolution,
        )
    )
    return Applied(
        outcome="applied",
        draft_id=event.id,
        version=event.version + 1,
        activity_id=UUID(activity_id),
    )

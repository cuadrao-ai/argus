from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from argus.domain.business.actions import dossier, mutations, plans
from argus.domain.business.actions.facts import validate_facts
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    Applied,
    ApprovalCommand,
    ApproveExpense,
    ExistingDraft,
    OutcomeUnknown,
    Refused,
)
from argus.domain.business.transactions import transaction
from argus.domain.ingestion.reconcile.recording import _NOT_WRITTEN
from argus.domain.recording.money_schemas import MoneyRequest

if TYPE_CHECKING:
    from argus.domain.business.actions.service import BusinessActions


def reviewed_request(
    service: BusinessActions, context: ActionContext, draft_id: UUID, version: int
) -> MoneyRequest:
    with transaction(service.authority, context, "approve") as tx:
        mutations.event_at(tx, ExistingDraft(draft_id=draft_id, version=version))
        view = dossier.dossier(tx, draft_id)
        if view.blockers:
            raise ActionError("invalid_input", view.blockers[0].code)
        validate_facts(tx, view.facts)
    facts = view.facts
    draft = MoneyRequest(
        kind="expense",
        account_id=str(facts.funding.value.account_id),
        amount=facts.amount.value,
        occurred_at=datetime.combine(
            facts.occurred_on.value, time(0), tzinfo=ZoneInfo("America/Santo_Domingo")
        ),
        note=facts.counterparty.value[:200]
        if facts.counterparty.value is not None
        else None,
        category_id=facts.category_id.value,
    )
    preview = service.imports.money.preview(
        user_id=context.owner_id, request=draft, scope=context.scope
    )
    if not preview["ready"]:
        raise ActionError("invalid_input", "balance_coverage_required")
    return MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )


def approve(
    service: BusinessActions,
    context: ActionContext,
    draft_id: UUID,
    request: ApproveExpense,
    key: str,
) -> ActionOutcome:
    command = ApprovalCommand(draft_id=draft_id, request=request)
    try:
        with transaction(service.authority, context) as tx:
            tx.authorization.require("approve")
            if context.actor.actor_kind != "member":
                raise ActionError("permission_denied", "business_human_command_required")
            old = plans.receipt(tx, key, command)
            if (
                old is not None
                and old["outcome"]
                and old["outcome"]["outcome"] != "outcome_unknown"
            ):
                return plans.replay(old)
        try:
            money_request = (
                None
                if old is not None
                else reviewed_request(service, context, draft_id, request.version)
            )
        except (ActionError, *_NOT_WRITTEN) as error:
            refusal = (
                error.result
                if isinstance(error, ActionError)
                else Refused(
                    outcome="invalid_input",
                    code=getattr(error, "code", "activity_invalid"),
                )
            )
            with transaction(service.authority, context, "approve") as tx:
                old = plans.receipt(tx, key, command)
                if old is not None:
                    return plans.replay(old)
                plans.start_receipt(tx, key, command)
                return plans.finish_receipt(tx, key, refusal)
        with transaction(service.authority, context, "approve") as tx:
            old = plans.receipt(tx, key, command)
            if old is not None:
                if old["outcome"] and old["outcome"]["outcome"] != "outcome_unknown":
                    return plans.replay(old)
                event = tx.imports.event(str(draft_id))
                pointer = event.resolution.get("approval_receipt")
                if pointer != {"actor_id": str(context.actor.actor_id), "key": key}:
                    return OutcomeUnknown(
                        code="business_approval_reconciliation_required"
                    )
            else:
                plans.start_receipt(tx, key, command)
                try:
                    event = mutations.event_at(
                        tx, ExistingDraft(draft_id=draft_id, version=request.version)
                    )
                    view = dossier.dossier(tx, draft_id)
                    if view.blockers:
                        raise ActionError("invalid_input", view.blockers[0].code)
                    validate_facts(tx, view.facts)
                except ActionError as error:
                    return plans.finish_receipt(tx, key, error.result)
                claim_key = hashlib.sha256(
                    f"{context.actor.actor_id}:{key}".encode()
                ).hexdigest()
                event = replace(
                    event,
                    state="accepting",
                    accept_key=claim_key,
                    version=event.version + 1,
                    updated_at=datetime.now(timezone.utc),
                    resolution={
                        **event.resolution,
                        "pending_request": money_request.model_dump(mode="json"),
                        "approval_receipt": {
                            "actor_id": str(context.actor.actor_id),
                            "key": key,
                        },
                    },
                )
                tx.imports.put_event(event)
                plans.finish_receipt(
                    tx, key, OutcomeUnknown(code="business_recording_unsettled")
                )
        try:
            recorded = service.imports._write(
                context.owner_id,
                event,
                None,
                service.imports.clock(),
                scope=context.scope,
            )
        except _NOT_WRITTEN as error:
            result = Refused(
                outcome="invalid_input", code=getattr(error, "code", "activity_invalid")
            )
        except Exception:
            return OutcomeUnknown(code="business_recording_unsettled")
        else:
            result = Applied(
                outcome="applied",
                draft_id=draft_id,
                version=request.version,
                activity_id=recorded["activity"]["activity_id"],
            )
        with service.authority.pool.connection() as connection, connection.transaction():
            connection.execute(
                "update public.business_action_receipts set outcome=%s"
                " where space_id=%s and actor_id=%s and idempotency_key=%s"
                " and (outcome is null or outcome->>'outcome'='outcome_unknown')",
                (
                    Jsonb(result.model_dump(mode="json")),
                    context.actor.space_id,
                    context.actor.actor_id,
                    key,
                ),
            )
        return result
    except ActionError as error:
        return error.result

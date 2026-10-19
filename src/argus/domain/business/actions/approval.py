from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from argus.domain.business.actions import dossier, mutations, plans
from argus.domain.business.actions.facts import validate_facts
from argus.domain.business.actions.fiscal import (
    refund_reference,
    require_distinct_fiscal_document,
)
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import (
    ActionOutcome,
    Applied,
    ApprovalCommand,
    ApproveExpense,
    ApproveIncome,
    ApproveRefund,
    ExistingDraft,
    IncomeApprovalCommand,
    OutcomeUnknown,
    RefundApprovalCommand,
    Refused,
)
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFacts,
    Known,
    OwnerFunding,
)
from argus.domain.business.transactions import ActionTransaction, transaction
from argus.domain.ingestion.reconcile.model import ImportEvent
from argus.domain.ingestion.reconcile.recording import _NOT_WRITTEN
from argus.domain.recording.money_schemas import MoneyRequest, OwnerFunds

if TYPE_CHECKING:
    from argus.domain.business.actions.service import BusinessActions


def _reviewed_facts(
    tx: ActionTransaction,
    draft_id: UUID,
    version: int,
    kind: Literal["expense", "income", "refund"],
) -> tuple[ImportEvent, BusinessFacts]:
    event = mutations.event_at(tx, ExistingDraft(draft_id=draft_id, version=version))
    view = dossier.dossier(tx, draft_id)
    if view.blockers:
        first = view.blockers[0]
        raise ActionError(
            "not_found" if first.code == "business_record_not_found" else "invalid_input",
            first.code,
        )
    if not isinstance(view.facts.kind, Known) or view.facts.kind.value != kind:
        raise ActionError("invalid_input", "activity_kind_unsupported")
    validate_facts(tx, view.facts)
    require_distinct_fiscal_document(tx, event, view.facts)
    return event, view.facts


def _money_request(
    facts: BusinessFacts,
    space_id: UUID,
    kind: Literal["expense", "income", "refund"],
    purchase_activity_id: str | None = None,
) -> MoneyRequest:
    if not isinstance(facts.kind, Known) or facts.kind.value != kind:
        raise ActionError("invalid_input", "activity_kind_unsupported")
    if not isinstance(facts.funding, Known):
        raise ActionError("invalid_input", "fact_required")
    funding = facts.funding.value
    if kind in {"income", "refund"} and not isinstance(funding, BusinessAccountFunding):
        raise ActionError("invalid_input", "business_funding_unsupported")
    return MoneyRequest(
        kind=kind,
        purchase_activity_id=purchase_activity_id,
        owner_funding=OwnerFunds(owner_space_id=space_id, currency=facts.currency.value)
        if isinstance(funding, OwnerFunding)
        else None,
        account_id=None if isinstance(funding, OwnerFunding) else str(funding.account_id),
        amount=facts.amount.value,
        occurred_at=datetime.combine(
            facts.occurred_on.value, time(0), tzinfo=ZoneInfo("America/Santo_Domingo")
        ),
        note=facts.counterparty.value[:200]
        if facts.counterparty.value is not None
        else None,
        category_id=facts.category_id.value,
    )


def reviewed_request(
    service: BusinessActions,
    context: ActionContext,
    draft_id: UUID,
    version: int,
    kind: Literal["expense", "income", "refund"],
) -> MoneyRequest:
    with transaction(service.authority, context, "approve") as tx:
        event, facts = _reviewed_facts(tx, draft_id, version, kind)
        purchase = refund_reference(event) if kind == "refund" else None
    draft = _money_request(facts, context.actor.space_id, kind, purchase)
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
    request: ApproveExpense | ApproveIncome | ApproveRefund,
    key: str,
) -> ActionOutcome:
    kind: Literal["expense", "income", "refund"] = (
        "refund"
        if isinstance(request, ApproveRefund)
        else "income"
        if isinstance(request, ApproveIncome)
        else "expense"
    )
    command = (
        RefundApprovalCommand(draft_id=draft_id, request=request)
        if isinstance(request, ApproveRefund)
        else IncomeApprovalCommand(draft_id=draft_id, request=request)
        if isinstance(request, ApproveIncome)
        else ApprovalCommand(draft_id=draft_id, request=request)
    )
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
                else reviewed_request(service, context, draft_id, request.version, kind)
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
                    event, _ = _reviewed_facts(tx, draft_id, request.version, kind)
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

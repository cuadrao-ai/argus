from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from loguru import logger
from psycopg.types.json import Jsonb

from argus.domain.business.actions import dossier, mutations, plans
from argus.domain.business.actions.facts import facts_of, validate_facts
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
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from argus.domain.business.contracts.facts import (
    BusinessAccountFunding,
    BusinessFacts,
    Known,
    OwnerFunding,
)
from argus.domain.business.purchase_review import declaration_from_facts
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


def _approval_declaration(
    tx: ActionTransaction, event: ImportEvent, facts: BusinessFacts, stale: bool
) -> PurchaseDeclaration | None:
    """The 606 declaration an expense approval writes from its stored facts.

    None when the draft holds a declaration a person saved: theirs wins. A
    ``stale`` one, left by an approval whose money write failed, is rebuilt.
    """

    if (event.resolution.get("business") or {}).get("dgii") and not stale:
        return None
    if not isinstance(facts.kind, Known) or facts.kind.value != "expense":
        return None
    funding = facts.funding.value
    paid_from = (
        "owner_funds"
        if isinstance(funding, OwnerFunding)
        else next(
            account.type
            for account in dossier.record_context(tx).accounts
            if account.id == funding.account_id
        )
    )
    return declaration_from_facts(facts, paid_from)


def _failed_approval_declaration(tx: ActionTransaction, event: ImportEvent) -> bool:
    """Whether an open draft's declaration is the one its last approval built.

    That approval wrote it as the revision at the version its claim took
    (request version + 1); a person's saved declaration is never there.
    """

    dgii = (event.resolution.get("business") or {}).get("dgii")
    pointer = event.resolution.get("approval_receipt")
    if event.state != "open" or not dgii or not pointer:
        return False
    built = tx.rows(
        "select r.after_dgii from public.business_action_receipts a"
        " join public.business_draft_revisions r on r.space_id=a.space_id"
        " and r.draft_id=%s and r.version=(a.command->'request'->>'version')::integer+1"
        " where a.space_id=%s and a.actor_id::text=%s and a.idempotency_key=%s",
        (event.id, tx.context.actor.space_id, pointer["actor_id"], pointer["key"]),
    )
    return bool(built) and built[0]["after_dgii"] == dgii


def _clear_approval_declaration(
    service: BusinessActions, context: ActionContext, draft_id: UUID
) -> None:
    """Clear, on the reopened draft, the declaration a failed approval built.

    A failure here leaves it for the next approval to rebuild and never stops
    the refusal from being stored.
    """

    try:
        with transaction(service.authority, context, "approve") as tx:
            event = tx.imports.event(str(draft_id))
            if not _failed_approval_declaration(tx, event):
                return
            facts = facts_of(event)
            mutations.save_revision(
                tx,
                replace(
                    event,
                    version=event.version + 1,
                    updated_at=datetime.now(timezone.utc),
                ),
                facts,
                facts,
                (),
                tx.authorization.provenance,
                None,
                clear_dgii=True,
            )
    except ActionError as error:
        logger.warning("business.approval_declaration_not_cleared code={}", error.code)


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
                    event, facts = _reviewed_facts(tx, draft_id, request.version, kind)
                except ActionError as error:
                    return plans.finish_receipt(tx, key, error.result)
                stale = _failed_approval_declaration(tx, event)
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
                declared = _approval_declaration(tx, event, facts, stale)
                if declared is None and not stale:
                    tx.imports.put_event(event)
                else:
                    # Revisions are immutable, so the declaration is the approval's
                    # own revision, at the version the accepting record takes.
                    mutations.save_revision(
                        tx,
                        event,
                        facts,
                        facts,
                        (),
                        tx.authorization.provenance,
                        None,
                        dgii=declared,
                        clear_dgii=declared is None,
                    )
                    event = tx.imports.event(str(draft_id))
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
            _clear_approval_declaration(service, context, draft_id)
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

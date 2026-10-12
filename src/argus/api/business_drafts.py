from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from argus.api.business import (
    BusinessContext,
    _captured,
    require_business_surface,
    unavailable_problem,
)
from argus.api.business_spaces import business_spaces
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.ingestion import IngestionContext, require_ingestion_context
from argus.domain.business.actions import BusinessActions
from argus.domain.business.actions.dossier import record_context
from argus.domain.business.actions.receipts import draft_for_receipt
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Refused
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import AccountChoice, RecordContext
from argus.domain.business.scope import BusinessScope
from argus.domain.business.service import BusinessService
from argus.domain.business.transactions import GrantImportStore, transaction
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository


def action_problem(request: Request, refusal: Refused) -> HTTPException:
    status = {
        "not_found": 404,
        "permission_denied": 403,
        "stale_version": 409,
        "idempotency_conflict": 409,
        "invalid_input": 422,
    }[refusal.outcome]
    if refusal.code == "draft_not_prepared":
        status = 409
    return problem(
        request,
        status_code=status,
        code=refusal.code,
        title=refusal.code.replace("_", " ").capitalize(),
        detail=refusal.code,
        headers=NO_STORE,
    )


@dataclass(frozen=True)
class DraftContext:
    service: BusinessActions
    actor_id: UUID


def require_drafts(
    request: Request,
    _surface: Annotated[None, Depends(require_business_surface)],
    ingestion: Annotated[IngestionContext, Depends(require_ingestion_context)],
) -> DraftContext:
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None or not isinstance(ingestion.hub.sink, ReconciliationService):
        raise unavailable_problem(request)
    return DraftContext(
        BusinessActions(pool, ingestion.hub.sink), UUID(ingestion.user_id)
    )


def scoped_legacy(request, documents, hub, user_id, scope):
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        if not isinstance(hub.sink.money.repository, InMemoryFinancialAccountRepository):
            raise unavailable_problem(request)
        account_rows = hub.sink.money.accounts.list_accounts(
            user_id=scope.person_id, scope=scope.owner
        )
        space = business_spaces().open_space(user_id)
        record = RecordContext(
            space_id=scope.owner.space_id,
            space_name=space.name,
            accounts=tuple(
                AccountChoice(
                    id=row.account.id,
                    nickname=row.account.nickname,
                    type=row.account.type,
                    currency=row.account.currency,
                )
                for row in account_rows
            ),
            capabilities={"read", "prepare"},
        )
        return BusinessContext(
            scope, BusinessService(documents, hub.sink, _captured), record
        )
    actions = BusinessActions(pool, hub.sink)
    try:
        receipt_id = request.path_params.get("receipt_id")
        context = (
            actions.context_for_receipt(UUID(user_id), UUID(receipt_id))
            if receipt_id
            else actions.resolve_actor(
                TrustedActor(
                    actor_id=user_id, actor_kind="member", space_id=scope.owner.space_id
                )
            )
        )
        record = actions.record_context(context)
        capability = (
            "read"
            if request.method == "GET"
            else ("approve" if request.url.path.endswith("/confirm") else "prepare")
        )
        if capability not in record.capabilities:
            raise ActionError("permission_denied", "business_permission_denied")
    except ValueError:
        raise action_problem(
            request, Refused(outcome="not_found", code="business_record_not_found")
        ) from None
    except ActionError as error:
        raise action_problem(request, error.result) from None
    imports = ReconciliationService(
        GrantImportStore(actions.authority, context, capability),
        hub.sink.money,
        hub.sink.clock,
        connections=hub.sink.connections,
    )
    scoped_hub, scoped_documents = copy(hub), copy(documents)
    scoped_hub.sink = imports
    scoped_documents.hub = scoped_hub
    return BusinessContext(
        BusinessScope(context.owner_id, context.scope),
        BusinessService(scoped_documents, imports, _captured),
        record,
    )


def require_legacy_receipt_write(context: BusinessContext, receipt_id: str) -> None:
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context, "prepare") as tx:
            draft_id, ambiguous = draft_for_receipt(tx, UUID(receipt_id), None)
            if draft_id is not None or ambiguous:
                raise ActionError("invalid_input", "business_action_required")


def receipt_detail(context: BusinessContext, receipt) -> dict:
    detail = receipt.detail()
    store = context.service.imports.store
    if isinstance(store, GrantImportStore):
        with transaction(store.authority, store.context) as tx:
            legacy_id = UUID(detail["draft_id"]) if detail["draft_id"] else None
            draft_id, ambiguous = draft_for_receipt(tx, UUID(receipt.id), legacy_id)
            detail["draft_id"] = draft_id
            if draft_id is not None and legacy_id is None:
                event = tx.imports.event(str(draft_id))
                detail.update(version=event.version, preparable=False, enterable=False)
                read = (event.resolution.get("business") or {}).get(
                    "read_purchases"
                ) or ()
                if (
                    event.state == "open"
                    and len(read) != 1
                    and (read or detail["amount"] is None)
                ):
                    # Several purchases, or none the read could settle: the one
                    # draft waits for a person, with the read kept as evidence.
                    detail.update(
                        status="needs_attention",
                        attention="several_purchases",
                        error_code="several_purchases_found",
                    )
            detail["record_context"] = record_context(tx).model_dump(mode="json")
            if ambiguous:
                detail.update(
                    status="needs_attention",
                    attention="check_details",
                    error_code="receipt_candidate_ambiguous",
                    preparable=False,
                    enterable=False,
                )
        return detail
    if context.record_context is not None:
        detail["record_context"] = context.record_context.model_dump(mode="json")
    return detail

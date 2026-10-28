from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Request, Response

from argus.api.business_drafts import (
    DraftContext,
    action_problem,
    require_drafts,
    with_source_channels,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    ApproveRefund,
    DecideFiscalInclusion,
    MarkPersonal,
    Refused,
    ResolveDuplicate,
    ReviewDraft,
    SettleRemainder,
)
from argus.domain.business.contracts.dossier import BusinessDossier

router = APIRouter(
    prefix="/business/drafts",
    tags=["business"],
    responses={
        403: {
            "description": "`business_grant_not_live`: the chosen grant (`X-Business-Grant`) is missing, someone else's, revoked or expired; `business_permission_denied`: the live grant does not allow this."
        }
    },
)


def _key(request: Request, value: str | None) -> str:
    from argus.api.routers.financial_accounts import _required_idempotency_key

    return _required_idempotency_key(request, value)


def _email_store_unavailable(request: Request):
    return problem(
        request,
        status_code=503,
        code="email_store_unavailable",
        title="Service Unavailable",
        detail="Email receiving could not be checked. Retry.",
        headers=NO_STORE,
    )


def _email_sender_blocks_approval(request, context, draft_id) -> bool:
    from argus.api.email_intake import email_intake
    from argus.domain.ingestion.email_intake.store import PostgresEmailStore

    runtime = email_intake()
    store = getattr(runtime, "store", None) if runtime is not None else None
    if store is None:
        pool = getattr(getattr(context.service, "authority", None), "pool", None)
        if pool is None:
            return False
        store = PostgresEmailStore(pool)
    try:
        standing = store.email_document_standing(str(context.space_id), str(draft_id))
    except Exception:
        raise _email_store_unavailable(request) from None
    return standing is not None and standing != "authorized"


def _run(request, response, context, draft_id, command=None, key=None):
    response.headers.update(NO_STORE)
    try:
        if isinstance(command, (ApproveExpense, ApproveIncome, ApproveRefund)):
            if _email_sender_blocks_approval(request, context, draft_id):
                raise ActionError("permission_denied", "email_sender_unauthorized")
        actor = context.for_draft(draft_id)
        if command is not None:
            if isinstance(command, ReviewDraft):
                method = context.service.review
            elif isinstance(command, ResolveDuplicate):
                method = context.service.resolve_duplicate
            elif isinstance(command, SettleRemainder):
                method = context.service.settle_remainder
            elif isinstance(command, MarkPersonal):
                method = context.service.mark_personal
            elif isinstance(command, DecideFiscalInclusion):
                method = context.service.decide_606
            elif isinstance(command, ApproveIncome):
                method = context.service.approve_income
            elif isinstance(command, ApproveRefund):
                method = context.service.approve_refund
            else:
                method = context.service.approve
            result = method(actor, draft_id, command, key)
            if isinstance(result, Refused):
                raise action_problem(request, result)
        dossier = context.service.dossier(actor, draft_id)
        return with_source_channels(
            dossier, space_id=str(actor.actor.space_id), owner_id=actor.owner_id
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.get("/{draft_id}/dossier", response_model=BusinessDossier)
def get_dossier(
    request: Request,
    response: Response,
    draft_id: UUID,
    context: Annotated[DraftContext, Depends(require_drafts)],
):
    return _run(request, response, context, draft_id)


@router.patch("/{draft_id}/review", response_model=BusinessDossier)
def review_draft(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: ReviewDraft,
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )


@router.post("/{draft_id}/duplicate-resolution", response_model=BusinessDossier)
def resolve_duplicate(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: ResolveDuplicate,
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )


@router.post("/{draft_id}/personal", response_model=BusinessDossier)
def mark_personal(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: MarkPersonal,
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """The owner or anyone holding prepare marks the receipt as personal or
    takes the mark back; a read-only grant is refused."""

    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )


@router.post("/{draft_id}/fiscal-inclusion", response_model=BusinessDossier)
def decide_fiscal_inclusion(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: DecideFiscalInclusion,
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """A prepare-holder other than the owner answers whether a personal receipt
    with a fiscal number goes into the 606."""

    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )


@router.post("/{draft_id}/approve", response_model=BusinessDossier)
def approve_draft(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: Annotated[ApproveExpense | ApproveIncome | ApproveRefund, Body(discriminator="action")],
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )


@router.post(
    "/{draft_id}/remainder/settle",
    response_model=BusinessDossier,
    responses={
        403: {
            "description": "`business_permission_denied` without approve permission;"
            " `business_human_command_required` for a non-person actor."
        },
        409: {"description": "`stale_version` or `idempotency_conflict`."},
        422: {
            "description": "`business_draft_not_recorded` before approval;"
            " `business_remainder_none` when nothing is left."
        },
    },
)
def settle_remainder(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: SettleRemainder,
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """A person with approval permission settles the read purchases a recorded
    draft does not cover. The dossier then reports 0 unrecorded purchases."""

    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )

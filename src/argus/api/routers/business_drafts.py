from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Request, Response

from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.documents import NO_STORE
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    Refused,
    ReviewDraft,
)
from argus.domain.business.contracts.dossier import BusinessDossier

router = APIRouter(prefix="/business/drafts", tags=["business"])


def _key(request: Request, value: str | None) -> str:
    from argus.api.routers.financial_accounts import _required_idempotency_key

    return _required_idempotency_key(request, value)


def _run(request, response, context, draft_id, command=None, key=None):
    response.headers.update(NO_STORE)
    try:
        actor = context.service.context_for_draft(context.actor_id, draft_id)
        if command is not None:
            if isinstance(command, ReviewDraft):
                method = context.service.review
            elif isinstance(command, ApproveIncome):
                method = context.service.approve_income
            else:
                method = context.service.approve
            result = method(actor, draft_id, command, key)
            if isinstance(result, Refused):
                raise action_problem(request, result)
        return context.service.dossier(actor, draft_id)
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


@router.post("/{draft_id}/approve", response_model=BusinessDossier)
def approve_draft(
    request: Request,
    response: Response,
    draft_id: UUID,
    body: Annotated[ApproveExpense | ApproveIncome, Body(discriminator="action")],
    context: Annotated[DraftContext, Depends(require_drafts)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(
        request, response, context, draft_id, body, _key(request, idempotency_key)
    )

"""Registered-owner debt transport delegates all financial decisions."""

from typing import Any

from fastapi import APIRouter, Request

from argus.api.routers.financial_loop import _key
from argus.api.routers.financial_plan import Context, Key, call
from argus.domain.planning.debt_schemas import (
    DebtCreate,
    DebtEdit,
    DebtLink,
    DebtPaymentPreview,
    DebtPaymentReceipt,
    DebtProgress,
    DebtReceipt,
    DebtRecord,
)
from argus.domain.planning.debts import DebtService
from argus.domain.planning.responses import Candidates
from argus.domain.planning.service import PlanService

router = APIRouter(prefix="/financial-plan/debts", tags=["financial-plan"])


@router.post("", response_model=DebtReceipt, status_code=201)
def create(
    request: Request, context: Context, body: DebtCreate, idempotency_key: Key = None
) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).create(
            context.user_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/{debt_id}", response_model=DebtProgress)
def get(request: Request, context: Context, debt_id: str) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).get(context.user_id, debt_id),
    )


@router.patch("/{debt_id}", response_model=DebtReceipt)
def edit(
    request: Request,
    context: Context,
    debt_id: str,
    body: DebtEdit,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).edit(
            context.user_id, debt_id, body, _key(request, idempotency_key)
        ),
    )


@router.get("/{debt_id}/payments/candidates", response_model=Candidates)
def candidates(request: Request, context: Context, debt_id: str) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).candidates(
            context.user_id, debt_id
        ),
    )


@router.post("/{debt_id}/payments/link", response_model=DebtReceipt)
def link(
    request: Request,
    context: Context,
    debt_id: str,
    body: DebtLink,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).link(
            context.user_id, debt_id, body, _key(request, idempotency_key)
        ),
    )


@router.post("/{debt_id}/payments/preview", response_model=DebtPaymentPreview)
def preview(request: Request, context: Context, debt_id: str, body: DebtRecord) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).preview(
            context.user_id, debt_id, body
        ),
    )


@router.post("/{debt_id}/payments", response_model=DebtPaymentReceipt)
def record(
    request: Request,
    context: Context,
    debt_id: str,
    body: DebtRecord,
    idempotency_key: Key = None,
) -> Any:
    return call(
        request,
        lambda: DebtService(PlanService(context.service)).record(
            context.user_id, debt_id, body, _key(request, idempotency_key)
        ),
    )

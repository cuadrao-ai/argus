"""Household financial adapters over the canonical lifecycle and Recording."""

from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from argus.api.routers.financial_accounts import _required_idempotency_key
from argus.api.routers.households import Context, call
from argus.domain.household import financial_schemas as wire
from argus.domain.household.financial import HouseholdFinancialService
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.money_responses import MoneyPreviewResponse
from argus.domain.recording.money_schemas import (
    DESTINATION_ELIGIBILITY,
    ELIGIBILITY,
    SOURCE_IDS,
)

router = APIRouter(prefix="/api/v1/households", tags=["households"])


@router.get("/{household_id}/snapshot", response_model=wire.Snapshot)
def snapshot(household_id: UUID, request: Request, response: Response, context: Context):
    return call(
        request,
        response,
        lambda: HouseholdFinancialService(context.service).snapshot(
            context.user_id, str(household_id)
        ),
    )


@router.get("/{household_id}/accounts/{account_id}", response_model=wire.SharedDetail)
def detail(
    household_id: UUID,
    account_id: UUID,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: HouseholdFinancialService(context.service).detail(
            context.user_id, str(household_id), str(account_id)
        ),
    )


@router.get(
    "/{household_id}/activities/{activity_id}/history",
    response_model=wire.ActivityHistory,
)
def history(
    household_id: UUID,
    activity_id: UUID,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: HouseholdFinancialService(context.service).history(
            context.user_id, str(household_id), str(activity_id)
        ),
    )


@router.get("/{household_id}/search", response_model=wire.SearchPage)
def search(
    household_id: UUID,
    request: Request,
    response: Response,
    context: Context,
    q: str = Query(default="", max_length=200),
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=30, ge=1, le=100),
):
    return call(
        request,
        response,
        lambda: HouseholdFinancialService(context.service).search(
            context.user_id, str(household_id), q, cursor, limit
        ),
    )


def money(request, response, context, hid, body, activity_id=None, *, write=False):
    key = (
        _required_idempotency_key(request, request.headers.get("Idempotency-Key"))
        if write
        else None
    )
    return call(
        request,
        response,
        lambda: HouseholdFinancialService(context.service).money(
            context.user_id,
            str(hid),
            body.activity,
            str(activity_id) if activity_id else None,
            key,
            membership_id=str(body.membership_id),
            expected_household_version=body.expected_version,
        ),
    )


@router.post("/{household_id}/activities/preview", response_model=MoneyPreviewResponse)
def preview(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.FinancialCommand,
    context: Context,
):
    return money(request, response, context, household_id, body)


@router.post("/{household_id}/activities", response_model=wire.SharedReceipt)
def post(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.FinancialCommand,
    context: Context,
):
    return money(request, response, context, household_id, body, write=True)


@router.post(
    "/{household_id}/activities/{activity_id}/preview",
    response_model=MoneyPreviewResponse,
)
def correction_preview(
    household_id: UUID,
    activity_id: UUID,
    request: Request,
    response: Response,
    body: wire.FinancialCommand,
    context: Context,
):
    return money(request, response, context, household_id, body, activity_id)


@router.patch(
    "/{household_id}/activities/{activity_id}", response_model=wire.SharedReceipt
)
def correct(
    household_id: UUID,
    activity_id: UUID,
    request: Request,
    response: Response,
    body: wire.FinancialCommand,
    context: Context,
):
    return money(request, response, context, household_id, body, activity_id, write=True)


@router.get("/{household_id}/activity-options", response_model=wire.HouseholdMoneyOptions)
def options(household_id: UUID, request: Request, response: Response, context: Context):
    def read():
        snapshot = HouseholdFinancialService(context.service).snapshot(
            context.user_id, str(household_id)
        )
        return {
            "accounts": [
                a["account"] for a in snapshot["accounts"] if a["permission"] == "edit"
            ],
            "eligibility": ELIGIBILITY,
            "destination_eligibility": DESTINATION_ELIGIBILITY,
            "categories": CATEGORY_IDS,
            "sources": SOURCE_IDS,
        }

    return call(request, response, read)

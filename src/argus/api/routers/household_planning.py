"""Thin transport for scoped canonical shared Plan commands."""

from uuid import UUID

from fastapi import APIRouter, Request, Response

from argus.api.routers.financial_accounts import _required_idempotency_key
from argus.api.routers.households import Context, call
from argus.domain.household import planning_schemas as wire
from argus.domain.household.planning import SharedPlanningService

router = APIRouter(prefix="/api/v1/households/{household_id}/plan", tags=["households"])


def service(context):
    return SharedPlanningService(context.service)


def key(request):
    return _required_idempotency_key(request, request.headers.get("Idempotency-Key"))


@router.get("", response_model=wire.PlanSnapshot)
def snapshot(household_id: UUID, request: Request, response: Response, context: Context):
    return call(
        request,
        response,
        lambda: service(context).snapshot(context.user_id, str(household_id)),
    )


@router.get("/options", response_model=wire.PlanOptions)
def options(household_id: UUID, request: Request, response: Response, context: Context):
    return call(
        request,
        response,
        lambda: service(context).options(context.user_id, str(household_id)),
    )


@router.post("/{kind}", response_model=wire.PlanReceipt, status_code=201)
def create(
    household_id: UUID,
    kind: wire.PlanKind,
    body: wire.CreatePlan,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).create(
            context.user_id, str(household_id), kind, body, key(request)
        ),
    )


@router.get("/{kind}/{identifier}", response_model=wire.SharedPlan)
def detail(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).get(
            context.user_id, str(household_id), kind, str(identifier)
        ),
    )


@router.post("/{kind}/{identifier}/share", response_model=wire.PlanReceipt)
def share(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.SharePlan,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).share(
            context.user_id, str(household_id), kind, str(identifier), body, key(request)
        ),
    )


@router.patch("/{kind}/{identifier}", response_model=wire.PlanReceipt)
def edit(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.EditPlan,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).edit(
            context.user_id, str(household_id), kind, str(identifier), body, key(request)
        ),
    )


@router.put("/{kind}/{identifier}/participants", response_model=wire.PlanReceipt)
def participants(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.ReplaceParticipants,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).replace_participants(
            context.user_id, str(household_id), kind, str(identifier), body, key(request)
        ),
    )


@router.get("/{kind}/{identifier}/history", response_model=wire.PlanHistory)
def history(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).history(
            context.user_id, str(household_id), kind, str(identifier)
        ),
    )


@router.get(
    "/{kind}/{identifier}/contributions/candidates",
    response_model=wire.ContributionCandidates,
)
def candidates(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).candidates(
            context.user_id, str(household_id), kind, str(identifier)
        ),
    )


@router.post(
    "/{kind}/{identifier}/contributions/preview", response_model=wire.ContributionPreview
)
def preview(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.ContributionRecord,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).money(
            context.user_id, str(household_id), kind, str(identifier), body
        ),
    )


@router.post(
    "/{kind}/{identifier}/contributions", response_model=wire.PlanReceipt, status_code=201
)
def record(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.ContributionRecord,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).money(
            context.user_id, str(household_id), kind, str(identifier), body, key(request)
        ),
    )


@router.post("/{kind}/{identifier}/contributions/link", response_model=wire.PlanReceipt)
def link(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.ContributionLink,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).link(
            context.user_id, str(household_id), kind, str(identifier), body, key(request)
        ),
    )


@router.post(
    "/{kind}/{identifier}/contributions/{claim_id}/release",
    response_model=wire.PlanReceipt,
)
def release(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    claim_id: UUID,
    body: wire.PlanCommand,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).release(
            context.user_id,
            str(household_id),
            kind,
            str(identifier),
            str(claim_id),
            body,
            key(request),
        ),
    )


@router.post(
    "/{kind}/{identifier}/contributions/{claim_id}/preview",
    response_model=wire.ContributionPreview,
)
def correction_preview(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    claim_id: UUID,
    body: wire.ContributionCorrection,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).money(
            context.user_id,
            str(household_id),
            kind,
            str(identifier),
            body,
            cid=str(claim_id),
        ),
    )


@router.patch(
    "/{kind}/{identifier}/contributions/{claim_id}", response_model=wire.PlanReceipt
)
def correct(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    claim_id: UUID,
    body: wire.ContributionCorrection,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).money(
            context.user_id,
            str(household_id),
            kind,
            str(identifier),
            body,
            key(request),
            cid=str(claim_id),
        ),
    )


@router.put("/{kind}/{identifier}/allocations", response_model=wire.PlanReceipt)
def allocations(
    household_id: UUID,
    kind: wire.PlanKind,
    identifier: UUID,
    body: wire.AllocationWrite,
    request: Request,
    response: Response,
    context: Context,
):
    return call(
        request,
        response,
        lambda: service(context).allocate(
            context.user_id, str(household_id), kind, str(identifier), body, key(request)
        ),
    )

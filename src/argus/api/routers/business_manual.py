from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.business_manual_schemas import ManualCapturePage
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.routers.business_drafts import _key
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import CaptureNote, OutcomeUnknown, Refused
from argus.domain.business.contracts.dossier import BusinessDossier

router = APIRouter(
    prefix="/business/captures",
    tags=["business"],
    responses={
        403: {
            "description": "`business_grant_not_live`: the chosen grant (`X-Business-Grant`) is missing, someone else's, revoked or expired; `business_permission_denied`: the live grant does not allow this."
        }
    },
)


def _owner(
    request: Request, context: DraftContext, person: BusinessPerson
) -> ActionContext:
    """The Business the caller is working in: a chosen client's, else their own."""

    return context.for_space(request, person.spaces)


@router.post("", response_model=BusinessDossier)
def capture_note(
    request: Request,
    response: Response,
    body: CaptureNote,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    response.headers.update(NO_STORE)
    key = _key(request, idempotency_key)
    try:
        actor = (
            _owner(request, context, person)
            if body.draft is None
            else context.for_draft(body.draft.draft_id)
        )
        result = context.service.capture(actor, body, key)
        if isinstance(result, Refused):
            raise action_problem(request, result)
        if isinstance(result, OutcomeUnknown):
            raise problem(
                request,
                status_code=409,
                code=result.code,
                title="Capture outcome unknown",
                detail=result.code,
                headers=NO_STORE,
            )
        assert result.draft_id is not None
        return context.service.dossier(actor, result.draft_id)
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.get("", response_model=ManualCapturePage)
def list_captures(
    request: Request,
    response: Response,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    q: Annotated[str, Query(max_length=200, pattern=r"^[^\x00]*$")] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    view: Literal["inbox", "all"] = "all",
):
    response.headers.update(NO_STORE)
    try:
        actor = _owner(request, context, person)
        return context.service.captures_page(actor, query=q, limit=limit, view=view)
    except ActionError as error:
        raise action_problem(request, error.result) from None

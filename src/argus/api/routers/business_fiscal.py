from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response

from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.documents import NO_STORE
from argus.api.routers.business_drafts import _key
from argus.api.routers.business_export import ExportRoute
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.dgii import (
    FiscalField,
    FiscalProfile,
    FiscalProfileSaved,
    RegistryAnswer,
)
from argus.domain.business.dgii_form import input_fields
from argus.domain.business.fiscal_profile import (
    FiscalProfileInput,
    LegalNameInput,
    RegistryLookupInput,
    accepted_change,
    accepted_legal_name,
    accepted_query,
    lookup_registry,
    read_profile,
    set_legal_name,
    set_profile,
)

router = APIRouter(
    prefix="/business/fiscal-profile", tags=["business"], route_class=ExportRoute
)


@router.get(
    "/fields", response_model=dict[Literal["606", "607"], tuple[FiscalField, ...]]
)
def fiscal_fields(person: Annotated[BusinessPerson, Depends(require_business_person)]):
    return {form: input_fields(form) for form in ("606", "607")}


@router.get("", response_model=FiscalProfile)
def fiscal_profile(
    request: Request,
    response: Response,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    draft_id: UUID | None = None,
):
    response.headers.update(NO_STORE)
    try:
        actor = (
            context.for_draft(draft_id)
            if draft_id
            else context.for_space(request, person.spaces)
        )
        return read_profile(context.service.authority, actor)
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.patch("", response_model=FiscalProfileSaved)
def change_fiscal_profile(
    request: Request,
    response: Response,
    body: FiscalProfileInput,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    response.headers.update(NO_STORE)
    try:
        actor = context.for_space(request, person.spaces)
        return set_profile(
            context.service.authority,
            actor,
            accepted_change(body),
            _key(request, idempotency_key),
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.post("/registry", response_model=RegistryAnswer)
def registry_lookup(
    request: Request,
    response: Response,
    body: RegistryLookupInput,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
):
    response.headers.update(NO_STORE)
    try:
        actor = context.for_space(request, person.spaces)
        return lookup_registry(
            context.service.authority, actor, accepted_query(body)
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None


@router.put("/legal-name", response_model=FiscalProfile)
def change_legal_name(
    request: Request,
    response: Response,
    body: LegalNameInput,
    context: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    response.headers.update(NO_STORE)
    try:
        actor = context.for_space(request, person.spaces)
        return set_legal_name(
            context.service.authority,
            actor,
            accepted_legal_name(body),
            _key(request, idempotency_key),
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None

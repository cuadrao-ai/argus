"""``GET /business/setup``: the selected Business's setup steps for Inicio's
setup guide. Setup is configuration, so only someone who may manage the
Business reads it."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict

from argus.api.business import (
    BusinessContext,
    BusinessPerson,
    manager_only,
    require_business_person,
    require_business_workspace,
)
from argus.api.business_drafts import DraftContext, action_problem, require_drafts
from argus.api.business_invite_delivery import invitations_available
from argus.api.business_spaces import business_access
from argus.api.routers.email_intake import receiving_address_ready
from argus.api.whatsapp import whatsapp_receiving_available, whatsapp_runtime
from argus.domain.business.authority import ActionError
from argus.domain.business.fiscal_profile import read_profile
from argus.domain.business.setup import SetupFacts, SetupStepKey, setup_steps
from argus.domain.business.space_name import given_name

router = APIRouter()


class BusinessSetupStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: SetupStepKey
    required: bool
    done: bool


class BusinessSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: In display order. A step whose feature is off on this server is absent;
    #: setup is complete when every required step is done.
    steps: list[BusinessSetupStep]


def _fiscal_identity(request: Request, drafts: DraftContext, person: BusinessPerson) -> bool:
    try:
        profile = read_profile(
            drafts.service.authority, drafts.for_space(request, person.spaces)
        )
    except ActionError as error:
        raise action_problem(request, error.result) from None
    return profile["tax_id"] is not None and given_name(profile["name"]) is not None


def _receipt_reading(context: BusinessContext) -> bool | None:
    permission = context.service.documents.business_receipt_consent
    if permission is None:
        return None
    state = permission.status(context.scope.owner.space_id, context.scope.person_id)
    return bool(state["enabled"]) if state["available"] else None


def _first_document(context: BusinessContext) -> bool:
    # A received document is a saved source on this Business, however it arrived.
    connections = context.service.documents.hub.connections.list(
        user_id=context.scope.person_id, scope=context.scope.owner
    )
    return any(
        connection.source == "statement" and connection.status != "disconnected"
        for connection in connections
    )


def _team(context: BusinessContext) -> bool | None:
    store = business_access()
    if store is None or not invitations_available():
        return None
    found = store.list(context.scope.owner.space_id, context.scope.acting_person_id)
    # An invitation counts once it is created, accepted or not; the owner's own grant does not.
    return bool(found.invites) or any(not grant.owner for grant in found.grants)


def _whatsapp(context: BusinessContext) -> bool | None:
    runtime = whatsapp_runtime()
    if runtime is None or not whatsapp_receiving_available(context.scope):
        return None
    link = runtime.intake.store.destination_link(
        destination_owner_id=context.scope.acting_person_id
    )
    return link is not None


def _facts(
    request: Request,
    context: BusinessContext,
    drafts: DraftContext,
    person: BusinessPerson,
) -> SetupFacts:
    return SetupFacts(
        fiscal_identity=_fiscal_identity(request, drafts, person),
        receiving_address=receiving_address_ready(context.scope.owner.space_id),
        receipt_reading=_receipt_reading(context),
        first_document=_first_document(context),
        team=_team(context),
        whatsapp=_whatsapp(context),
    )


@router.get("/setup", response_model=BusinessSetup)
async def get_setup(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_workspace)],
    drafts: Annotated[DraftContext, Depends(require_drafts)],
    person: Annotated[BusinessPerson, Depends(require_business_person)],
) -> dict[str, Any]:
    manager_only(request, context)
    facts = await run_in_threadpool(_facts, request, context, drafts, person)
    return {"steps": setup_steps(facts)}

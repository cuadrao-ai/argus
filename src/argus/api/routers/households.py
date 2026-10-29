"""The canonical Household lifecycle and explicit named-member consent API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from argus.api import invite_limits
from argus.api.households import (
    HouseholdsContext,
    InvitesContext,
    domain_problem,
    require_households_context,
    require_invites_context,
)
from argus.api.routers.financial_accounts import _required_idempotency_key
from argus.domain.backtest_admission import canonical_hash
from argus.domain.household import invite_schemas as invites
from argus.domain.household import schemas as wire

router = APIRouter(prefix="/api/v1", tags=["households"])
Context = Annotated[HouseholdsContext, Depends(require_households_context)]
Invites = Annotated[InvitesContext, Depends(require_invites_context)]


class HouseholdListResponse(BaseModel):
    households: list[wire.HouseholdRecord]


class SharedAccountListResponse(BaseModel):
    accounts: list[wire.SharedAccountView]


def call(request, response, action):
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except Exception as error:
        raise domain_problem(request, error) from None


def mutate(request, response, context, body, hid, action):
    key = _required_idempotency_key(request, request.headers.get("Idempotency-Key"))
    return call(
        request,
        response,
        lambda: context.service.execute(
            actor=context.user_id,
            operation=request.method + ":" + request.url.path,
            key=key,
            body=body.model_dump(mode="json"),
            household_id=str(hid) if hid else None,
            action=action,
        ),
    )


@router.post("/households", response_model=wire.CommandResult, status_code=201)
def create_household(
    request: Request,
    response: Response,
    body: wire.CreateHouseholdRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        None,
        lambda: context.service.create(user_id=context.user_id, request=body),
    )


@router.get("/households", response_model=HouseholdListResponse)
def list_households(request: Request, response: Response, context: Context):
    return call(
        request,
        response,
        lambda: HouseholdListResponse(
            households=context.service.list(user_id=context.user_id)
        ),
    )


@router.get("/households/{household_id}", response_model=wire.HouseholdRecord)
def get_household(
    household_id: UUID, request: Request, response: Response, context: Context
):
    return call(
        request,
        response,
        lambda: context.service.get(
            user_id=context.user_id, household_id=str(household_id)
        ),
    )


@router.post(
    "/households/{household_id}/invitations",
    response_model=wire.CommandResult,
    status_code=201,
)
def create_invitation(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.VersionRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.invite(
            user_id=context.user_id, household_id=str(household_id)
        ),
    )


@router.post(
    "/households/{household_id}/invitations/{invitation_id}/revoke",
    response_model=wire.CommandResult,
)
def revoke_invitation(
    household_id: UUID,
    invitation_id: UUID,
    request: Request,
    response: Response,
    body: wire.VersionRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.revoke_invitation(
            user_id=context.user_id,
            household_id=str(household_id),
            invitation_id=str(invitation_id),
        ),
    )


@router.post("/household-invitations/preview", response_model=wire.InvitationPreview)
def preview_invitation(
    request: Request,
    response: Response,
    body: wire.AcceptInvitationRequest,
    context: Context,
):
    with invite_limits.attempt(request, context.user_id) as lookup:
        return call(
            request,
            response,
            lookup.wrap(
                lambda: context.service.preview_invitation(
                    user_id=context.user_id, token=body.token, code=body.code
                )
            ),
        )


@router.post("/household-invitations/accept", response_model=wire.CommandResult)
def accept_invitation(
    request: Request,
    response: Response,
    body: wire.AcceptInvitationRequest,
    context: Context,
):
    with invite_limits.attempt(request, context.user_id) as lookup:
        return mutate(
            request,
            response,
            context,
            body,
            None,
            lookup.wrap(
                lambda: context.service.accept(
                    user_id=context.user_id,
                    token=body.token,
                    code=body.code,
                    display_name=body.display_name,
                )
            ),
        )


@router.post("/households/{household_id}/leave", response_model=wire.CommandResult)
def leave_household(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.VersionRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.leave(
            user_id=context.user_id, household_id=str(household_id)
        ),
    )


@router.post(
    "/households/{household_id}/members/{member_user_id}/remove",
    response_model=wire.CommandResult,
)
def remove_member(
    household_id: UUID,
    member_user_id: UUID,
    request: Request,
    response: Response,
    body: wire.VersionRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.remove_member(
            user_id=context.user_id,
            household_id=str(household_id),
            member_user_id=str(member_user_id),
        ),
    )


@router.post(
    "/households/{household_id}/transfer-admin", response_model=wire.CommandResult
)
def transfer_admin(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.TransferAdminRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.transfer_admin(
            user_id=context.user_id,
            household_id=str(household_id),
            new_admin_user_id=body.user_id,
        ),
    )


@router.post("/households/{household_id}/close", response_model=wire.CommandResult)
def close_household(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.VersionRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.close(
            user_id=context.user_id, household_id=str(household_id)
        ),
    )


@router.post(
    "/households/{household_id}/account-grants",
    response_model=wire.CommandResult,
    status_code=201,
)
def create_account_grant(
    household_id: UUID,
    request: Request,
    response: Response,
    body: wire.CreateAccountGrantRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.create_grant(
            user_id=context.user_id, household_id=str(household_id), request=body
        ),
    )


@router.patch(
    "/households/{household_id}/account-grants/{grant_id}",
    response_model=wire.CommandResult,
)
def update_account_grant(
    household_id: UUID,
    grant_id: UUID,
    request: Request,
    response: Response,
    body: wire.UpdateAccountGrantRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.update_grant(
            user_id=context.user_id,
            household_id=str(household_id),
            grant_id=str(grant_id),
            request=body,
        ),
    )


@router.delete(
    "/households/{household_id}/account-grants/{grant_id}",
    response_model=wire.CommandResult,
)
def revoke_account_grant(
    household_id: UUID,
    grant_id: UUID,
    request: Request,
    response: Response,
    body: wire.VersionRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.revoke_grant(
            user_id=context.user_id,
            household_id=str(household_id),
            grant_id=str(grant_id),
        ),
    )


@router.put(
    "/households/{household_id}/accounts/{account_id}/grants",
    response_model=wire.CommandResult,
)
def replace_account_grants(
    household_id: UUID,
    account_id: UUID,
    request: Request,
    response: Response,
    body: wire.ReplaceAccountGrantsRequest,
    context: Context,
):
    return mutate(
        request,
        response,
        context,
        body,
        household_id,
        lambda: context.service.replace_grants(
            user_id=context.user_id,
            household_id=str(household_id),
            account_id=str(account_id),
            recipients=body.recipients,
        ),
    )


@router.get(
    "/households/{household_id}/accounts", response_model=SharedAccountListResponse
)
def list_shared_accounts(
    household_id: UUID, request: Request, response: Response, context: Context
):
    return call(
        request,
        response,
        lambda: SharedAccountListResponse(
            accounts=context.service.list_shared_accounts(
                user_id=context.user_id, household_id=str(household_id)
            )
        ),
    )


# Beta invites, the founder group link and the in-app code gate. Default-off
# behind CUADRAO_BETA_INVITES_ENABLED; the gate itself is CUADRAO_BETA_INVITE_GATE_ENABLED.


def keyed(request, body):
    key = _required_idempotency_key(request, request.headers.get("Idempotency-Key"))
    return key, canonical_hash(body.model_dump(mode="json"))


@router.get("/invites/access", response_model=invites.BetaAccess)
def beta_access(request: Request, response: Response, context: Invites):
    return call(request, response, lambda: context.store.access(user_id=context.user_id))


@router.get("/invites", response_model=invites.SentInvitesResponse)
def list_sent_invites(request: Request, response: Response, context: Invites):
    return call(request, response, lambda: context.store.sent(user_id=context.user_id))


@router.post(
    "/invites", response_model=invites.BetaInviteCreatedResponse, status_code=201
)
def create_beta_invite(
    request: Request,
    response: Response,
    body: invites.CreateBetaInviteRequest,
    context: Invites,
):
    key, digest = keyed(request, body)
    return call(
        request,
        response,
        lambda: context.store.create_beta(
            user_id=context.user_id, key=key, request_hash=digest
        ),
    )


@router.post("/invites/{invitation_id}/revoke", status_code=204)
def revoke_beta_invite(
    invitation_id: UUID, request: Request, response: Response, context: Invites
):
    call(
        request,
        response,
        lambda: context.store.revoke(
            user_id=context.user_id, invitation_id=str(invitation_id)
        ),
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/invites/preview", response_model=invites.InvitePreview)
def preview_invite(
    request: Request,
    response: Response,
    body: invites.InviteSecretRequest,
    context: Invites,
):
    with invite_limits.attempt(request, context.user_id) as lookup:
        return call(
            request,
            response,
            lookup.wrap(lambda: context.store.preview(token=body.token, code=body.code)),
        )


@router.post("/invites/redeem", response_model=invites.RedeemResult)
def redeem_invite(
    request: Request,
    response: Response,
    body: invites.InviteSecretRequest,
    context: Invites,
):
    with invite_limits.attempt(request, context.user_id) as lookup:
        return call(
            request,
            response,
            lookup.wrap(
                lambda: context.store.redeem(
                    user_id=context.user_id, token=body.token, code=body.code
                )
            ),
        )


@router.post(
    "/invites/group-links",
    response_model=invites.BetaInviteCreatedResponse,
    status_code=201,
)
def create_group_link(
    request: Request,
    response: Response,
    body: invites.CreateGroupLinkRequest,
    context: Invites,
):
    key, digest = keyed(request, body)
    return call(
        request,
        response,
        lambda: context.store.create_group_link(
            user_id=context.user_id, request=body, key=key, request_hash=digest
        ),
    )


@router.get("/invites/group-links", response_model=invites.GroupLinkListResponse)
def list_group_links(request: Request, response: Response, context: Invites):
    return call(
        request,
        response,
        lambda: invites.GroupLinkListResponse(
            links=context.store.group_links(user_id=context.user_id)
        ),
    )


@router.post("/invites/group-links/{link_id}/revoke", status_code=204)
def revoke_group_link(
    link_id: UUID, request: Request, response: Response, context: Invites
):
    call(
        request,
        response,
        lambda: context.store.revoke_group_link(
            user_id=context.user_id, link_id=str(link_id)
        ),
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/invites/quota-grants", response_model=invites.QuotaGrantResult, status_code=201
)
def grant_invite_quota(
    request: Request,
    response: Response,
    body: invites.QuotaGrantRequest,
    context: Invites,
):
    key, digest = keyed(request, body)
    return call(
        request,
        response,
        lambda: context.store.grant_quota(
            user_id=context.user_id, request=body, key=key, request_hash=digest
        ),
    )


@router.get("/invites/network", response_model=invites.NetworkNumbers)
def invite_network_numbers(request: Request, response: Response, context: Invites):
    return call(request, response, lambda: context.store.network(user_id=context.user_id))

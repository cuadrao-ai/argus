"""In-app account deletion (Lane 6).

``POST /api/v1/account/delete`` runs the whole deletion command for the signed-in
person. It is off unless ``ARGUS_ACCOUNT_DELETION_ENABLED`` is on, and while off
it answers 404 before any authentication. The user id comes only from the
verified session, never from the request body. A guest session is deleted
the same way. A person whose run is in flight (locked out of every other
route) may call it again to resume their own run (``account_deletion_auth``).
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from argus.api import state as api_state
from argus.api.account_deletion_auth import deletion_requester
from argus.api.dependencies import problem
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.schemas import User
from argus.domain.account_deletion.apple import AccountDeletionAdmissionError
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionRejected,
    AccountDeletionService,
)
from argus.domain.apple_sign_in.client import MAX_CODE_LENGTH

FLAG = "ARGUS_ACCOUNT_DELETION_ENABLED"

router = APIRouter(prefix="/api/v1", tags=["account"])

# Per account: a retry loop can't hammer the Admin API or the providers. A
# guest create-then-delete loop makes a new account each time, so it is bounded
# where guests are made (captcha and the per-visitor guest limits), not here.
_per_account = SlidingWindowLimiter()
_PER_ACCOUNT = (6, 60)
_INCOMPLETE_RETRY_SECONDS = 5


def account_deletion_enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


class AccountDeletionRequest(BaseModel):
    # A JSON body is required, so a cross-site form post can't reach this route.
    # Nothing else is accepted: whose account it is comes from the session.
    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True]
    apple_authorization_code: str | None = Field(
        default=None, min_length=1, max_length=MAX_CODE_LENGTH, pattern=r"^[\x00-\x7f]+$"
    )


class AccountDeletionResponse(BaseModel):
    # done: everything is deleted and every third party settled.
    # in_progress (202): the run is open and the account is locked (signed
    # out, its tokens refused everywhere but here), but a step hasn't finished
    # (``pending``: apple, gmail, plaid, analytics, storage; empty when another request
    # holds the run or the data step must be retried). A retry of this route
    # or the operator-run sweep resumes it.
    status: Literal["done", "in_progress"]
    pending: list[str]


def account_deletion_service() -> AccountDeletionService | None:
    """Built from deletion's own Postgres pool and the Admin API client, not
    from another feature's runtime service; None without either."""

    from argus.api.account_deletion_runtime import build_service
    from argus.api.apple_sign_in import apple_credentials_service
    from argus.api.ingestion import ingestion_hub

    gateway = api_state.supabase_gateway
    if (
        api_state.PERSISTENCE_MODE != "supabase"
        or not api_state.DATABASE_URL
        or gateway is None
    ):
        return None
    return build_service(
        database_url=api_state.DATABASE_URL,
        supabase_client=gateway.client,
        # The running surfaces when they're up; revoke-only stand-ins when not.
        revoker=ingestion_hub(),
        apple=apple_credentials_service(),
    )


def _deleting_user(request: Request) -> User:
    # The flag is checked before any session check, so a disabled route says
    # nothing about sessions.
    if not account_deletion_enabled():
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="Not found.",
        )
    user = deletion_requester(request)
    limit, seconds = _PER_ACCOUNT
    retry = _per_account.record_or_retry_after(
        keys=(user.id,), limit=limit, window_seconds=seconds
    )
    if retry is not None:
        raise problem(
            request,
            status_code=429,
            code="too_many_requests",
            title="Too Many Requests",
            detail="Wait a moment before trying again.",
            headers={"Retry-After": str(retry)},
        )
    return user


def _problem(description: str) -> dict:  # type: ignore[type-arg]
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        },
    }


# The same POST starts a deletion and resumes one in flight (a locked person
# retrying), so one list covers both (Priya #801 note 7).
_RESPONSES: dict = {  # type: ignore[type-arg]
    202: {
        "model": AccountDeletionResponse,
        "description": (
            "`in_progress`: the run is open and the account locked, but a step "
            "hasn't finished (`pending`). A retry of this route, or the "
            "operator-run sweep, resumes it."
        ),
    },
    400: _problem(
        "`apple_authorization_invalid`: fresh Apple code is invalid or consumed; no run started."
    ),
    409: _problem(
        "`apple_reauthorization_required` or `apple_identity_mismatch`: fresh authorization is required before deletion starts."
    ),
    401: _problem(
        "No valid session: missing or invalid token, an ended session, or on "
        "resume a token that doesn't name the person's own live session (or "
        "lacks `sub`, `exp` or `session_id`)."
    ),
    403: _problem(
        "`account_deletion_not_allowed`: the account can't be deleted here "
        "(an account placeholder)."
    ),
    404: _problem(
        "`not_found`: `ARGUS_ACCOUNT_DELETION_ENABLED` is off; answered before "
        "any session check."
    ),
    429: _problem(
        "`too_many_requests`: six requests per account per minute; see Retry-After."
    ),
    # 503 (account_deletion_incomplete, account_deletion_unavailable and the
    # shared session-verification one) is declared in openapi_compat, which
    # rewrites every authenticated operation's 503.
}


@router.post(
    "/account/delete",
    response_model=AccountDeletionResponse,
    responses=_RESPONSES,
)
def delete_account(
    payload: AccountDeletionRequest,
    request: Request,
    response: Response,
    user: User = Depends(_deleting_user),  # noqa: B008
) -> AccountDeletionResponse:
    # A guest session is deleted by the same command (Lane 6 acceptance).
    try:
        service = account_deletion_service()
    except Exception:
        service = None
    if service is None:
        started = getattr(request.state, "account_deletion_started", False)
        raise problem(
            request,
            status_code=503,
            code=(
                "account_deletion_incomplete"
                if started
                else "account_deletion_unavailable"
            ),
            title="Account Deletion Unavailable",
            detail="Account deletion is not available right now.",
            headers={"Retry-After": str(_INCOMPLETE_RETRY_SECONDS)} if started else None,
        )
    try:
        outcome = service.delete_account(
            user_id=user.id,
            **(
                {"apple_authorization_code": payload.apple_authorization_code}
                if payload.apple_authorization_code is not None
                else {}
            ),
        )
    except AccountDeletionAdmissionError as exc:
        raise problem(
            request,
            status_code=exc.status,
            code=exc.code,
            title="Account Deletion Not Started",
            detail="Authorize Apple again to delete this account."
            if exc.status == 409
            else "Deletion could not start. Please try again.",
        ) from None
    except AccountDeletionRejected as exc:
        if str(exc) == "unknown_user":
            # The session was verified a moment ago, so the person existed:
            # another request finished the run in between. Done.
            return AccountDeletionResponse(status="done", pending=[])
        raise problem(
            request,
            status_code=403,
            code="account_deletion_not_allowed",
            title="Not Allowed",
            detail="This account can't be deleted here.",
        ) from None
    except AccountDeletionIncomplete as exc:
        # Accepted, not failed: the account is locked, and a retry or the
        # operator-run sweep finishes it. ``in_progress`` from the service
        # means another request holds the run right now.
        response.status_code = 202
        return AccountDeletionResponse(status="in_progress", pending=exc.pending)
    except Exception as exc:
        # No user id in logs: the run is keyed on a hash for that reason.
        logger.error("Account deletion failed: {}", type(exc).__name__)
        raise problem(
            request,
            status_code=503,
            code="account_deletion_incomplete",
            title="Account Deletion Incomplete",
            # The run may be open and the account locked; a retry of this
            # route resumes it (the web treats this as in progress).
            detail="Deletion did not finish. Try again to finish it.",
            headers={"Retry-After": str(_INCOMPLETE_RETRY_SECONDS)},
        ) from None
    return AccountDeletionResponse(status="done", pending=sorted(outcome.pending))

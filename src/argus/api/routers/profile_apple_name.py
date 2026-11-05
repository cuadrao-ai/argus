from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException

from argus.api import state as api_state
from argus.api.account_deletion_runtime import deletion_pool
from argus.api.apple_sign_in import capture_enabled
from argus.api.dependencies import current_user, problem, require_account_capability
from argus.api.guest_access import account_context
from argus.api.routers import profile
from argus.api.schemas import User, UserResponse
from argus.domain.apple_sign_in.credentials import AppleIdentityMissing
from argus.domain.apple_sign_in.name import (
    AppleNameAccountUnavailable,
    initialize_apple_display_name,
)

router = APIRouter(prefix="/api/v1", tags=["profile"])


class AppleDisplayNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


@router.post("/me/apple-name", response_model=UserResponse)
def initialize_apple_name(
    body: AppleDisplayNameRequest,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UserResponse:
    if not capture_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    require_account_capability(
        request,
        "can_manage_account",
        detail="Sign in to manage a permanent profile.",
        reason="manage_account",
    )
    if not api_state.DATABASE_URL:
        raise problem(
            request,
            status_code=503,
            code="apple_name_unavailable",
            title="Name Save Unavailable",
            detail="The name could not be saved.",
        )
    try:
        identity = profile._apple_identity(request, user.id)
        row = initialize_apple_display_name(
            deletion_pool(api_state.DATABASE_URL),
            user_id=user.id,
            display_name=body.display_name,
        )
        saved = User.model_validate({**row, "id": str(row["id"])})
    except AppleIdentityMissing:
        raise problem(
            request,
            status_code=409,
            code="apple_identity_missing",
            title="Apple Identity Missing",
            detail="This account has no Apple identity.",
        ) from None
    except AppleNameAccountUnavailable:
        raise problem(
            request,
            status_code=403,
            code="account_unavailable",
            title="Account Unavailable",
            detail="This account cannot save a name.",
        ) from None
    except Exception:
        raise problem(
            request,
            status_code=503,
            code="apple_name_unavailable",
            title="Name Save Unavailable",
            detail="The name could not be saved.",
        ) from None
    return profile._user_response(saved, account_context(request), identity)

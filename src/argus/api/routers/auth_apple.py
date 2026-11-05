"""Sign in with Apple token capture: ``POST /api/v1/auth/apple/authorization-code``.

The native app calls this right after it signs in through Supabase Auth with
Apple's identity token, sending Apple's one-time authorization code under the
new session. The user id comes only from that verified session. The API checks
that the code's Apple subject is the Apple identity Supabase linked to this
user, then keeps only the sealed refresh token for the account-deletion revoke
(App Store Review Guideline 5.1.1(v)). No response carries a token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from argus.api.apple_sign_in import apple_credentials_service, capture_enabled
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.schemas import User
from argus.domain.apple_sign_in.client import MAX_CODE_LENGTH, AppleError
from argus.domain.apple_sign_in.credentials import (
    AppleCaptureNotStored,
    AppleCredentialService,
    AppleIdentityMismatch,
    AppleIdentityMissing,
)

router = APIRouter(prefix="/api/v1", tags=["auth"])

CAPTURE_ATTEMPT_LIMIT = 5
_CAPTURE_WINDOW_SECONDS = 10 * 60
_LIMITER = SlidingWindowLimiter()


def reset_apple_capture_limiter_for_tests() -> None:
    _LIMITER.reset()


class AppleAuthorizationCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_code: str = Field(min_length=1, max_length=MAX_CODE_LENGTH)


def require_apple_capture_surface(request: Request) -> AppleCredentialService:
    if not capture_enabled():
        # Backstop only: AppleCaptureFlagGateMiddleware answers first, with
        # this same plain 404 of an unmatched route.
        raise StarletteHTTPException(status_code=404, detail="Not Found")
    service = apple_credentials_service()
    if service is None:
        raise problem(
            request,
            status_code=503,
            code="apple_sign_in_unconfigured",
            title="Apple Sign-In Unavailable",
            detail="Apple token capture is not configured.",
        )
    return service


def _problem(description: str) -> dict:  # type: ignore[type-arg]
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        },
    }


@router.post(
    "/auth/apple/authorization-code",
    status_code=204,
    responses={
        400: _problem(
            "`apple_authorization_invalid`: Apple says the code expired, was used, or is malformed."
        ),
        401: _problem("The session is invalid or expired."),
        403: _problem("Registered-account or private-alpha access is required."),
        503: _problem(
            "`apple_sign_in_unconfigured` or `apple_sign_in_unavailable`: "
            "identity could not be verified, exchange failed, or capture was not stored."
        ),
        404: {
            "description": (
                'Capture is off: `{"detail": "Not Found"}`, the plain answer of '
                "a route that doesn't exist, before the body or session is read."
            )
        },
        409: _problem(
            "`apple_identity_missing`: the account has no Apple identity. "
            "`apple_identity_mismatch`: the code belongs to another Apple ID; "
            "nothing is stored and the exchanged token is revoked at Apple."
        ),
        429: _problem("`too_many_requests`: five attempts per user per ten minutes."),
    },
)
def capture_apple_authorization_code(
    request: Request,
    body: AppleAuthorizationCodeRequest,
    service: AppleCredentialService = Depends(require_apple_capture_surface),  # noqa: B008
    user: User = Depends(current_user),  # noqa: B008
) -> Response:
    if account_context(request).kind != "registered":
        raise problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Apple token capture needs a registered account.",
        )
    retry_after = _LIMITER.record_or_retry_after(
        keys=(f"apple_capture:user:{user.id}",),
        limit=CAPTURE_ATTEMPT_LIMIT,
        window_seconds=_CAPTURE_WINDOW_SECONDS,
    )
    if retry_after is not None:
        raise problem(
            request,
            status_code=429,
            code="too_many_requests",
            title="Too Many Requests",
            detail="Too many Apple sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        service.capture(
            user_id=user.id,
            authorization_code=body.authorization_code,
        )
    except AppleIdentityMissing:
        raise problem(
            request,
            status_code=409,
            code="apple_identity_missing",
            title="Apple Identity Missing",
            detail="This account is not signed in with Apple.",
        ) from None
    except AppleIdentityMismatch:
        raise problem(
            request,
            status_code=409,
            code="apple_identity_mismatch",
            title="Apple Identity Mismatch",
            detail="This Apple authorization belongs to a different Apple ID.",
        ) from None
    except AppleCaptureNotStored as exc:
        logger.warning("Apple token capture not stored", error=str(exc))
        raise problem(
            request,
            status_code=503,
            code="apple_sign_in_unavailable",
            title="Apple Sign-In Unavailable",
            detail="The Apple authorization could not be saved. Please try again.",
        ) from None
    except AppleError as exc:
        if exc.invalid_grant or exc.reason == "malformed_code":
            raise problem(
                request,
                status_code=400,
                code="apple_authorization_invalid",
                title="Apple Authorization Invalid",
                detail="This Apple authorization expired or was already used.",
            ) from None
        logger.warning(
            "Apple token exchange failed", status=exc.status, reason=exc.reason
        )
        raise problem(
            request,
            status_code=503,
            code="apple_sign_in_unavailable",
            title="Apple Sign-In Unavailable",
            detail="Apple could not be reached. Please try again.",
        ) from None
    return Response(status_code=204)

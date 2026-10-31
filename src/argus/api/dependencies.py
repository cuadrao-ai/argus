from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from argus.api import state as api_state
from argus.api.auth_sessions import (
    AuthSessionVerificationUnavailable,
    auth_session_is_active,
)
from argus.api.browser_cookies import set_browser_cookie
from argus.api.browser_session import REFRESH_COOKIE_MAX_AGE, renew_browser_token
from argus.api.guest_access import (
    guest_account_context,
    permanent_account_access_allowed,
    registered_account_context,
    store_account_context,
    visitor_key_for_request,
)
from argus.api.schemas import User


def validate_startup_configuration() -> None:
    enabled_flags = [
        name
        for name in (
            "NEXT_PUBLIC_MOCK_AUTH",
            "CUADRAO_MOCK_AUTH",
            "ARGUS_DEV_ENDPOINTS_ENABLED",
        )
        if os.getenv(name, "").strip().lower() == "true"
    ]
    if not enabled_flags:
        return
    environments = {
        value
        for name in ("APP_ENV", "ENVIRONMENT", "ARGUS_ENV", "ARGUS_APP_ENV")
        if (value := os.getenv(name, "").strip().lower())
    }
    local = bool(environments) and environments <= {
        "local",
        "development",
        "dev",
        "test",
        "local-smoke",
    }
    hosted = os.getenv("RENDER", "").strip().lower() == "true" or bool(
        os.getenv("RENDER_SERVICE_ID", "").strip()
    )
    if not local or hosted:
        reason = "local_environment_required_for_" + ",".join(enabled_flags)
        logger.error("startup_config_refused{{reason={}}}", reason)
        raise RuntimeError(reason)


def _json_safe_validation_error(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _json_safe_validation_error(nested) for key, nested in value.items()
        }
    if isinstance(value, list | tuple):
        return [_json_safe_validation_error(nested) for nested in value]
    return str(value)


def validation_problem_body(
    request_id: str,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "https://api.argus.app/problems/validation-error",
        "title": "Validation Error",
        "status": 422,
        "detail": "The request body or parameters did not match the API contract.",
        "code": "validation_error",
        "request_id": request_id,
        "context": {
            "errors": [
                {
                    str(key): _json_safe_validation_error(value)
                    for key, value in error.items()
                }
                for error in errors
            ]
        },
    }


async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("x-request-id")
        or api_state.store.new_id()
    )
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unexpected API failure",
            request_id=request_id,
            method=request.method,
            status_code=500,
        )
        response = JSONResponse(
            {
                "type": "https://api.argus.app/problems/internal-error",
                "title": "Internal Error",
                "status": 500,
                "detail": "An unexpected error occurred. Please try again.",
                "code": "internal_error",
                "request_id": request_id,
            },
            status_code=500,
        )
    renewed = getattr(request.state, "renewed_browser_session", None)
    if renewed is not None and response.status_code < 400:
        _apply_auth_session_cookies(request, response, renewed)
    response.headers["X-Request-Id"] = request_id
    return response


def problem(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    context: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    body = {
        "type": f"https://api.argus.app/problems/{code.replace('_', '-')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "request_id": request.state.request_id,
    }
    if context:
        body["context"] = context
    return HTTPException(status_code=status_code, detail=body, headers=headers)


def private_alpha_access_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=403,
        code="private_alpha_access_required",
        title="Private Alpha Access",
        detail=(
            "Argus is in private alpha right now. Use the email that was "
            "invited, or ask the Argus team for access."
        ),
    )


AccountCapabilityName = Literal[
    "can_create_additional_conversation",
    "can_manage_conversation",
    "can_save_decision",
    "can_manage_account",
]


def require_account_capability(
    request: Request,
    capability: AccountCapabilityName,
    *,
    detail: str,
    reason: str,
) -> None:
    from argus.api.guest_access import account_context

    capabilities = account_context(request).capabilities
    allowed = {
        "can_create_additional_conversation": (
            capabilities.can_create_additional_conversation
        ),
        "can_manage_conversation": capabilities.can_manage_conversation,
        "can_save_decision": capabilities.can_save_decision,
        "can_manage_account": capabilities.can_manage_account,
    }[capability]
    if allowed:
        return
    raise problem(
        request,
        status_code=403,
        code="account_conversion_required",
        title="Account Required",
        detail=detail,
        context={"reason": reason},
    )


def auth_response(request: Request, payload: dict[str, Any]) -> JSONResponse:
    response = JSONResponse(payload)
    _apply_auth_session_cookies(request, response, payload)
    # Conversion/sign-in owns the final session, after any source renewal.
    request.state.renewed_browser_session = None
    return response


def _apply_auth_session_cookies(
    request: Request,
    response: JSONResponse,
    payload: dict[str, Any],
) -> None:
    session = payload.get("session")
    if not isinstance(session, dict):
        return

    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    max_age = session.get("expires_in")
    cookie_kwargs: dict[str, Any] = {
        "httponly": True,
        "path": "/",
        **browser_cookie_policy(request),
    }
    if isinstance(max_age, int):
        cookie_kwargs["max_age"] = max_age

    if isinstance(access_token, str) and access_token:
        set_browser_cookie(response, "sb-auth-token", access_token, **cookie_kwargs)
    if isinstance(refresh_token, str) and refresh_token:
        set_browser_cookie(
            response,
            "sb-refresh-token",
            refresh_token,
            **{**cookie_kwargs, "max_age": REFRESH_COOKIE_MAX_AGE},
        )


def browser_cookie_policy(request: Request) -> dict[str, Any]:
    """One owner for how every Argus browser cookie crosses origins.

    `Lax` depends on the API sharing a registrable domain with the app, which
    is what makes these cookies first-party. Move the API off that domain and
    every browser silently stops returning them; the release-contract test
    that pins the two hosts together is the guard against that.
    """

    return {"secure": _session_cookie_secure(request), "samesite": "lax"}


def _session_cookie_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    forwarded_scheme = forwarded_proto.split(",", 1)[0].strip().lower()
    return (
        request.url.scheme == "https"
        or forwarded_scheme == "https"
        or _production_like_environment()
    )


def _production_like_environment() -> bool:
    for name in ("APP_ENV", "ENVIRONMENT", "ARGUS_ENV", "ARGUS_APP_ENV"):
        value = os.getenv(name, "").strip().lower()
        if value in {"production", "prod", "staging"}:
            return True
    return False


def dev_memory_fallback_enabled() -> bool:
    return os.getenv("ARGUS_DEV_MEMORY_FALLBACK", "").strip().lower() == "true"


def request_access_token(request: Request) -> str | None:
    """The bearer token, or the Supabase session cookie's access token."""
    renewed_token = getattr(request.state, "access_token", None)
    if isinstance(renewed_token, str) and renewed_token:
        return renewed_token
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
    else:
        potential_tokens = []
        for key, value in request.cookies.items():
            if key.startswith("sb-") and ("auth-token" in key or "access-token" in key):
                try:
                    clean_value = value.strip('"')
                    if clean_value.startswith("{") or clean_value.startswith("["):
                        token_data = json.loads(clean_value)
                        extracted = (
                            token_data.get("access_token")
                            if isinstance(token_data, dict)
                            else None
                        )
                        if extracted:
                            potential_tokens.append(extracted)
                    else:
                        potential_tokens.append(clean_value)
                except Exception:
                    potential_tokens.append(value)

        for token_value in potential_tokens:
            if token_value:
                token = token_value
                break

    return token


def current_user(request: Request) -> User:
    if (
        os.getenv("NEXT_PUBLIC_MOCK_AUTH", "").strip().lower() == "true"
        or os.getenv("CUADRAO_MOCK_AUTH", "").strip().lower() == "true"
    ):
        if api_state.supabase_gateway is not None:
            try:
                user = api_state.supabase_gateway.get_or_create_mock_user()
                store_account_context(request, registered_account_context(user.id))
                return user
            except Exception:
                if not dev_memory_fallback_enabled():
                    raise
        user = api_state.store.get_or_create_dev_user()
        store_account_context(request, registered_account_context(user.id))
        return user

    if api_state.supabase_gateway is None:
        raise problem(
            request,
            status_code=500,
            code="internal_error",
            title="Internal Error",
            detail="Supabase persistence is required for non-mock authentication.",
        )

    token = request_access_token(request)
    try:
        token = renew_browser_token(request, api_state.supabase_gateway, token)
    except Exception:
        raise problem(
            request,
            status_code=401,
            code="unauthorized",
            title="Unauthorized",
            detail="Invalid or expired session.",
        ) from None

    if not token:
        raise problem(
            request,
            status_code=401,
            code="unauthorized",
            title="Unauthorized",
            detail="Missing or invalid Authorization header or session cookie.",
        )

    try:
        auth_user = api_state.supabase_gateway.get_auth_user_from_token(token)
    except Exception:
        raise problem(
            request,
            status_code=401,
            code="unauthorized",
            title="Unauthorized",
            detail="Invalid or expired access token.",
        ) from None

    auth_user_id = str(auth_user.get("id") or "")
    try:
        # Also false for an account-deletion placeholder (banned with no
        # sessions, so defense in depth) and for a person whose deletion run
        # is in flight: that account is locked until the run finishes. Only
        # POST /account/delete accepts the latter, to resume its own run
        # (argus.api.account_deletion_auth).
        session_is_active = auth_session_is_active(
            database_url=api_state.DATABASE_URL,
            token=token,
            user_id=auth_user_id,
        )
    except AuthSessionVerificationUnavailable:
        raise problem(
            request,
            status_code=503,
            code="auth_session_verification_unavailable",
            title="Session Verification Unavailable",
            detail="Argus could not verify this session. Please try again.",
        ) from None
    if not session_is_active:
        raise problem(
            request,
            status_code=401,
            code="unauthorized",
            title="Unauthorized",
            detail="Invalid or expired access token.",
        )

    if auth_user.get("is_anonymous") is True:
        workspace = api_state.supabase_gateway.get_active_guest_workspace(
            user_id=auth_user_id,
            at=datetime.now(timezone.utc),
        )
        if workspace is None and request.scope.get("path") == "/api/v1/auth/guest/signup":
            # A claim can commit before its response reaches the browser. Keep
            # that source session valid only for the replay-safe signup route.
            workspace = api_state.supabase_gateway.get_guest_workspace_for_signup_retry(
                user_id=auth_user_id,
                at=datetime.now(timezone.utc),
            )
        if workspace is None:
            raise problem(
                request,
                status_code=403,
                code="guest_session_expired",
                title="Guest Session Expired",
                detail="This temporary guest session is no longer available.",
            )
        user = api_state.supabase_gateway.get_or_create_profile_for_auth_user(auth_user)
        store_account_context(
            request,
            guest_account_context(
                workspace,
                visitor_key=visitor_key_for_request(request),
            ),
        )
        return user

    auth_email = str(auth_user.get("email") or "")
    if not permanent_account_access_allowed(api_state.supabase_gateway, auth_email):
        raise private_alpha_access_problem(request)

    user = api_state.supabase_gateway.get_or_create_profile_for_auth_user(auth_user)
    store_account_context(request, registered_account_context(user.id))
    return user

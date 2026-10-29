from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from loguru import logger
from pydantic import ValidationError

from argus.api import state as api_state
from argus.api.guest_access import permanent_account_access_allowed
from argus.api.ops_contract import (
    ACCESS_REQUEST_APPROVE_PATH,
    REQUESTED_SIGNUP_DENIAL_PATH,
)
from argus.api.schemas import AccessApprovalRequest, AccessApprovalResponse, Language
from argus.domain.access_approval_email import (
    ACCESS_WELCOME_CONTENT_VERSION,
    build_access_welcome_email,
    send_access_welcome_email,
)
from argus.domain.market_data import warm_asset_universe
from argus.settings_names import setting_value

router = APIRouter(tags=["ops"])

_APPROVAL_UNAVAILABLE_DETAIL = "Approval is unavailable."
_INELIGIBLE_DETAIL = "Access request is not eligible for approval."


def _ops_token() -> str:
    return (os.getenv("CUADRAO_OPS_TOKEN") or "").strip()


def _latin1_bytes(value: str) -> bytes | None:
    try:
        return value.encode("latin-1")
    except UnicodeEncodeError:
        return None


def _require_ops_token(authorization: str | None) -> None:
    expected = _ops_token()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    expected_header = _latin1_bytes(f"Bearer {expected}")
    provided = _latin1_bytes(authorization or "")
    if expected_header is None or provided is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not hmac.compare_digest(provided, expected_header):
        raise HTTPException(status_code=404, detail="Not found")


def _require_ops_authorization(
    authorization: str | None = Header(default=None),
) -> None:
    _require_ops_token(authorization)


def _check(name: str, status: str, duration_ms: int, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "duration_ms": duration_ms,
        **extra,
    }


def _readiness_timeout_seconds() -> float:
    raw = (os.getenv("ARGUS_READINESS_ASSET_TIMEOUT_SECONDS") or "25").strip()
    try:
        value = float(raw)
    except ValueError:
        return 25.0
    return max(value, 1.0)


async def run_readiness_checks(request: Request, *, force: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    started = time.perf_counter()
    try:
        api_state.get_agent_runtime_workflow(request)
        checks.append(
            _check(
                "agent_runtime_workflow",
                "ready",
                int((time.perf_counter() - started) * 1000),
            )
        )
    except Exception:
        checks.append(
            _check(
                "agent_runtime_workflow",
                "degraded",
                int((time.perf_counter() - started) * 1000),
            )
        )

    started = time.perf_counter()
    if api_state.supabase_gateway is None:
        checks.append(_check("supabase", "degraded", 0, reason="gateway_unavailable"))
    else:
        try:
            result = await asyncio.to_thread(api_state.supabase_gateway.health_check)
            checks.append(_check("supabase", result["status"], result["duration_ms"]))
        except Exception:
            checks.append(
                _check(
                    "supabase",
                    "degraded",
                    int((time.perf_counter() - started) * 1000),
                )
            )

    started = time.perf_counter()
    try:
        asset_result = await asyncio.wait_for(
            asyncio.to_thread(warm_asset_universe, force=force),
            timeout=_readiness_timeout_seconds(),
        )
        checks.append(
            _check(
                "asset_universe",
                asset_result.status,
                asset_result.duration_ms,
                provider_mode=asset_result.provider_mode,
                alias_count=asset_result.alias_count,
                required_symbols=list(asset_result.required_symbols),
                resolved_symbols=list(asset_result.resolved_symbols),
                missing_symbols=list(asset_result.missing_symbols),
            )
        )
    except Exception:
        checks.append(
            _check(
                "asset_universe",
                "degraded",
                int((time.perf_counter() - started) * 1000),
            )
        )

    invite_codes = _invite_code_check()
    if invite_codes is not None:
        checks.append(invite_codes)

    status = (
        "ready" if all(check["status"] == "ready" for check in checks) else "degraded"
    )
    return {"status": status, "checks": checks}


def _invite_code_check() -> dict[str, Any] | None:
    """With a code surface on, a missing or short secret makes readiness fail."""
    from argus.domain.household.invite_codes import code_secret_problem, code_surface_on

    if not code_surface_on():
        return None
    if code_secret_problem() is None:
        return _check("invite_codes", "ready", 0)
    return _check("invite_codes", "degraded", 0, reason="invite_code_secret_unusable")


@router.get("/internal/readiness")
async def readiness(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    force: bool = False,
) -> dict[str, Any]:
    _require_ops_token(authorization)
    payload = await run_readiness_checks(request, force=force)
    if payload.get("status") != "ready":
        response.status_code = 503
    return payload


@router.post(
    REQUESTED_SIGNUP_DENIAL_PATH,
    dependencies=[Depends(_require_ops_authorization)],
)
async def requested_signup_denial(request: Request) -> dict[str, bool]:
    try:
        body = AccessApprovalRequest.model_validate(await request.json())
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(status_code=422, detail="Invalid request body.") from None
    if api_state.supabase_gateway is None:
        raise HTTPException(status_code=503, detail="Canary probe is unavailable.")
    return {
        "denied": not permanent_account_access_allowed(
            api_state.supabase_gateway,
            body.email,
        )
    }


def _approval_signup_url() -> str:
    origin = (setting_value("APP_ORIGIN") or "").strip().rstrip("/")
    if not origin:
        raise RuntimeError("Approval signup origin is unavailable.")
    return f"{origin}/?auth=signup"


def _approval_unavailable(stage: str) -> HTTPException:
    # Spec item 14 forbids logging the body, address, receipt, or token; the
    # stage alone still separates a provider outage from an RPC rejection.
    logger.exception("access approval failed", stage=stage)
    return HTTPException(status_code=503, detail=_APPROVAL_UNAVAILABLE_DETAIL)


async def _completed_access_welcome_replay(email: str) -> bool:
    gateway = api_state.supabase_gateway
    if gateway is None:
        return False
    try:
        existing = await asyncio.to_thread(
            gateway.get_private_alpha_access_welcome_delivery, email
        )
        if existing is None:
            return False
        return bool(
            await asyncio.to_thread(
                gateway.complete_private_alpha_access_welcome,
                email=email,
                language=existing["language"],
                content_version=existing["content_version"],
                subject=existing["subject"],
                provider_receipt=existing["provider_receipt"],
                claim_token=None,
            )
        )
    except Exception as exc:
        raise _approval_unavailable("delivery_replay") from exc


@router.post(
    ACCESS_REQUEST_APPROVE_PATH,
    response_model=AccessApprovalResponse,
    dependencies=[Depends(_require_ops_authorization)],
)
async def approve_access_request(request: Request) -> AccessApprovalResponse:
    try:
        body = AccessApprovalRequest.model_validate(await request.json())
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(status_code=422, detail="Invalid request body.") from None
    gateway = api_state.supabase_gateway
    if gateway is None:
        raise HTTPException(status_code=503, detail=_APPROVAL_UNAVAILABLE_DETAIL)
    if await _completed_access_welcome_replay(body.email):
        return AccessApprovalResponse()

    try:
        requested = await asyncio.to_thread(
            gateway.get_requested_private_alpha_access, body.email
        )
    except Exception as exc:
        raise _approval_unavailable("eligibility") from exc
    if requested is None:
        if await _completed_access_welcome_replay(body.email):
            return AccessApprovalResponse()
        raise HTTPException(status_code=409, detail=_INELIGIBLE_DETAIL)

    language: Language = "es-419" if requested.get("language") == "es-419" else "en"
    try:
        signup_url = _approval_signup_url()
        content = build_access_welcome_email(
            language=language,
            signup_url=signup_url,
        )
        claim = await asyncio.to_thread(
            gateway.claim_private_alpha_access_welcome,
            email=body.email,
            language=language,
            content_version=ACCESS_WELCOME_CONTENT_VERSION,
            subject=content.subject,
        )
    except Exception as exc:
        raise _approval_unavailable("claim") from exc
    if claim is None:
        if await _completed_access_welcome_replay(body.email):
            return AccessApprovalResponse()
        raise HTTPException(status_code=409, detail=_INELIGIBLE_DETAIL)
    claim_token = claim.get("claim_token")
    if claim.get("send_allowed") is not True or not isinstance(claim_token, str):
        raise HTTPException(status_code=409, detail=_INELIGIBLE_DETAIL)

    try:
        result = await asyncio.to_thread(
            send_access_welcome_email,
            recipient=body.email,
            language=language,
            signup_url=signup_url,
            claim_token=claim_token,
        )
    except Exception as exc:
        raise _approval_unavailable("smtp") from exc

    try:
        completed = await asyncio.to_thread(
            gateway.complete_private_alpha_access_welcome,
            email=body.email,
            language=language,
            content_version=result.content_version,
            subject=result.subject,
            provider_receipt=result.provider_receipt,
            claim_token=claim_token,
        )
    except Exception as exc:
        raise _approval_unavailable("completion") from exc
    if not completed:
        raise HTTPException(status_code=409, detail=_INELIGIBLE_DETAIL)
    return AccessApprovalResponse()

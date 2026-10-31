"""Resend receiving webhook (signed, no session) and the owner's receiving address."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from argus.api import state as api_state
from argus.api.business import (
    BusinessContext,
    manager_only,
    require_business,
    require_business_management,
)
from argus.api.client_ip import resolve_client_ip
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.email_intake import email_intake, part_repeat, webhook_enabled
from argus.api.ingestion import ingestion_hub
from argus.api.rate_limits import SlidingWindowLimiter
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.ingestion.email_intake.addressing import AliasTaken
from argus.domain.ingestion.email_intake.alias import (
    ALIAS_UNAVAILABLE,
    inspect_alias,
    suggest_alias,
)
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from argus.domain.ingestion.email_intake.routing import FIRST_SCAN_LABEL
from argus.domain.ingestion.email_intake.service import EmailCapture
from argus.domain.ingestion.email_intake.signatures import (
    WebhookSignatureError,
    verify_webhook,
)
from argus.domain.ingestion.email_intake.standing import email_row
from argus.domain.ingestion.email_intake.store import RecipientTaken
from argus.domain.ingestion.reconcile.service import ReconciliationService

webhook_router = APIRouter(prefix="/webhooks/resend", tags=["business-email"])
router = APIRouter(
    prefix="/business/email",
    tags=["business-email"],
    responses={
        403: {
            "description": "`business_grant_not_live`: the chosen grant (`X-Business-Grant`) is missing, someone else's, revoked or expired; `business_permission_denied`: the live grant does not allow this."
        }
    },
)
MAX_WEBHOOK_BYTES = 64 * 1024
_ALIAS_LOOKUP_LIMIT = 30
_ALIAS_LOOKUP_WINDOW_SECONDS = 60
_alias_lookup_limiter = SlidingWindowLimiter()


class EmailDeliveryWaiting(BaseModel):
    reason: Literal["daily_budget"] = "daily_budget"
    retry_at: datetime


class ReceivedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email_id: UUID
    to: list[str] = Field(min_length=1, max_length=100)


class ReceivedEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    data: ReceivedData


def _problem(request: Request, status: int, code: str, detail: str, context=None):  # noqa: ANN001
    return problem(
        request,
        status_code=status,
        code=code,
        title=detail,
        detail=detail,
        context=context,
        headers=NO_STORE,
    )


@webhook_router.post("", status_code=202)
async def receive(request: Request) -> Response:
    """Signature checked over the raw bytes before parsing. 202 means the event
    is a durable row; the worker fetches the message later."""

    runtime = email_intake()
    if not webhook_enabled() or runtime is None or runtime.provider is None:
        raise _problem(
            request, 404, "email_intake_unavailable", "Email receiving is not available."
        )
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_WEBHOOK_BYTES:
            raise _problem(
                request,
                413,
                "email_webhook_too_large",
                "Webhook body is larger than allowed.",
            )
    try:
        verify_webhook(
            bytes(body),
            request.headers,
            EmailIntakeSettings().webhook_secret.get_secret_value(),
            time.time(),
        )
    except WebhookSignatureError:
        raise _problem(
            request, 401, "invalid_webhook_signature", "Webhook signature is invalid."
        ) from None
    try:
        raw = json.loads(body)
        if raw.get("type") != "email.received":
            return Response(status_code=204, headers=NO_STORE)
        event = ReceivedEvent.model_validate(raw)
        recipients = tuple(sorted({address.strip().lower() for address in event.data.to}))
        if any(
            not address or len(address) > 254 or "\n" in address or "\r" in address
            for address in recipients
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise _problem(
            request, 400, "invalid_email_event", "Webhook event is invalid."
        ) from None
    try:
        await run_in_threadpool(
            runtime.enqueue_resend, str(event.data.email_id), recipients
        )
    except Exception:
        raise _problem(
            request, 503, "email_capture_unavailable", "Email receiving is unavailable."
        ) from None
    return Response(status_code=202, headers=NO_STORE)


def _runtime(request: Request) -> EmailCapture:
    runtime = email_intake()
    if runtime is None:
        raise _problem(
            request, 503, "email_capture_unavailable", "Email receiving is unavailable."
        )
    return runtime


def _stored_runtime(request: Request) -> EmailCapture | None:
    """``_runtime`` for a read that lists: None when the in-memory app keeps no
    deliveries, so the list is empty rather than refused."""

    if email_intake() is None and api_state.PERSISTENCE_MODE != "supabase":
        return None
    return _runtime(request)


def _readiness(runtime: EmailCapture, space_id: str) -> dict[str, Any]:
    route = runtime.store.route_for_space(space_id)
    usable = route is not None and runtime.route_usable(route)
    # Configuration readiness, not a claim about provider or DNS health.
    return {
        "enabled": bool(usable and webhook_enabled() and runtime.provider is not None),
        "receiving_address": route.recipient if usable else None,
        "alias": route.alias if usable else None,
        "review_required": bool(route.review_required) if usable else False,
    }


@router.get("")
def receiving(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    return _readiness(_runtime(request), context.scope.owner.space_id)


def _require_usable(request: Request, runtime: EmailCapture, route) -> None:  # noqa: ANN001
    """An existing address that can no longer receive is a typed refusal, not a 200 with nothing in it."""

    try:
        runtime.check_route(route)
    except ActionError as error:
        detail = (
            "This address's grant is no longer live. Stop receiving, then create a new address."
            if error.code == "email_route_revoked"
            else "Email receiving is off."
        )
        raise _problem(request, 409, error.code, detail) from None


class AliasBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    alias: str = Field(min_length=1, max_length=80)


class SenderBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal["address", "domain"]
    value: str = Field(min_length=3, max_length=254)
    status: Literal["authorized", "blocked"]


def _configured_domain(request: Request) -> str:
    domain = EmailIntakeSettings().receiving_domain.strip().lower()
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    hub = ingestion_hub()
    if (
        not domain
        or pool is None
        or hub is None
        or not isinstance(hub.sink, ReconciliationService)
    ):
        raise _problem(
            request,
            503,
            "email_receiving_unconfigured",
            "Email receiving is not configured.",
        )
    return domain


def _alias_report(runtime: EmailCapture, raw: str, *, except_route_id: str | None = None):
    return inspect_alias(
        raw,
        lambda alias: runtime.store.alias_taken(alias, except_route_id=except_route_id),
    )


def _refuse_alias(request: Request, report: dict) -> None:
    if report["status"] == "invalid":
        raise _problem(
            request,
            422,
            "email_alias_invalid",
            "This receipt name is not valid.",
        )
    if not report["available"]:
        logger.bind(route_id=None).warning("email_alias_unavailable")
        raise _problem(
            request,
            422,
            "email_alias_unavailable",
            ALIAS_UNAVAILABLE,
            context={"suggestions": report["suggestions"]},
        )


@router.post("", status_code=201)
def create_receiving_address(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_management)],
    body: Annotated[AliasBody | None, Body()] = None,
) -> dict[str, Any]:
    """One address per Business. The Business owner owns the captured documents;
    the caller's own live grant is the authority checked before each capture.
    A replay or a concurrent create returns the one live address."""

    # The address is the owner's to create or stop; a grantee only sees it.
    manager_only(request, context)
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    existing = runtime.store.route_for_space(space_id)
    if existing is not None:
        _require_usable(request, runtime, existing)
        response.status_code = 200
        return _readiness(runtime, space_id)
    domain = _configured_domain(request)
    if body is None or not body.alias.strip():
        raise _problem(
            request, 422, "email_alias_required", "A receipt name is required."
        )
    report = _alias_report(runtime, body.alias)
    _refuse_alias(request, report)
    pool = request.app.state.financial_accounts_pool
    hub = ingestion_hub()
    try:
        actor = BusinessActions(pool, hub.sink).resolve_actor(
            TrustedActor(
                actor_id=UUID(context.scope.acting_person_id),
                actor_kind="member",
                space_id=UUID(space_id),
            )
        )
    except ActionError as error:
        raise _problem(
            request, 403, error.code, "Your current access cannot receive email."
        ) from None
    try:
        route = runtime.store.create_route(
            recipient=f"{report['alias']}@{domain}",
            space_id=space_id,
            principal_id=actor.owner_id,
            granted_by=context.scope.acting_person_id,
            grant_id=str(actor.grant_id),
            alias=report["alias"],
            alias_normalized=report["alias"],
            review_required=report["review_required"],
        )
    except (AliasTaken, RecipientTaken):
        logger.bind(route_id=None).warning("email_alias_unavailable")
        raise _problem(
            request,
            422,
            "email_alias_unavailable",
            ALIAS_UNAVAILABLE,
            context={"suggestions": report["suggestions"]},
        ) from None
    if route.granted_by != context.scope.person_id:
        _require_usable(request, runtime, route)
        response.status_code = 200
    return _readiness(runtime, space_id)


@router.delete("", status_code=204)
def stop_receiving(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_management)],
) -> Response:
    manager_only(request, context)
    _runtime(request).store.deactivate_routes(
        context.scope.owner.space_id, actor_id=context.scope.acting_person_id
    )
    return Response(status_code=204, headers=NO_STORE)


def _limit_alias_lookup(request: Request, context: BusinessContext) -> None:
    user_id = context.scope.actor_id or context.scope.person_id
    retry = _alias_lookup_limiter.record_or_retry_after(
        keys=(f"user:{user_id}", f"ip:{resolve_client_ip(request)}"),
        limit=_ALIAS_LOOKUP_LIMIT,
        window_seconds=_ALIAS_LOOKUP_WINDOW_SECONDS,
    )
    if retry is None:
        return
    raise problem(
        request,
        status_code=429,
        code="email_alias_lookup_limited",
        title="Too Many Requests",
        detail="Wait before checking another receipt name.",
        headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
    )


def _public_alias(report: dict) -> dict[str, Any]:
    return {
        "available": report["available"],
        "review_required": report["review_required"],
        "suggestions": report["suggestions"],
        "message": report["message"],
    }


@router.get("/availability")
def alias_availability(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_management)],
    alias: Annotated[str, Query(min_length=1, max_length=80)],
) -> dict[str, Any]:
    manager_only(request, context)
    _limit_alias_lookup(request, context)
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    current = runtime.store.route_for_space(context.scope.owner.space_id)
    return _public_alias(
        _alias_report(
            runtime, alias, except_route_id=current.id if current is not None else None
        )
    )


@router.get("/suggestion")
def alias_suggestion(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_management)],
    name: Annotated[str | None, Query(max_length=80)] = None,
) -> dict[str, Any]:
    manager_only(request, context)
    _limit_alias_lookup(request, context)
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    chosen = (
        name or runtime.store.space_name(context.scope.owner.space_id) or ""
    ).strip()
    if not chosen:
        raise _problem(
            request, 422, "email_alias_name_required", "A business name is required."
        )
    suggested = suggest_alias(chosen)
    return {"alias": suggested, **_public_alias(_alias_report(runtime, suggested))}


@router.post("/address")
def change_receiving_address(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_management)],
    body: AliasBody,
) -> dict[str, Any]:
    """Replace the live alias. The old alias is reserved and deliveries stay put."""

    manager_only(request, context)
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    current = runtime.store.route_for_space(space_id)
    if current is None:
        raise _problem(request, 409, "email_route_unavailable", "Email receiving is off.")
    _require_usable(request, runtime, current)
    domain = _configured_domain(request)
    report = _alias_report(runtime, body.alias, except_route_id=current.id)
    _refuse_alias(request, report)
    try:
        runtime.store.change_address(
            current.id,
            alias=report["alias"],
            alias_normalized=report["alias"],
            recipient=f"{report['alias']}@{domain}",
            review_required=report["review_required"],
            actor_id=context.scope.acting_person_id,
        )
    except AliasTaken:
        logger.bind(route_id=current.id).warning("email_alias_unavailable")
        raise _problem(
            request,
            422,
            "email_alias_unavailable",
            ALIAS_UNAVAILABLE,
            context={"suggestions": report["suggestions"]},
        ) from None
    return _readiness(runtime, space_id)


def _sender_value(kind: str, value: str) -> str | None:
    cleaned = value.strip().lower()
    if kind == "domain":
        if "@" in cleaned or " " in cleaned or "." not in cleaned:
            return None
        return cleaned
    if cleaned.count("@") != 1 or " " in cleaned:
        return None
    local, domain = cleaned.split("@", 1)
    if not local or not domain or "." not in domain:
        return None
    return cleaned


@router.get("/senders")
def list_senders(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    return {
        "items": [
            {"id": item.id, "kind": item.kind, "value": item.value, "status": item.status}
            for item in runtime.store.list_senders(context.scope.owner.space_id)
        ]
    }


@router.post("/senders", status_code=201)
def authorize_sender(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_management)],
    body: SenderBody,
) -> dict[str, Any]:
    manager_only(request, context)
    response.headers.update(NO_STORE)
    value = _sender_value(body.kind, body.value)
    if value is None:
        raise _problem(request, 422, "email_sender_invalid", "That sender is not valid.")
    if body.kind == "domain":
        raise _problem(
            request,
            422,
            "email_sender_domain_refused",
            "That domain cannot be authorized as a whole.",
        )
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    existed = any(
        item.kind == body.kind and item.value == value
        for item in runtime.store.list_senders(space_id)
    )
    rule = runtime.store.upsert_sender(
        space_id, body.kind, value, body.status, actor_id=context.scope.acting_person_id
    )
    runtime.store.regroup_held(space_id, rule.value, rule.status)
    if existed:
        response.status_code = 200
    return {"id": rule.id, "kind": rule.kind, "value": rule.value, "status": rule.status}


@router.delete("/senders/{sender_id}", status_code=204)
def remove_sender(
    sender_id: UUID,
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_management)],
) -> Response:
    manager_only(request, context)
    removed = _runtime(request).store.remove_sender(
        context.scope.owner.space_id,
        str(sender_id),
        actor_id=context.scope.acting_person_id,
    )
    if removed is None:
        raise _problem(
            request, 404, "email_sender_not_found", "That sender is not on this list."
        )
    return Response(status_code=204, headers=NO_STORE)


@router.get("/inbox")
def inbox(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    relations = runtime.store.membership(space_id)
    grouped = {"remitentes_nuevos": [], "bandeja": []}
    for item in runtime.store.list(space_id, limit=200):
        if item.inbox_group not in grouped:
            continue
        view = _group(runtime, item, relations=relations)
        view["notice"] = FIRST_SCAN_LABEL if item.first_scan else None
        grouped[item.inbox_group].append(view)
    return {
        "groups": [
            {"id": "remitentes_nuevos", "items": grouped["remitentes_nuevos"]},
            {"id": "bandeja", "items": grouped["bandeja"]},
        ]
    }


def _group(
    runtime: EmailCapture,
    delivery,  # noqa: ANN001
    *,
    detail: bool = False,
    relations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One delivery with its parts. A part whose document an earlier delivery
    already brought names that delivery; a part whose document was saved before
    this email arrived (a web upload) is a repeat of that receipt. The answer
    reads this Business's email relations once, never other deliveries' parts."""

    result = asdict(delivery)
    for key in (
        "provider",
        "external_id",
        "recipients",
        "route_id",
        "space_id",
        "principal_id",
        "lease_token",
        "attempts",
        "cap_exempt",
    ):
        result.pop(key, None)
    if not detail:
        result.pop("text_body")
    budget_limited = delivery.error_code in (
        "email_daily_message_budget",
        "email_daily_byte_budget",
    )
    available_at = result.pop("available_at")
    waiting = (
        EmailDeliveryWaiting(retry_at=available_at)
        if delivery.state == "received"
        and budget_limited
        and available_at is not None
        and available_at > datetime.now(timezone.utc)
        else None
    )
    if budget_limited:
        result["error_code"] = None
    result["waiting"] = waiting.model_dump() if waiting else None
    result["retryable"] = False if waiting else runtime.retryable(delivery)
    known = (
        relations
        if relations is not None
        else runtime.store.membership(delivery.space_id)
    )
    result["parts"] = []
    repeats: dict[str, bool] = {}
    parts = runtime.store.parts(delivery.id)
    for part in parts:
        repeat_of_delivery, repeat_of_upload = part_repeat(runtime, delivery, part, known)
        repeats[part.id] = bool(repeat_of_delivery or repeat_of_upload)
        result["parts"].append(
            {
                **asdict(part),
                "repeat_of_delivery_id": repeat_of_delivery,
                "repeat_of_upload": repeat_of_upload,
            }
        )
    row = email_row(delivery, parts, lambda part: repeats[part.id])
    result["standing"] = row.standing
    result["sender_standing"] = runtime.store.sender_standing(
        delivery.space_id, delivery.sender
    )
    result["saved_receipt_count"] = row.saved_receipt_count
    result["no_receipt_reason"] = row.no_receipt_reason
    return result


@router.get("/deliveries")
def deliveries(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    runtime = _stored_runtime(request)
    if runtime is None:
        return {"items": []}
    space_id = context.scope.owner.space_id
    relations = runtime.store.membership(space_id)
    return {
        "items": [
            _group(runtime, item, relations=relations)
            for item in runtime.store.list(space_id)
        ]
    }


@router.get("/deliveries/{delivery_id}")
def delivery(
    delivery_id: UUID,
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    item = runtime.store.get(str(delivery_id), context.scope.owner.space_id)
    if item is None:
        raise _problem(
            request, 404, "email_delivery_not_found", "This email is not available."
        )
    return _group(runtime, item, detail=True)


@router.post("/deliveries/{delivery_id}/retry", status_code=202)
def retry(
    delivery_id: UUID,
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_management)],
) -> dict[str, Any]:
    # Re-running a delivery runs under the owner's grant: the owner's call alone.
    manager_only(request, context)
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    if not runtime.enabled():
        raise _problem(
            request, 409, "email_intake_unavailable", "Email receiving is off."
        )
    item = runtime.store.get(str(delivery_id), context.scope.owner.space_id)
    if item is None:
        raise _problem(
            request, 404, "email_delivery_not_found", "This email is not available."
        )
    if runtime.retryable(item):
        runtime.store.retry(item.id, context.scope.owner.space_id)
    return {"id": item.id}

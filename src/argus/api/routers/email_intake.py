"""Resend receiving webhook (signed, no session) and the owner's receiving address."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from argus.api.business import (
    BusinessContext,
    require_business,
    require_business_document_write,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.email_intake import email_intake, webhook_enabled
from argus.api.ingestion import ingestion_hub
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from argus.domain.ingestion.email_intake.service import EmailCapture
from argus.domain.ingestion.email_intake.signatures import (
    WebhookSignatureError,
    verify_webhook,
)
from argus.domain.ingestion.reconcile.service import ReconciliationService

webhook_router = APIRouter(prefix="/webhooks/resend", tags=["business-email"])
router = APIRouter(prefix="/business/email", tags=["business-email"])
MAX_WEBHOOK_BYTES = 64 * 1024


class ReceivedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email_id: UUID
    to: list[str] = Field(min_length=1, max_length=100)


class ReceivedEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    data: ReceivedData


def _problem(request: Request, status: int, code: str, detail: str):
    return problem(
        request,
        status_code=status,
        code=code,
        title=detail,
        detail=detail,
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


def _readiness(runtime: EmailCapture, space_id: str) -> dict[str, Any]:
    route = runtime.store.route_for_space(space_id)
    usable = route is not None and runtime.route_usable(route)
    # Configuration readiness, not a claim about provider or DNS health.
    return {
        "enabled": bool(usable and webhook_enabled() and runtime.provider is not None),
        "receiving_address": route.recipient if usable else None,
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


@router.post("", status_code=201)
def create_receiving_address(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business_document_write)],
) -> dict[str, Any]:
    """One address per Business. The Business owner owns the captured documents;
    the caller's own live grant is the authority checked before each capture.
    A replay or a concurrent create returns the one live address."""

    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    existing = runtime.store.route_for_space(space_id)
    if existing is not None:
        _require_usable(request, runtime, existing)
        response.status_code = 200
        return _readiness(runtime, space_id)
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
    try:
        actor = BusinessActions(pool, hub.sink).resolve_actor(
            TrustedActor(
                actor_id=UUID(context.scope.person_id),
                actor_kind="member",
                space_id=UUID(space_id),
            )
        )
    except ActionError as error:
        raise _problem(
            request, 403, error.code, "Your current access cannot receive email."
        ) from None
    route = runtime.store.create_route(
        recipient=f"recibos-{secrets.token_hex(4)}@{domain}",
        space_id=space_id,
        principal_id=actor.owner_id,
        granted_by=context.scope.person_id,
        grant_id=str(actor.grant_id),
    )
    if route.granted_by != context.scope.person_id:
        _require_usable(request, runtime, route)
        response.status_code = 200
    return _readiness(runtime, space_id)


@router.delete("", status_code=204)
def stop_receiving(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_document_write)],
) -> Response:
    _runtime(request).store.deactivate_routes(context.scope.owner.space_id)
    return Response(status_code=204, headers=NO_STORE)


def _first_deliveries(runtime: EmailCapture, space_id: str) -> dict[str, str]:
    """Document id to the delivery that brought it first, by arrival, within the
    deliveries this Business lists. A later delivery of the same bytes names
    that first one instead of pretending to add a receipt."""

    first: dict[str, str] = {}
    for item in sorted(runtime.store.list(space_id), key=lambda d: d.received_at):
        for part in runtime.store.parts(item.id):
            if part.document_id and part.document_id not in first:
                first[part.document_id] = item.id
    return first


def _group(
    runtime: EmailCapture,
    delivery,  # noqa: ANN001
    *,
    detail: bool = False,
    first: dict[str, str] | None = None,
) -> dict[str, Any]:
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
    ):
        result.pop(key)
    if not detail:
        result.pop("text_body")
    result["retryable"] = runtime.retryable(delivery)
    earlier = (
        first if first is not None else _first_deliveries(runtime, delivery.space_id)
    )
    result["parts"] = []
    for part in runtime.store.parts(delivery.id):
        origin = earlier.get(part.document_id or "")
        result["parts"].append(
            {
                **asdict(part),
                "repeat_of_delivery_id": origin
                if origin and origin != delivery.id
                else None,
            }
        )
    return result


@router.get("/deliveries")
def deliveries(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    first = _first_deliveries(runtime, space_id)
    return {
        "items": [
            _group(runtime, item, first=first) for item in runtime.store.list(space_id)
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
    context: Annotated[BusinessContext, Depends(require_business_document_write)],
) -> dict[str, Any]:
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

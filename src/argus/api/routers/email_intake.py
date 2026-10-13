"""Resend receiving webhook (signed, no session) and the owner's receiving address."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from argus.api.business import (
    BusinessContext,
    require_business,
    require_business_document_write,
)
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.api.email_intake import email_consent, email_intake, webhook_enabled
from argus.api.ingestion import ingestion_hub
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.ingestion.email_intake.ai_consent import (
    EmailConsentRequest,
    EmailConsentStore,
)
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from argus.domain.ingestion.email_intake.service import EmailCapture
from argus.domain.ingestion.email_intake.signatures import (
    WebhookSignatureError,
    verify_webhook,
)
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.whatsapp.ai_consent import ConsentError

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


class AddressReading(BaseModel):
    """The one-line notice was on the screen that asked for the address: the
    token binds the agreement to that exact text and model."""

    model_config = ConfigDict(extra="forbid")
    disclosure_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    language: str | None = Field(default=None, max_length=16)


class CreateAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_reading: AddressReading | None = None


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


def _reading_view(
    space_id: str, person_id: str, language: str | None
) -> dict[str, Any] | None:
    """Where the owner's permission to read emailed receipts stands, as this
    person may see it; None where no permission store exists (no database)."""

    consent = email_consent()
    if consent is None:
        return None
    return consent.status(space_id, person_id, language)


def _readiness(
    runtime: EmailCapture,
    space_id: str,
    person_id: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    route = runtime.store.route_for_space(space_id)
    usable = route is not None and runtime.route_usable(route)
    # Configuration readiness, not a claim about provider or DNS health.
    return {
        "enabled": bool(usable and webhook_enabled() and runtime.provider is not None),
        "receiving_address": route.recipient if usable else None,
        "ai_reading": _reading_view(space_id, person_id, language)
        if person_id is not None
        else None,
    }


def _consent_problem(request: Request, error: ConsentError):  # noqa: ANN202
    return problem(
        request,
        status_code=error.status,
        code=error.code,
        title="Email AI permission unavailable",
        detail=error.code,
        headers=NO_STORE,
    )


def _consent_store(request: Request) -> EmailConsentStore:
    consent = email_consent()
    if consent is None:
        raise _problem(
            request,
            503,
            "email_ai_consent_unavailable",
            "The AI reading permission is unavailable.",
        )
    return consent


@router.get("")
def receiving(
    request: Request,
    response: Response,
    context: Annotated[BusinessContext, Depends(require_business)],
    language: str | None = Query(default=None, max_length=16),
) -> dict[str, Any]:
    response.headers.update(NO_STORE)
    return _readiness(
        _runtime(request),
        context.scope.owner.space_id,
        context.scope.person_id,
        language,
    )


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
    body: CreateAddress | None = None,
) -> dict[str, Any]:
    """One address per Business. The Business owner owns the captured documents;
    the caller's own live grant is the authority checked before each capture.
    A replay or a concurrent create returns the one live address. With the
    notice's token, the owner's permission to read with AI is recorded in the
    same request, against the text that was on the screen."""

    response.headers.update(NO_STORE)
    runtime = _runtime(request)
    space_id = context.scope.owner.space_id
    person_id = context.scope.person_id
    reading = body.ai_reading if body else None
    existing = runtime.store.route_for_space(space_id)
    if existing is not None:
        _require_usable(request, runtime, existing)
        response.status_code = 200
        _agree(request, space_id, person_id, reading)
        return _readiness(runtime, space_id, person_id, reading and reading.language)
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
    _agree(request, space_id, person_id, reading)
    return _readiness(runtime, space_id, person_id, reading and reading.language)


def _agree(
    request: Request, space_id: str, person_id: str, reading: AddressReading | None
) -> None:
    """The agreement given on the address screen. Its key is the token itself,
    so a replayed create records one permission."""

    if reading is None:
        return
    try:
        _consent_store(request).enable(
            space_id,
            person_id,
            EmailConsentRequest(
                action="enable",
                disclosure_token=reading.disclosure_token,
                language=reading.language,
            ),
            "address:" + reading.disclosure_token[:64],
        )
    except ConsentError as error:
        raise _consent_problem(request, error) from None


@router.post("/ai-consent")
def answer_ai_reading(
    request: Request,
    response: Response,
    body: EmailConsentRequest,
    context: Annotated[BusinessContext, Depends(require_business_document_write)],
    idempotency_key: str = Header(min_length=1, max_length=80),
) -> dict[str, Any]:
    """The owner turns reading on against the text shown, or declines the
    one-time notice. Only the owner may answer; the store refuses anyone else."""

    response.headers.update(NO_STORE)
    space_id, person_id = context.scope.owner.space_id, context.scope.person_id
    consent = _consent_store(request)
    try:
        if body.action == "enable":
            return consent.enable(space_id, person_id, body, idempotency_key)
        return consent.decline(space_id, person_id, idempotency_key)
    except ConsentError as error:
        raise _consent_problem(request, error) from None


@router.delete("/ai-consent", status_code=204)
def revoke_ai_reading(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_document_write)],
) -> Response:
    try:
        _consent_store(request).revoke(
            context.scope.owner.space_id, context.scope.person_id
        )
    except ConsentError as error:
        raise _consent_problem(request, error) from None
    return Response(status_code=204, headers=NO_STORE)


@router.delete("", status_code=204)
def stop_receiving(
    request: Request,
    context: Annotated[BusinessContext, Depends(require_business_document_write)],
) -> Response:
    _runtime(request).store.deactivate_routes(context.scope.owner.space_id)
    return Response(status_code=204, headers=NO_STORE)


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
    ):
        result.pop(key)
    if not detail:
        result.pop("text_body")
    result["retryable"] = runtime.retryable(delivery)
    known = (
        relations
        if relations is not None
        else runtime.store.membership(delivery.space_id)
    )
    result["parts"] = []
    for part in runtime.store.parts(delivery.id):
        earlier = known.get(part.document_id or "", {}).get("delivery_ids") or []
        first = earlier[0] if earlier else None
        repeat_of_delivery = first if first and first != delivery.id else None
        repeat_of_upload = False
        if part.document_id and repeat_of_delivery is None:
            draft = runtime.documents.store.draft(
                user_id=delivery.principal_id, connection_id=part.document_id
            )
            repeat_of_upload = (
                draft is not None and draft.created_at < delivery.received_at
            )
        result["parts"].append(
            {
                **asdict(part),
                "repeat_of_delivery_id": repeat_of_delivery,
                "repeat_of_upload": repeat_of_upload,
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

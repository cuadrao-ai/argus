"""WhatsApp webhook (Meta-signed, no session) and signed-in sender linking."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from loguru import logger
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, ConfigDict

from argus.api import state as api_state
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.schemas import User
from argus.api.whatsapp import (
    WhatsAppOwnerContext,
    WhatsAppRuntime,
    link_store,
    require_whatsapp_owner,
    require_whatsapp_surface,
    whatsapp_runtime,
)
from argus.domain.business.authority import ActionError
from argus.domain.ingestion.whatsapp.ai_consent import (
    AIConsentStore,
    ConsentError,
    EnableAIConsent,
)
from argus.domain.ingestion.whatsapp.identity import link_message, signature_matches
from argus.domain.ingestion.whatsapp.payload import PayloadInvalid, parse_delivery
from argus.domain.ingestion.whatsapp.store import ReplyLanguage

MAX_WEBHOOK_BYTES = 512 * 1024

webhook_router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])
link_router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
_code_limiter = SlidingWindowLimiter()


class WebhookAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received: bool


class LinkCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The web app's current i18n language; WhatsApp replies use it.
    language: ReplyLanguage = "es-419"


class LinkCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message_text: str
    expires_at: datetime
    wa_me_url: str | None


class LinkStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linked: bool
    last4: str | None = None
    linked_at: datetime | None = None
    reply_language: ReplyLanguage | None = None


class AIConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linked: bool
    available: bool
    reason: str | None
    last4: str | None
    scope_version: int
    purpose: str
    active_scope_version: int | None = None
    disclosure: str
    route: dict | None
    disclosure_token: str | None
    enabled: bool
    consented_at: datetime | None
    revoked_at: datetime | None


async def _consent_call(request: Request, callback, *args):
    try:
        return await run_in_threadpool(callback, *args)
    except (ConsentError, ActionError) as error:
        raise problem(
            request,
            status_code=getattr(error, "status", 403),
            code=error.code,
            title="WhatsApp AI permission unavailable",
            detail=error.code,
        ) from None
    except (OperationalError, PoolTimeout):
        raise problem(
            request,
            status_code=503,
            code="whatsapp_ai_consent_unavailable",
            title="Service Unavailable",
            detail="The AI permission could not be reached. Retry.",
        ) from None


def _consent_store(request: Request, context: WhatsAppOwnerContext) -> AIConsentStore:
    store = context.runtime.receipts
    if store is None:
        raise problem(
            request,
            status_code=503,
            code="whatsapp_ai_consent_unavailable",
            title="Service Unavailable",
            detail="WhatsApp AI permission is unavailable.",
        )
    return store


@link_router.get("/ai-consent", response_model=AIConsentResponse)
async def get_whatsapp_ai_consent(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    language: str | None = Query(default=None, max_length=16),
) -> AIConsentResponse:
    if account_context(request).kind != "registered":
        raise problem(
            request,
            status_code=403,
            code="registered_account_required",
            title="Account Required",
            detail="A registered account is required.",
        )
    runtime = whatsapp_runtime()
    store = runtime.receipts if runtime else None
    if store is None:
        from argus.domain.ingestion.whatsapp.receipt_consent import (
            receipt_consent_store,
        )

        store = receipt_consent_store(_consent_pool(request))
    reason = (
        None
        if runtime is not None and runtime.receipts is not None
        else "whatsapp_unavailable"
    )
    try:
        require_whatsapp_surface(request)
    except HTTPException:
        reason = "whatsapp_unavailable"
    return await _consent_call(
        request,
        store.status,
        UUID(user.id),
        reason,
        language,
    )


@link_router.post("/ai-consent", response_model=AIConsentResponse)
async def enable_whatsapp_ai_consent(
    request: Request,
    body: EnableAIConsent,
    context: Annotated[WhatsAppOwnerContext, Depends(require_whatsapp_owner)],
    idempotency_key: str = Header(min_length=1, max_length=80),
) -> AIConsentResponse:
    return await _consent_call(
        request,
        _consent_store(request, context).enable,
        UUID(context.destination_owner_id),
        body,
        idempotency_key,
    )


@link_router.delete("/ai-consent", status_code=204)
async def revoke_whatsapp_ai_consent(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    await _consent_call(
        request, AIConsentStore(_consent_pool(request), lambda: {}).revoke, UUID(user.id)
    )
    return Response(status_code=204)


def _consent_pool(request: Request):
    pool = getattr(request.app.state, "financial_accounts_pool", None)
    if pool is None:
        if api_state.PERSISTENCE_MODE != "supabase" or not api_state.DATABASE_URL:
            raise problem(
                request,
                status_code=503,
                code="whatsapp_ai_consent_unavailable",
                title="Service Unavailable",
                detail="AI permission storage is unavailable.",
            )
        from argus.api.account_deletion_runtime import deletion_pool

        pool = deletion_pool(api_state.DATABASE_URL)
    return pool


@webhook_router.get("", response_class=PlainTextResponse)
def verify_whatsapp_webhook(
    request: Request,
    mode: str | None = Query(default=None, alias="hub.mode", max_length=32),
    token: str | None = Query(default=None, alias="hub.verify_token", max_length=256),
    challenge: str | None = Query(default=None, alias="hub.challenge", max_length=128),
    runtime: WhatsAppRuntime = Depends(require_whatsapp_surface),  # noqa: B008
) -> PlainTextResponse:
    expected = runtime.settings.verify_token.get_secret_value()
    if (
        mode == "subscribe"
        and token is not None
        and challenge
        and challenge.isascii()
        and challenge.isalnum()
        and hmac.compare_digest(token.encode(), expected.encode())
    ):
        return PlainTextResponse(challenge)
    raise problem(
        request,
        status_code=403,
        code="whatsapp_webhook_verification_failed",
        title="Forbidden",
        detail="Webhook verification failed.",
    )


@webhook_router.post("", response_model=WebhookAck)
async def receive_whatsapp_webhook(
    request: Request,
    runtime: WhatsAppRuntime = Depends(require_whatsapp_surface),  # noqa: B008
) -> WebhookAck:
    """Signature checked over the raw bytes before any parsing.

    200 means every message in the delivery has a committed record. A failure
    after that answers 503 so Meta redelivers; the redelivery resumes the
    same record instead of starting a second capture.
    """

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_WEBHOOK_BYTES:
            raise problem(
                request,
                status_code=413,
                code="whatsapp_webhook_too_large",
                title="Content Too Large",
                detail="Webhook body is larger than allowed.",
            )
    settings = runtime.settings
    if not signature_matches(
        settings.app_secret.get_secret_value(),
        request.headers.get("X-Hub-Signature-256"),
        bytes(body),
    ):
        logger.warning("WhatsApp webhook signature rejected")
        raise problem(
            request,
            status_code=401,
            code="whatsapp_webhook_rejected",
            title="Unauthorized",
            detail="Webhook could not be verified.",
        )
    try:
        delivery = parse_delivery(bytes(body), phone_number_id=settings.phone_number_id)
    except PayloadInvalid:
        logger.warning("WhatsApp webhook payload invalid")
        raise problem(
            request,
            status_code=400,
            code="whatsapp_webhook_invalid",
            title="Bad Request",
            detail="Webhook payload is not a WhatsApp messages change.",
        ) from None
    try:
        await runtime.intake.handle(delivery)
    except Exception as error:
        logger.warning(
            "WhatsApp delivery not finished; Meta will redeliver",
            failure_mode=type(error).__name__,
        )
        raise problem(
            request,
            status_code=503,
            code="whatsapp_webhook_retry",
            title="Service Unavailable",
            detail="Delivery recorded but not finished. Retry.",
        ) from None
    return WebhookAck(received=True)


@link_router.post("/link-codes", response_model=LinkCodeResponse, status_code=201)
async def create_whatsapp_link_code(
    request: Request,
    body: LinkCodeRequest | None = None,
    context: WhatsAppOwnerContext = Depends(require_whatsapp_owner),  # noqa: B008
) -> LinkCodeResponse:
    retry = _code_limiter.record_or_retry_after(
        keys=(context.destination_owner_id,), limit=5, window_seconds=600
    )
    if retry is not None:
        raise problem(
            request,
            status_code=429,
            code="whatsapp_link_code_rate_limited",
            title="Too Many Requests",
            detail="Wait before creating another WhatsApp code.",
            headers={"Retry-After": str(retry)},
        )
    issued = await run_in_threadpool(
        context.runtime.intake.issue_code,
        destination_owner_id=context.destination_owner_id,
        reply_language=(body or LinkCodeRequest()).language,
    )
    text = link_message(issued.code)
    number = context.runtime.settings.wa_me_number
    return LinkCodeResponse(
        code=issued.code,
        message_text=text,
        expires_at=issued.expires_at,
        wa_me_url=f"https://wa.me/{number}?text={quote(text)}" if number else None,
    )


@link_router.get("/link", response_model=LinkStatusResponse)
async def get_whatsapp_link(
    context: WhatsAppOwnerContext = Depends(require_whatsapp_owner),  # noqa: B008
) -> LinkStatusResponse:
    link = await run_in_threadpool(
        context.runtime.intake.store.destination_link,
        destination_owner_id=context.destination_owner_id,
    )
    if link is None:
        return LinkStatusResponse(linked=False)
    return LinkStatusResponse(
        linked=True,
        last4=link.last4,
        linked_at=link.linked_at,
        reply_language=link.reply_language,
    )


@link_router.delete("/link", status_code=204)
async def revoke_whatsapp_link(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> Response:
    """Never gated: a person can always end their own sender link and its
    unused codes, whatever the Business and intake flags say."""

    store = link_store()
    unreachable = store is None and api_state.PERSISTENCE_MODE == "supabase"
    if store is not None:
        try:
            await run_in_threadpool(
                store.revoke,
                destination_owner_id=user.id,
                now=datetime.now(timezone.utc),
            )
        except (OperationalError, PoolTimeout):
            unreachable = True
    if unreachable:
        raise problem(
            request,
            status_code=503,
            code="whatsapp_link_unavailable",
            title="Service Unavailable",
            detail="The WhatsApp link could not be reached. Retry.",
        )
    return Response(status_code=204)

"""WhatsApp webhook (Meta-signed, no session) and signed-in sender linking."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from loguru import logger
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, ConfigDict, Field

from argus.api import state as api_state
from argus.api.dependencies import current_user, problem
from argus.api.documents import document_problem, documents_service
from argus.api.rate_limits import SlidingWindowLimiter
from argus.api.schemas import User
from argus.api.whatsapp import (
    WhatsAppRuntime,
    WhatsAppSenderContext,
    eligible_sender_businesses,
    link_store,
    require_whatsapp_sender,
    require_whatsapp_surface,
    sender_businesses_with_tax_ids,
    unavailable_problem,
    whatsapp_receiving_available,
)
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.contracts.dgii import TaxId
from argus.domain.ingestion.documents.config import SOURCE_MEDIA_TYPES
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.objects import (
    IMAGE_MEDIA_TYPES,
    SourceStorageUnavailable,
)
from argus.domain.ingestion.documents.rebuilt import rebuild_image
from argus.domain.ingestion.documents.service import DocumentServiceError
from argus.domain.ingestion.whatsapp.ai_consent import (
    AIConsentStore,
    ConsentError,
    accepted_link_disclosure,
    link_disclosure,
)
from argus.domain.ingestion.whatsapp.held import Reason, held_files
from argus.domain.ingestion.whatsapp.identity import link_message, signature_matches
from argus.domain.ingestion.whatsapp.payload import PayloadInvalid, parse_delivery
from argus.domain.ingestion.whatsapp.store import ReplyLanguage

MAX_WEBHOOK_BYTES = 512 * 1024

_UNAVAILABLE = {
    404: {"description": "whatsapp_unavailable: receiving is unavailable."}
}
webhook_router = APIRouter(
    prefix="/webhooks/whatsapp", tags=["whatsapp"], responses=_UNAVAILABLE
)
link_router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
_code_limiter = SlidingWindowLimiter()


class WebhookAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received: bool


class LinkCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The web app's current i18n language; WhatsApp replies use it.
    language: ReplyLanguage = "es-419"
    disclosure_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class LinkCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message_text: str
    expires_at: datetime
    wa_me_url: str | None
    qr_data_url: str | None


class HeldBusiness(BaseModel):
    space_id: str
    name: str


class ReceivingBusiness(HeldBusiness):
    tax_id: TaxId


class HeldFileResponse(BaseModel):
    id: str
    reason: Reason
    reading: bool
    held_at: datetime
    expires_at: datetime
    media_type: str
    preview_url: str


class HeldFilesResponse(BaseModel):
    files: list[HeldFileResponse]
    receiving_businesses: list[HeldBusiness]


class HeldFileAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: UUID


class LinkStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receiving_businesses: list[ReceivingBusiness]
    held_count: int
    disclosure: str
    disclosure_token: str
    linked: bool
    last4: str | None = None
    linked_at: datetime | None = None
    reply_language: ReplyLanguage | None = None


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
    """The webhook verifies the signature, saves linked media and queues eligible reads before acknowledging the delivery. A settled replay returns 200. An unfinished delivery can be retried after its claim expires."""

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
            "WhatsApp delivery unfinished, awaiting redelivery",
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


def require_link_setup(
    request: Request,
    context: WhatsAppSenderContext = Depends(require_whatsapp_sender),  # noqa: B008
) -> WhatsAppSenderContext:
    if not eligible_sender_businesses(context.person_id):
        raise problem(
            request, status_code=409, code="whatsapp_setup_required",
            title="Conflict", detail="WhatsApp setup is required.",
        )
    return context


@link_router.post(
    "/link-codes", response_model=LinkCodeResponse, status_code=201,
    responses={**_UNAVAILABLE, 409: {"description": "Setup is incomplete or the consent notice changed."}},
)
async def create_whatsapp_link_code(
    request: Request,
    body: LinkCodeRequest,
    context: WhatsAppSenderContext = Depends(require_link_setup),  # noqa: B008
) -> LinkCodeResponse:
    disclosure = await _consent_call(
        request, accepted_link_disclosure, context.person_id, body.language, body.disclosure_token
    )
    retry = _code_limiter.record_or_retry_after(
        keys=(context.person_id,), limit=5, window_seconds=600
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
        destination_owner_id=context.person_id,
        reply_language=body.language,
        disclosure=disclosure,
    )
    text = link_message(issued.code)
    number = context.runtime.settings.wa_me_number
    url = f"https://wa.me/{number}?text={quote(text)}" if number else None
    return LinkCodeResponse(
        code=issued.code,
        message_text=text,
        expires_at=issued.expires_at,
        wa_me_url=url,
        qr_data_url=segno.make_qr(url).png_data_uri(scale=5) if url else None,
    )


_PRIVATE = {"Cache-Control": "private, no-store"}
_Sender = Annotated[WhatsAppSenderContext, Depends(require_whatsapp_sender)]


def _held_problem(request: Request, code: str, status: int) -> HTTPException:
    return problem(
        request,
        status_code=status,
        code=code,
        title="Held file unavailable",
        detail=code,
        headers=_PRIVATE,
    )


@link_router.get("/held-files", response_model=HeldFilesResponse, responses=_UNAVAILABLE)
def list_held_files(
    request: Request, response: Response, context: _Sender
) -> HeldFilesResponse:
    documents = documents_service()
    assert documents is not None
    response.headers.update(_PRIVATE)
    now = documents.hub.clock()
    files = [
        HeldFileResponse(
            id=item.held.id,
            reason=item.held.reason,
            held_at=item.held.held_at,
            expires_at=item.held.held_at + PURGE_AFTER,
            media_type=item.draft.media_type,
            reading=item.draft.read_pending(
                business_permission=None,
                lease_until=item.lease_until,
                now=now,
            ),
            preview_url=str(
                request.app.url_path_for("preview_held_file", held_id=item.held.id)
            ),
        )
        for item in held_files(documents.store).pending_for_user(context.person_id)
    ]
    return HeldFilesResponse(
        files=files,
        receiving_businesses=[
            HeldBusiness(space_id=grant.space_id, name=grant.name)
            for grant in context.runtime.intake.store.eligible_businesses(
                context.person_id
            )
        ],
    )


@link_router.get(
    "/held-files/{held_id}/preview",
    response_class=Response,
    responses={
        200: {
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "application/pdf")
            }
        },
        404: {
            "description": "Receiving unavailable, or no pending file for this sender."
        },
    },
)
def preview_held_file(request: Request, held_id: UUID, context: _Sender) -> Response:
    documents = documents_service()
    assert documents is not None
    files = held_files(documents.store)
    owner = context.person_id
    pending = files.pending_for_user(owner, str(held_id))
    if not pending:
        raise _held_problem(request, "held_file_unavailable", 404)
    draft = pending[0].draft
    key = {"user_id": owner, "connection_id": draft.connection_id}
    try:
        download = documents.store.download_source(**key)
        if download is None and draft.media_type in IMAGE_MEDIA_TYPES:
            # Unread photos need a metadata-free preview without saving a copy or starting a read.
            original = documents.store.source(**key)
            if original is not None:
                download = ("image/jpeg", rebuild_image(original, draft.media_type))
    except (SourceStorageUnavailable, DocumentExtractionError) as error:
        raise document_problem(request, error) from None
    # Assignment and expiry may have completed during the object download.
    if download is None or not files.pending_for_user(owner, str(held_id)):
        raise _held_problem(request, "held_file_unavailable", 404)
    media_type, content = download
    return Response(
        content,
        media_type=media_type,
        headers={
            **_PRIVATE,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="document.{SOURCE_MEDIA_TYPES[media_type]}"',
        },
    )


@link_router.post(
    "/held-files/{held_id}/assign",
    status_code=204,
    responses={
        403: {
            "description": "business_permission_denied: selected Business is ineligible."
        },
        404: {
            "description": "Receiving unavailable, or no pending file for this sender."
        },
        409: {"description": "document_busy or held_file_already_assigned."},
    },
)
def assign_held_file(
    request: Request,
    held_id: UUID,
    body: HeldFileAssignment,
    context: _Sender,
) -> Response:
    documents = documents_service()
    assert documents is not None
    try:
        documents.adopt(
            user_id=context.person_id,
            held_id=str(held_id),
            business_id=str(body.business_id),
        )
    except DocumentServiceError as error:
        status = {
            "business_permission_denied": 403,
            "held_file_unavailable": 404,
            "held_file_already_assigned": 409,
            "document_busy": 409,
            "whatsapp_unavailable": 404,
        }.get(error.code)
        if status is not None:
            raise _held_problem(request, error.code, status) from None
        raise document_problem(request, error) from None
    return Response(status_code=204, headers=_PRIVATE)


@link_router.get("/link", response_model=LinkStatusResponse, responses=_UNAVAILABLE)
def get_whatsapp_link(
    request: Request,
    response: Response,
    language: ReplyLanguage = "es-419",
    context: WhatsAppSenderContext = Depends(require_whatsapp_sender),  # noqa: B008
) -> LinkStatusResponse:
    response.headers["Cache-Control"] = "no-store"
    documents = documents_service()
    assert documents is not None
    held = held_files(documents.store).list_for_user(context.person_id)
    held_count = sum(item.state == "held" for item in held)
    link = context.link
    if not link and not held_count and not whatsapp_receiving_available(context.person_id):
        raise unavailable_problem(request)
    businesses = sender_businesses_with_tax_ids(context.person_id)
    disclosure, disclosure_token = link_disclosure(context.person_id, language)
    return LinkStatusResponse(
        disclosure=disclosure,
        disclosure_token=disclosure_token,
        linked=link is not None,
        last4=link.last4 if link else None,
        linked_at=link.linked_at if link else None,
        reply_language=link.reply_language if link else None,
        receiving_businesses=[
            ReceivingBusiness(space_id=grant.space_id, name=grant.name, tax_id=tax_id)
            for grant, tax_id in businesses
        ],
        held_count=held_count,
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

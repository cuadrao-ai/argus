"""WhatsApp intake wiring, exposure gate and the Business destination.

Default-off behind ``CUADRAO_WHATSAPP_INTAKE_ENABLED`` and nested inside the
document surface and the Business pilot: a WhatsApp receipt is a saved document
draft in the owner's Business space, so intake cannot be on while either is
off. Every route but unlinking answers 404 when off.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.business_spaces import business_spaces, space_missing_problem
from argus.api.dependencies import problem
from argus.api.documents import documents_service
from argus.api.ingestion import IngestionContext, ingestion_hub, require_ingestion_context
from argus.domain.business.config import business_pilot_enabled
from argus.domain.business.scope import resolve_business_scope
from argus.domain.business.spaces import SpaceStore
from argus.domain.ingestion.documents.config import load_document_extraction_settings
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.whatsapp.config import (
    WhatsAppSettings,
    load_whatsapp_settings,
)
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.intake import (
    Captured,
    CaptureFailed,
    CaptureRejected,
    WhatsAppIntake,
)
from argus.domain.ingestion.whatsapp.media import GraphMedia
from argus.domain.ingestion.whatsapp.replies import CloudApiTransport
from argus.domain.ingestion.whatsapp.store import (
    SENDER_LINK_REVOKED,
    InMemoryWhatsAppStore,
    WhatsAppStore,
)

WEBHOOK_PATH = "/api/v1/webhooks/whatsapp"


class _RedactWebhookQuery(logging.Filter):
    """uvicorn's access line carries the query string, and so the verify token."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (
            isinstance(args, tuple)
            and len(args) >= 3
            and isinstance(args[2], str)
            and args[2].startswith(f"{WEBHOOK_PATH}?")
        ):
            record.args = (*args[:2], f"{WEBHOOK_PATH}?<redacted>", *args[3:])
        return True


_access_logger = logging.getLogger("uvicorn.access")
if not any(isinstance(f, _RedactWebhookQuery) for f in _access_logger.filters):
    _access_logger.addFilter(_RedactWebhookQuery())


_REJECTED_CAPTURE = {
    "document_too_large": "whatsapp_media_too_large",
    "unsupported_media_type": "whatsapp_media_unsupported",
}


class DocumentsDestination:
    """Saves the bytes as a document draft in the owner's Business space, with
    ``consent=False``; never queues."""

    def __init__(self, documents: DocumentsService, spaces: SpaceStore) -> None:
        self.documents, self.spaces = documents, spaces

    async def capture(
        self,
        *,
        owner_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None,
    ) -> Captured:
        # A link needs a space, so an owner without one has no link to send through.
        scope = resolve_business_scope(self.spaces, owner_id)
        if scope is None:
            raise CaptureRejected(SENDER_LINK_REVOKED)
        try:
            outcome = await self.documents.upload(
                user_id=owner_id,
                content=content,
                filename=filename,
                media_type=media_type,
                consent=False,
                source_text=source_text,
                scope=scope.owner,
            )
        except DocumentExtractionError as error:
            raise CaptureRejected(
                _REJECTED_CAPTURE.get(error.code, "whatsapp_media_invalid")
            ) from None
        except DocumentServiceError:
            raise CaptureFailed("whatsapp_capture_failed") from None
        return Captured(outcome.connection_id, already_held=outcome.replayed)

    async def discard(self, *, owner_id: str, connection_id: str) -> None:
        scope = resolve_business_scope(self.spaces, owner_id)
        if scope is None:
            return
        await asyncio.to_thread(
            self.documents.hub.disconnect,
            user_id=owner_id,
            connection_id=connection_id,
            scope=scope.owner,
        )


class BackgroundWork:
    """Runs the work behind an acknowledged delivery and lets shutdown wait for it."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self, timeout: float) -> None:
        pending = set(self._tasks)
        if pending:
            await asyncio.wait(pending, timeout=timeout)


@dataclass(frozen=True)
class WhatsAppRuntime:
    intake: WhatsAppIntake
    settings: WhatsAppSettings
    work: BackgroundWork | None = None


_runtime: WhatsAppRuntime | None = None


def whatsapp_runtime() -> WhatsAppRuntime | None:
    return _runtime


def configure_whatsapp(runtime: WhatsAppRuntime | None) -> None:
    global _runtime
    _runtime = runtime


def build_whatsapp(
    settings: WhatsAppSettings,
    *,
    documents: DocumentsService,
    spaces: SpaceStore,
    store,  # noqa: ANN001
    client: httpx.AsyncClient,
    app_origin: str | None = None,
    work: BackgroundWork | None = None,
) -> WhatsAppRuntime:
    access_token = settings.access_token.get_secret_value()
    max_bytes = load_document_extraction_settings().max_bytes
    transport = None
    if settings.outbound_enabled:
        transport = CloudApiTransport(
            client=client,
            access_token=access_token,
            phone_number_id=settings.phone_number_id,
            graph_api_version=settings.graph_api_version,
        )
    intake = WhatsAppIntake(
        store=store,
        keys=WhatsAppKeys(settings.sender_key.get_secret_value()),
        media=GraphMedia(
            client=client,
            access_token=access_token,
            graph_api_version=settings.graph_api_version,
            max_bytes=max_bytes,
        ),
        destination=DocumentsDestination(documents, spaces),
        clock=documents.hub.clock,
        transport=transport,
        app_origin=app_origin,
        max_bytes=max_bytes,
        background=work.start if work is not None else None,
    )
    return WhatsAppRuntime(intake, settings, work)


def start_whatsapp(app: object) -> None:
    settings = load_whatsapp_settings()
    documents = documents_service()
    spaces = business_spaces()
    if not settings.intake_ready or documents is None or spaces is None:
        configure_whatsapp(None)
        return
    try:
        pool = getattr(getattr(app, "state", None), "financial_accounts_pool", None)
        if api_state.PERSISTENCE_MODE == "supabase":
            if pool is None:
                configure_whatsapp(None)
                return
            from argus.domain.ingestion.whatsapp.store_postgres import (
                PostgresWhatsAppStore,
            )

            store = PostgresWhatsAppStore(pool)
        else:
            store = InMemoryWhatsAppStore()
        configure_whatsapp(
            build_whatsapp(
                settings,
                documents=documents,
                spaces=spaces,
                store=store,
                client=httpx.AsyncClient(),
                app_origin=settings.app_origin,
                work=BackgroundWork(),
            )
        )
    except Exception as exc:
        logger.warning(
            "WhatsApp intake failed to start; it stays off",
            failure_mode=type(exc).__name__,
        )
        configure_whatsapp(None)


async def drain_whatsapp(timeout: float = 20.0) -> None:
    """Shutdown: give acknowledged deliveries time to settle before the pool closes."""

    runtime = whatsapp_runtime()
    if runtime is not None and runtime.work is not None:
        await runtime.work.drain(timeout)


def unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="whatsapp_unavailable",
        title="Not Found",
        detail="WhatsApp intake is not available.",
    )


def require_whatsapp_surface(request: Request) -> WhatsAppRuntime:
    """Flag first, before signatures or sessions, so an off surface looks absent."""

    runtime = whatsapp_runtime()
    documents = documents_service()
    if (
        runtime is None
        or not business_pilot_enabled()
        or not load_whatsapp_settings().intake_ready
        or not load_document_extraction_settings().enabled
        or documents is None
        or documents.hub is not ingestion_hub()
    ):
        raise unavailable_problem(request)
    return runtime


def link_store() -> WhatsAppStore | None:
    """Where a person's sender link lives, whatever the flags say.

    The running intake's store when intake is up. Otherwise the durable tables
    through deletion's own small pool, since unlinking removes data like
    deletion does. None in memory mode without intake: nothing here holds a
    link. None as well when Postgres cannot be reached."""

    runtime = whatsapp_runtime()
    if runtime is not None:
        return runtime.intake.store
    if api_state.PERSISTENCE_MODE != "supabase" or not api_state.DATABASE_URL:
        return None
    from argus.api.account_deletion_runtime import deletion_pool
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

    return PostgresWhatsAppStore(deletion_pool(api_state.DATABASE_URL))


@dataclass(frozen=True)
class WhatsAppOwnerContext:
    runtime: WhatsAppRuntime
    destination_owner_id: str


def require_whatsapp_owner(
    request: Request,
    runtime: WhatsAppRuntime = Depends(require_whatsapp_surface),  # noqa: B008
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> WhatsAppOwnerContext:
    """Linking needs the person's Business space: captures land there."""

    spaces = business_spaces()
    scope = resolve_business_scope(spaces, context.user_id) if spaces else None
    if scope is None:
        raise space_missing_problem(request)
    return WhatsAppOwnerContext(runtime, scope.person_id)

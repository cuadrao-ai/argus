"""WhatsApp intake wiring, exposure gate and the Business destination.

Default-off behind ``CUADRAO_WHATSAPP_INTAKE_ENABLED`` and nested inside the
document surface and the Business pilot: a WhatsApp receipt is a saved document
draft in the owner's Business space, so intake cannot be on while either is
off. Every route but unlinking answers 404 when off.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
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
from argus.domain.ingestion.whatsapp.ai_consent import AIConsentStore
from argus.domain.ingestion.whatsapp.business_worker import BusinessWhatsAppWorker
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
from argus.domain.ingestion.whatsapp.payload import TextMessage
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
    """Saves the bytes as a document draft in the owner's Business space. It is
    read by the model only when the owner turned receipt reading on; else it
    waits saved, unread."""

    def __init__(
        self,
        documents: DocumentsService,
        spaces: SpaceStore,
        reading_enabled: Callable[[str], bool] | None = None,
    ) -> None:
        self.documents, self.spaces = documents, spaces
        self.reading_enabled = reading_enabled

    async def capture(
        self,
        *,
        owner_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None = None,
    ) -> Captured:
        # A link needs a space, so an owner without one has no link to send through.
        scope = resolve_business_scope(self.spaces, owner_id)
        if scope is None:
            raise CaptureRejected(SENDER_LINK_REVOKED)
        read = await asyncio.to_thread(self._reading, owner_id)
        try:
            outcome = await self.documents.upload(
                user_id=owner_id,
                content=content,
                filename=filename,
                media_type=media_type,
                consent=read,
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

    def _reading(self, owner_id: str) -> bool:
        if self.reading_enabled is None:
            return False
        try:
            return self.reading_enabled(owner_id)
        except Exception as error:
            logger.warning(
                "WhatsApp receipt reading permission unreadable; the receipt waits unread",
                failure_mode=getattr(error, "code", type(error).__name__),
            )
            return False

    async def read(
        self, *, owner_id: str, connection_id: str
    ) -> tuple[str, dict[str, str] | None] | None:
        """Read a queued receipt through the owner's own preparation path, after
        the acknowledgement. The draft's status when it settles, else ``None``."""

        from fastapi import BackgroundTasks

        from argus.api.documents import dispatch_preparation

        scope = resolve_business_scope(self.spaces, owner_id)
        if scope is None:
            return None
        current = self.documents.get(
            user_id=owner_id, connection_id=connection_id, scope=scope.owner
        )
        if current.status != "queued":
            return None
        tasks = BackgroundTasks()
        try:
            await dispatch_preparation(
                _as_owner(self.documents, owner_id, scope.owner),
                owner_id,
                connection_id,
                tasks,
                scope=scope.owner,
            )
        except Exception as error:
            # A read that could not start is not "reading": the receipt waits
            # saved, with the reason recorded, for the owner to prepare. If the
            # release fails too, the original error is the one raised, with the
            # release failure chained behind it.
            try:
                self.documents.release_queued(
                    user_id=owner_id,
                    connection_id=connection_id,
                    scope=scope.owner,
                    code=getattr(error, "code", type(error).__name__),
                )
            except Exception as release_error:  # noqa: BLE001
                raise error from release_error
            raise
        await tasks()
        settled = self.documents.get(
            user_id=owner_id, connection_id=connection_id, scope=scope.owner
        )
        return settled.status, self._found(owner_id, connection_id)

    def _found(self, owner_id: str, connection_id: str) -> dict[str, str] | None:
        """The merchant, amount and currency of a receipt that read as exactly
        one purchase; anything less certain is left for the owner to review."""

        batch = self.documents.store.get(user_id=owner_id, connection_id=connection_id)
        if batch is None or len(batch.candidates) != 1:
            return None
        candidate = batch.candidates[0]
        merchant = plain_merchant(candidate.merchant)
        if (
            candidate.uncertain
            or not merchant
            or not (candidate.amount and candidate.currency)
        ):
            return None
        return {
            "merchant": merchant,
            "amount": candidate.amount,
            "currency": candidate.currency,
        }

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


_MERCHANT_CHARS = re.compile(r"[\w &'.\-]+", re.UNICODE)
_DOMAIN_LIKE = re.compile(r"[^\W_]\.[^\W_]{2,}")


def plain_merchant(text: str | None) -> str | None:
    """A merchant read from a receipt, safe to put in a message from our number:
    letters, digits, spaces and & ' - . only. Anything removed, a domain-like
    dot, or nothing left means no merchant is shown."""

    cleaned = " ".join((text or "").split())[:40]
    if "_" in cleaned or not _MERCHANT_CHARS.fullmatch(cleaned or "!"):
        return None
    if _DOMAIN_LIKE.search(cleaned) or cleaned != " ".join((text or "").split()):
        return None
    return cleaned


def _as_owner(documents: DocumentsService, owner_id: str, scope):  # noqa: ANN001, ANN202
    """The documents service the Business routes build for the signed-in owner:
    the same hub with a sink bound to the owner's own grant. A read started by a
    delivery has no request, so it is bound here, and only to the owner who
    received the receipt."""

    from argus.api.business_drafts import bind_to_grant
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.ingestion.reconcile.service import ReconciliationService

    actions, sink = documents.business_actions, documents.hub.sink
    if actions is None or not isinstance(sink, ReconciliationService):
        return documents
    context = actions.resolve_actor(
        TrustedActor(actor_id=owner_id, actor_kind="member", space_id=scope.space_id)
    )
    # Only the owner who received the receipt binds the read: a grant that
    # resolves for someone else, however capable, is not that owner.
    if str(context.owner_id) != str(owner_id):
        raise CaptureFailed("business_permission_denied")
    if "prepare" not in actions.record_context(context).capabilities:
        raise CaptureFailed("business_permission_denied")
    return bind_to_grant(documents, documents.hub, actions, context, "prepare")[0]


def _whatsapp_read_gate(store, reading):  # noqa: ANN001, ANN202
    """A receipt that arrived by WhatsApp is read only while the owner's switch
    is on at the moment of the read; other uploads carry their own consent."""

    def allowed(user_id: str, connection_id: str) -> bool:
        # The owner's switch decides, whoever asks for the read.
        try:
            owner = store.capture_owner(connection_id=connection_id)
            return True if owner is None else reading(owner)
        except Exception:
            return False

    return allowed


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
    worker: BusinessWhatsAppWorker | None = None
    consent: AIConsentStore | None = None
    work: BackgroundWork | None = None
    receipts: AIConsentStore | None = None


_runtime: WhatsAppRuntime | None = None


def whatsapp_runtime() -> WhatsAppRuntime | None:
    return _runtime


def configure_whatsapp(runtime: WhatsAppRuntime | None) -> None:
    global _runtime
    _runtime = runtime


def _capture_when_enabled(worker: BusinessWhatsAppWorker):  # noqa: ANN202
    """Text goes to the Business agent only while the worker can answer it.

    With the Business pilot, intake or the extraction switch off, or without
    canonical actions, text keeps the ordinary reply instead of being stored
    for an agent that never runs."""

    def capture(message: TextMessage) -> bool:
        return bool(
            worker.enabled()
            and worker.actions is not None
            and worker.captures.capture(message)
        )

    return capture


def build_whatsapp(
    settings: WhatsAppSettings,
    *,
    documents: DocumentsService,
    spaces: SpaceStore,
    store,  # noqa: ANN001
    client: httpx.AsyncClient,
    app_origin: str | None = None,
    pool=None,
    runner=None,
    route_resolver=None,
    work: BackgroundWork | None = None,
) -> WhatsAppRuntime:
    access_token = settings.access_token.get_secret_value()
    max_bytes = load_document_extraction_settings().max_bytes
    # Built once; whether it is used is re-read from the setting at each send.
    transport = CloudApiTransport(
        client=client,
        access_token=access_token,
        phone_number_id=settings.phone_number_id,
        graph_api_version=settings.graph_api_version,
    )
    worker = None
    consent = None
    keys = WhatsAppKeys(settings.sender_key.get_secret_value())
    reading = None
    receipts = None
    if pool is not None:
        from argus.domain.ingestion.whatsapp.receipt_consent import (
            receipt_consent_store,
        )

        receipts = receipt_consent_store(pool)

        def reading(owner):
            scope = resolve_business_scope(spaces, owner)
            permission = documents.business_receipt_consent
            return bool(
                scope and permission and permission.enabled(scope.owner.space_id, owner)
            )

    if pool is not None and documents.hub.box is not None:
        from argus.api.whatsapp_worker import build_worker
        from argus.domain.business.actions import BusinessActions
        from argus.domain.ingestion.reconcile.service import ReconciliationService

        actions = None
        if isinstance(documents.hub.sink, ReconciliationService):
            from argus.agent_runtime.business.runner import (
                BusinessTurnRunner,
                business_provider_route,
            )

            actions = BusinessActions(pool, documents.hub.sink)
            runner = runner or BusinessTurnRunner()
            consent = AIConsentStore(pool, route_resolver or business_provider_route)

        worker = build_worker(
            pool,
            box=documents.hub.box,
            keys=keys,
            transport=transport,
            actions=actions,
            runner=runner,
            consent=consent,
            enabled=lambda: business_pilot_enabled()
            and load_whatsapp_settings().intake_ready
            and load_whatsapp_settings().agent_enabled
            and load_document_extraction_settings().enabled,
            send_enabled=lambda: load_whatsapp_settings().outbound_enabled,
            app_origin=app_origin,
        )
    intake = WhatsAppIntake(
        store=store,
        keys=keys,
        media=GraphMedia(
            client=client,
            access_token=access_token,
            graph_api_version=settings.graph_api_version,
            max_bytes=max_bytes,
        ),
        destination=DocumentsDestination(documents, spaces, reading),
        clock=documents.hub.clock,
        transport=transport,
        app_origin=app_origin,
        max_bytes=max_bytes,
        capture_text=_capture_when_enabled(worker) if worker is not None else None,
        background=work.start if work is not None else None,
        send_enabled=lambda: load_whatsapp_settings().outbound_enabled,
    )
    return WhatsAppRuntime(intake, settings, worker, consent, work, receipts)


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
                pool=pool if api_state.PERSISTENCE_MODE == "supabase" else None,
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
    """Linking needs the person's Business space: captures land there.
    WhatsApp is the owner's channel: a chosen client grant is refused."""

    from argus.api.business import own_business_only

    own_business_only(request, context.user_id)
    spaces = business_spaces()
    scope = resolve_business_scope(spaces, context.user_id) if spaces else None
    if scope is None:
        raise space_missing_problem(request)
    return WhatsAppOwnerContext(runtime, scope.person_id)

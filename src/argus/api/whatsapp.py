"""WhatsApp intake wiring, exposure gate and the Business destination.

Default-off behind ``CUADRAO_WHATSAPP_INTAKE_ENABLED`` and nested inside the
document surface and the Business pilot: a WhatsApp receipt is a saved document
draft in the owner's Business space, so intake cannot be on while either is
off. Every route but unlinking and consent revocation answers 404 when off.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from copy import copy
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request
from loguru import logger
from psycopg import Connection

from argus.api import state as api_state
from argus.api.business_spaces import (
    business_access,
    business_spaces,
    space_missing_problem,
)
from argus.api.dependencies import problem
from argus.api.documents import documents_service, record_dispatch_preparation
from argus.api.ingestion import IngestionContext, ingestion_hub, require_ingestion_context
from argus.domain.business import analytics as business_analytics
from argus.domain.business.access import AccessStore, PostgresAccessStore
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.spaces import SpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.config import load_document_extraction_settings
from argus.domain.ingestion.documents.models import DocumentDraft, DocumentExtractionError
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.whatsapp.ai_consent import AIConsentStore
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
from argus.domain.ingestion.whatsapp.receipt_consent import receipt_consent_store
from argus.domain.ingestion.whatsapp.replies import CloudApiTransport
from argus.domain.ingestion.whatsapp.reply_groups import ReplyGroupCodec
from argus.domain.ingestion.whatsapp.store import (
    SENDER_LINK_REVOKED,
    CapturePermissionLost,
    InMemoryWhatsAppStore,
    Settlement,
    WhatsAppStore,
)
from argus.domain.owner_scope import BusinessSpace
from argus.domain.postgres_connection import BorrowedConnection

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
    """Stages a receipt in the current landing Business under the sender's grant."""

    def __init__(
        self,
        documents: DocumentsService,
        spaces: SpaceStore,
        access: AccessStore,
    ) -> None:
        self.documents, self.spaces, self.access = documents, spaces, access

    async def capture(
        self,
        *,
        owner_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None = None,
    ) -> Captured:
        # Keep the existing landing Business. The sender acts under their own grant.
        scope = await asyncio.to_thread(resolve_business_scope, self.spaces, owner_id)
        if scope is None:
            raise CaptureRejected(SENDER_LINK_REVOKED)
        capabilities = await asyncio.to_thread(
            self.access.capabilities, scope.owner.space_id, owner_id
        )
        if "prepare" not in capabilities:
            raise CaptureRejected("business_permission_denied")
        try:
            outcome = await self.documents.upload(
                user_id=scope.person_id,
                content=content,
                filename=filename,
                media_type=media_type,
                source_text=source_text,
                scope=scope.owner,
                defer_capture=True,
            )
        except DocumentExtractionError as error:
            raise CaptureRejected(
                _REJECTED_CAPTURE.get(error.code, "whatsapp_media_invalid")
            ) from None
        except DocumentServiceError:
            raise CaptureFailed("whatsapp_capture_failed") from None
        if not outcome.replayed:
            business_analytics.document_received(
                channel="whatsapp",
                business_id=scope.owner.space_id,
                user_id=owner_id,
                media_type=media_type,
                size_bytes=len(content),
            )
        return Captured(
            outcome.connection_id,
            already_held=outcome.replayed,
            storage_user_id=scope.person_id,
            space_id=scope.owner.space_id,
        )

    def prepare(self, connection: Connection | None, settlement: Settlement) -> bool:
        """Publish the source and record its read on the fenced claim's transaction."""
        person_id, owner_id = settlement.destination_owner_id, settlement.storage_user_id
        connection_id = settlement.connection_id
        assert person_id and owner_id and connection_id and settlement.space_id
        scope = BusinessSpace(settlement.space_id)
        documents, access = self.documents, self.access
        if connection is not None:
            documents = _documents_on_connection(documents, connection)
            access = PostgresAccessStore(BorrowedConnection(connection))
        if "prepare" not in access.capabilities(scope.space_id, person_id):
            raise CapturePermissionLost()
        draft = documents.get(user_id=owner_id, connection_id=connection_id, scope=scope)
        staged = draft.status == "saved" and not draft.source_available
        queued = (
            draft.status == "queued"
            and draft.consent
            and documents.store.job(user_id=owner_id, connection_id=connection_id) is None
        )
        if draft.business_reading_consent_id is not None and (staged or queued):
            return self._prepare_read(
                documents, connection, person_id, owner_id, draft, scope
            )
        documents.publish_capture(
            user_id=owner_id, connection_id=connection_id, scope=scope
        )
        return False

    def _prepare_read(
        self,
        documents: DocumentsService,
        connection: Connection | None,
        person_id: str,
        owner_id: str,
        draft: DocumentDraft,
        scope: BusinessSpace,
    ) -> bool:
        # Roll back the read if preparation refuses while keeping an accepted
        # source available for the owner's review.
        connection_id = draft.connection_id
        try:
            with connection.transaction() if connection is not None else nullcontext():
                owned = _as_sender(documents, person_id, scope)
                consent = owned.business_receipt_consent
                if (
                    consent is None
                    or draft.business_reading_consent_id is None
                    or not consent.enabled(
                        scope.space_id,
                        owner_id,
                        draft.business_reading_consent_id,
                        db=connection,
                    )
                ):
                    raise DocumentServiceError("document_reading_not_allowed")
                published = owned.publish_capture(
                    user_id=owner_id, connection_id=connection_id, scope=scope
                )
                if draft.status == "saved":
                    owned.queue(
                        user_id=owner_id,
                        connection_id=connection_id,
                        consent=True,
                        scope=scope,
                        expected_version=published.version,
                    )
                record_dispatch_preparation(owned, owner_id, connection_id, scope=scope)
        except (ActionError, CaptureFailed, DocumentServiceError) as error:
            code = error.code
            documents.publish_capture(
                user_id=owner_id,
                connection_id=connection_id,
                scope=scope,
                error_code=None if code == "document_reading_not_allowed" else code,
            )
            documents.release_queued(
                user_id=owner_id,
                connection_id=connection_id,
                scope=scope,
                code=code,
            )
            logger.warning(
                "WhatsApp receipt waits unread", failure_mode=type(error).__name__
            )
            return False
        return True

    async def discard(self, *, owner_id: str, space_id: str, connection_id: str) -> None:
        await asyncio.to_thread(
            self.documents.hub.disconnect,
            user_id=owner_id,
            connection_id=connection_id,
            scope=BusinessSpace(space_id),
        )


def _documents_on_connection(
    documents: DocumentsService, connection: Connection
) -> DocumentsService:
    pool = BorrowedConnection(connection)
    store = documents.store
    assert isinstance(store, PostgresDocumentStore)
    scoped = copy(documents)
    scoped.hub = copy(documents.hub)
    scoped.hub.connections = PostgresConnectionRepository(pool)
    scoped.store = PostgresDocumentStore(pool, store.objects)
    if documents.business_actions is not None:
        scoped.business_actions = BusinessActions(
            pool, documents.business_actions.imports
        )
    if documents.business_receipt_consent is not None:
        scoped.business_receipt_consent = copy(documents.business_receipt_consent)
        scoped.business_receipt_consent.pool = pool
    return scoped


def _as_sender(
    documents: DocumentsService, person_id: str, scope: BusinessSpace
) -> DocumentsService:
    """Bind the import sink to the sender's live grant in the receipt's Business."""

    from argus.api.business_drafts import bind_to_grant
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.ingestion.reconcile.service import ReconciliationService

    actions, sink = documents.business_actions, documents.hub.sink
    if actions is None or not isinstance(sink, ReconciliationService):
        return documents
    context = actions.resolve_actor(
        TrustedActor(actor_id=person_id, actor_kind="member", space_id=scope.space_id)
    )
    return bind_to_grant(documents, documents.hub, actions, context, "prepare")[0]


@dataclass(frozen=True)
class WhatsAppRuntime:
    intake: WhatsAppIntake
    settings: WhatsAppSettings
    receipts: AIConsentStore | None = None


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
    access: AccessStore,
    store: WhatsAppStore,
    client: httpx.AsyncClient,
    app_origin: str | None = None,
    pool=None,
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
    keys = WhatsAppKeys(settings.sender_key.get_secret_value())
    reply_codec = ReplyGroupCodec(documents.hub.box, keys) if documents.hub.box else None
    intake = WhatsAppIntake(
        store=store,
        keys=keys,
        media=GraphMedia(
            client=client,
            access_token=access_token,
            graph_api_version=settings.graph_api_version,
            max_bytes=max_bytes,
        ),
        destination=DocumentsDestination(documents, spaces, access),
        clock=documents.hub.clock,
        transport=transport,
        app_origin=app_origin,
        max_bytes=max_bytes,
        send_enabled=lambda: load_whatsapp_settings().replies_ready,
        reply_codec=reply_codec,
        reply_group_wait_seconds=settings.reply_group_wait_seconds,
    )
    receipts = receipt_consent_store(pool) if pool is not None else None
    return WhatsAppRuntime(intake, settings, receipts)


def start_whatsapp(app: object) -> None:
    settings = load_whatsapp_settings()
    documents = documents_service()
    spaces = business_spaces()
    access = business_access()
    if not settings.intake_ready or documents is None or spaces is None or access is None:
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
            store = InMemoryWhatsAppStore(documents.hub.connections, access)
        configure_whatsapp(
            build_whatsapp(
                settings,
                documents=documents,
                spaces=spaces,
                access=access,
                store=store,
                client=httpx.AsyncClient(),
                app_origin=settings.app_origin,
                pool=pool if api_state.PERSISTENCE_MODE == "supabase" else None,
            )
        )
    except Exception as exc:
        logger.warning(
            "WhatsApp intake failed to start; it stays off",
            failure_mode=type(exc).__name__,
        )
        configure_whatsapp(None)


def unavailable_problem(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=404,
        code="whatsapp_unavailable",
        title="Not Found",
        detail="WhatsApp intake is not available.",
    )


def whatsapp_receiving_available(scope: BusinessScope | None = None) -> bool:
    """Receiving readiness and eligibility for the selected Business."""
    documents = documents_service()
    ready = bool(
        whatsapp_runtime() is not None
        and load_whatsapp_settings().intake_ready
        and load_document_extraction_settings().enabled
        and documents is not None
        and documents.hub is ingestion_hub()
    )
    return ready and (scope is None or "prepare" in scope.permissions)


def require_whatsapp_surface(request: Request) -> WhatsAppRuntime:
    """Flag first, before signatures or sessions, so an off surface looks absent."""
    if not whatsapp_receiving_available():
        raise unavailable_problem(request)
    runtime = whatsapp_runtime()
    assert runtime is not None
    return runtime


def whatsapp_history_store() -> WhatsAppStore | None:
    """Read captured receipts through the existing Business document authority."""
    runtime = whatsapp_runtime()
    if runtime is not None:
        return runtime.intake.store
    documents = documents_service()
    if documents is None:
        return None
    authority = getattr(documents.business_actions, "authority", None)
    pool = getattr(authority, "pool", None)
    if pool is None:
        return None
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore

    return PostgresWhatsAppStore(pool)


def link_store() -> WhatsAppStore | None:
    """Where a person's sender link lives, whatever the flags say.

    The running intake's store when intake is up. Otherwise the durable tables
    through the process-owned business pool, as deletion uses too. None in memory mode without intake: nothing here holds a
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
class WhatsAppSenderContext:
    runtime: WhatsAppRuntime
    person_id: str
    space_id: str


def require_whatsapp_sender(
    request: Request,
    runtime: WhatsAppRuntime = Depends(require_whatsapp_surface),  # noqa: B008
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> WhatsAppSenderContext:
    """Authorize the signed-in sender in the selected Business."""

    from argus.api.business import working_scope

    spaces = business_spaces()
    scope = working_scope(request, spaces, context.user_id) if spaces else None
    if scope is None:
        raise space_missing_problem(request)
    if not whatsapp_receiving_available(scope):
        raise unavailable_problem(request)
    return WhatsAppSenderContext(runtime, context.user_id, scope.owner.space_id)

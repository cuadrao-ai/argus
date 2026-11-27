"""WhatsApp intake wiring, exposure gate and the Business destination.

Default-off behind ``CUADRAO_WHATSAPP_INTAKE_ENABLED`` and nested inside the
document surface and the Business pilot. Receipts go to an eligible Business
or wait privately for the linked sender. Every route but unlinking and consent revocation answers 404 when off.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from dataclasses import dataclass, replace
from hashlib import sha256

import httpx
from fastapi import Depends, HTTPException, Request
from loguru import logger
from psycopg import Connection

from argus.api import state as api_state
from argus.api.business_spaces import (
    business_access,
    business_spaces,
)
from argus.api.dependencies import problem
from argus.api.documents import documents_service, record_dispatch_preparation
from argus.api.ingestion import IngestionContext, ingestion_hub, require_ingestion_context
from argus.domain.business import analytics as business_analytics
from argus.domain.business.access import AccessStore, GrantedSpace, PostgresAccessStore
from argus.domain.business.authority import ActionError
from argus.domain.business.spaces import SpaceStore
from argus.domain.ingestion.documents.config import load_document_extraction_settings
from argus.domain.ingestion.documents.models import DocumentDraft, DocumentExtractionError
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
    document_ref,
)
from argus.domain.ingestion.whatsapp.ai_consent import AIConsentStore
from argus.domain.ingestion.whatsapp.config import (
    WhatsAppSettings,
    load_whatsapp_settings,
)
from argus.domain.ingestion.whatsapp.held import MARK, held_files
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.intake import (
    Captured,
    CaptureFailed,
    CaptureRejected,
    WhatsAppIntake,
)
from argus.domain.ingestion.whatsapp.media import GraphMedia
from argus.domain.ingestion.whatsapp.receipt_consent import (
    receipt_consent_store,
    receipt_reading_enabled,
)
from argus.domain.ingestion.whatsapp.replies import CloudApiTransport
from argus.domain.ingestion.whatsapp.reply_groups import ReplyGroupCodec
from argus.domain.ingestion.whatsapp.senders import (
    SenderBusinesses,
    postgres_senders,
    preparing_businesses,
)
from argus.domain.ingestion.whatsapp.store import (
    InMemoryWhatsAppStore,
    SenderLink,
    Settlement,
    WhatsAppStore,
)
from argus.domain.owner_scope import PERSONAL, BusinessSpace, scope_of, space_id
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


class _BusinessAuthorizationLost(Exception):
    pass


class DocumentsDestination:
    """Stage one eligible Business directly, or keep the sender's original private."""

    def __init__(
        self,
        documents: DocumentsService,
        store: WhatsAppStore,
    ) -> None:
        self.documents, self.store = documents, store

    async def capture(
        self,
        *,
        owner_id: str,
        content: bytes,
        filename: str,
        media_type: str,
        source_text: str | None = None,
    ) -> Captured:
        grants = await asyncio.to_thread(self.store.eligible_businesses, owner_id)
        digest = sha256(content).hexdigest()
        if grants:
            refs = [
                document_ref(g.owner_id, BusinessSpace(g.space_id), digest)
                for g in grants
            ]
            existing = await asyncio.to_thread(
                self.store.previous_business_copy, owner_id, refs
            )
            if existing:
                return Captured(
                    existing.connection_id,
                    True,
                    existing.custodian,
                    existing.space_id,
                    previous_business_copy=True,
                )
        grant = grants[0] if len(grants) == 1 else None
        if grant is not None:
            private_ref = document_ref(owner_id, PERSONAL, digest, MARK)
            private = await asyncio.to_thread(
                self.documents.hub.connections.find_live,
                source=self.documents.source,
                external_ref=private_ref,
            )
            if private:
                grant = None
        scope = BusinessSpace(grant.space_id) if grant else PERSONAL
        custodian = grant.owner_id if grant else owner_id
        try:
            outcome = await self.documents.upload(
                user_id=custodian,
                content=content,
                filename=filename,
                media_type=media_type,
                source_text=source_text,
                scope=scope,
                namespace=None if grant else MARK,
                defer_capture=True,
            )
        except DocumentExtractionError as error:
            raise CaptureRejected(
                _REJECTED_CAPTURE.get(error.code, "whatsapp_media_invalid")
            ) from None
        except DocumentServiceError as error:
            if grant is None:
                raise
            raise CaptureFailed(
                "whatsapp_capture_failed", retry_delivery=error.retryable
            ) from None
        return Captured(
            outcome.connection_id,
            already_held=outcome.replayed,
            storage_user_id=custodian,
            space_id=space_id(scope),
        )

    def prepare(
        self, connection: Connection | None, settlement: Settlement, message_key: bytes
    ) -> Settlement:
        person, custodian = settlement.destination_owner_id, settlement.storage_user_id
        connection_id = settlement.connection_id
        assert person and custodian and connection_id and settlement.sender_link_id
        if connection is None:
            documents = self.documents
            grants = self.store.eligible_businesses(person)
        else:
            documents = self.documents.on_connection(connection)
            grants = postgres_senders(connection).eligible_businesses(person)
        scope = scope_of(settlement.space_id)
        draft = documents.get(user_id=custodian, connection_id=connection_id, scope=scope)
        if isinstance(scope, BusinessSpace):
            reachable = any(
                g.space_id == scope.space_id and g.owner_id == custodian for g in grants
            )
            if reachable and settlement.previous_business_copy:
                return settlement
            if reachable and len(grants) == 1:
                try:
                    return self._publish_business(
                        documents, connection, settlement, draft, scope
                    )
                except _BusinessAuthorizationLost:
                    grants = ()
            # The staged Business is no longer the sole destination. Preserve the
            # original bytes in the sender's partition under this same claim.
            original = settlement.original
            assert original is not None
            private = documents._upload(
                user_id=person,
                content=original.content,
                filename=original.filename,
                media_type=original.media_type,
                source_text=original.caption,
                scope=PERSONAL,
                consent=False,
                proposal=None,
                on_capture=None,
                defer_capture=True,
                namespace=MARK,
            )
            if not draft.source_available:
                documents.hub.connections.disconnect(
                    user_id=custodian,
                    connection_id=connection_id,
                    now=documents.hub.clock(),
                )
                documents.store.forget(user_id=custodian, connection_id=connection_id)
            connection_id = private.connection_id
            settlement = replace(
                settlement,
                storage_user_id=person,
                space_id=None,
                connection_id=connection_id,
            )

        files = held_files(documents.store)
        if connection is not None:
            existing = connection.execute(
                "select 1 from public.whatsapp_held_files where user_id=%s and connection_id=%s limit 1",
                (person, connection_id),
            ).fetchone()
        else:
            existing = any(
                row.connection_id == connection_id for row in files.list_for_user(person)
            )
        if existing:
            return replace(settlement, duplicate=True)
        files.hold(
            user_id=person,
            sender_link_id=settlement.sender_link_id,
            provider_message_key=message_key,
            connection_id=connection_id,
            reason="no_match" if grants else "no_eligible_business",
            now=documents.hub.clock(),
        )
        published = documents.publish_capture(
            user_id=person, connection_id=connection_id, scope=PERSONAL
        )
        reading = bool(
            grants
            and connection is not None
            and receipt_reading_enabled(
                receipt_consent_store(BorrowedConnection(connection)), person
            )
        )
        if reading:
            documents.queue(
                user_id=person,
                connection_id=connection_id,
                consent=True,
                expected_version=published.version,
                scope=PERSONAL,
            )
            record_dispatch_preparation(documents, person, connection_id, scope=PERSONAL)
        return replace(settlement, duplicate=False, reading=reading)

    def _publish_business(
        self,
        documents: DocumentsService,
        connection: Connection | None,
        settlement: Settlement,
        draft: DocumentDraft,
        scope: BusinessSpace,
    ) -> Settlement:
        person, custodian = settlement.destination_owner_id, settlement.storage_user_id
        assert person and custodian
        connection_id = draft.connection_id
        staged = draft.status == "saved" and not draft.source_available
        queued = (
            draft.status == "queued"
            and draft.consent
            and documents.store.job(user_id=custodian, connection_id=connection_id)
            is None
        )
        reading = False
        if draft.business_reading_consent_id is not None and (staged or queued):
            reading = self._prepare_read(
                documents, connection, person, custodian, draft, scope
            )
        else:
            documents.publish_capture(
                user_id=custodian, connection_id=connection_id, scope=scope
            )
        if staged:
            business_analytics.document_received(
                channel="whatsapp",
                business_id=scope.space_id,
                user_id=person,
                media_type=draft.media_type,
                size_bytes=draft.size_bytes,
            )
        return replace(settlement, reading=reading)

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
                owned = documents.for_sender(person_id, scope)
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
            if code in {
                "business_permission_denied",
                "business_record_not_found",
                "business_closed",
                "document_reading_not_allowed",
                "business_receipt_reading_off",
            }:
                raise _BusinessAuthorizationLost() from error
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

    def discard(self, db: Connection | None, staged: Settlement) -> None:
        """Remove an unpublished draft while the settlement still holds its owner lock."""
        user, connection_id = staged.storage_user_id, staged.connection_id
        assert user and connection_id
        documents = self.documents.on_connection(db) if db is not None else self.documents
        draft = documents.store.draft(user_id=user, connection_id=connection_id)
        if draft is not None and not draft.source_available:
            documents.hub.connections.disconnect(
                user_id=user, connection_id=connection_id, now=documents.hub.clock()
            )
            documents.store.forget(user_id=user, connection_id=connection_id)


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
        destination=DocumentsDestination(documents, store),
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
            store = InMemoryWhatsAppStore(documents.hub.connections, access, eligible_sender_businesses)
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


def whatsapp_receiving_available(person_id: str | None = None, space_id: str | None = None) -> bool:
    """A preparer may open settings even while their Business setup is incomplete."""
    documents = documents_service()
    ready = bool(
        whatsapp_runtime() is not None
        and load_whatsapp_settings().intake_ready
        and load_document_extraction_settings().enabled
        and documents is not None
        and documents.hub is ingestion_hub()
    )
    if not ready or person_id is None:
        return ready
    if space_id is not None:
        return any(g.space_id == space_id for g in eligible_sender_businesses(person_id))
    access = business_access()
    return bool(access and preparing_businesses(access, person_id))


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
    link: SenderLink | None


def _memory_has_tax_id(space_id: str) -> bool:
    # Fiscal profiles are stored only in Postgres.
    return False


def eligible_sender_businesses(person_id: str) -> tuple[GrantedSpace, ...]:
    access = business_access()
    documents = documents_service()
    if access is None or documents is None:
        return ()
    if isinstance(access, PostgresAccessStore):
        with access.pool.connection() as db:
            return postgres_senders(db).eligible_businesses(person_id)
    reading = documents.business_receipt_consent
    if reading is None:
        return ()
    grants = SenderBusinesses(
        access, _memory_has_tax_id, lambda g: reading.status(g.space_id, g.owner_id)
    ).eligible_businesses(person_id)
    spaces = business_spaces()
    return tuple(
        replace(g, name=space.name) for g in grants if spaces and (space := spaces.get(g.space_id))
    )


def require_whatsapp_sender(
    runtime: WhatsAppRuntime = Depends(require_whatsapp_surface),  # noqa: B008
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> WhatsAppSenderContext:
    link = runtime.intake.store.destination_link(destination_owner_id=context.user_id)
    return WhatsAppSenderContext(runtime, context.user_id, link)

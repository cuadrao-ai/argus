"""Document extraction wiring and registered-owner admission."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.dependencies import problem
from argus.api.document_jobs import (
    document_jobs,
    start_document_jobs,
    stop_document_jobs,
)
from argus.api.financial_accounts import (
    FinancialAccountsContext,
    require_financial_accounts_context,
)
from argus.api.ingestion import (
    IngestionContext,
    connection_problem,
    ingestion_enabled,
    ingestion_hub,
    require_ingestion_context,
    require_ingestion_surface,
    unavailable_problem,
)
from argus.api.rate_limits import SlidingWindowLimiter
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.documents.config import (
    SOURCE_MEDIA_TYPES,
    DocumentExtractionSettings,
    load_document_extraction_settings,
    load_document_job_settings,
)
from argus.domain.ingestion.documents.extractor import DocumentExtractor
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import PERSONAL, OwnerScope

NO_STORE = {"Cache-Control": "no-store"}
_service: DocumentsService | None = None
_minute = SlidingWindowLimiter()
_day = SlidingWindowLimiter()


def documents_service() -> DocumentsService | None:
    return _service


def configure_documents(service: DocumentsService | None) -> None:
    global _service
    stop_document_jobs()
    _service = service
    _minute.reset()
    _day.reset()


def start_documents(app: object, hub: IngestionHub | None) -> None:
    if hub is None:
        configure_documents(None)
        return
    try:
        _start_documents(app, hub)
    except Exception as exc:
        logger.warning(
            "Document surface failed to start; other connectors stay available",
            failure_mode=type(exc).__name__,
        )
        configure_documents(None)


def _start_documents(app: object, hub: IngestionHub) -> None:
    # Register cleanup even when extraction is off, so disconnect still erases it.
    service = _service_over(app, hub, DocumentExtractor())
    configure_documents(service)
    jobs = load_document_job_settings()
    if service is not None and jobs.enabled:
        start_document_jobs(service, jobs)


def start_saved_documents(app: object, hub: IngestionHub | None) -> None:
    """Ingestion is off: reading and removal only. No job starts and the
    extractor is switched off, so nothing here can reach a model."""

    configure_documents(
        None
        if hub is None
        else _service_over(
            app, hub, DocumentExtractor(DocumentExtractionSettings(enabled=False))
        )
    )


def _service_over(
    app: object, hub: IngestionHub, extractor: DocumentExtractor
) -> DocumentsService | None:
    pool = getattr(getattr(app, "state", None), "financial_accounts_pool", None)
    if api_state.PERSISTENCE_MODE == "supabase":
        gateway = api_state.supabase_gateway
        if pool is None or gateway is None:
            return None
        from argus.domain.ingestion.documents.objects import SupabaseSourceObjects
        from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore

        store = PostgresDocumentStore(pool, SupabaseSourceObjects(gateway.client.storage))
    else:
        store = InMemoryDocumentStore(hub.connections)
    # With jobs on, an expired attempt waits for the job reconciler, which
    # resumes it once intake is back; a read never settles it.
    from argus.domain.business.actions import BusinessActions
    from argus.domain.ingestion.reconcile.service import ReconciliationService

    actions = (
        BusinessActions(pool, hub.sink)
        if pool is not None and isinstance(hub.sink, ReconciliationService)
        else None
    )
    return DocumentsService(
        hub,
        store,
        extractor,
        jobs_recover_interruptions=load_document_job_settings().enabled,
        business_actions=actions,
    )


def require_saved_documents(request: Request) -> DocumentsService:
    """Reading and removing what the owner saved outlives every intake flag.

    Checked before authentication, so a missing service looks absent."""

    service = documents_service()
    if service is None:
        raise unavailable_problem(request)
    return service


def require_document_surface(
    request: Request,
    hub: IngestionHub = Depends(require_ingestion_surface),  # noqa: B008
) -> DocumentsService:
    service = documents_service()
    if (
        not load_document_extraction_settings().enabled
        or service is None
        or service.hub is not hub
    ):
        raise unavailable_problem(request)
    return service


@dataclass(frozen=True)
class DocumentContext:
    service: DocumentsService
    user_id: str


def require_saved_document_context(
    service: DocumentsService = Depends(require_saved_documents),  # noqa: B008
    accounts: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> DocumentContext:
    return DocumentContext(service, accounts.user_id)


def require_removal_surface(request: Request) -> tuple[IngestionHub, bool]:
    """The hub a disconnect goes through, and whether it may end only a
    document: with ingestion off no connector is running to revoke a grant."""

    hub = ingestion_hub()
    if ingestion_enabled() and hub is not None:
        return hub, False
    return require_saved_documents(request).hub, True


def require_connection_removal(
    request: Request,
    connection_id: str,
    surface: tuple[IngestionHub, bool] = Depends(require_removal_surface),  # noqa: B008
    accounts: FinancialAccountsContext = Depends(require_financial_accounts_context),  # noqa: B008
) -> IngestionContext:
    hub, documents_only = surface
    if documents_only:
        try:
            row = hub.connections.get(
                user_id=accounts.user_id, connection_id=connection_id, scope=PERSONAL
            )
        except ConnectionNotFound as error:
            raise connection_problem(request, error) from None
        if row.source != DocumentsService.source:
            raise unavailable_problem(request)
    return IngestionContext(hub=hub, user_id=accounts.user_id)


def require_document_context(
    request: Request,
    service: DocumentsService = Depends(require_document_surface),  # noqa: B008
    context: IngestionContext = Depends(require_ingestion_context),  # noqa: B008
) -> DocumentContext:
    limits = ((_minute, 5, 60), (_day, 30, 86400)) if request.method == "POST" else ()
    for limiter, limit, seconds in limits:
        retry = limiter.record_or_retry_after(
            keys=(context.user_id,), limit=limit, window_seconds=seconds
        )
        if retry is not None:
            raise problem(
                request,
                status_code=429,
                code="document_rate_limited",
                title="Too Many Requests",
                detail="Wait before uploading another document.",
                headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
            )
    return DocumentContext(service, context.user_id)


async def read_document_upload(request: Request) -> tuple[str, bytes]:
    """The media type and bounded raw bytes of an upload request body."""

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if media_type not in SOURCE_MEDIA_TYPES:
        raise problem(
            request,
            status_code=415,
            code="document_media_type_unsupported",
            title="Unsupported document",
            detail="Upload a PDF, JPEG or PNG file.",
            headers=NO_STORE,
        )
    limit = load_document_extraction_settings().max_bytes
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise problem(
                request,
                status_code=413,
                code="document_too_large",
                title="Document too large",
                detail=f"Upload a document of at most {limit / 1048576:g} MiB.",
                headers=NO_STORE,
            )
        content.extend(chunk)
    return media_type, bytes(content)


def document_filename(header: str | None) -> str:
    """``X-Document-Filename`` is percent-encoded UTF-8 (``encodeURIComponent``),
    which is pure ASCII. Anything else is raw UTF-8, read by the server as
    latin-1: it is recovered and never percent-decoded, and bytes that are not
    UTF-8 become replacement characters rather than mojibake."""

    if not header:
        return "document"
    if header.isascii():
        return unquote(header, errors="replace")
    return header.encode("latin-1").decode("utf-8", errors="replace")


async def dispatch_preparation(
    service: DocumentsService,
    user_id: str,
    connection_id: str,
    background_tasks: BackgroundTasks,
    *,
    scope: OwnerScope,
) -> None:
    """A durable attempt when preparation jobs are on, else a background task.

    A job reads its scope from the connection; the background task is told it.
    """

    from uuid import UUID

    from argus.domain.business.transactions import GrantImportStore
    from argus.domain.owner_scope import space_id

    if space_id(scope) is not None:
        imports = getattr(service.hub.sink, "store", None)
        if service.business_actions is None or not isinstance(imports, GrantImportStore):
            raise DocumentServiceError("business_preparation_unavailable")
        service.business_actions.capture_attachment_preparation(
            imports.context,
            UUID(connection_id),
            target=None,
        )
    jobs = document_jobs()
    if jobs is None:
        background_tasks.add_task(
            service.background_prepare,
            user_id=user_id,
            connection_id=connection_id,
            scope=scope,
        )
        return
    # Recorded before the response, so a closed client cannot lose the intake.
    await asyncio.to_thread(jobs.start, user_id=user_id, connection_id=connection_id)


def document_problem(request: Request, error: Exception) -> HTTPException:
    if isinstance(error, ConnectionNotFound):
        return problem(
            request,
            status_code=404,
            code="financial_document_not_found",
            title="Not Found",
            detail="No such document.",
            headers=NO_STORE,
        )
    if isinstance(error, (DocumentServiceError, DocumentExtractionError)):
        unavailable = error.retryable or error.code in {
            "missing_vision_model",
            "missing_api_key",
            "document_tools_unavailable",
        }
        status = 503 if unavailable else 422
        if error.code in {
            "document_busy",
            "document_version_conflict",
            "document_entered_by_owner",
            "document_already_prepared",
        }:
            status = 409
        if error.code == "document_disconnected":
            status = 410
        return problem(
            request,
            status_code=status,
            code=error.code,
            title="Document unavailable" if unavailable else "Document needs attention",
            detail="The document could not be prepared for review. Retry or upload a clearer copy.",
            headers=NO_STORE,
        )
    return problem(
        request,
        status_code=503,
        code="document_extraction_unavailable",
        title="Document unavailable",
        detail="Document extraction is temporarily unavailable.",
        headers=NO_STORE,
    )

"""Render Workflow worker for one document preparation attempt (#823).

The task input is ``[connection_id, attempt_id]``; the owner comes from the
stored row, never from the input. The worker runs the same ``run_attempt`` as
the API's in-process fallback and never dispatches: retries and dead-worker
recovery belong to the API's reconciler sweep.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone

from argus.domain.business.actions import BusinessActions
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.extractor import DocumentExtractor
from argus.domain.ingestion.documents.jobs import run_attempt
from argus.domain.ingestion.documents.objects import (
    SourceObjects,
    SupabaseSourceObjects,
)
from argus.domain.ingestion.documents.service import DocumentsService, Extractor
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.postgres_repository import (
    PostgresFinancialAccountRepository,
)
from argus.domain.recording.service import FinancialAccountService
from psycopg_pool import ConnectionPool


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def storage_source_objects(env: Mapping[str, str] | None = None) -> SourceObjects:
    """The private source bucket through the service role, as the API reaches it."""
    from argus.domain.supabase_gateway import _supabase_client_options

    from supabase import create_client

    source = os.environ if env is None else env
    url = source.get("SUPABASE_URL") or source.get("SUPABASE_PROJECT_URL")
    key = source.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "The document worker reads sources from Storage and needs "
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    client = create_client(url, key, options=_supabase_client_options())
    return SupabaseSourceObjects(client.storage)


def postgres_documents_service(
    pool: ConnectionPool,
    objects: SourceObjects,
    extractor: Extractor | None = None,
) -> DocumentsService:
    """The API's durable document graph: connections, sink, checkpoint, the
    canonical Business bridge and the owner's stored reading setting."""
    connections = PostgresConnectionRepository(pool)
    sink = ReconciliationService(
        PostgresImportStore(pool),
        MoneyService(FinancialAccountService(PostgresFinancialAccountRepository(pool))),
        _clock,
        connections=connections,
    )
    hub = IngestionHub(connections, box=None, sink=sink, clock=_clock)
    service = DocumentsService(
        hub,
        PostgresDocumentStore(pool, objects),
        extractor or DocumentExtractor(),
        jobs_recover_interruptions=True,
        business_actions=BusinessActions(pool, sink),
        business_preparation_required=True,
    )
    service.business_receipt_consent = BusinessReceiptConsentStore(pool)
    return service


async def run_document_preparation(
    connection_id: str,
    attempt_id: str,
    *,
    env: Mapping[str, str] | None = None,
    objects: SourceObjects | None = None,
    extractor: Extractor | None = None,
) -> dict[str, str]:
    # Imported per run, as main.py's siblings are, so importing main.py never
    # depends on proof.py's names.
    try:
        from workflows.proof import require_database_url
    except ModuleNotFoundError:  # pragma: no cover - `python workflows/main.py`
        from proof import require_database_url

    objects = objects if objects is not None else storage_source_objects(env)
    with ConnectionPool(
        require_database_url(env),
        min_size=0,
        max_size=2,
        kwargs={"prepare_threshold": None},
    ) as pool:
        outcome = await run_attempt(
            postgres_documents_service(pool, objects, extractor),
            connection_id,
            attempt_id,
        )
    return {"connection_id": connection_id, "attempt_id": attempt_id, "outcome": outcome}

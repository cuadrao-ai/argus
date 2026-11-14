"""A standalone document reader: ``python -m workflows.document_worker``.

It is the only process that reads receipts: the API records each read as an
attempt on its row and never reads it. Every worker pulls under the same
``max_reads`` cap. SIGTERM stops the pulls and gives reads in flight
``drain_seconds``. Its sweep loop also purges, at most once an hour, the
documents that spent their days in Eliminados.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import timedelta

from argus.domain.business.actions.document_purge import DocumentExpiry
from argus.domain.connection_budget import worker_pool_max
from argus.domain.ingestion.documents.config import load_document_job_settings
from argus.domain.ingestion.documents.worker import DocumentWorker
from argus.log_sink import configure_logging
from psycopg_pool import ConnectionPool

from workflows.document_job import postgres_documents_service, storage_source_objects
from workflows.proof import require_database_url


async def serve() -> None:
    settings = load_document_job_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    with ConnectionPool(
        require_database_url(),
        min_size=0,
        max_size=worker_pool_max(settings.max_reads),
        kwargs={"prepare_threshold": None},
    ) as pool:
        objects = storage_source_objects()
        service = postgres_documents_service(pool, objects)
        expiry = DocumentExpiry(
            pool, objects, every=timedelta(seconds=settings.purge_every_seconds)
        )
        await DocumentWorker(service, settings, expiry.tick).run(stop)


def main() -> None:
    configure_logging()
    asyncio.run(serve())


if __name__ == "__main__":
    main()

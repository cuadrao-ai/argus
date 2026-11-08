"""A standalone document reader: ``python -m workflows.document_worker``.

It is the only process that reads receipts: the API records each read as an
attempt on its row and never reads it. Every worker pulls under the same
``max_reads`` cap. SIGTERM stops the pulls and gives reads in flight
``drain_seconds``.
"""

from __future__ import annotations

import asyncio
import signal

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
        max_size=settings.max_reads + 2,
        kwargs={"prepare_threshold": None},
    ) as pool:
        service = postgres_documents_service(pool, storage_source_objects())
        await DocumentWorker(service, settings).run(stop)


def main() -> None:
    configure_logging()
    asyncio.run(serve())


if __name__ == "__main__":
    main()

"""A standalone document reader: ``python -m workflows.document_worker``.

It is the only process that reads receipts: the API records each read as an
attempt on its row and never reads it. Every worker pulls under the same
``max_reads`` cap. SIGTERM stops the pulls and gives reads in flight
``drain_seconds``. Its sweep loop also purges, at most once an hour, the
documents that spent their days in Eliminados, and starts again, at most once
every ten minutes, the reads a spent Business read budget left waiting.
The same sweep sends grouped WhatsApp intake failures and expires reply state.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from datetime import timedelta

from argus.domain.business.actions.document_purge import DocumentExpiry
from argus.domain.connection_budget import worker_pool_max
from argus.domain.ingestion.documents.config import load_document_job_settings
from argus.domain.ingestion.documents.worker import DocumentWorker
from argus.domain.ingestion.whatsapp.document_step import FailureReplyUpkeep
from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups
from argus.llm.openrouter_key_policy import validate_hosted_openrouter_configuration
from argus.log_sink import configure_logging
from loguru import logger
from psycopg_pool import ConnectionPool

from workflows.document_job import postgres_documents_service, storage_source_objects
from workflows.proof import require_database_url
from workflows.read_resume import ReadResume


def in_turn(*passes: Callable[[], object]) -> Callable[[], None]:
    """One upkeep for the sweep loop. Each pass paces itself, and one that
    fails does not cost the next its turn."""

    def upkeep() -> None:
        for work in passes:
            try:
                work()
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Document upkeep pass failed",
                    work=getattr(work, "__qualname__", repr(work)),
                    failure_mode=type(error).__name__,
                )

    return upkeep


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
        replies = FailureReplyUpkeep(PostgresReplyGroups(pool), clock=service.hub.clock)
        upkeep = in_turn(
            expiry.tick, ReadResume(service).tick, replies.cleanup, replies.send_due
        )
        await DocumentWorker(service, settings, upkeep).run(stop)


def main() -> None:
    configure_logging()
    validate_hosted_openrouter_configuration()
    asyncio.run(serve())


if __name__ == "__main__":
    main()

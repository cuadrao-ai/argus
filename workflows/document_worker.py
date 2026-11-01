"""Plain background worker for document reads: ``python -m workflows.document_worker``.

It pulls waiting attempts from Postgres, oldest first, and runs each through the
same ``run_attempt`` as every other dispatch mode. ``max_reads`` caps reads at
once across all workers. The sweep runs here, because the API runs none in pull
mode. SIGTERM stops the pulls and gives reads in flight ``drain_seconds`` to
finish. A read that outlives it is cancelled, which releases its lease, and the
sweep recovers it as it recovers any dead worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from argus.domain.ingestion.documents.config import (
    DocumentJobSettings,
    load_document_extraction_settings,
    load_document_job_settings,
)
from argus.domain.ingestion.documents.jobs import (
    PreparationJobs,
    run_attempt,
    sweep_forever,
)
from argus.domain.ingestion.documents.service import DocumentsService
from argus.llm.openrouter_key_policy import validate_hosted_openrouter_configuration
from argus.log_sink import configure_logging
from loguru import logger
from psycopg_pool import ConnectionPool

from workflows.document_job import postgres_documents_service, storage_source_objects
from workflows.proof import require_database_url

POLL_SECONDS = 1.0
# How long a cancelled read gets to release its lease before the process exits.
CANCEL_SECONDS = 5.0


class DocumentWorker:
    def __init__(self, service: DocumentsService, settings: DocumentJobSettings) -> None:
        self.service, self.settings = service, settings
        self.reads: set[asyncio.Task[None]] = set()

    async def run(self, stop: asyncio.Event) -> None:
        jobs = PreparationJobs(self.service, None)
        sweeper = asyncio.create_task(sweep_forever(jobs, self.settings.sweep_seconds))
        logger.info("Document worker started max_reads={}", self.settings.max_reads)
        try:
            while not stop.is_set():
                await self._pull(stop)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), POLL_SECONDS)
        finally:
            sweeper.cancel()
        await self._drain()

    async def _pull(self, stop: asyncio.Event) -> None:
        # As in the sweep: with extraction off a queued read neither runs nor fails.
        if not load_document_extraction_settings().enabled:
            return
        store, clock = self.service.store, self.service.hub.clock
        while len(self.reads) < self.settings.max_reads and not stop.is_set():
            try:
                pulled = await asyncio.to_thread(
                    store.pull, now=clock(), cap=self.settings.max_reads
                )
            except Exception as error:
                logger.warning(
                    "Document read pull failed failure_mode={}", type(error).__name__
                )
                return
            if pulled is None:
                return
            read = asyncio.create_task(self._read(*pulled))
            self.reads.add(read)
            read.add_done_callback(self.reads.discard)

    async def _read(self, connection_id: str, attempt_id: str) -> None:
        outcome = await run_attempt(self.service, connection_id, attempt_id)
        logger.info(
            "Document read finished connection_id={} outcome={}", connection_id, outcome
        )

    async def _drain(self) -> None:
        if not self.reads:
            return
        _, late = await asyncio.wait(set(self.reads), timeout=self.settings.drain_seconds)
        if late:
            logger.warning("Document reads outlived the drain count={}", len(late))
            for read in late:
                read.cancel()
            await asyncio.wait(late, timeout=CANCEL_SECONDS)


async def serve() -> None:
    settings = load_document_job_settings()
    if not (settings.enabled and settings.pull):
        raise SystemExit("Document pull mode is off; reads stay where they run today.")
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
    validate_hosted_openrouter_configuration()
    asyncio.run(serve())


if __name__ == "__main__":
    main()

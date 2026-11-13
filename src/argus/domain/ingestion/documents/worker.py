"""The one way a queued receipt gets read: a loop that pulls waiting attempts.

Only ``python -m workflows.document_worker`` runs one; the API never does. Every
worker pulls from the same rows through ``store.pull``, which holds
``max_reads`` across every puller. A stop takes no new read, gives reads in
flight ``drain_seconds`` to finish and cancels the rest, which releases their
leases for the next boot's sweep.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from argus.domain.ingestion.documents.config import (
    CANCEL_SECONDS,
    DocumentJobSettings,
    load_document_extraction_settings,
)
from argus.domain.ingestion.documents.jobs import (
    PreparationJobs,
    run_attempt,
    sweep_forever,
)
from argus.domain.ingestion.documents.service import DocumentsService
from argus.observability.envelope import capture_exception

POLL_SECONDS = 1.0


class DocumentWorker:
    def __init__(self, service: DocumentsService, settings: DocumentJobSettings) -> None:
        self.service, self.settings = service, settings
        self.reads: set[asyncio.Task[str]] = set()

    async def run(self, stop: asyncio.Event) -> None:
        jobs = PreparationJobs(self.service)
        sweeper = asyncio.create_task(sweep_forever(jobs, self.settings.sweep_seconds))
        logger.info("Document worker started max_reads={}", self.settings.max_reads)
        delay = POLL_SECONDS
        try:
            while not stop.is_set():
                found = await self._pull(stop)
                if found or self.reads:
                    delay = POLL_SECONDS
                await self._nap(stop, delay)
                delay = min(delay * 2, self.settings.idle_poll_seconds)
        finally:
            sweeper.cancel()
            # Joins a sweep still on its thread. Waiting, not awaiting, so a
            # cancel of this loop is never mistaken for the sweeper's own.
            await asyncio.wait({sweeper})
        await self._drain()

    async def _nap(self, stop: asyncio.Event, seconds: float) -> None:
        waiting = asyncio.ensure_future(stop.wait())
        try:
            await asyncio.wait({waiting}, timeout=seconds)
        finally:
            waiting.cancel()

    async def _pull(self, stop: asyncio.Event) -> bool:
        # As in the sweep: with extraction off a queued read neither runs nor fails.
        if not load_document_extraction_settings().enabled:
            return False
        found = False
        store, clock = self.service.store, self.service.hub.clock
        while len(self.reads) < self.settings.max_reads and not stop.is_set():
            try:
                pulled = await asyncio.to_thread(
                    store.pull, now=clock(), cap=self.settings.max_reads
                )
            except Exception as error:
                capture_exception(error, job="document_read_pull")
                logger.warning(
                    "Document read pull failed failure_mode={}", type(error).__name__
                )
                return True  # Retry failures at the existing busy pace.
            if pulled is None:
                return found
            found = True
            read = asyncio.create_task(self._read(*pulled))
            self.reads.add(read)
            read.add_done_callback(self.reads.discard)
        return found

    async def _read(self, connection_id: str, attempt_id: str) -> str:
        outcome = await run_attempt(self.service, connection_id, attempt_id)
        logger.info(
            "Document read finished connection_id={} outcome={}", connection_id, outcome
        )
        return outcome

    async def _drain(self) -> None:
        if not self.reads:
            return
        _, late = await asyncio.wait(set(self.reads), timeout=self.settings.drain_seconds)
        if late:
            logger.warning("Document reads outlived the drain count={}", len(late))
            for read in late:
                read.cancel()
            await asyncio.wait(late, timeout=CANCEL_SECONDS)

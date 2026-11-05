"""Document reads in the API process: one puller per instance, and its sweep.

Every accepted preparation becomes a recorded attempt that waits on its row.
This process's ``DocumentWorker`` pulls it under ``max_reads``, the cap
``store.pull`` holds across every API instance and any standalone worker, and
runs the sweep that settles or requeues attempts whose process died, once at
startup and every ``sweep_seconds``. Shutdown stops the pulls, joins a running
sweep, gives reads in flight ``drain_seconds`` and cancels the rest; the host's
shutdown delay must cover the WhatsApp drain, that drain and ``CANCEL_SECONDS``.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from argus.domain.ingestion.documents.config import DocumentJobSettings
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.worker import DocumentWorker

_worker: DocumentWorker | None = None
_stop: asyncio.Event | None = None
_running: asyncio.Task[None] | None = None


def document_worker() -> DocumentWorker | None:
    return _worker


def start_document_jobs(service: DocumentsService, settings: DocumentJobSettings) -> None:
    global _worker, _stop, _running
    stop_document_jobs()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Document reads need a running event loop; attempts only wait")
        return
    _worker, _stop = DocumentWorker(service, settings), asyncio.Event()
    _running = loop.create_task(_worker.run(_stop))


async def wake_document_reads() -> None:
    """Runs on the loop once an attempt is recorded here: pull now, not at the
    next poll. Pullers in other processes take it at their own next poll."""
    if _worker is not None:
        _worker.wake()


async def drain_document_jobs() -> None:
    """Shutdown: the puller stops, joins its sweep and drains its reads."""
    global _running, _stop
    if _stop is not None:
        _stop.set()
    if _running is not None:
        await _running
    _running, _stop = None, None


def stop_document_jobs() -> None:
    global _worker, _stop, _running
    if _running is not None:
        _running.cancel()
    if _worker is not None:
        for read in list(_worker.reads):
            read.cancel()
    _worker, _stop, _running = None, None, None

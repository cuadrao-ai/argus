"""Default-off durable dispatch and recovery for document preparation (#823).

Settings are ``DocumentJobSettings`` (``ARGUS_DOCUMENT_JOBS_*``). Disabled
leaves the routes on FastAPI background tasks, exactly as before. Enabled, each
accepted preparation becomes a recorded attempt: a Render Workflow task when
``workflow_task`` is set in durable mode (the local Render dev server under
``RENDER_USE_LOCAL_DEV``), otherwise a task on this process's event loop. A
sweep in this process settles or re-dispatches attempts whose worker died, once
at startup and every ``sweep_seconds``.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from argus.api import state as api_state
from argus.domain.ingestion.documents.config import (
    DocumentJobSettings,
    load_document_extraction_settings,
)
from argus.domain.ingestion.documents.jobs import (
    Dispatch,
    PreparationJobs,
    run_attempt,
)
from argus.domain.ingestion.documents.service import DocumentsService

_jobs: PreparationJobs | None = None
_sweeper: asyncio.Task[None] | None = None


def document_jobs() -> PreparationJobs | None:
    return _jobs


class InProcessDispatcher:
    """Local fallback: each attempt runs as a task on the API's event loop."""

    def __init__(
        self, loop: asyncio.AbstractEventLoop, service: DocumentsService
    ) -> None:
        self.loop, self.service = loop, service
        self.tasks: set[asyncio.Task[str]] = set()

    def __call__(self, connection_id: str, attempt_id: str) -> None:
        self.loop.call_soon_threadsafe(self._spawn, connection_id, attempt_id)

    def _spawn(self, connection_id: str, attempt_id: str) -> None:
        task = self.loop.create_task(run_attempt(self.service, connection_id, attempt_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


def render_dispatcher(task_id: str) -> Dispatch:
    from argus.api.chat.backtest_jobs import RenderWorkflowDispatcher

    dispatcher = RenderWorkflowDispatcher(task_id=task_id)

    def dispatch(connection_id: str, attempt_id: str) -> None:
        run = dispatcher.dispatch(job_id=connection_id, nonce=attempt_id)
        logger.info(
            "Document preparation dispatched",
            connection_id=connection_id,
            task_run_id=run.get("id"),
        )

    return dispatch


async def sweep_forever(jobs: PreparationJobs, interval: float) -> None:
    """Waits while extraction is off: a queued draft is then neither sent to
    the model nor failed, and resumes when extraction is back."""

    while True:
        try:
            if load_document_extraction_settings().enabled:
                await asyncio.to_thread(jobs.sweep)
        except Exception as error:
            logger.warning(
                "Document preparation sweep failed",
                failure_mode=type(error).__name__,
            )
        await asyncio.sleep(interval)


def start_document_jobs(service: DocumentsService, settings: DocumentJobSettings) -> None:
    global _jobs, _sweeper
    stop_document_jobs()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Document jobs need a running event loop; jobs stay off")
        return
    task_id = settings.workflow_task.strip()
    dispatch: Dispatch = (
        render_dispatcher(task_id)
        if task_id and api_state.PERSISTENCE_MODE == "supabase"
        else InProcessDispatcher(loop, service)
    )
    _jobs = PreparationJobs(service, dispatch)
    _sweeper = loop.create_task(sweep_forever(_jobs, settings.sweep_seconds))


def stop_document_jobs() -> None:
    global _jobs, _sweeper
    if _sweeper is not None:
        _sweeper.cancel()
    if _jobs is not None and isinstance(_jobs.dispatch, InProcessDispatcher):
        for task in list(_jobs.dispatch.tasks):
            task.cancel()
    _jobs, _sweeper = None, None

"""Durable document preparation: bounded attempts that recover a dead worker.

The API records one attempt per accepted preparation and leaves it on its row,
where a puller (``worker.DocumentWorker``) takes it. An attempt no process has
taken is waiting, however old, and costs nothing. A reconciler sweep requeues
an attempt whose worker died when the attempt provably never reached the
provider (no ``provider_call_started_at``), up to ``MAX_ATTEMPTS``.
An attempt that died past its provider marker with no saved result (a deploy,
a restart or a crash mid-read) is run again once, ``MAX_RERUNS``, as a new paid
attempt through the same admission; a rerun that dies the same way settles to
``needs_attention`` and only the owner's consented prepare or resume starts a
new paid attempt. The extractor's own second call when the provider times out
is made inside the same attempt under its lease. A superseded attempt cannot
claim the draft, and its late result is refused by the connection lease, so a
receipt is saved once however many attempts complete.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from argus.domain.ingestion.connections import (
    DEFAULT_LEASE,
    ConnectionNotFound,
    SourceConnection,
)
from argus.domain.ingestion.documents.config import load_document_extraction_settings
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    DocumentExtractionError,
    PreparationJob,
)
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
    lease_live,
)
from argus.observability.envelope import capture_exception
from argus.observability.product_events import actor_hash_for_user

MAX_ATTEMPTS = 3
MAX_RERUNS = 1
OUTCOME_UNKNOWN = "document_preparation_outcome_unknown"
# A pulled attempt that never claimed is presumed lost after the same window a
# lease lasts.
DISPATCH_WINDOW = DEFAULT_LEASE


def in_flight(
    draft: DocumentDraft,
    job: PreparationJob | None,
    connection: SourceConnection,
    now: datetime,
) -> bool:
    """The one liveness oracle: a held lease, an attempt no puller has taken
    yet however old, or a queued draft whose take (or, before any attempt,
    whose queueing) is younger than the window. An attempt recorded for an
    older draft version can never claim, so it is not in flight."""
    if lease_live(connection, now):
        return True
    if draft.status != "queued" or (job is not None and not dispatched(draft, job)):
        return False
    anchor = job.dispatched_at if job is not None else draft.updated_at
    return anchor is None or anchor + DISPATCH_WINDOW > now


def dispatched(draft: DocumentDraft, job: PreparationJob | None) -> bool:
    return job is not None and job.draft_version == draft.version


@dataclass
class SweepReport:
    redispatched: list[str] = field(default_factory=list)
    rerun: list[str] = field(default_factory=list)
    exhausted: list[str] = field(default_factory=list)
    outcome_unknown: list[str] = field(default_factory=list)
    errors: int = 0


def own_claim(draft: DocumentDraft, job: PreparationJob | None) -> bool:
    """The current attempt wrote this ``preparing`` draft: it claimed the draft,
    and the draft moved exactly once since the version it was dispatched for."""
    return job is not None and job.claimed and draft.version == job.draft_version + 1


class PreparationJobs:
    """The row is the queue: every waiting attempt keeps its draft ``queued``
    until a puller takes it."""

    def __init__(self, service: DocumentsService) -> None:
        self.service = service

    def start(self, *, user_id: str, connection_id: str) -> None:
        """Record a fresh preparation unless an attempt is already in flight."""
        store, now = self.service.store, self.service.hub.clock()
        draft = store.draft(user_id=user_id, connection_id=connection_id)
        if draft is None:
            return
        connection = self.service.hub.connections.get_any_scope(
            user_id=user_id, connection_id=connection_id
        )
        job = store.job(user_id=user_id, connection_id=connection_id)
        if lease_live(connection, now) or (
            dispatched(draft, job) and in_flight(draft, job, connection, now)
        ):
            return
        if (
            draft.status != "queued"
            and store.get(user_id=user_id, connection_id=connection_id) is None
        ):
            return
        # A saved read with no source is never pulled, so it keeps its status.
        self._advance(
            user_id, connection_id, now, job, draft, attempt=1, requeue=draft.source_available
        )

    def sweep(self, *, limit: int = 50) -> SweepReport:
        report, now = SweepReport(), self.service.hub.clock()
        for user_id, connection_id in self.service.store.pending(limit=limit):
            try:
                self._reconcile(user_id, connection_id, now, report)
            except ConnectionNotFound:
                continue
            except Exception as error:
                report.errors += 1
                logger.warning(
                    "Document preparation reconcile failed",
                    connection_id=connection_id,
                    failure_mode=type(error).__name__,
                )
        return report

    def _reconcile(
        self, user_id: str, connection_id: str, now: datetime, report: SweepReport
    ) -> None:
        store = self.service.store
        draft = store.draft(user_id=user_id, connection_id=connection_id)
        job = store.job(user_id=user_id, connection_id=connection_id)
        connection = self.service.hub.connections.get_any_scope(
            user_id=user_id, connection_id=connection_id
        )
        if draft is None:
            return
        if draft.status in {"queued", "preparing"}:
            if in_flight(draft, job, connection, now):
                return
            reason = "unclaimed" if draft.status == "queued" else "interrupted"
        elif draft.status == "needs_attention" and job is not None and job.retry:
            reason = "retryable_failure"
        else:
            return
        saved = store.get(user_id=user_id, connection_id=connection_id) is not None
        mine = own_claim(draft, job)
        if draft.status == "preparing" and not saved and not (
            mine and job.provider_call_started_at is None
        ):
            # The provider may have been reached. The current attempt's own
            # read is run again once, paid again; any other writer's is not.
            if mine and job.reruns < MAX_RERUNS:
                if self._advance(
                    user_id,
                    connection_id,
                    now,
                    job,
                    draft,
                    attempt=job.attempt + 1,
                    requeue=True,
                    reruns=job.reruns + 1,
                ):
                    report.rerun.append(connection_id)
                    logger.warning(
                        "Document preparation rerun after an interrupted provider call",
                        connection_id=connection_id,
                        attempt=job.attempt + 1,
                        reason=reason,
                    )
                return
            if self._settle(user_id, connection_id, now, job, draft, OUTCOME_UNKNOWN):
                report.outcome_unknown.append(connection_id)
                logger.warning(
                    "Document preparation outcome unknown; waiting for the owner",
                    connection_id=connection_id,
                    attempt=job.attempt if job is not None else None,
                    reason=reason,
                )
            return
        # A waiting attempt is in flight, so a queued draft here has no attempt
        # for its version and never ran.
        fresh = job is None or (draft.status == "queued" and not dispatched(draft, job))
        attempt = 1 if fresh or job is None else job.attempt + 1
        if attempt <= MAX_ATTEMPTS:
            if self._advance(
                user_id,
                connection_id,
                now,
                job,
                draft,
                attempt=attempt,
                requeue=True,
                # A saved preparation replays without a provider call.
                unmarked=not fresh and not saved,
                reruns=0 if fresh or job is None else job.reruns,
            ):
                report.redispatched.append(connection_id)
                logger.info(
                    "Document preparation redispatched",
                    connection_id=connection_id,
                    attempt=attempt,
                    reason=reason,
                )
            return
        assert job is not None
        if self._settle(
            user_id,
            connection_id,
            now,
            job,
            draft,
            "document_preparation_interrupted",
        ):
            report.exhausted.append(connection_id)
            logger.warning(
                "Document preparation attempts exhausted",
                connection_id=connection_id,
                attempt=job.attempt,
                reason=reason,
            )

    def _settle(
        self,
        user_id: str,
        connection_id: str,
        now: datetime,
        job: PreparationJob | None,
        draft: DocumentDraft,
        code: str,
    ) -> bool:
        """End automatic work on this attempt; the owner decides what is next."""
        settled = (
            None
            if draft.status == "needs_attention"
            else self.service.revise(draft, status="needs_attention", error_code=code)
        )
        if job is None:
            return settled is not None and self.service.store.update(
                user_id=user_id, draft=settled, expected_version=draft.version
            )
        return self.service.store.advance(
            user_id=user_id,
            connection_id=connection_id,
            now=now,
            expected_attempt_id=job.attempt_id,
            job=job.model_copy(update={"retry": False}),
            draft=settled,
        )

    def _advance(
        self,
        user_id: str,
        connection_id: str,
        now: datetime,
        job: PreparationJob | None,
        draft: DocumentDraft,
        *,
        attempt: int,
        requeue: bool,
        unmarked: bool = False,
        reruns: int = 0,
    ) -> bool:
        """Make a new attempt current and leave it for a puller. A sweep also
        returns an interrupted or failed draft to ``queued``."""
        requeued = (
            self.service.revise(draft, status="queued", error_code=None)
            if requeue and draft.status != "queued"
            else None
        )
        nxt = PreparationJob(
            attempt=attempt,
            attempt_id=str(uuid.uuid4()),
            draft_version=(requeued or draft).version,
            reruns=reruns,
        )
        return self.service.store.advance(
            user_id=user_id,
            connection_id=connection_id,
            now=now,
            expected_attempt_id=job.attempt_id if job is not None else None,
            job=nxt,
            draft=requeued,
            unmarked=unmarked,
        )


async def sweep_forever(jobs: PreparationJobs, interval: float) -> None:
    """Waits while extraction is off: a queued draft is then neither sent to
    the model nor failed, and resumes when extraction is back."""

    while True:
        try:
            if load_document_extraction_settings().enabled:
                sweep = asyncio.ensure_future(asyncio.to_thread(jobs.sweep))
                try:
                    await asyncio.shield(sweep)
                except asyncio.CancelledError:
                    # A cancel cannot stop the thread, so a stopping process
                    # waits for the sweep to return before it drains reads.
                    # The cancel wins over whatever that sweep raises: awaiting
                    # it would raise its error, which the loop below swallows.
                    await asyncio.wait({sweep})
                    if not sweep.cancelled() and sweep.exception() is not None:
                        logger.warning(
                            "Document preparation sweep failed while stopping",
                            failure_mode=type(sweep.exception()).__name__,
                        )
                    raise
        except Exception as error:
            logger.warning(
                "Document preparation sweep failed",
                failure_mode=type(error).__name__,
            )
        await asyncio.sleep(interval)


async def run_attempt(
    service: DocumentsService, connection_id: str, attempt_id: str
) -> str:
    """A puller's entry point for the attempt it took."""
    user_id = service.store.owner(connection_id=connection_id)
    if user_id is None:
        return "gone"
    try:
        # The job is keyed by its connection, so the draft keeps that scope.
        scope = service.hub.connections.get_any_scope(
            user_id=user_id, connection_id=connection_id
        ).scope
    except ConnectionNotFound:
        return "gone"
    try:
        await service.resume(
            user_id=user_id,
            connection_id=connection_id,
            queued_only=True,
            attempt_id=attempt_id,
            scope=scope,
        )
        return "prepared"
    except (DocumentServiceError, DocumentExtractionError) as error:
        if not error.retryable:
            return error.code
        job = service.store.job(user_id=user_id, connection_id=connection_id)
        if (
            job is not None
            and job.attempt_id == attempt_id
            and job.provider_call_started_at is None
        ):
            service.store.advance(
                user_id=user_id,
                connection_id=connection_id,
                now=service.hub.clock(),
                expected_attempt_id=attempt_id,
                job=job.model_copy(update={"retry": True}),
            )
        return error.code
    except Exception as error:
        from argus.domain.business.authority import ActionError

        if not isinstance(error, ActionError):
            capture_exception(
                error, job="document_preparation", actor_hash=actor_hash_for_user(user_id)
            )
        logger.warning(
            "Document preparation attempt failed",
            connection_id=connection_id,
            failure_mode=type(error).__name__,
        )
        return "document_extraction_failed"

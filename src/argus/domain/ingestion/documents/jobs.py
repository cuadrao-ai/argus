"""Durable document preparation: bounded attempts that recover a dead worker.

The API dispatches one attempt per accepted preparation. A reconciler sweep
re-dispatches an attempt whose worker died only when the attempt provably never
reached the provider (no ``provider_call_started_at``), up to ``MAX_ATTEMPTS``.
An attempt that may have reached the provider is never billed again
automatically: it settles to ``needs_attention`` and only the owner's consented
prepare or resume starts a new paid attempt. A superseded attempt cannot claim
the draft, and its late result is refused by the connection lease.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from argus.domain.ingestion.connections import (
    DEFAULT_LEASE,
    ConnectionNotFound,
    SourceConnection,
)
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

MAX_ATTEMPTS = 3
OUTCOME_UNKNOWN = "document_preparation_outcome_unknown"
# An unclaimed dispatch is presumed lost after the same window a lease lasts.
DISPATCH_WINDOW = DEFAULT_LEASE

Dispatch = Callable[[str, str], None]
"""Start ``(connection_id, attempt_id)`` on a worker; return once handed off."""


def in_flight(
    draft: DocumentDraft,
    job: PreparationJob | None,
    connection: SourceConnection,
    now: datetime,
) -> bool:
    """The one liveness oracle: a held lease, or a queued draft whose dispatch
    (or, before any dispatch, whose queueing) is younger than the window. An
    attempt dispatched for an older draft version can never claim, so it is
    not in flight."""
    if lease_live(connection, now):
        return True
    if draft.status != "queued" or (job is not None and not dispatched(draft, job)):
        return False
    anchor = job.dispatched_at if job is not None else draft.updated_at
    return anchor + DISPATCH_WINDOW > now


def dispatched(draft: DocumentDraft, job: PreparationJob | None) -> bool:
    return job is not None and job.draft_version == draft.version


@dataclass
class SweepReport:
    redispatched: list[str] = field(default_factory=list)
    exhausted: list[str] = field(default_factory=list)
    outcome_unknown: list[str] = field(default_factory=list)
    errors: int = 0


class PreparationJobs:
    def __init__(self, service: DocumentsService, dispatch: Dispatch) -> None:
        self.service, self.dispatch = service, dispatch

    def start(self, *, user_id: str, connection_id: str) -> None:
        """Dispatch a fresh preparation unless an attempt is already in flight."""
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
        self._advance(user_id, connection_id, now, job, draft, attempt=1, requeue=False)

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
        if (
            draft.status == "preparing"
            and not saved
            and not (
                # Only the current attempt's own claim, before any provider call.
                job is not None
                and job.claimed
                and draft.version == job.draft_version + 1
                and job.provider_call_started_at is None
            )
        ):
            if self._settle(user_id, connection_id, now, job, draft, OUTCOME_UNKNOWN):
                report.outcome_unknown.append(connection_id)
                logger.warning(
                    "Document preparation outcome unknown; waiting for the owner",
                    connection_id=connection_id,
                    attempt=job.attempt if job is not None else None,
                    reason=reason,
                )
            return
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
    ) -> bool:
        """Make a new attempt current, then hand it to a worker. A sweep also
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
            dispatched_at=now,
        )
        if not self.service.store.advance(
            user_id=user_id,
            connection_id=connection_id,
            now=now,
            expected_attempt_id=job.attempt_id if job is not None else None,
            job=nxt,
            draft=requeued,
            unmarked=unmarked,
        ):
            return False
        try:
            self.dispatch(connection_id, nxt.attempt_id)
        except Exception as error:
            # The job is durable: the sweep re-dispatches once the window passes.
            logger.warning(
                "Document preparation dispatch failed",
                connection_id=connection_id,
                attempt=nxt.attempt,
                failure_mode=type(error).__name__,
            )
        return True


async def run_attempt(
    service: DocumentsService, connection_id: str, attempt_id: str
) -> str:
    """Worker entry point, in process or in a Render Workflow task."""
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
        logger.warning(
            "Document preparation attempt failed",
            connection_id=connection_id,
            failure_mode=type(error).__name__,
        )
        return "document_extraction_failed"

"""``/transactions/sync`` for one connection, safe under retries and races.

Order that keeps evidence and the cursor truthful:

1. Refuse before touching the provider when there is no candidate sink.
2. Take the connection lease; a second webhook or a retried delivery for the
   same Item finds it held and returns ``busy``.
3. Page with ``has_more`` from the cursor the sync started with, renewing the
   lease (held-only ``renew``) before every page. A lease lost meanwhile (a webhook recorded
   ``needs_reauth``, which releases it) stops the sync as ``superseded``. On
   ``TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION`` restart the whole loop from
   that same starting cursor, as Plaid requires (bounded attempts).
4. Hand every page's candidates to the sink in one batch.
5. Only then advance the cursor with ``record_success`` (compare-and-set on the
   starting cursor). A sink failure, ignored candidates or a lost race leave
   the cursor alone, so the same changes are fetched again and the idempotent
   sink absorbs them.

Only a complete update (``has_more`` false) is ever handed over or persisted:
a mid-update cursor is never stored, so a later mutation restart can never
mistake it for the update's starting cursor. If the page cap or the time
bound is reached first, the sync records ``plaid_sync_incomplete`` (status
kept) and hands nothing over.

Provider failures are recorded with an actionable code; ``last_success_at``
and the cursor are never cleared by a failure.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from loguru import logger

from argus.domain.ingestion.connections import ConnectionNotFound, SourceConnection
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.candidates import build_candidates
from argus.domain.ingestion.plaid.client import PlaidClient, PlaidError
from argus.domain.ingestion.plaid.failures import MUTATION_DURING_PAGINATION, meaning
from argus.domain.owner_scope import PERSONAL

SyncStatus = Literal[
    "synced", "not_ready", "busy", "no_sink", "failed", "sink_failed", "superseded"
]
PAGE_SIZE = 500
# 200 pages of 500 is 100,000 changes in one update, beyond two years of
# history for a household; the time bound keeps the run inside its lease.
MAX_PAGES = 200
MAX_SECONDS = 8 * 60
MAX_RESTARTS = 3
LEASE_TTL = timedelta(minutes=10)
CREDENTIAL_UNAVAILABLE = "plaid_credential_unavailable"
INCOMPLETE = "plaid_sync_incomplete"


@dataclass(frozen=True)
class SyncOutcome:
    status: SyncStatus
    added: int = 0
    modified: int = 0
    removed: int = 0
    pending: int = 0
    posted: int = 0
    replacing: int = 0
    skipped: int = 0
    skipped_accounts: int = 0
    pages: int = 0
    restarts: int = 0
    error_code: str | None = None


@dataclass
class _Pages:
    payloads: list[dict[str, Any]] = field(default_factory=list)
    cursor: str | None = None
    restarts: int = 0


class _Incomplete(Exception):
    pass


class _LeaseLost(Exception):
    pass


class PlaidSync:
    def __init__(
        self,
        hub: IngestionHub,
        client: PlaidClient,
        *,
        page_size: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES,
        max_seconds: float = MAX_SECONDS,
        max_restarts: int = MAX_RESTARTS,
        holder: Callable[[], str] = lambda: uuid.uuid4().hex,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hub = hub
        self.client = client
        self.page_size = max(1, min(page_size, PAGE_SIZE))
        self.max_pages = max_pages
        self.max_seconds = max_seconds
        self.max_restarts = max_restarts
        self.timer = timer
        self._holder = holder

    def sync(self, connection: SourceConnection) -> SyncOutcome:
        sink = self.hub.sink
        if sink is None:
            return SyncOutcome("no_sink")
        repo = self.hub.connections
        holder = self._holder()
        if not repo.lease(
            connection_id=connection.id,
            holder=holder,
            now=self.hub.clock(),
            ttl=LEASE_TTL,
        ):
            return SyncOutcome("busy")
        try:
            try:
                current = repo.get(
                    user_id=connection.user_id,
                    connection_id=connection.id,
                    scope=PERSONAL,
                )
            except ConnectionNotFound:
                return SyncOutcome("busy")
            return self._run(current, holder, sink)
        finally:
            repo.release(connection_id=connection.id, holder=holder)

    def _run(self, current: SourceConnection, holder: str, sink) -> SyncOutcome:  # noqa: ANN001
        try:
            token = self.hub.credential(current)
        except Exception:
            token = None
        if not token:
            self._fail(current, holder, CREDENTIAL_UNAVAILABLE, "error")
            return SyncOutcome("failed", error_code=CREDENTIAL_UNAVAILABLE)
        start = current.cursor
        try:
            pages = self._fetch(current, holder, token, start)
            changes = sum(len(p.get(k) or ()) for p in pages.payloads for k in _LISTS)
            if not pages.cursor and changes == 0:
                # Plaid has not prepared transactions yet (empty next_cursor):
                # nothing was observed, so freshness is not claimed either.
                return SyncOutcome("not_ready", pages=len(pages.payloads))
            candidates, counts = build_candidates(
                self.client, current, token, pages.payloads, now=self.hub.clock()
            )
        except _LeaseLost:
            return SyncOutcome("superseded")
        except _Incomplete:
            self._fail(current, holder, INCOMPLETE, current.status)
            return SyncOutcome("failed", error_code=INCOMPLETE)
        except PlaidError as exc:
            failure = meaning(exc.error_code)
            self._fail(current, holder, failure.code, failure.status or current.status)
            return SyncOutcome("failed", error_code=failure.code)
        try:
            result = sink.submit(
                user_id=current.user_id,
                connection_id=current.id,
                candidates=candidates,
                scope=PERSONAL,
            )
        except Exception as exc:
            logger.warning(
                "Plaid sync could not hand candidates to the sink; cursor kept",
                failure_mode=type(exc).__name__,
            )
            return SyncOutcome("sink_failed", **counts)
        if getattr(result, "ignored", 0):
            logger.warning(
                "Plaid sync candidates were not recorded; cursor kept",
                ignored=result.ignored,
            )
            return SyncOutcome("sink_failed", **counts)
        advanced = self.hub.connections.record_success(
            connection_id=current.id,
            holder=holder,
            expected_cursor=start,
            cursor=pages.cursor or start,
            now=self.hub.clock(),
        )
        return SyncOutcome(
            "synced" if advanced else "superseded",
            pages=len(pages.payloads),
            restarts=pages.restarts,
            **counts,
        )

    def _fetch(
        self, current: SourceConnection, holder: str, token: str, start: str | None
    ) -> _Pages:
        began = self.timer()
        restarts = 0
        while True:
            pages = _Pages(cursor=start, restarts=restarts)
            try:
                for _ in range(self.max_pages):
                    if self.timer() - began > self.max_seconds:
                        raise _Incomplete()
                    self._renew(current, holder)
                    payload = self.client.transactions_sync(
                        access_token=token, cursor=pages.cursor, count=self.page_size
                    )
                    pages.payloads.append(payload)
                    next_cursor = payload.get("next_cursor")
                    pages.cursor = next_cursor if isinstance(next_cursor, str) else None
                    if not payload.get("has_more"):
                        return pages
                raise _Incomplete()
            except PlaidError as exc:
                if (
                    exc.error_code != MUTATION_DURING_PAGINATION
                    or restarts >= self.max_restarts
                ):
                    raise
                restarts += 1

    def _renew(self, current: SourceConnection, holder: str) -> None:
        """Extend the lease only while this sync still holds it.

        ``renew`` is one compare-and-set: it never re-takes a lease that
        ``record_failure`` released (a webhook said the Item needs
        re-authorization) or another sync acquired, so ``False`` ends this
        sync before it fetches or records anything else.
        """

        if not self.hub.connections.renew(
            connection_id=current.id, holder=holder, now=self.hub.clock(), ttl=LEASE_TTL
        ):
            raise _LeaseLost()

    def _fail(  # noqa: ANN001
        self, current: SourceConnection, holder: str, code: str, status
    ) -> None:
        logger.warning("Plaid sync failed", failure_code=code, connection_status=status)
        try:
            # Fenced by the lease: a sync that lost it cannot overwrite the
            # state a newer sync or a webhook established.
            self.hub.connections.record_failure(
                connection_id=current.id,
                code=code,
                status=status,
                now=self.hub.clock(),
                holder=holder,
            )
        except ConnectionNotFound:
            pass


_LISTS = ("added", "modified", "removed")

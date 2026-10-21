"""Periodic or manual Gmail sync for one connection, safe under retries and races.

The cursor is the mailbox ``historyId``. Order that keeps evidence and the
cursor truthful:

1. Refuse before touching Google when there is no candidate sink, and when
   the person has not chosen any sender yet.
2. Take the connection lease; a concurrent sync of the same mailbox gets
   ``busy``.
3. Mint a short-lived access token from the sealed refresh token (memory only).
4. Collect message ids:
   - no cursor (initial): read the current ``historyId`` first, then search
     ``from:(allowlist) newer_than:<lookback>d`` with bounded pages;
   - cursor: ``users.history.list`` from it (``messageAdded`` and
     ``labelRemoved`` of spam/trash), bounded pages;
   - history answers 404 (the cursor is too old): bounded re-scan since the
     last success minus a margin, then the current ``historyId``;
   - senders added since their last scan are searched over the lookback too.
5. Read each id through ``MessageReader`` (allowlist and sender
   authentication before any body is fetched).
6. Hand the candidates to the sink, and only then advance the cursor with
   ``record_success`` (compare-and-set on the starting cursor, under the
   lease). A sink failure, ignored candidates or a lost race leave the cursor
   alone; the same messages come back next time and the sink absorbs them by
   message id.

Gmail push (``users.watch`` with Pub/Sub) is a production follow-up; it needs
a hosted Pub/Sub topic.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from loguru import logger

from argus.domain.ingestion.connections import ConnectionNotFound, SourceConnection
from argus.domain.ingestion.gmail import failures
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.config import DEFAULT_LOOKBACK_DAYS
from argus.domain.ingestion.gmail.extract import EmailExtractor
from argus.domain.ingestion.gmail.messages import HIDDEN_LABELS, MessageReader
from argus.domain.ingestion.gmail.senders import (
    SenderRepository,
    SenderRule,
    sender_query,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.owner_scope import PERSONAL

SyncStatus = Literal[
    "synced", "busy", "no_sink", "no_senders", "failed", "sink_failed", "superseded"
]
SyncMode = Literal["initial", "incremental", "recovery"]
PAGE_SIZE = 100
MAX_SCAN_PAGES = 5
MAX_HISTORY_PAGES = 5
LEASE_TTL = timedelta(minutes=10)
RECOVERY_MARGIN = timedelta(days=1)


@dataclass(frozen=True)
class SyncOutcome:
    status: SyncStatus
    mode: SyncMode | None = None
    messages: int = 0
    candidates: int = 0
    # Candidates the sink refused without recording (connection ended while
    # the batch was in flight); never reported as saved.
    ignored: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    attachments: int = 0
    attachments_skipped: dict[str, int] = field(default_factory=dict)
    # History page cap reached: the cursor moved to the last record read and
    # the next sync continues from there.
    more_pending: bool = False
    # A search reached its page cap; older matches in the window were not read.
    scan_truncated: bool = False
    error_code: str | None = None


@dataclass
class _Plan:
    mode: SyncMode
    cursor: str
    ids: list[str] = field(default_factory=list)
    backfilled: tuple[str, ...] = ()
    more_pending: bool = False
    truncated: bool = False


class GmailSync:
    def __init__(
        self,
        hub: IngestionHub,
        client: GmailClient,
        senders: SenderRepository,
        extractor: EmailExtractor,
        *,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        holder: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self.hub = hub
        self.client = client
        self.senders = senders
        self.reader = MessageReader(client, extractor)
        self.lookback_days = max(1, lookback_days)
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

    def _run(self, current: SourceConnection, holder: str, sink: Any) -> SyncOutcome:
        rules = self.senders.list(connection_id=current.id)
        if not rules:
            return SyncOutcome("no_senders")
        try:
            refresh = self.hub.credential(current)
        except Exception:
            refresh = None
        if not refresh:
            return self._fail(
                current,
                holder,
                failures.FailureMeaning(failures.CREDENTIAL_UNAVAILABLE, "error"),
            )
        try:
            access = self.client.refresh(refresh)
            plan = self._plan(access, current, rules)
            tally = self.reader.read_all(
                access, plan.ids, rules=rules, connection_id=current.id
            )
        except GmailError as exc:
            return self._fail(current, holder, failures.meaning(exc))
        counts = {
            "mode": plan.mode,
            "messages": len(dict.fromkeys(plan.ids)),
            "candidates": len(tally.candidates),
            "skipped": dict(tally.skipped),
            "attachments": tally.attachments,
            "attachments_skipped": dict(tally.attachments_skipped),
            "more_pending": plan.more_pending,
            "scan_truncated": plan.truncated,
        }
        if tally.candidates:
            try:
                result = sink.submit(
                    user_id=current.user_id,
                    connection_id=current.id,
                    candidates=tally.candidates,
                    scope=PERSONAL,
                )
                counts["ignored"] = result.ignored
            except Exception as exc:
                logger.warning(
                    "Gmail sync could not hand candidates to the sink; cursor kept",
                    failure_mode=type(exc).__name__,
                )
                return SyncOutcome("sink_failed", **counts)
            if result.ignored:
                # Not recorded: moving the cursor or marking senders scanned
                # would skip these messages for good.
                logger.warning(
                    "Gmail sync candidates were not recorded; cursor kept",
                    ignored=result.ignored,
                )
                return SyncOutcome("sink_failed", **counts)
        now = self.hub.clock()
        advanced = self.hub.connections.record_success(
            connection_id=current.id,
            holder=holder,
            expected_cursor=current.cursor,
            cursor=plan.cursor,
            now=now,
        )
        if not advanced:
            return SyncOutcome("superseded", **counts)
        if plan.backfilled:
            self.senders.mark_backfilled(
                connection_id=current.id, senders=plan.backfilled, now=now
            )
        return SyncOutcome("synced", **counts)

    def _plan(
        self, access: str, current: SourceConnection, rules: list[SenderRule]
    ) -> _Plan:
        senders = [r.sender for r in rules]
        unscanned = [r.sender for r in rules if r.backfilled_at is None]
        if current.cursor is None:
            head = self.client.profile(access).history_id
            ids, truncated = self._scan(access, senders, self.lookback_days)
            return _Plan("initial", head, ids, tuple(senders), truncated=truncated)
        try:
            ids, cursor, more = self._history(access, current.cursor)
            plan = _Plan("incremental", cursor, ids, more_pending=more)
        except GmailError as exc:
            if exc.status != 404:
                raise
            head = self.client.profile(access).history_id
            ids, truncated = self._scan(access, senders, self._recovery_days(current))
            plan = _Plan("recovery", head, ids, truncated=truncated)
        if unscanned:
            more_ids, truncated = self._scan(access, unscanned, self.lookback_days)
            plan.ids.extend(more_ids)
            plan.backfilled = tuple(unscanned)
            plan.truncated = plan.truncated or truncated
        return plan

    def _recovery_days(self, current: SourceConnection) -> int:
        if current.last_success_at is None:
            return self.lookback_days
        since = current.last_success_at - RECOVERY_MARGIN
        days = math.ceil((self.hub.clock() - since).total_seconds() / 86400)
        return max(1, min(days, self.lookback_days))

    def _scan(self, access: str, senders: list[str], days: int) -> tuple[list[str], bool]:
        query = sender_query(senders, newer_than_days=days)
        ids: list[str] = []
        token: str | None = None
        for _ in range(MAX_SCAN_PAGES):
            page = self.client.list_messages(
                access, query=query, page_token=token, max_results=PAGE_SIZE
            )
            ids.extend(_ids(m for m in page.get("messages") or ()))
            token = (
                page.get("nextPageToken")
                if isinstance(page.get("nextPageToken"), str)
                else None
            )
            if not token:
                return ids, False
        return ids, True

    def _history(self, access: str, start: str) -> tuple[list[str], str, bool]:
        ids: list[str] = []
        latest = int(start) if start.isdigit() else 0
        token: str | None = None
        for _ in range(MAX_HISTORY_PAGES):
            page = self.client.list_history(
                access, start_history_id=start, page_token=token, max_results=PAGE_SIZE
            )
            for record in page.get("history") or ():
                if not isinstance(record, dict):
                    continue
                if str(record.get("id", "")).isdigit():
                    latest = max(latest, int(record["id"]))
                for added in record.get("messagesAdded") or ():
                    ids.extend(_ids([(added or {}).get("message")]))
                for change in record.get("labelsRemoved") or ():
                    if set((change or {}).get("labelIds") or ()) & HIDDEN_LABELS:
                        ids.extend(_ids([change.get("message")]))
            token = (
                page.get("nextPageToken")
                if isinstance(page.get("nextPageToken"), str)
                else None
            )
            if not token:
                head = str(page.get("historyId") or "")
                return ids, head if head.isdigit() else str(latest or start), False
        return ids, str(latest or start), True

    def _fail(
        self,
        current: SourceConnection,
        holder: str,
        failure: failures.FailureMeaning,
    ) -> SyncOutcome:
        logger.warning(
            "Gmail sync failed",
            failure_code=failure.code,
            connection_status=failure.status,
        )
        try:
            self.hub.connections.record_failure(
                connection_id=current.id,
                code=failure.code,
                status=failure.status,
                now=self.hub.clock(),
                # Fenced by the lease: a sync that lost it cannot overwrite
                # the state a newer sync established.
                holder=holder,
            )
        except ConnectionNotFound:
            pass
        return SyncOutcome("failed", error_code=failure.code)


def _ids(items: Any) -> list[str]:
    found = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
            found.append(item["id"])
    return found

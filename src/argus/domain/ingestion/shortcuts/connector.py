"""Shortcuts device enrollment, token checks and event intake.

Enrollment creates an inert ``shortcuts`` connection (``external_ref`` is a
random device id, ``label`` the person's device name) and returns its token
once. Intake turns verified events into candidates through the hub's sink and
nothing else; with no sink it refuses before anything is recorded.

Every event gets its own outcome, and only ``recorded`` or ``unchanged`` mean
the evidence is held: ``out_of_window`` and ``rejected`` can never be saved,
``not_saved`` can be sent again. A capture is never reported saved unless the
sink said so.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from loguru import logger
from pydantic import ValidationError

from argus.domain.ingestion.connections import LIVE, SourceConnection
from argus.domain.ingestion.contract import inert_text
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.shortcuts import tokens
from argus.domain.ingestion.shortcuts.events import (
    ShortcutEvent,
    external_id,
    receipt_id,
    to_candidate,
)
from argus.domain.ingestion.shortcuts.store import DeviceTokenStore
from argus.domain.owner_scope import PERSONAL

MAX_LIVE_DEVICES = 5
MAX_EVENT_AGE = timedelta(days=30)
MAX_CLOCK_SKEW = timedelta(minutes=10)


class DeviceLimitReached(RuntimeError):
    pass


class IntakeUnavailable(RuntimeError):
    """No candidate sink yet: nothing can be recorded, so nothing is."""


class EventsNotSaved(RuntimeError):
    """The sink failed part-way; earlier events may be held. Retry is safe."""


class ConnectionEnded(RuntimeError):
    """The device was disconnected while its events were in flight."""


@dataclass(frozen=True)
class Enrollment:
    connection: SourceConnection
    token: str

    def __repr__(self) -> str:
        return f"Enrollment(connection_id={self.connection.id!r}, token=<redacted>)"


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    external_id: str
    # recorded | unchanged | out_of_window | rejected | not_saved
    outcome: str

    @property
    def held(self) -> bool:
        return self.outcome in ("recorded", "unchanged")


class ShortcutsAdapter:
    """Revocation is local: the token digest is deleted; no provider exists."""

    source = "shortcuts"

    def __init__(self, store: DeviceTokenStore) -> None:
        self._store = store

    def revoke(self, connection: SourceConnection, credential: str | None) -> None:
        self._store.delete(connection_id=connection.id)


class ShortcutsConnector:
    def __init__(self, hub: IngestionHub, store: DeviceTokenStore) -> None:
        self.hub = hub
        self.store = store
        self.adapter = ShortcutsAdapter(store)

    def enroll(self, *, user_id: str, device_name: str) -> Enrollment:
        live = [
            row
            for row in self.hub.list(user_id=user_id, scope=PERSONAL)
            if row.source == "shortcuts" and row.status in LIVE
        ]
        if len(live) >= MAX_LIVE_DEVICES:  # cheap early answer; the store decides
            raise DeviceLimitReached()
        minted = tokens.mint()
        now = self.hub.clock()
        row = self.hub.connections.create(
            user_id=user_id,
            source="shortcuts",
            external_ref=minted.device_id,
            label=inert_text(device_name, 80),
            now=now,
            scope=PERSONAL,
        )
        try:
            stored = self.store.put_within_limit(
                connection_id=row.id,
                user_id=user_id,
                digest=minted.digest,
                now=now,
                limit=MAX_LIVE_DEVICES,
            )
        except Exception:
            stored = None
        if not stored:
            # No usable token: do not leave a live device that can never send.
            self.hub.connections.disconnect(
                user_id=user_id, connection_id=row.id, now=self.hub.clock()
            )
            if stored is None:
                raise RuntimeError("device token could not be stored")
            raise DeviceLimitReached()
        logger.info("Shortcuts device enrolled", connection_id=row.id)
        return Enrollment(connection=row, token=minted.token)

    def authenticate(self, authorization: str | None) -> SourceConnection | None:
        """The live connection a bearer device token proves, else ``None``.

        Every failure looks the same to the caller, and a malformed or unknown
        token still pays for one digest comparison.
        """

        token = tokens.bearer_token(authorization)
        device_id = tokens.device_id_of(token)
        row: SourceConnection | None = None
        if device_id is not None:
            rows = self.hub.connections.find_live(
                source="shortcuts", external_ref=device_id
            )
            row = rows[0] if len(rows) == 1 else None
        stored = self.store.get(connection_id=row.id) if row is not None else None
        if not tokens.matches(token or "", stored):
            return None
        return row

    def intake(
        self, connection: SourceConnection, events: Sequence[ShortcutEvent]
    ) -> list[Receipt]:
        sink = self.hub.sink
        if sink is None:
            raise IntakeUnavailable()
        now = self.hub.clock()
        receipts: list[Receipt] = []
        for event in events:
            receipts.append(self._one(sink, connection, event, now))
        if any(receipt.held for receipt in receipts):
            self._mark_fresh(connection)
        logger.info(
            "Shortcuts events received",
            connection_id=connection.id,
            events=len(receipts),
            recorded=sum(r.outcome == "recorded" for r in receipts),
            held=sum(r.held for r in receipts),
        )
        return receipts

    def _one(self, sink, connection, event, now) -> Receipt:  # noqa: ANN001
        external = external_id(event)
        receipt = receipt_id(connection_id=connection.id, external_id=external)
        if not now - MAX_EVENT_AGE <= event.captured_at <= now + MAX_CLOCK_SKEW:
            return Receipt(receipt, external, "out_of_window")
        try:
            candidate = to_candidate(event, connection_id=connection.id)
        except ValidationError:
            # The contract refused this event's content; the rest proceed.
            logger.warning(
                "Shortcuts event refused by contract", connection_id=connection.id
            )
            return Receipt(receipt, external, "rejected")
        try:
            result = sink.submit(
                user_id=connection.user_id,
                connection_id=connection.id,
                candidates=[candidate],
                scope=PERSONAL,
            )
        except Exception as exc:
            # Earlier events of a batch are kept; a retry is harmless because
            # each one is idempotent by its external id.
            logger.warning(
                "Shortcuts sink refused an event",
                connection_id=connection.id,
                failure_mode=type(exc).__name__,
            )
            raise EventsNotSaved() from None
        if result.recorded:
            return Receipt(receipt, external, "recorded")
        if result.unchanged:
            return Receipt(receipt, external, "unchanged")
        # Ignored, or not accounted for: never report it as saved.
        current = self.hub.connections.get(
            user_id=connection.user_id, connection_id=connection.id, scope=PERSONAL
        )
        if current.status not in LIVE:
            raise ConnectionEnded()
        return Receipt(receipt, external, "not_saved")

    def _mark_fresh(self, connection: SourceConnection) -> None:
        """Last successful capture for the connections list; best effort."""

        holder = f"shortcuts:{uuid.uuid4().hex[:16]}"
        now = self.hub.clock()
        repo = self.hub.connections
        try:
            if not repo.lease(connection_id=connection.id, holder=holder, now=now):
                return
            try:
                repo.record_success(
                    connection_id=connection.id,
                    holder=holder,
                    expected_cursor=None,
                    cursor=None,
                    now=now,
                )
            finally:
                repo.release(connection_id=connection.id, holder=holder)
        except Exception as exc:
            # The evidence is already recorded; only the timestamp is stale.
            logger.warning(
                "Shortcuts freshness update failed",
                connection_id=connection.id,
                failure_mode=type(exc).__name__,
            )

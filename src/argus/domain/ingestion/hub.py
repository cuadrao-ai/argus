"""Connection lifecycle shared by every connector: list and disconnect.

Connectors register a ``SourceAdapter`` for provider-side revocation. The hub
owns the order that keeps disconnect truthful: try to revoke at the provider,
always delete the stored credential and cursor, then let reconciliation drop
unreviewed evidence. A provider outage cannot keep a credential alive here; it
is reported so the person can also revoke at the provider.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from loguru import logger

from argus.domain.ingestion.connections import (
    ConnectionRepository,
    SourceConnection,
)
from argus.domain.ingestion.contract import SourceKind
from argus.domain.ingestion.secrets import SecretBox, SecretUnreadable
from argus.domain.ingestion.sink import CandidateSink
from argus.domain.owner_scope import PERSONAL, OwnerScope

Revocation = Literal["revoked", "failed", "not_applicable"]
# Account deletion also learns when the provider no longer held the grant
# (``already_revoked``) and when a credential does not open under this key
# (``unreadable``: a wrong key and a truly dead credential look the same here;
# the deletion run's key check tells them apart by the stored key fingerprint).
DeletionRevocation = Literal[
    "revoked", "already_revoked", "failed", "not_applicable", "unreadable"
]


class SourceAdapter(Protocol):
    source: SourceKind

    def revoke(self, connection: SourceConnection, credential: str | None) -> str | None:
        """Revoke provider-side access. Raise on failure; never log the credential.
        May return ``"already_revoked"`` when the provider no longer held it."""
        ...


class LocalCleanup(Protocol):
    """Optional adapter hook: delete connector-owned local state (a sender
    list, a device token digest) after the connection has ended."""

    def forget(self, connection: SourceConnection) -> None: ...


@dataclass(frozen=True)
class DisconnectOutcome:
    connection: SourceConnection
    provider_revocation: Revocation
    unreviewed_removed: int


class IngestionHub:
    def __init__(
        self,
        connections: ConnectionRepository,
        *,
        box: SecretBox | None,
        sink: CandidateSink | None,
        clock: Callable[[], datetime],
    ) -> None:
        self.connections = connections
        self.box = box
        self.sink = sink
        self.clock = clock
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        self._adapters[adapter.source] = adapter

    def adapter(self, source: str) -> SourceAdapter | None:
        return self._adapters.get(source)

    def list(self, *, user_id: str, scope: OwnerScope) -> list[SourceConnection]:
        return self.connections.list(user_id=user_id, scope=scope)

    def credential(self, connection: SourceConnection) -> str | None:
        if connection.secret is None or self.box is None:
            return None
        return self.box.open(
            connection.secret, source=connection.source, connection_id=connection.id
        )

    def disconnect(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> DisconnectOutcome:
        connection = self.connections.get(
            user_id=user_id, connection_id=connection_id, scope=scope
        )
        adapter = self._adapters.get(connection.source)
        if connection.status == "disconnected":
            # Already ended: never contact the provider again, but finish any
            # local cleanup a failed earlier attempt left behind. Both cleanup
            # steps are idempotent.
            return DisconnectOutcome(
                connection, "not_applicable", self._cleanup(adapter, connection)
            )
        revocation: Revocation = "not_applicable"
        if adapter is None and connection.secret is not None:
            # A provider grant exists but nothing here can revoke it (the
            # connector is switched off): say so instead of implying success.
            revocation = "failed"
        if adapter is not None:
            try:
                adapter.revoke(connection, self.credential(connection))
                revocation = "revoked"
            except Exception as exc:
                revocation = "failed"
                logger.warning(
                    "Provider revocation failed; local credential is deleted anyway",
                    source=connection.source,
                    failure_mode=type(exc).__name__,
                )
        ended = self.connections.disconnect(
            user_id=user_id, connection_id=connection_id, now=self.clock()
        )
        return DisconnectOutcome(ended, revocation, self._cleanup(adapter, ended))

    def _cleanup(self, adapter: SourceAdapter | None, ended: SourceConnection) -> int:
        """Connector-owned local state, then unreviewed evidence. Safe to
        repeat; a retry after a partial failure completes what is left."""

        forget = getattr(adapter, "forget", None)
        if forget is not None:
            forget(ended)
        if self.sink is None:
            return 0
        return self.sink.forget_connection(
            user_id=ended.user_id, connection_id=ended.id, scope=ended.scope
        )

    def revoke_for_deletion(
        self,
        *,
        source: str,
        connection_id: str,
        external_ref: str,
        envelope: bytes | None,
    ) -> DeletionRevocation:
        """Account deletion's revocation path (Lane 6, step 2).

        Unlike ``disconnect`` it touches no connection row: the caller holds the
        encrypted credential in the deletion run and drops it only after this
        returns ``revoked``. ``failed`` keeps the revocation pending for a retry;
        ``already_revoked`` means the provider no longer held the grant;
        ``unreadable`` means the credential does not open under this process's
        key, which the caller must not take as proof it never will.
        """
        adapter = self._adapters.get(source)
        if envelope is None:
            return "not_applicable"
        if adapter is None or self.box is None:
            return "failed"
        now = self.clock()
        connection = SourceConnection(
            id=connection_id,
            user_id="",
            source=source,  # type: ignore[arg-type]
            status="disconnected",
            label=None,
            external_ref=external_ref,
            cursor=None,
            secret=envelope,
            last_success_at=None,
            last_attempt_at=None,
            last_error_code=None,
            attention_code=None,
            attention_at=None,
            lease_holder=None,
            lease_until=None,
            created_at=now,
            updated_at=now,
            disconnected_at=now,
            version=0,
            # Only Plaid and Gmail hold a revocable grant, and both are Personal.
            scope=PERSONAL,
        )
        try:
            credential = self.credential(connection)
        except SecretUnreadable:
            # Not openable under this process's key: a wrong or missing key
            # looks the same as a dead credential, so the caller decides.
            return "unreadable"
        try:
            result = adapter.revoke(connection, credential)
        except Exception as exc:
            logger.warning(
                "Deletion revocation failed; the credential stays pending",
                source=source,
                failure_mode=type(exc).__name__,
            )
            return "failed"
        return "already_revoked" if result == "already_revoked" else "revoked"

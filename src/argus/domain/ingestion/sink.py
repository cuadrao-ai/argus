"""The one door from a connector into reconciliation.

Connectors depend on this protocol only. Reconciliation implements it; it is
the single owner of evidence storage, cross-source matching, review and the
canonical write. Keeping the door this narrow is what stops a connector from
growing its own ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.owner_scope import OwnerScope


@dataclass(frozen=True)
class SubmitResult:
    # New observations or changed content for a known external id.
    recorded: int
    # Re-deliveries whose content fingerprint did not change.
    unchanged: int
    # Status ``removed`` applied to previously recorded evidence.
    withdrawn: int
    # Refused without recording, e.g. the connection ended while the batch
    # was in flight. A connector must not report these as saved.
    ignored: int = 0


class CandidateSink(Protocol):
    def submit(
        self,
        *,
        user_id: str,
        connection_id: str,
        candidates: Sequence[ImportCandidate],
        scope: OwnerScope,
    ) -> SubmitResult:
        """Record evidence idempotently, keyed by ``ImportCandidate.key``.

        Must be safe to call again with the same batch (webhook retries, a
        sync replayed after a crash) and must refuse candidates whose
        ``connection_id`` differs from the argument. ``scope`` is the
        connection's own scope, which the events it creates inherit.
        """
        ...

    def forget_connection(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> int:
        """Disconnect retention: drop unreviewed evidence from this connection.

        Confirmed canonical activity is the person's record and stays, with its
        minimal provenance (source kind, dates, external id). Returns the number
        of unreviewed observations removed.
        """
        ...

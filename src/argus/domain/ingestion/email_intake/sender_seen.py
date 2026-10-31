"""The sender row as the only trace of mail that is not stored. Both stores.

With pending senders on, mail from a sender not on the list is fetched once,
judged, and dropped; ``record_sender`` keeps its address, verdict and arrival
time. It adds a ``pending`` row for an address with no row and never changes
the status of a row that exists."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from argus.domain.ingestion.email_intake.addressing import SenderRule, _address_value
from argus.domain.ingestion.email_intake.alignment import bare_address


def _full(address: str | None) -> str | None:
    parsed = _address_value(bare_address(address))
    return parsed[0] if parsed else None


class PostgresSenderSeen:
    def record_sender(self, space_id: str, address: str | None, verdict: str) -> None:
        full = _full(address)
        if full is None:
            return
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "insert into public.business_email_senders"
                "(space_id, kind, value, status, last_auth_result, last_seen_at) "
                "values (%s,'address',%s,'pending',%s,now()) "
                "on conflict(space_id, kind, value) do update set "
                "last_auth_result=excluded.last_auth_result, last_seen_at=now()",
                (space_id, full, verdict),
            )


class MemorySenderSeen:
    def record_sender(self, space_id: str, address: str | None, verdict: str) -> None:
        full = _full(address)
        if full is None:
            return
        with self._lock:
            key = (space_id, "address", full)
            current = self._senders.get(key) or SenderRule(
                str(uuid4()), space_id, "address", full, "pending"
            )
            self._senders[key] = replace(
                current, last_auth_result=verdict, last_seen_at=self.clock()
            )

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

    def member_addresses(self, space_id: str) -> frozenset[str]:
        # The Business's people with a live grant, as require_manager sees them.
        with self.pool.connection() as connection:
            rows = connection.execute(
                "select distinct lower(u.email) from public.business_client_grants g"
                " join auth.users u on u.id=g.grantee_id where g.space_id=%s"
                " and g.revoked_at is null"
                " and (g.expires_at is null or g.expires_at>clock_timestamp())"
                " and u.email is not null and not coalesce(u.is_anonymous,false)"
                " and (u.banned_until is null or u.banned_until<=clock_timestamp())"
                " and not exists(select 1 from argus_private.account_deletion_runs d"
                " where d.user_id=u.id)",
                (space_id,),
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def add_default_sender(self, space_id: str, address: str | None) -> None:
        full = _full(address)
        if full is None:
            return
        with (
            self.pool.connection() as connection,
            connection.transaction(),
            connection.cursor() as cursor,
        ):
            added = cursor.execute(
                "insert into public.business_email_senders(space_id, kind, value, status)"
                " values (%s,'address',%s,'authorized')"
                " on conflict(space_id, kind, value) do nothing returning id",
                (space_id, full),
            ).fetchone()
            if added:
                self._write_event(cursor, space_id, None, "sender_authorized", None, full)


class MemorySenderSeen:
    def add_member(self, space_id: str, address: str) -> None:
        """Test seam: one of the Business's people, by account address."""

        with self._lock:
            self.__dict__.setdefault("_members", {}).setdefault(space_id, set()).add(
                address.lower()
            )

    def member_addresses(self, space_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self.__dict__.get("_members", {}).get(space_id, ()))

    def add_default_sender(self, space_id: str, address: str | None) -> None:
        full = _full(address)
        if full is None:
            return
        with self._lock:
            key = (space_id, "address", full)
            if key in self._senders:
                return
            self._senders[key] = SenderRule(
                str(uuid4()), space_id, "address", full, "authorized"
            )
            self._remember(space_id, None, "sender_authorized", None, full)

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

"""Postgres WhatsApp state. Every statement commits before the caller proceeds."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from psycopg import Connection
from psycopg_pool import ConnectionPool

from argus.domain.business.transactions import lock_owner
from argus.domain.ingestion.whatsapp.reply_groups import PendingFailure
from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups
from argus.domain.ingestion.whatsapp.store import (
    UNLINKED_REPLY_RESERVED,
    Claim,
    InboundRecord,
    PrepareCapture,
    SenderLink,
    Settlement,
    dominican_day,
    revoked,
    settlement_seconds,
    settlement_time,
    unlinked_reply_key,
)

_INBOUND_COLUMNS = (
    "provider_message_key, sender_hash, status, destination_owner_id::text, "
    "connection_id::text, error_code, claim_until, received_at, updated_at"
)


def _record(row: tuple) -> InboundRecord:
    key, sender, *rest = row
    return InboundRecord(bytes(key), bytes(sender), *rest)


def _limit_statement_time(
    connection: Connection,
    claim_until: datetime,
    now: datetime | Callable[[], datetime],
    deadline: float | None,
) -> datetime | None:
    settled_at = settlement_time(now)
    seconds = settlement_seconds(claim_until, settled_at, deadline)
    if seconds <= 0:
        return None
    milliseconds = max(1, int(seconds * 1000))
    connection.execute(
        "select set_config('statement_timeout', %s, true)", (str(milliseconds),)
    )
    return settled_at


class PostgresWhatsAppStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self.reply_groups = PostgresReplyGroups(pool)

    def claim(
        self,
        *,
        provider_message_key: bytes,
        sender_hash: bytes,
        now: datetime,
        claim_until: datetime,
    ) -> Claim:
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "insert into public.whatsapp_inbound_messages as m "
                "(provider_message_key, sender_hash, status, claim_until, received_at, "
                "updated_at) values (%s, %s, 'received', %s, %s, %s) "
                "on conflict (provider_message_key) do update "
                "set claim_until = excluded.claim_until, updated_at = excluded.updated_at "
                "where m.status in ('received', 'failed') "
                "and (m.claim_until is null or m.claim_until <= excluded.updated_at) "
                f"returning {_INBOUND_COLUMNS}",
                (
                    provider_message_key,
                    sender_hash,
                    claim_until,
                    now,
                    now,
                ),
            ).fetchone()
            if row is not None:
                return Claim(_record(row), True)
            row = connection.execute(
                f"select {_INBOUND_COLUMNS} from public.whatsapp_inbound_messages "
                "where provider_message_key = %s",
                (provider_message_key,),
            ).fetchone()
        return Claim(_record(row), False)

    def settle(
        self,
        *,
        provider_message_key: bytes,
        claim_until: datetime | None,
        settlement: Settlement,
        now: datetime | Callable[[], datetime],
        reply_failure: PendingFailure | None = None,
        prepare: PrepareCapture | None = None,
        deadline: float | None = None,
    ) -> Settlement | None:
        if claim_until is None:
            return None
        seconds = settlement_seconds(claim_until, settlement_time(now), deadline)
        if seconds <= 0:
            return None
        with (
            self._pool.connection(timeout=seconds) as connection,
            connection.transaction(),
        ):
            if _limit_statement_time(connection, claim_until, now, deadline) is None:
                return None
            owner = settlement.destination_owner_id
            if settlement.status == "captured" and owner is not None:
                # Document purge takes the owner lock before deleting receipts and
                # their inbound rows. Use the same order when publishing a receipt.
                lock_owner(connection, owner)
                if _limit_statement_time(connection, claim_until, now, deadline) is None:
                    return None
            holder = connection.execute(
                "select sender_hash from public.whatsapp_inbound_messages "
                "where provider_message_key = %s and status in ('received', 'failed') "
                "and claim_until = %s for update",
                (provider_message_key, claim_until),
            ).fetchone()
            if holder is None:
                return None
            # Held until commit, so a revoke cannot land between this read and
            # the write; whatsapp_capture_same_space checks the same fact.
            if settlement.connection_id is not None:
                if _limit_statement_time(connection, claim_until, now, deadline) is None:
                    return None
                link = connection.execute(
                    "select 1 from public.whatsapp_sender_links "
                    "where wa_id_hash = %s and destination_owner_id = %s "
                    "and status = 'active' for share",
                    (holder[0], settlement.destination_owner_id),
                ).fetchone()
                if link is None:
                    settlement = revoked(settlement)
            # Check expiry after acquiring the locks. The inbound row remains
            # unavailable to another claimant through publication and commit.
            settled_at = _limit_statement_time(connection, claim_until, now, deadline)
            if settled_at is None:
                return None
            connection.execute(
                "update public.whatsapp_inbound_messages set status = %s, "
                "destination_owner_id = %s, connection_id = %s, error_code = %s, "
                "claim_until = null, updated_at = %s "
                "where provider_message_key = %s",
                (
                    settlement.status,
                    settlement.destination_owner_id,
                    settlement.connection_id,
                    settlement.error_code,
                    settled_at,
                    provider_message_key,
                ),
            )
            if prepare is not None and settlement.status == "captured":
                if _limit_statement_time(connection, claim_until, now, deadline) is None:
                    raise TimeoutError("whatsapp_settlement_timeout")
                settlement = replace(settlement, reading=prepare(connection, settlement))
            if reply_failure is not None:
                self.reply_groups.enqueue_on(connection, reply_failure)
            if settlement_seconds(claim_until, settlement_time(now), deadline) <= 0:
                raise TimeoutError("whatsapp_settlement_timeout")
            return settlement

    def renew(
        self,
        *,
        provider_message_key: bytes,
        held: datetime,
        now: datetime,
        claim_until: datetime,
    ) -> datetime | None:
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "update public.whatsapp_inbound_messages "
                "set claim_until = %s, updated_at = %s "
                "where provider_message_key = %s and status in ('received', 'failed') "
                "and claim_until = %s returning claim_until",
                (claim_until, now, provider_message_key, held),
            ).fetchone()
        return None if row is None else row[0]

    def inbound(self, provider_message_key: bytes) -> InboundRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                f"select {_INBOUND_COLUMNS} from public.whatsapp_inbound_messages "
                "where provider_message_key = %s",
                (provider_message_key,),
            ).fetchone()
        return _record(row) if row else None

    def reserve_unlinked_reply(
        self, *, sender_hash: bytes, provider_message_key: bytes, now: datetime
    ) -> bool:
        with self._pool.connection() as connection, connection.transaction():
            (received_at,) = connection.execute(
                "select received_at from public.whatsapp_inbound_messages "
                "where provider_message_key = %s",
                (provider_message_key,),
            ).fetchone()
            key = unlinked_reply_key(sender_hash, dominican_day(received_at))
            row = connection.execute(
                "insert into public.whatsapp_inbound_messages "
                "(provider_message_key, sender_hash, status, error_code, received_at, "
                "updated_at) values (%s, %s, 'rejected', %s, %s, %s) "
                "on conflict (provider_message_key) do nothing returning 1",
                (key, sender_hash, UNLINKED_REPLY_RESERVED, now, now),
            ).fetchone()
        return row is not None

    def captured_connections(self, *, destination_owner_id: str) -> frozenset[str]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "select distinct connection_id::text from public.whatsapp_inbound_messages "
                "where destination_owner_id = %s and status = 'captured' "
                "and connection_id is not null",
                (destination_owner_id,),
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def issue_code(
        self,
        *,
        destination_owner_id: str,
        code_digest: bytes,
        reply_language: str,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                "delete from public.whatsapp_link_codes "
                "where destination_owner_id = %s and consumed_at is null",
                (destination_owner_id,),
            )
            connection.execute(
                "insert into public.whatsapp_link_codes "
                "(destination_owner_id, code_digest, reply_language, created_at, "
                "expires_at) values (%s, %s, %s, %s, %s)",
                (destination_owner_id, code_digest, reply_language, now, expires_at),
            )

    def redeem_code(
        self, *, code_digest: bytes, sender_hash: bytes, last4: str, now: datetime
    ) -> SenderLink | None:
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "update public.whatsapp_link_codes set consumed_at = %s "
                "where code_digest = %s and consumed_at is null and expires_at > %s "
                "returning destination_owner_id::text, reply_language",
                (now, code_digest, now),
            ).fetchone()
            if row is None:
                return None
            owner, reply_language = row
            connection.execute(
                "update public.whatsapp_sender_links "
                "set status = 'revoked', revoked_at = %s "
                "where status = 'active' and (wa_id_hash = %s or destination_owner_id = %s)",
                (now, sender_hash, owner),
            )
            connection.execute(
                "insert into public.whatsapp_sender_links "
                "(destination_owner_id, wa_id_hash, last4, reply_language, status, "
                "linked_at) values (%s, %s, %s, %s, 'active', %s)",
                (owner, sender_hash, last4, reply_language, now),
            )
        return SenderLink(owner, last4, now, reply_language)

    def _active(self, column: str, value: object) -> SenderLink | None:
        from psycopg import sql

        with self._pool.connection() as connection:
            row = connection.execute(
                sql.SQL(
                    "select destination_owner_id::text, last4, linked_at, reply_language "
                    "from public.whatsapp_sender_links "
                    "where {} = %s and status = 'active'"
                ).format(sql.Identifier(column)),
                (value,),
            ).fetchone()
        return SenderLink(*row) if row else None

    def sender_link(self, *, sender_hash: bytes) -> SenderLink | None:
        return self._active("wa_id_hash", sender_hash)

    def destination_link(self, *, destination_owner_id: str) -> SenderLink | None:
        return self._active("destination_owner_id", destination_owner_id)

    def revoke(self, *, destination_owner_id: str, now: datetime) -> bool:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                "delete from public.whatsapp_link_codes "
                "where destination_owner_id = %s and consumed_at is null",
                (destination_owner_id,),
            )
            cursor = connection.execute(
                "update public.whatsapp_sender_links "
                "set status = 'revoked', revoked_at = %s "
                "where destination_owner_id = %s and status = 'active'",
                (now, destination_owner_id),
            )
            return cursor.rowcount > 0

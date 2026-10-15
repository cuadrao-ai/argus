"""Postgres WhatsApp state. Every statement commits before the caller proceeds."""

from __future__ import annotations

from datetime import datetime

from psycopg_pool import ConnectionPool

from argus.domain.ingestion.whatsapp.store import (
    Claim,
    InboundRecord,
    SenderLink,
    Settlement,
    revoked,
)

_INBOUND_COLUMNS = (
    "provider_message_key, sender_hash, status, destination_owner_id::text, "
    "connection_id::text, error_code, claim_until, received_at, updated_at"
)


def _record(row: tuple) -> InboundRecord:
    key, sender, *rest = row
    return InboundRecord(bytes(key), bytes(sender), *rest)


class PostgresWhatsAppStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

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
                (provider_message_key, sender_hash, claim_until, now, now),
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
        now: datetime,
    ) -> Settlement | None:
        with self._pool.connection() as connection, connection.transaction():
            # Held until commit, so a revoke cannot land between this read and
            # the write; whatsapp_capture_same_space checks the same fact.
            if settlement.connection_id is not None and (
                connection.execute(
                    "select 1 from public.whatsapp_sender_links"
                    " where destination_owner_id = %s and status = 'active' for share",
                    (settlement.destination_owner_id,),
                ).fetchone()
                is None
            ):
                settlement = revoked(settlement)
            cursor = connection.execute(
                "update public.whatsapp_inbound_messages set status = %s, "
                "destination_owner_id = %s, connection_id = %s, error_code = %s, "
                "claim_until = null, updated_at = %s "
                "where provider_message_key = %s and status in ('received', 'failed') "
                "and claim_until is not distinct from %s",
                (
                    settlement.status,
                    settlement.destination_owner_id,
                    settlement.connection_id,
                    settlement.error_code,
                    now,
                    provider_message_key,
                    claim_until,
                ),
            )
            return settlement if cursor.rowcount == 1 else None

    def inbound(self, provider_message_key: bytes) -> InboundRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                f"select {_INBOUND_COLUMNS} from public.whatsapp_inbound_messages "
                "where provider_message_key = %s",
                (provider_message_key,),
            ).fetchone()
        return _record(row) if row else None

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

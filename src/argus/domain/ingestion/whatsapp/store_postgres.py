"""Postgres WhatsApp state. Every statement commits before the caller proceeds."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from psycopg import Connection
from psycopg_pool import ConnectionPool

from argus.domain.business.transactions import lock_owner
from argus.domain.ingestion.whatsapp.ai_consent import (
    matches_link_disclosure,
    record_link_consent,
    require_link_disclosure,
)
from argus.domain.ingestion.whatsapp.reply_groups import PendingFailure
from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups
from argus.domain.ingestion.whatsapp.senders import postgres_senders
from argus.domain.ingestion.whatsapp.store import (
    UNLINKED_REPLY_RESERVED,
    CapturePermissionLost,
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
    "connection_id::text, error_code, claim_until, received_at, updated_at, sender_link_id::text"
)


def _record(row: tuple) -> InboundRecord:
    key, sender, *rest = row
    return InboundRecord(bytes(key), bytes(sender) if sender is not None else None, *rest)


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
                lock_owner(connection, settlement.storage_user_id or owner)
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
            # Hold the exact link through publication so revoke and capture serialize.
            link_id = None
            if settlement.connection_id is not None:
                if _limit_statement_time(connection, claim_until, now, deadline) is None:
                    return None
                link = connection.execute(
                    "select l.id from public.whatsapp_sender_links l"
                    " join public.financial_source_connections c on c.id=%s"
                    " and c.user_id=%s and c.owner_space_id=%s"
                    " where l.wa_id_hash=%s and l.destination_owner_id=%s"
                    " and l.status='active' for share of l,c",
                    (
                        settlement.connection_id,
                        settlement.storage_user_id,
                        settlement.space_id,
                        holder[0],
                        owner,
                    ),
                ).fetchone()
                if link is None:
                    settlement = revoked(settlement)
                else:
                    (link_id,) = link
            # Check expiry after acquiring the locks. The inbound row remains
            # unavailable to another claimant through publication and commit.
            settled_at = _limit_statement_time(connection, claim_until, now, deadline)
            if settled_at is None:
                return None
            if prepare is not None and settlement.status == "captured":
                try:
                    with connection.transaction():
                        settlement = replace(
                            settlement, reading=prepare(connection, settlement)
                        )
                except CapturePermissionLost:
                    settlement = revoked(settlement)
                    link_id = None
            connection.execute(
                "update public.whatsapp_inbound_messages set status = %s, "
                "destination_owner_id = %s, connection_id = %s, error_code = %s, "
                "claim_until = null, updated_at = %s, sender_link_id = %s "
                "where provider_message_key = %s",
                (
                    settlement.status,
                    settlement.destination_owner_id,
                    settlement.connection_id,
                    settlement.error_code,
                    settled_at,
                    link_id,
                    provider_message_key,
                ),
            )
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
                "select distinct m.connection_id::text from public.whatsapp_inbound_messages m"
                " join public.financial_source_connections c on c.id=m.connection_id"
                " where c.user_id=%s and m.status='captured'",
                (destination_owner_id,),
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def issue_code(
        self,
        *,
        destination_owner_id: str,
        code_digest: bytes,
        reply_language: str,
        disclosure: str,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        require_link_disclosure(reply_language, disclosure)
        with self._pool.connection() as connection, connection.transaction():
            lock_owner(connection, destination_owner_id)
            connection.execute(
                "delete from public.whatsapp_link_codes "
                "where destination_owner_id = %s and consumed_at is null",
                (destination_owner_id,),
            )
            connection.execute(
                "insert into public.whatsapp_link_codes "
                "(destination_owner_id, code_digest, reply_language, created_at, "
                "expires_at, disclosure) values (%s, %s, %s, %s, %s, %s)",
                (destination_owner_id, code_digest, reply_language, now, expires_at, disclosure),
            )

    def redeem_code(
        self, *, code_digest: bytes, sender_hash: bytes, last4: str, now: datetime
    ) -> SenderLink | None:
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select destination_owner_id::text, reply_language, disclosure"
                " from public.whatsapp_link_codes"
                " where code_digest=%s and consumed_at is null and expires_at>%s for update",
                (code_digest, now),
            ).fetchone()
            if row is None:
                return None
            owner, reply_language, disclosure = row
            connection.execute(
                "update public.whatsapp_link_codes set consumed_at=%s, disclosure=null where code_digest=%s",
                (now, code_digest),
            )
            if not matches_link_disclosure(reply_language, disclosure):
                return None
            grants = postgres_senders(connection).eligible_businesses(owner)
            if not grants:
                return None
            connection.execute(
                "update public.whatsapp_sender_links "
                "set status = 'revoked', revoked_at = %s "
                "where status = 'active' and (wa_id_hash = %s or destination_owner_id = %s)",
                (now, sender_hash, owner),
            )
            link = connection.execute(
                "insert into public.whatsapp_sender_links "
                "(destination_owner_id, wa_id_hash, last4, reply_language, status, "
                "linked_at) values (%s, %s, %s, %s, 'active', %s) returning id",
                (owner, sender_hash, last4, reply_language, now),
            ).fetchone()
            # Keep one reproducible grant as evidence of authority at redemption.
            # Consent belongs to the link and checks current eligibility at read time.
            record_link_consent(
                connection, grant=min(grants, key=lambda grant: grant.grant_id),
                link_id=link[0], sender_hash=sender_hash,
                language=reply_language, disclosure=disclosure,
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

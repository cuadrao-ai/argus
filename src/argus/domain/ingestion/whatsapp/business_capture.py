from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.ingestion.whatsapp.business_envelope import EnvelopeCodec, TextEnvelope
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore
from argus.domain.ingestion.whatsapp.identity import looks_like_link_attempt
from argus.domain.ingestion.whatsapp.payload import TextMessage


@dataclass(frozen=True)
class CapturedText:
    id: UUID
    message_key: bytes
    sender_hash: bytes
    space_id: UUID
    owner_id: UUID
    link_id: UUID
    arrival_sequence: int
    received_at: datetime
    language: str
    composition_state: str
    envelope: TextEnvelope
    ai_consent_id: UUID | None = None

    @property
    def turn_key(self) -> str:
        return self.message_key.hex()


class BusinessCaptureStore:
    def __init__(self, pool: ConnectionPool, codec: EnvelopeCodec, consent=None) -> None:
        self.pool, self.codec = pool, codec
        self.consent = consent

    def capture(self, message: TextMessage) -> bool:
        if not message.body or looks_like_link_attempt(message.body):
            return False
        key = self.codec.keys.message(message.id)
        sender = self.codec.keys.sender(message.sender)
        sealed = self.codec.seal(message)
        with self.pool.connection() as connection, connection.transaction():
            link = connection.execute(
                "select id,destination_space_id,destination_owner_id"
                " from public.whatsapp_sender_links where wa_id_hash=%s and status='active' for update",
                (sender,),
            ).fetchone()
            if link is None:
                return False
            consent_id = (
                self.consent.capture_consent(connection, link[0])
                if self.consent
                else None
            )
            connection.execute(
                "insert into public.whatsapp_inbound_messages"
                " (provider_message_key,sender_hash,destination_owner_id,status,received_at,updated_at,"
                " sender_link_id,destination_space_id,sent_at,transport_envelope,transport_key_id,ai_consent_id)"
                " values (%s,%s,%s,'captured',clock_timestamp(),clock_timestamp(),%s,%s,%s,%s,%s,%s)"
                " on conflict (provider_message_key) do nothing",
                (
                    key,
                    sender,
                    link[2],
                    link[0],
                    link[1],
                    message.sent_at,
                    sealed,
                    self.codec.box.key_id,
                    consent_id,
                ),
            )
            original = connection.execute(
                "select sender_hash,transport_envelope from public.whatsapp_inbound_messages"
                " where provider_message_key=%s",
                (key,),
            ).fetchone()
            if original[1] is None:
                return False
            restored = self.codec.open(
                original[1], message_key=key, sender_hash=original[0]
            )
            if restored != TextEnvelope.from_message(message):
                raise ValueError("whatsapp_message_identity_conflict")
            return True

    def pending(self, *, limit: int = 16) -> list[tuple[UUID, str, bytes]]:
        if not 1 <= limit <= 100:
            raise ValueError("invalid worker batch limit")
        with self.pool.connection() as connection:
            return connection.execute(
                "select destination_space_id,encode(sender_hash,'hex'),provider_message_key from ("
                " select distinct on (i.destination_space_id,i.sender_hash) i.destination_space_id,"
                " i.sender_hash,i.provider_message_key,i.arrival_sequence"
                " from public.whatsapp_inbound_messages i where i.transport_envelope is not null"
                " and (i.composition_state in ('not_started','started') or exists ("
                " select 1 from public.whatsapp_outbox o where o.provider_message_key=i.provider_message_key"
                " and o.state in ('pending','sending')))"
                " order by i.destination_space_id,i.sender_hash,i.arrival_sequence"
                " ) heads order by arrival_sequence limit %s",
                (limit,),
            ).fetchall()

    def read(self, key: bytes, *, lease: SenderLease) -> CapturedText:
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "select i.*,l.reply_language from public.whatsapp_inbound_messages i"
                    " join public.whatsapp_sender_links l on l.id=i.sender_link_id"
                    " where i.provider_message_key=%s and i.destination_space_id=%s and i.sender_hash=%s",
                    (key, lease.space_id, bytes.fromhex(lease.sender_hash)),
                )
                row = cursor.fetchone()
            if row is None:
                raise ValueError("whatsapp_capture_not_found")
            return CapturedText(
                id=row["id"],
                message_key=key,
                sender_hash=row["sender_hash"],
                space_id=row["destination_space_id"],
                owner_id=row["destination_owner_id"],
                link_id=row["sender_link_id"],
                arrival_sequence=row["arrival_sequence"],
                received_at=row["received_at"],
                language=row["reply_language"],
                composition_state=row["composition_state"],
                ai_consent_id=row["ai_consent_id"],
                envelope=self.codec.open(
                    row["transport_envelope"],
                    message_key=key,
                    sender_hash=row["sender_hash"],
                ),
            )

    def live_binding(self, captured: CapturedText, *, lease: SenderLease) -> bool:
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            row = connection.execute(
                "select 1 from public.whatsapp_sender_links where id=%s and status='active'"
                " and destination_space_id=%s and destination_owner_id=%s and wa_id_hash=%s for share",
                (
                    captured.link_id,
                    captured.space_id,
                    captured.owner_id,
                    captured.sender_hash,
                ),
            ).fetchone()
            BusinessTurnStore.require_lease(connection, lease)
            return row is not None

    def quarantine(self, key: bytes, *, lease: SenderLease) -> None:
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            bound = connection.execute(
                "select 1 from public.whatsapp_inbound_messages where provider_message_key=%s"
                " and destination_space_id=%s and sender_hash=%s for update",
                (key, lease.space_id, bytes.fromhex(lease.sender_hash)),
            ).fetchone()
            if bound is None:
                raise ValueError("whatsapp_capture_not_found")
            connection.execute(
                "update public.whatsapp_outbox set state=case when state='sending' then 'unknown' else 'suppressed' end,"
                " error_code='whatsapp_envelope_unreadable' where provider_message_key=%s and state in ('pending','sending')",
                (key,),
            )
            connection.execute(
                "update public.whatsapp_inbound_messages set composition_state='unknown',"
                " error_code='whatsapp_envelope_unreadable',updated_at=clock_timestamp()"
                " where provider_message_key=%s and destination_space_id=%s and sender_hash=%s"
                " and composition_state in ('not_started','started')",
                (key, lease.space_id, bytes.fromhex(lease.sender_hash)),
            )
            BusinessTurnStore.require_lease(connection, lease)

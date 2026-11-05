from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.ingestion.whatsapp.business_capture import CapturedText
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore


class ReplyOutcomeUnknown(RuntimeError):
    pass


@dataclass(frozen=True)
class OutboundReply:
    index: int
    body: str


class BusinessOutbox:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def begin_reply(self, captured: CapturedText, *, lease: SenderLease) -> str | None:
        unknown = False
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            row = connection.execute(
                "select t.reply_text,i.composition_state from public.business_turns t"
                " join public.whatsapp_inbound_messages i on encode(i.provider_message_key,'hex')=t.turn_key"
                " where t.turn_key=%s and t.space_id=%s and t.sender_hash=%s and t.lease_fence=%s"
                " and t.model_state='completed' for update of t,i",
                (captured.turn_key, lease.space_id, lease.sender_hash, lease.fence),
            ).fetchone()
            if row is None:
                raise ValueError("whatsapp_reply_plan_required")
            if row[0] is not None:
                return row[0]
            if row[1] in ("started", "unknown"):
                connection.execute(
                    "update public.whatsapp_inbound_messages set composition_state='unknown'"
                    " where provider_message_key=%s",
                    (captured.message_key,),
                )
                connection.execute(
                    "update public.business_turns set phase='reply_unknown' where turn_key=%s",
                    (captured.turn_key,),
                )
                unknown = True
            else:
                connection.execute(
                    "update public.whatsapp_inbound_messages set composition_state='started'"
                    " where provider_message_key=%s",
                    (captured.message_key,),
                )
            BusinessTurnStore.require_lease(connection, lease)
        if unknown:
            raise ReplyOutcomeUnknown("whatsapp_composition_outcome_unknown")
        return None

    def save_reply(
        self,
        captured: CapturedText,
        body: str,
        *,
        lease: SenderLease,
        fixed: bool = False,
    ) -> None:
        chunks = self._chunks(body)
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            state = connection.execute(
                "select composition_state from public.whatsapp_inbound_messages"
                " where provider_message_key=%s and destination_space_id=%s and sender_hash=%s for update",
                (captured.message_key, lease.space_id, bytes.fromhex(lease.sender_hash)),
            ).fetchone()
            if state is None:
                raise ValueError("whatsapp_capture_not_found")
            if state[0] == "completed":
                existing = connection.execute(
                    "select body from public.whatsapp_outbox where provider_message_key=%s order by reply_index",
                    (captured.message_key,),
                ).fetchall()
                if [row[0] for row in existing] != chunks:
                    raise ValueError("whatsapp_reply_identity_conflict")
                return
            if state[0] != ("not_started" if fixed else "started"):
                raise ReplyOutcomeUnknown("whatsapp_composition_outcome_unknown")
            if not fixed:
                row = connection.execute(
                    "update public.business_turns set reply_text=%s,phase='reply_pending',updated_at=clock_timestamp()"
                    " where turn_key=%s and space_id=%s and sender_hash=%s and lease_fence=%s"
                    " and model_state='completed' and reply_text is null returning turn_key",
                    (
                        body,
                        captured.turn_key,
                        lease.space_id,
                        lease.sender_hash,
                        lease.fence,
                    ),
                ).fetchone()
                if row is None:
                    raise ValueError("whatsapp_reply_plan_required")
            connection.execute(
                "update public.whatsapp_inbound_messages set composition_state='completed',updated_at=clock_timestamp()"
                " where provider_message_key=%s",
                (captured.message_key,),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    "insert into public.whatsapp_outbox(provider_message_key,reply_index,body) values (%s,%s,%s)",
                    [
                        (captured.message_key, index, chunk)
                        for index, chunk in enumerate(chunks)
                    ],
                )
            BusinessTurnStore.require_lease(connection, lease)

    def mark_unknown(self, captured: CapturedText, *, lease: SenderLease) -> None:
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            connection.execute(
                "update public.whatsapp_inbound_messages set composition_state='unknown',updated_at=clock_timestamp()"
                " where provider_message_key=%s and destination_space_id=%s and sender_hash=%s and composition_state in ('not_started','started')",
                (captured.message_key, lease.space_id, bytes.fromhex(lease.sender_hash)),
            )
            connection.execute(
                "update public.business_turns set phase=case when plan is not null then 'reply_unknown' else phase end,"
                " model_state=case when plan is null then 'unknown' else model_state end,updated_at=clock_timestamp()"
                " where turn_key=%s and space_id=%s and sender_hash=%s and lease_fence=%s and reply_text is null",
                (captured.turn_key, lease.space_id, lease.sender_hash, lease.fence),
            )
            BusinessTurnStore.require_lease(connection, lease)

    @staticmethod
    def _chunks(body: str) -> list[str]:
        if not body.strip():
            raise ValueError("whatsapp_reply_empty")
        return [body[start : start + 4096] for start in range(0, len(body), 4096)]

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.ingestion.whatsapp.business_capture import CapturedText
from argus.domain.ingestion.whatsapp.business_outbox import OutboundReply
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore


@dataclass(frozen=True)
class DeliveryClaim:
    state: Literal[
        "sending", "done", "unknown", "waiting_for_window", "suppressed", "deferred"
    ]
    reply: OutboundReply | None = None


class BusinessDeliveryStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def claim(
        self,
        captured: CapturedText,
        *,
        lease: SenderLease,
        permitted: Callable[[], bool],
        sending: Callable[[], bool] = lambda: True,
    ) -> DeliveryClaim:
        """``permitted`` is about authority and ends the reply when false.
        ``sending`` is only whether the transport is on: when off, or while an
        older saved reply of this sender is still unsent, the reply stays
        pending and is picked up later, in arrival order."""

        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            if (captured.space_id, captured.sender_hash.hex()) != (
                lease.space_id,
                lease.sender_hash,
            ):
                raise ValueError("whatsapp_delivery_scope_mismatch")
            row = connection.execute(
                "select reply_index,body,state from public.whatsapp_outbox"
                " where provider_message_key=%s and state in ('pending','sending')"
                " order by reply_index limit 1 for update",
                (captured.message_key,),
            ).fetchone()
            if row is None:
                return DeliveryClaim("done")
            if row[2] == "sending":
                connection.execute(
                    "update public.whatsapp_outbox set state='unknown',error_code='whatsapp_send_outcome_unknown'"
                    " where provider_message_key=%s and reply_index=%s",
                    (captured.message_key, row[0]),
                )
                self._suppress(
                    connection, captured.message_key, "whatsapp_prior_reply_unknown"
                )
                self._phase(connection, captured.turn_key, "reply_unknown")
                BusinessTurnStore.require_lease(connection, lease)
                return DeliveryClaim("unknown")
            if not sending() or self._older_unsent(connection, captured):
                return DeliveryClaim("deferred")
            bound = connection.execute(
                "select 1 from public.whatsapp_sender_links where id=%s and status='active'"
                " and destination_space_id=%s and destination_owner_id=%s and wa_id_hash=%s for share",
                (
                    captured.link_id,
                    captured.space_id,
                    captured.owner_id,
                    captured.sender_hash,
                ),
            ).fetchone()
            if bound is None or not permitted():
                self._suppress(
                    connection, captured.message_key, "whatsapp_send_not_permitted"
                )
                BusinessTurnStore.require_lease(connection, lease)
                return DeliveryClaim("suppressed")
            inside = connection.execute(
                "select clock_timestamp()<%s+interval '24 hours'",
                (captured.envelope.sent_at,),
            ).fetchone()[0]
            if not inside:
                return DeliveryClaim("waiting_for_window")
            connection.execute(
                "update public.whatsapp_outbox set state='sending',attempted_at=clock_timestamp()"
                " where provider_message_key=%s and reply_index=%s",
                (captured.message_key, row[0]),
            )
            BusinessTurnStore.require_lease(connection, lease)
            return DeliveryClaim("sending", OutboundReply(index=row[0], body=row[1]))

    @staticmethod
    def _older_unsent(connection, captured: CapturedText) -> bool:  # noqa: ANN001
        return (
            connection.execute(
                "select 1 from public.whatsapp_inbound_messages me"
                " join public.whatsapp_inbound_messages older"
                " on older.destination_space_id=me.destination_space_id"
                " and older.sender_hash=me.sender_hash"
                " and older.arrival_sequence<me.arrival_sequence"
                " join public.whatsapp_outbox o on o.provider_message_key=older.provider_message_key"
                " where me.provider_message_key=%s and o.state in ('pending','sending') limit 1",
                (captured.message_key,),
            ).fetchone()
            is not None
        )

    def settle(
        self,
        captured: CapturedText,
        reply: OutboundReply,
        *,
        lease: SenderLease,
        sent: bool,
        code: str | None = None,
    ) -> None:
        """``code`` is why an unsent reply is unknown; without one the outcome
        itself is unknown, because the send had started."""

        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            if (captured.space_id, captured.sender_hash.hex()) != (
                lease.space_id,
                lease.sender_hash,
            ):
                raise ValueError("whatsapp_delivery_scope_mismatch")
            row = connection.execute(
                "update public.whatsapp_outbox set state=%s,"
                " sent_at=case when %s then clock_timestamp() else null end,"
                " error_code=case when %s then null else coalesce(%s,'whatsapp_send_outcome_unknown') end"
                " where provider_message_key=%s and reply_index=%s and state='sending' returning reply_index",
                (
                    "sent" if sent else "unknown",
                    sent,
                    sent,
                    code,
                    captured.message_key,
                    reply.index,
                ),
            ).fetchone()
            if row is None:
                raise ValueError("whatsapp_outbox_not_sending")
            if not sent:
                self._suppress(
                    connection, captured.message_key, "whatsapp_prior_reply_unknown"
                )
                self._phase(connection, captured.turn_key, "reply_unknown")
            elif not connection.execute(
                "select 1 from public.whatsapp_outbox where provider_message_key=%s and state<>'sent'",
                (captured.message_key,),
            ).fetchone():
                self._phase(connection, captured.turn_key, "reply_sent")
            BusinessTurnStore.require_lease(connection, lease)

    def give_up(self, key: bytes, *, lease: SenderLease, code: str) -> None:
        """A message that keeps failing for a reason that is not a refusal stops
        blocking its sender: the unsent reply is suppressed with a code and an
        unfinished interpretation is settled unknown."""

        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            sender = bytes.fromhex(lease.sender_hash)
            connection.execute(
                "update public.whatsapp_outbox o set state='suppressed',error_code=%s"
                " from public.whatsapp_inbound_messages i"
                " where o.provider_message_key=i.provider_message_key and o.provider_message_key=%s"
                " and i.destination_space_id=%s and i.sender_hash=%s and o.state='pending'",
                (code, key, lease.space_id, sender),
            )
            connection.execute(
                "update public.whatsapp_inbound_messages set composition_state='unknown',"
                "updated_at=clock_timestamp() where provider_message_key=%s"
                " and destination_space_id=%s and sender_hash=%s"
                " and composition_state in ('not_started','started')",
                (key, lease.space_id, sender),
            )
            BusinessTurnStore.require_lease(connection, lease)

    def wait_for_window(self, captured: CapturedText, *, lease: SenderLease) -> None:
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            connection.execute(
                "update public.whatsapp_outbox o set state='waiting_for_window'"
                " from public.whatsapp_inbound_messages i"
                " where o.provider_message_key=i.provider_message_key and o.provider_message_key=%s"
                " and i.destination_space_id=%s and i.sender_hash=%s and o.state='pending'"
                " and clock_timestamp()>=i.sent_at+interval '24 hours'",
                (captured.message_key, lease.space_id, bytes.fromhex(lease.sender_hash)),
            )
            BusinessTurnStore.require_lease(connection, lease)

    def suppress(self, captured: CapturedText, *, lease: SenderLease) -> None:
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            row = connection.execute(
                "select 1 from public.whatsapp_inbound_messages where provider_message_key=%s"
                " and destination_space_id=%s and sender_hash=%s for share",
                (captured.message_key, lease.space_id, bytes.fromhex(lease.sender_hash)),
            ).fetchone()
            if row is None:
                raise ValueError("whatsapp_delivery_scope_mismatch")
            self._suppress(
                connection, captured.message_key, "whatsapp_send_not_permitted"
            )

    @staticmethod
    def _suppress(connection, key: bytes, code: str) -> None:
        connection.execute(
            "update public.whatsapp_outbox set state='suppressed',error_code=%s"
            " where provider_message_key=%s and state='pending'",
            (code, key),
        )

    @staticmethod
    def _phase(connection, key: str, phase: str) -> None:
        connection.execute(
            "update public.business_turns set phase=%s,updated_at=clock_timestamp()"
            " where turn_key=%s and plan is not null",
            (phase, key),
        )

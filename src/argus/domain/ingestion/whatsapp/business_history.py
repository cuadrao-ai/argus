from __future__ import annotations

from uuid import UUID

from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.ingestion.whatsapp.business_capture import CapturedText
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore


def sent_history(
    pool: ConnectionPool, captured: CapturedText, *, lease: SenderLease, grant_id: UUID
) -> tuple[dict[str, str], ...]:
    with pool.connection() as connection, connection.transaction():
        BusinessTurnStore.require_lease(connection, lease)
        rows = connection.execute(
            "select s.text_content,t.reply_text from public.whatsapp_inbound_messages i"
            " join public.business_turns t on t.turn_key=encode(i.provider_message_key,'hex')"
            " join public.business_sources s on s.space_id=i.destination_space_id"
            " and s.source_key='message:whatsapp:'||i.id::text and s.kind='message' and s.channel='whatsapp'"
            " join public.business_client_grants g on g.id=%s and g.space_id=t.space_id"
            " and g.grantee_id=t.actor_id and g.revoked_at is null"
            " and (g.expires_at is null or g.expires_at>clock_timestamp())"
            " and array['read','prepare']::text[]<@g.capabilities"
            " where i.destination_space_id=%s and i.sender_hash=%s and i.destination_owner_id=%s"
            " and i.arrival_sequence<%s and i.composition_state='completed'"
            " and t.space_id=i.destination_space_id and t.sender_hash=encode(i.sender_hash,'hex')"
            " and t.actor_id=i.destination_owner_id and t.phase='reply_sent'"
            " and t.plan is not null and t.reply_text is not null"
            " and t.plan_actor->>'actor_kind'='owner_via_agent'"
            " and t.plan_actor->>'grant_id'=g.id::text and t.plan_actor->>'issuer_id'=g.issuer_id::text"
            " order by i.arrival_sequence desc limit 3",
            (
                grant_id,
                lease.space_id,
                bytes.fromhex(lease.sender_hash),
                captured.owner_id,
                captured.arrival_sequence,
            ),
        ).fetchall()
        BusinessTurnStore.require_lease(connection, lease)
    return tuple(
        {
            "role": role,
            "content": content.encode("utf-8")[:1000].decode("utf-8", errors="ignore"),
        }
        for user, assistant in reversed(rows)
        for role, content in (("user", user), ("assistant", assistant))
    )

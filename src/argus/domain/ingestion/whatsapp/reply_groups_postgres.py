from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from loguru import logger
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.ingestion.whatsapp.reply_groups import (
    ATTEMPT_TTL,
    WINDOW,
    PendingFailure,
    ReplyAttempt,
    ReplyGroup,
    earliest,
    suppressed,
)

_GROUP_COLUMNS = (
    "sender_hash,owner_id::text,link_id::text,failed_count,samples,"
    "last_sent_at,send_after,retries"
)


def _group(row: tuple) -> ReplyGroup:
    return ReplyGroup(bytes(row[0]), *row[1:])


class PostgresReplyGroups:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @staticmethod
    def enqueue_on(connection, failure: PendingFailure) -> None:
        link = connection.execute(
            "select id::text from public.whatsapp_sender_links"
            " where wa_id_hash=%s and destination_owner_id=%s and linked_at=%s"
            " and status='active' for share",
            (failure.sender_hash, failure.owner_id, failure.linked_at),
        ).fetchone()
        if link is None:
            suppressed("unknown_sender", failure.sender_hash)
            return
        PostgresReplyGroups._put(
            connection,
            ReplyGroup(
                failure.sender_hash,
                failure.owner_id,
                link[0],
                1,
                [failure.sample],
                failure.sent_at,
                failure.send_after,
            ),
        )

    @staticmethod
    def _put(connection, group: ReplyGroup, *, retry: bool = False) -> None:
        samples = (
            "excluded.samples || g.samples" if retry else "g.samples || excluded.samples"
        )
        connection.execute(
            "insert into public.whatsapp_reply_groups as g "
            "(sender_hash,owner_id,link_id,failed_count,samples,last_sent_at,send_after,retries)"
            " values (%s,%s,%s,%s,%s,%s,%s,%s)"
            " on conflict(sender_hash) do update set"
            " owner_id=excluded.owner_id,link_id=excluded.link_id,"
            " failed_count=case when g.link_id=excluded.link_id then g.failed_count+excluded.failed_count else excluded.failed_count end,"
            " samples=case when g.link_id=excluded.link_id then"
            " (select jsonb_agg(sample order by sample->>'at',ordinal) from"
            f" (select sample,ordinal from jsonb_array_elements({samples})"
            " with ordinality as items(sample,ordinal)"
            " order by sample->>'at',ordinal limit 3) first_three) else excluded.samples end,"
            " last_sent_at=case when g.link_id=excluded.link_id then greatest(g.last_sent_at,excluded.last_sent_at) else excluded.last_sent_at end,"
            " send_after=case when g.link_id=excluded.link_id then greatest(g.send_after,excluded.send_after) else excluded.send_after end,"
            " retries=case when g.link_id=excluded.link_id then greatest(g.retries,excluded.retries) else excluded.retries end",
            (
                group.sender_hash,
                group.owner_id,
                group.link_id,
                group.count,
                Jsonb(earliest(group.samples)),
                group.last_sent_at,
                group.send_after,
                group.retries,
            ),
        )

    def claim(self, *, now: datetime, limit: int) -> ReplyAttempt | None:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                f"select {_GROUP_COLUMNS} from public.whatsapp_reply_groups g"
                " where send_after<=%s and not exists"
                " (select 1 from public.whatsapp_reply_attempts a where a.sender_hash=g.sender_hash)"
                " order by send_after limit 1 for update of g skip locked",
                (now,),
            ).fetchone()
            if row is None:
                return None
            group = _group(row)
            linked = connection.execute(
                "select 1 from public.whatsapp_sender_links where id=%s"
                " and wa_id_hash=%s and destination_owner_id=%s and status='active'",
                (group.link_id, group.sender_hash, group.owner_id),
            ).fetchone()
            reason = (
                "unknown_sender"
                if linked is None
                else ("window" if now - group.last_sent_at >= WINDOW else None)
            )
            if reason:
                self._drop(connection, group.sender_hash)
                suppressed(reason, group.sender_hash)
                return None
            day = now.astimezone(timezone.utc).date()
            count = connection.execute(
                "insert into public.whatsapp_reply_days as d"
                " (sender_hash,day,owner_id,reserved_count) values (%s,%s,%s,1)"
                " on conflict(sender_hash,day) do update set reserved_count=d.reserved_count+1,owner_id=excluded.owner_id"
                " where d.sent_count+d.reserved_count<%s"
                " returning sent_count+reserved_count",
                (group.sender_hash, day, group.owner_id, limit),
            ).fetchone()
            if count is None:
                self._drop(connection, group.sender_hash)
                suppressed("daily_limit", group.sender_hash)
                return None
            token = str(uuid4())
            connection.execute(
                "insert into public.whatsapp_reply_attempts"
                " (sender_hash,token,owner_id,link_id,day,failed_count,samples,last_sent_at,expires_at,retries)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    group.sender_hash,
                    token,
                    group.owner_id,
                    group.link_id,
                    day,
                    group.count,
                    Jsonb(group.samples),
                    group.last_sent_at,
                    now + ATTEMPT_TTL,
                    group.retries,
                ),
            )
            self._drop(connection, group.sender_hash)
            return ReplyAttempt(token, group, count[0] == limit)

    @staticmethod
    def _drop(connection, sender_hash: bytes) -> None:
        connection.execute(
            "delete from public.whatsapp_reply_groups where sender_hash=%s",
            (sender_hash,),
        )

    def authorized(self, attempt: ReplyAttempt, *, now: datetime) -> bool:
        with self.pool.connection() as connection:
            return (
                connection.execute(
                    "select 1 from public.whatsapp_reply_attempts a"
                    " join public.whatsapp_sender_links l on l.id=a.link_id"
                    " where a.sender_hash=%s and a.token=%s and a.expires_at>%s"
                    " and l.status='active' and l.wa_id_hash=a.sender_hash"
                    " and l.destination_owner_id=a.owner_id",
                    (attempt.group.sender_hash, attempt.token, now),
                ).fetchone()
                is not None
            )

    def finish(self, attempt: ReplyAttempt, *, now: datetime, outcome: str) -> None:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select day from public.whatsapp_reply_attempts where sender_hash=%s"
                " and token=%s for update",
                (attempt.group.sender_hash, attempt.token),
            ).fetchone()
            if row is None:
                return
            sender, day = attempt.group.sender_hash, row[0]
            if outcome != "unknown":
                connection.execute(
                    "update public.whatsapp_reply_days set reserved_count=reserved_count-1,"
                    " sent_count=sent_count+%s where sender_hash=%s and day=%s and reserved_count>0",
                    (1 if outcome == "sent" else 0, sender, day),
                )
            linked = connection.execute(
                "select 1 from public.whatsapp_sender_links where id=%s and status='active' for share",
                (attempt.group.link_id,),
            ).fetchone()
            if outcome == "retry" and linked is not None:
                group = attempt.group
                self._put(
                    connection,
                    ReplyGroup(
                        sender,
                        group.owner_id,
                        group.link_id,
                        group.count,
                        group.samples,
                        group.last_sent_at,
                        now
                        + timedelta(seconds=min(30 * 2 ** min(group.retries, 7), 3600)),
                        group.retries + 1,
                    ),
                    retry=True,
                )
            connection.execute(
                "delete from public.whatsapp_reply_attempts where sender_hash=%s and token=%s",
                (sender, attempt.token),
            )
            logger.info(
                "WhatsApp grouped reply settled",
                event="whatsapp_grouped_reply_settled",
                outcome=outcome,
            )

    def recover(self, *, now: datetime) -> None:
        # A committed attempt may have reached the provider before the process stopped.
        # Keep its reservation and never replay it without a known send outcome.
        with self.pool.connection() as connection, connection.transaction():
            expired_groups = connection.execute(
                "delete from public.whatsapp_reply_groups where last_sent_at<=%s returning sender_hash",
                (now - WINDOW,),
            ).fetchall()
            for row in expired_groups:
                suppressed("window", bytes(row[0]))
            expired = connection.execute(
                "delete from public.whatsapp_reply_attempts where expires_at<=%s returning sender_hash",
                (now,),
            ).fetchall()
            for row in expired:
                suppressed("send_outcome_unknown", bytes(row[0]))
            removed = connection.execute(
                "delete from public.whatsapp_reply_days d where day<%s"
                " and not exists (select 1 from public.whatsapp_reply_attempts a"
                " where a.sender_hash=d.sender_hash and a.day=d.day) returning day",
                (now.astimezone(timezone.utc).date() - timedelta(days=7),),
            ).fetchall()
            if removed:
                logger.info(
                    "WhatsApp reply counters purged",
                    event="whatsapp_reply_counters_purged",
                    rows=len(removed),
                )

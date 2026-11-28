from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger
from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.read_budget import HELD_READ_REFUSAL
from argus.domain.ingestion.email_intake.budget import business_day
from argus.domain.ingestion.whatsapp.reply_groups import (
    ATTEMPT_TTL,
    DUE_EVERY,
    WINDOW,
    BatchOutcomes,
    PendingFailure,
    ReplyAttempt,
    ReplyGroup,
    suppressed,
)
from argus.domain.ingestion.whatsapp.store import CapturePublisher, Settlement
from argus.domain.postgres_connection import BorrowedConnection

if TYPE_CHECKING:
    from argus.domain.ingestion.whatsapp.reply_worker import ReplyClaim

QUIET = timedelta(minutes=1)
DEADLINE = timedelta(minutes=3)
_GROUP_COLUMNS = (
    "g.id,g.sender_hash,g.owner_id::text,g.link_id::text,g.member_count,g.samples,"
    "g.last_sent_at,g.send_after,g.retries,g.kind,g.last_arrival"
)


def _group(row: tuple) -> ReplyGroup:
    return ReplyGroup(bytes(row[1]), *row[2:10], last_arrival=row[10], group_id=row[0])


def _outcomes(db: Connection, group: ReplyGroup) -> BatchOutcomes:
    # Existing failure-only batches have no durable inbound membership.
    if "kind" not in group.samples[0]:
        return BatchOutcomes(
            not_received=group.count, failure_keys=tuple(s["key"] for s in group.samples)
        )
    rows = db.execute(
        "select m.provider_message_key,m.status,m.capture_duplicate,c.owner_space_id::text,"
        "d.draft->>'status',d.draft->>'error_code',h.state from public.whatsapp_inbound_messages m "
        "left join public.financial_source_connections c on c.id=m.connection_id "
        "left join public.financial_document_extractions d on d.connection_id=m.connection_id and d.user_id=c.user_id "
        "left join public.whatsapp_held_files h on h.provider_message_key=m.provider_message_key "
        "where m.reply_group_id=%s and m.sender_hash=%s and m.destination_owner_id=%s",
        (group.group_id, group.sender_hash, group.owner_id),
    ).fetchall()
    names = {}
    if any(row[3] for row in rows):
        names = {
            grant.space_id: grant.name
            for grant in PostgresAccessStore(BorrowedConnection(db)).spaces_for(
                group.owner_id
            )
        }
    duplicates = held = reading = tomorrow = 0
    failed = set()
    businesses: Counter[str] = Counter()
    for key, status, duplicate, space, draft_status, code, held_state in rows:
        if status != "captured":
            failed.add(key.hex())
        elif draft_status is None or held_state == "expired":
            continue
        elif duplicate:
            duplicates += 1
        elif draft_status in ("queued", "preparing"):
            reading += 1
        else:
            if held_state != "held" and space in names:
                businesses[space] += 1
            else:
                held += 1
            if code in ("business_read_budget_day", HELD_READ_REFUSAL):
                tomorrow += 1
    return BatchOutcomes(
        businesses=tuple(
            sorted((names[space], count) for space, count in businesses.items())
        ),
        held=held,
        duplicates=duplicates,
        not_received=len(failed),
        reading=reading,
        read_tomorrow=tomorrow,
        failure_keys=tuple(s["key"] for s in group.samples if s["key"] in failed),
    )


def _awaiting_capture(db: Connection, group: ReplyGroup) -> bool:
    pending = db.execute(
        "select 1 from public.whatsapp_inbound_messages where reply_group_id=%s"
        " and destination_owner_id is null and status in ('received','failed') limit 1",
        (group.group_id,),
    ).fetchone()
    return pending is not None


def _represented(outcomes: BatchOutcomes) -> int:
    return (
        sum(n for _, n in outcomes.businesses)
        + outcomes.held
        + outcomes.duplicates
        + outcomes.not_received
        + outcomes.reading
    )


def _samples(samples: list[dict]) -> list[dict]:
    ordered = sorted(samples, key=lambda sample: sample["at"])
    failures = [sample for sample in ordered if sample.get("failure", True)]
    return failures[:3] or ordered[:1]


def _write(db: Connection, group: ReplyGroup) -> None:
    db.execute(
        "insert into public.whatsapp_reply_groups "
        "(id,sender_hash,owner_id,link_id,member_count,samples,last_sent_at,send_after,retries,"
        "kind,last_arrival) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        " on conflict(id) do update set member_count=excluded.member_count,samples=excluded.samples,"
        "last_sent_at=excluded.last_sent_at,send_after=excluded.send_after,"
        "last_arrival=excluded.last_arrival",
        (
            group.group_id,
            group.sender_hash,
            group.owner_id,
            group.link_id,
            group.count,
            Jsonb(group.samples),
            group.last_sent_at,
            group.send_after,
            group.retries,
            group.kind,
            group.last_arrival,
        ),
    )


class CaptureForReply:
    """Record deduplication on the inbound row in the capture's own transaction."""

    def __init__(self, publisher: CapturePublisher) -> None:
        self._prepare = publisher.prepare
        self.discard = publisher.discard
        self.route_saved = publisher.route_saved

    def prepare(
        self,
        connection: Connection | None,
        settlement: Settlement,
        message_key: bytes,
        *,
        rollback: ExitStack | None = None,
    ) -> Settlement:
        result = self._prepare(connection, settlement, message_key, rollback=rollback)
        # A recovered staged upload reuses bytes but publishes a new receipt.
        if result.duplicate and result.report_arrival:
            result = replace(result, duplicate=False)
        if connection is not None and result.duplicate:
            connection.execute(
                "update public.whatsapp_inbound_messages set capture_duplicate=true"
                " where provider_message_key=%s",
                (message_key,),
            )
        return result


class PostgresReplyGroups:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def start_envelope(self, files: list[PendingFailure], arrived_at: datetime) -> None:
        """Persist a sender's file arrivals together. Processing claims each file in turn."""
        keys = sorted({bytes.fromhex(file.sample["key"]) for file in files})
        with self.pool.connection() as db, db.transaction():
            db.execute(
                "insert into public.whatsapp_inbound_messages "
                "(provider_message_key,sender_hash,status,received_at,updated_at) "
                "select key,%s,'received',%s,%s from unnest(%s::bytea[]) as f(key)"
                " order by key on conflict(provider_message_key) do nothing",
                (files[0].sender_hash, arrived_at, arrived_at, keys),
            )
            # Lock replayed rows as well as new ones before taking group locks.
            db.execute(
                "select provider_message_key from public.whatsapp_inbound_messages"
                " where provider_message_key=any(%s) order by provider_message_key for update",
                (keys,),
            )
            for file in files:
                self._enroll(db, file, starting=True)

    def start_file(self, pending: PendingFailure) -> None:
        """Bind the incoming file before the download starts, without declaring an outcome."""
        with self.pool.connection() as db, db.transaction():
            self._enroll(db, pending, starting=True)

    @staticmethod
    def enqueue_on(db: Connection, pending: PendingFailure) -> None:
        PostgresReplyGroups._enroll(db, pending, starting=False)

    @staticmethod
    def _enroll(db: Connection, pending: PendingFailure, *, starting: bool) -> None:
        key = pending.sample["key"]
        inbound = db.execute(
            "select l.id::text,m.status,m.received_at,m.reply_group_id from public.whatsapp_sender_links l"
            " join public.whatsapp_inbound_messages m on m.sender_hash=l.wa_id_hash"
            " and m.provider_message_key=%s"
            " where l.wa_id_hash=%s and l.destination_owner_id=%s and l.linked_at=%s"
            " and l.status='active' and (case when %s then m.status in ('received','failed')"
            " else m.destination_owner_id=l.destination_owner_id end)"
            " for share of l for update of m",
            (
                bytes.fromhex(key),
                pending.sender_hash,
                pending.owner_id,
                pending.linked_at,
                starting,
            ),
        ).fetchone()
        if inbound is None:
            suppressed("unknown_sender", pending.sender_hash)
            return
        link_id, status, arrival, previous_group = inbound
        kind = pending.sample["kind"]
        failed_file = not starting and kind == "files" and status != "captured"
        sample = {**pending.sample, "failure": failed_file}
        if previous_group is not None:
            if failed_file:
                row = db.execute(
                    "select samples from public.whatsapp_reply_groups"
                    " where id=%s and link_id=%s for update",
                    (previous_group, link_id),
                ).fetchone()
                if row:
                    others = [item for item in row[0] if item["key"] != key]
                    db.execute(
                        "update public.whatsapp_reply_groups set samples=%s where id=%s",
                        (Jsonb(_samples([*others, sample])), previous_group),
                    )
            return
        new = ReplyGroup(
            pending.sender_hash,
            pending.owner_id,
            link_id,
            1,
            [sample],
            pending.sent_at,
            arrival + QUIET,
            kind=kind,
            group_id=uuid4(),
            last_arrival=arrival,
        )
        # Serialize admissions even when neither transaction can see a first group yet.
        db.execute(
            "select pg_advisory_xact_lock(%s)",
            (int.from_bytes(pending.sender_hash[:8], "big", signed=True),),
        )
        row = db.execute(
            f"select {_GROUP_COLUMNS} from public.whatsapp_reply_groups g where g.sender_hash=%s "
            "and g.link_id=%s and g.kind=%s and g.retries=0 order by g.last_arrival desc,g.id limit 1 for update",
            (new.sender_hash, link_id, kind),
        ).fetchone()
        if row is not None:
            prior = _group(row)
            gap = arrival - prior.last_arrival
            # A deferred due pass keeps the forward open for claims that arrived
            # during the wait, even if its last read finished before settlement.
            if "kind" in prior.samples[0] and (
                arrival <= prior.send_after
                or (
                    kind == "files"
                    and gap < DEADLINE
                    and (_awaiting_capture(db, prior) or _outcomes(db, prior).reading)
                )
            ):
                new = replace(
                    prior,
                    count=prior.count + 1,
                    samples=_samples(prior.samples + [sample]),
                    last_sent_at=max(prior.last_sent_at, new.last_sent_at),
                    last_arrival=max(prior.last_arrival, arrival),
                    send_after=max(prior.last_arrival, arrival) + QUIET,
                )
        _write(db, new)
        db.execute(
            "update public.whatsapp_inbound_messages set reply_group_id=%s where provider_message_key=%s",
            (new.group_id, bytes.fromhex(key)),
        )

    def claim(self, *, now: datetime, limit: int) -> ReplyClaim:
        with self.pool.connection() as db, db.transaction():
            row = db.execute(
                f"select {_GROUP_COLUMNS} from public.whatsapp_reply_groups g"
                " where send_after<=%s and not exists"
                " (select 1 from public.whatsapp_reply_attempts a where a.sender_hash=g.sender_hash)"
                " and not exists (select 1 from public.whatsapp_reply_groups first_group where"
                " first_group.sender_hash=g.sender_hash and (first_group.send_after,first_group.id)<(g.send_after,g.id))"
                " order by send_after,g.id limit 1 for update of g skip locked",
                (now,),
            ).fetchone()
            if row is None:
                return None
            group = _group(row)
            linked = db.execute(
                "select 1 from public.whatsapp_sender_links where id=%s and wa_id_hash=%s"
                " and destination_owner_id=%s and status='active'",
                (group.link_id, group.sender_hash, group.owner_id),
            ).fetchone()
            reason = (
                "unknown_sender"
                if linked is None
                else "window"
                if now - group.last_sent_at >= WINDOW
                else None
            )
            if reason:
                db.execute(
                    "delete from public.whatsapp_reply_groups where id=%s", (row[0],)
                )
                suppressed(reason, group.sender_hash)
                return True
            outcomes = _outcomes(db, group) if group.kind == "files" else BatchOutcomes()
            if group.kind == "files":
                if (
                    _awaiting_capture(db, group) or outcomes.reading
                ) and now + DUE_EVERY <= group.last_arrival + DEADLINE:
                    db.execute(
                        "update public.whatsapp_reply_groups set send_after=%s where id=%s",
                        (now + DUE_EVERY, group.group_id),
                    )
                    return True
                total = _represented(outcomes)
                if total != group.count:
                    # An uncommitted or purged file has no outcome the worker can report.
                    db.execute(
                        "delete from public.whatsapp_reply_groups where id=%s",
                        (group.group_id,),
                    )
                    return True
            day = None
            final = exhausted = False
            if group.kind == "guidance":
                day = business_day(now)
                reservation = db.execute(
                    "insert into public.whatsapp_reply_days as d(sender_hash,owner_id,day,guidance_reserved)"
                    " values(%s,%s,%s,true) on conflict(sender_hash,day) do update set guidance_reserved=true,owner_id=excluded.owner_id"
                    " where not d.guidance_reserved returning 1",
                    (group.sender_hash, group.owner_id, day),
                ).fetchone()
                exhausted = reservation is None
            elif outcomes.not_received:
                day = now.astimezone(timezone.utc).date()
                count = db.execute(
                    "insert into public.whatsapp_reply_days as d(sender_hash,owner_id,day,reserved_count)"
                    " values(%s,%s,%s,1) on conflict(sender_hash,day) do update set reserved_count=d.reserved_count+1,owner_id=excluded.owner_id"
                    " where d.sent_count+d.reserved_count<%s returning sent_count+reserved_count",
                    (group.sender_hash, group.owner_id, day, limit),
                ).fetchone()
                exhausted = count is None
                final = bool(count and count[0] == limit)
            db.execute("delete from public.whatsapp_reply_groups where id=%s", (row[0],))
            if exhausted and (
                group.kind == "guidance" or outcomes.not_received == group.count
            ):
                suppressed("daily_limit", group.sender_hash)
                return True
            token = str(uuid4())
            db.execute(
                "insert into public.whatsapp_reply_attempts"
                " (sender_hash,token,owner_id,link_id,day,member_count,samples,last_sent_at,expires_at,retries)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    group.sender_hash,
                    token,
                    group.owner_id,
                    group.link_id,
                    None if exhausted else day,
                    group.count,
                    Jsonb(group.samples),
                    group.last_sent_at,
                    now + ATTEMPT_TTL,
                    group.retries,
                ),
            )
            return ReplyAttempt(token, group, final, outcomes, exhausted)

    def authorized(self, attempt: ReplyAttempt, *, now: datetime) -> bool:
        with self.pool.connection() as db, db.transaction():
            current = db.execute(
                "select 1 from public.whatsapp_reply_attempts a join public.whatsapp_sender_links l on l.id=a.link_id"
                " where a.sender_hash=%s and a.token=%s and a.expires_at>%s and a.last_sent_at>%s"
                " and l.status='active' and l.wa_id_hash=a.sender_hash and l.destination_owner_id=a.owner_id"
                " for update of a",
                (attempt.group.sender_hash, attempt.token, now, now - WINDOW),
            ).fetchone()
            if current is None:
                return False
            if (
                attempt.group.kind == "files"
                and _outcomes(db, attempt.group) != attempt.outcomes
            ):
                # A stale name or read result must never leave the worker. Return this
                # forward to the same due pass with its previous reservation released.
                self._finish_on(db, attempt, now=now, outcome="refresh")
                return False
            return True

    def finish(self, attempt: ReplyAttempt, *, now: datetime, outcome: str) -> None:
        with self.pool.connection() as db, db.transaction():
            self._finish_on(db, attempt, now=now, outcome=outcome)

    @staticmethod
    def _finish_on(
        db: Connection, attempt: ReplyAttempt, *, now: datetime, outcome: str
    ) -> None:
        row = db.execute(
            "delete from public.whatsapp_reply_attempts where sender_hash=%s and token=%s returning day",
            (attempt.group.sender_hash, attempt.token),
        ).fetchone()
        if row is None:
            return
        group, day = attempt.group, row[0]
        if day is not None and outcome != "unknown":
            if group.kind == "guidance":
                db.execute(
                    "update public.whatsapp_reply_days set guidance_reserved=%s where sender_hash=%s and day=%s",
                    (outcome == "sent", group.sender_hash, day),
                )
            else:
                db.execute(
                    "update public.whatsapp_reply_days set reserved_count=reserved_count-1,sent_count=sent_count+%s"
                    " where sender_hash=%s and day=%s and reserved_count>0",
                    (int(outcome == "sent"), group.sender_hash, day),
                )
        if (
            outcome in ("retry", "refresh")
            and db.execute(
                "select 1 from public.whatsapp_sender_links where id=%s and status='active' for share",
                (group.link_id,),
            ).fetchone()
        ):
            delay = (
                timedelta(seconds=min(30 * 2 ** min(group.retries, 7), 3600))
                if outcome == "retry"
                else timedelta()
            )
            _write(db, replace(group, retries=group.retries + 1, send_after=now + delay))
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

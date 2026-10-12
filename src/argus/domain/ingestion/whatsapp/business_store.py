from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from argus.domain.business.contracts.recovery import DurableTurn, SenderLease


class LeaseLost(RuntimeError):
    pass


class BusinessTurnStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def acquire(
        self,
        *,
        space_id: UUID,
        sender_hash: str,
        holder: UUID,
        duration: timedelta,
    ) -> SenderLease | None:
        if not timedelta(0) < duration <= timedelta(minutes=5):
            raise ValueError("lease duration must be positive and at most five minutes")
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "insert into public.business_sender_leases as l"
                " (space_id,sender_hash,holder,fence,lease_until)"
                " values (%s,%s,%s,1,clock_timestamp()+%s)"
                " on conflict (space_id,sender_hash) do update"
                " set holder=excluded.holder,fence=l.fence+1,"
                " lease_until=clock_timestamp()+%s"
                " where l.lease_until<=clock_timestamp()"
                " returning space_id,sender_hash,holder,fence,lease_until",
                (space_id, sender_hash, holder, duration, duration),
            ).fetchone()
        return self._lease(row) if row is not None else None

    def renew(self, lease: SenderLease, *, duration: timedelta) -> SenderLease:
        if not timedelta(0) < duration <= timedelta(minutes=5):
            raise ValueError("lease duration must be positive and at most five minutes")
        with self.pool.connection() as connection, connection.transaction():
            self.require_lease(connection, lease)
            row = connection.execute(
                "update public.business_sender_leases"
                " set lease_until=clock_timestamp()+%s"
                " where space_id=%s and sender_hash=%s and lease_until>clock_timestamp()"
                " returning space_id,sender_hash,holder,fence,lease_until",
                (duration, lease.space_id, lease.sender_hash),
            ).fetchone()
            if row is None:
                raise LeaseLost("business_sender_lease_lost")
        return self._lease(row)

    def release(self, lease: SenderLease) -> None:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "update public.business_sender_leases set lease_until=clock_timestamp()"
                " where space_id=%s and sender_hash=%s and holder=%s and fence=%s",
                (lease.space_id, lease.sender_hash, lease.holder, lease.fence),
            )

    def load_turn(self, turn_key: str) -> DurableTurn | None:
        with self.pool.connection() as connection:
            return self._turn(connection, turn_key)

    def start_turn(
        self, *, turn_key: str, actor_id: UUID, lease: SenderLease
    ) -> DurableTurn:
        with self.pool.connection() as connection, connection.transaction():
            self.require_lease(connection, lease)
            connection.execute(
                "insert into public.business_turns"
                " (turn_key,space_id,sender_hash,actor_id) values (%s,%s,%s,%s)"
                " on conflict (turn_key) do nothing",
                (turn_key, lease.space_id, lease.sender_hash, actor_id),
            )
            turn = self._turn(connection, turn_key, lock=True)
            if turn is None:
                raise RuntimeError("business_turn_missing")
            if (turn.space_id, turn.sender_hash, turn.actor_id) != (
                lease.space_id,
                lease.sender_hash,
                actor_id,
            ):
                raise ValueError("business_turn_identity_conflict")
            state = turn.model_state
            if state == "running":
                state = "unknown"
            elif state == "not_started":
                state = "running"
            connection.execute(
                "update public.business_turns set lease_fence=%s,model_state=%s,"
                " phase=case when phase='captured' then 'turn_running' else phase end,"
                " updated_at=clock_timestamp() where turn_key=%s",
                (lease.fence, state, turn_key),
            )
            self.require_lease(connection, lease)
            current = self._turn(connection, turn_key)
            if current is None:
                raise RuntimeError("business_turn_missing")
            return current

    def mark_model_unknown(self, *, turn_key: str, lease: SenderLease) -> None:
        with self.pool.connection() as connection, connection.transaction():
            self.require_lease(connection, lease)
            connection.execute(
                "update public.business_turns set model_state='unknown',"
                " updated_at=clock_timestamp() where turn_key=%s and space_id=%s"
                " and sender_hash=%s and lease_fence=%s and model_state='running'"
                " and plan is null",
                (turn_key, lease.space_id, lease.sender_hash, lease.fence),
            )
            self.require_lease(connection, lease)

    @staticmethod
    def _turn(
        connection: Connection, turn_key: str, *, lock: bool = False
    ) -> DurableTurn | None:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select space_id,actor_id,sender_hash,turn_key,arrival_sequence,"
                " phase,model_state,plan,plan_actor,lease_fence,reply_text"
                " from public.business_turns where turn_key=%s"
                + (" for update" if lock else ""),
                (turn_key,),
            )
            row = cursor.fetchone()
        return DurableTurn.model_validate(row) if row is not None else None

    @staticmethod
    def require_lease(connection: Connection, lease: SenderLease) -> None:
        row = connection.execute(
            "select holder,fence,lease_until"
            " from public.business_sender_leases"
            " where space_id=%s and sender_hash=%s for update",
            (lease.space_id, lease.sender_hash),
        ).fetchone()
        now = connection.execute("select clock_timestamp()").fetchone()[0]
        if row is None or row[:2] != (lease.holder, lease.fence) or row[2] <= now:
            raise LeaseLost("business_sender_lease_lost")

    @staticmethod
    def _lease(row: tuple) -> SenderLease:
        return SenderLease(
            space_id=row[0],
            sender_hash=row[1],
            holder=row[2],
            fence=row[3],
            lease_until=row[4],
        )

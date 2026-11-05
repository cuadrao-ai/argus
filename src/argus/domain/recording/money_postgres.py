"""Atomic multi-account persistence, without a second money-rule implementation."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from argus.domain.owner_scope import OwnerScope, sql_predicate
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RegisteredAccountRequired,
)
from argus.domain.recording.loop import ExpenseRecord
from argus.domain.recording.money_plan import MoneyPlan
from argus.domain.recording.repository import StoredAccount


def owner_lock(connection: Connection, user_id: str) -> None:
    connection.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s,0))",
        ("financial_activity:" + user_id,),
    )


def load_owner(
    repository: Any, connection: Connection, user_id: str, *, scope: OwnerScope
) -> list[StoredAccount]:
    in_scope, params = sql_predicate(scope, "owner_space_id")
    rows = connection.execute(
        "select id from public.financial_accounts"
        f" where user_id=%s and {in_scope} order by id",
        (user_id, *params),
    ).fetchall()
    return [repository._load(connection, user_id, str(r[0]), scope=scope) for r in rows]


def persist(
    connection: Connection,
    user_id: str,
    result: MoneyPlan,
    leg_owners: dict[str, str] | None = None,
) -> None:
    primary = next(
        m.record.current
        for m in result.mutations.values()
        if isinstance(m.record, ExpenseRecord)
        and m.record.current.active
        and m.record.current.role != "destination"
    )
    connection.execute(
        "insert into public.financial_activity_groups(id,user_id,kind,current_revision) values(%s,%s,%s,%s) on conflict(id) do update set current_revision=excluded.current_revision",
        (result.activity_id, user_id, primary.kind, result.revision),
    )
    connection.execute(
        "insert into public.financial_activity_revisions(activity_id,revision,user_id) values(%s,%s,%s)",
        (result.activity_id, result.revision, user_id),
    )
    for account_id, mutation in result.mutations.items():
        record_owner = leg_owners[account_id] if leg_owners is not None else user_id
        record = mutation.record
        assert isinstance(record, ExpenseRecord)
        r = record.current
        details = {
            key: getattr(r, key)
            for key in (
                "note",
                "category_id",
                "kind",
                "role",
                "active",
                "activity_id",
                "activity_revision",
                "source_id",
                "purchase_activity_id",
                "purchase_revision",
                "interest_minor",
                "reversal_of_activity_id",
                "reversal_of_revision",
            )
        }
        details["entered_on"] = r.entered_on.isoformat() if r.entered_on else None
        details["coverage_skips"] = [list(skip) for skip in r.coverage_skips]
        reason = r.reason
        if record_owner != user_id and r.role == "destination":
            for field in ("note", "category_id", "source_id", "interest_minor"):
                details[field] = None
            reason = None
        if r.reversal_of_activity_id:
            original = connection.execute(
                "select user_id from public.financial_activity_groups where id=%s",
                (r.reversal_of_activity_id,),
            ).fetchone()
            if original is None:
                raise AccountNotFound()
            details["reversal_of_owner_id"] = str(original[0])
        connection.execute(
            "insert into public.financial_records(id,account_id,user_id,record_kind,current_revision,created_at) values(%s,%s,%s,%s,%s,%s) on conflict(id) do update set current_revision=excluded.current_revision",
            (record.id, account_id, record_owner, r.kind, r.revision, r.recorded_at),
        )
        connection.execute(
            "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,reason,recorded_by,recorded_at,details) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                record.id,
                record_owner,
                r.revision,
                r.movement_minor,
                r.occurred_at,
                r.time_zone,
                reason,
                r.recorded_by,
                r.recorded_at,
                Jsonb(details),
            ),
        )
        if r.active:
            connection.execute(
                "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,role,record_owner_id) values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    result.activity_id,
                    user_id,
                    result.revision,
                    record.id,
                    r.revision,
                    r.role,
                    record_owner,
                ),
            )
        for link in mutation.coverage:
            connection.execute(
                "insert into public.financial_observation_coverage(account_id,user_id,observation_id,observation_revision,activity_id,activity_revision,included) values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    account_id,
                    record_owner,
                    link.observation_id,
                    link.observation_revision,
                    link.activity_id,
                    link.activity_revision,
                    link.included,
                ),
            )
    for aid in result.affected:
        connection.execute(
            "update public.financial_accounts set version=version+1 where id=%s and user_id=%s",
            (aid, leg_owners[aid] if leg_owners is not None else user_id),
        )


def transact_postgres(
    repository: Any,
    user_id: str,
    key: str,
    identity: str,
    planner: Callable[[list[StoredAccount]], MoneyPlan],
    now: datetime,
    legacy_account: str | None,
    *,
    scope: OwnerScope,
) -> tuple[list[StoredAccount], str, int, tuple[str, ...], bool]:
    in_scope, in_params = sql_predicate(scope, "owner_space_id")
    with repository._pool.connection() as connection:
        with connection.transaction():
            from .canonical_groups import VisibleAccounts, load, owner_closure

            for owner in owner_closure(connection, {user_id}):
                owner_lock(connection, owner)
            if not connection.execute(
                "select 1 from auth.users where id=%s and coalesce(is_anonymous,false)=false",
                (user_id,),
            ).fetchone():
                raise RegisteredAccountRequired()
            receipt = connection.execute(
                "select identity_hash,activity_id,revision,affected_accounts from public.financial_activity_receipts where user_id=%s and scope=%s and idempotency_key=%s",
                (user_id, legacy_account or "canonical", key),
            ).fetchone()
            if not receipt and legacy_account:
                old = connection.execute(
                    "select identity_hash,record_id,revision from public.financial_operation_receipts where user_id=%s and account_id=%s and idempotency_key=%s",
                    (user_id, legacy_account, key),
                ).fetchone()
                if old:
                    receipt = (*old, [legacy_account])
            if receipt:
                if receipt[0] != identity:
                    raise IdempotencyConflict()
                return (
                    load_owner(repository, connection, user_id, scope=scope),
                    str(receipt[1]),
                    receipt[2],
                    tuple(str(a) for a in receipt[3]),
                    True,
                )
            initial = planner(
                VisibleAccounts(
                    load_owner(repository, connection, user_id, scope=scope),
                    load(repository, connection, {user_id}, scope=scope),
                )
            )
            for aid in initial.affected:
                if not connection.execute(
                    "select id from public.financial_accounts where id=%s and user_id=%s"
                    f" and {in_scope} for update",
                    (aid, user_id, *in_params),
                ).fetchone():
                    raise AccountNotFound()
            result = planner(
                VisibleAccounts(
                    load_owner(repository, connection, user_id, scope=scope),
                    load(repository, connection, {user_id}, scope=scope),
                )
            )
            if result.affected != initial.affected:
                raise RuntimeError("Owner lock did not preserve activity membership")
            persist(connection, user_id, result)
            connection.execute(
                "insert into public.financial_activity_receipts(user_id,scope,idempotency_key,identity_hash,activity_id,revision,affected_accounts) values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    user_id,
                    legacy_account or "canonical",
                    key,
                    identity,
                    result.activity_id,
                    result.revision,
                    list(result.affected),
                ),
            )
            if legacy_account:
                connection.execute(
                    "insert into public.financial_operation_receipts(user_id,account_id,idempotency_key,identity_hash,record_id,revision,kind) values(%s,%s,%s,%s,%s,%s,'expense')",
                    (
                        user_id,
                        legacy_account,
                        key,
                        identity,
                        result.activity_id,
                        result.revision,
                    ),
                )
            return (
                load_owner(repository, connection, user_id, scope=scope),
                result.activity_id,
                result.revision,
                result.affected,
                False,
            )

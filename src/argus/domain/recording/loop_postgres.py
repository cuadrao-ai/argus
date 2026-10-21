"""Record hydration and atomic storage for the shared financial repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import Connection

from argus.domain.owner_scope import OwnerScope, sql_predicate
from argus.domain.recording.loop_storage import Planner
from argus.domain.recording.repository import StoredAccount

if TYPE_CHECKING:
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )

from dataclasses import replace
from datetime import date

from psycopg.types.json import Jsonb

from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RegisteredAccountRequired,
    StaleVersion,
)
from argus.domain.recording.loop import (
    CheckRecord,
    Coverage,
    ExpenseRecord,
    ExpenseRevision,
)
from argus.domain.recording.loop_storage import OperationResult


def hydrate(connection: Connection, stored: StoredAccount) -> StoredAccount:
    account = stored.account
    rows = connection.execute(
        "select r.id,r.record_kind,v.revision,v.amount_minor,v.as_of,v.as_of_zone,v.reason,v.recorded_by,v.recorded_at,v.details "
        "from public.financial_records r join public.financial_record_revisions v on v.record_id=r.id "
        "where r.user_id=%s and r.account_id=%s and r.record_kind <> 'opening_balance' order by r.id,v.revision",
        (account.user_id, account.id),
    ).fetchall()
    expenses: dict[str, list[ExpenseRevision]] = {}
    checks: dict[str, CheckRecord] = {}
    for rid, kind, rev, amount, stamp, zone, reason, by, at, details in rows:
        rid = str(rid)
        if kind in {
            "expense",
            "income",
            "transfer",
            "card_payment",
            "refund",
            "debt_payment",
            "payment_reversal",
        }:
            expenses.setdefault(rid, []).append(
                ExpenseRevision(
                    rev,
                    abs(amount),
                    stamp,
                    zone,
                    details.get("note"),
                    details.get("category_id"),
                    reason,
                    str(by) if by else None,
                    at,
                    kind=kind,
                    role=details.get("role", "single"),
                    active=details.get("active", True),
                    activity_id=details.get("activity_id"),
                    activity_revision=details.get("activity_revision"),
                    source_id=details.get("source_id"),
                    purchase_activity_id=details.get("purchase_activity_id"),
                    purchase_revision=details.get("purchase_revision"),
                    interest_minor=details.get("interest_minor"),
                    reversal_of_activity_id=details.get("reversal_of_activity_id"),
                    reversal_of_revision=details.get("reversal_of_revision"),
                    entered_on=date.fromisoformat(details["entered_on"])
                    if details.get("entered_on")
                    else None,
                    coverage_skips=tuple(
                        (str(o), str(r)) for o, r in details.get("coverage_skips", ())
                    ),
                )
            )
        elif kind == "balance_check":
            prior = checks.get(rid)
            checks[rid] = CheckRecord(
                rid,
                account.id,
                amount,
                stamp,
                zone,
                details["expected_minor"],
                details["difference_minor"],
                details["reviewed_version"],
                str(by) if by else None,
                at,
                source=details["source"],
                kind=details["kind"],
                note=details.get("note"),
                revision=rev,
                estimate_basis=details.get("estimate_basis"),
                reason=reason,
                prior_revisions=(
                    *prior.prior_revisions,
                    replace(prior, prior_revisions=()),
                )
                if prior
                else (),
            )
    links = connection.execute(
        "select observation_id,observation_revision,activity_id,activity_revision,included from public.financial_observation_coverage where user_id=%s and account_id=%s",
        (account.user_id, account.id),
    ).fetchall()
    from argus.domain.recording.asset_postgres import hydrate_asset

    return hydrate_asset(
        connection,
        replace(
            stored,
            expenses=tuple(
                ExpenseRecord(rid, account.id, tuple(revs))
                for rid, revs in expenses.items()
            ),
            checks=tuple(sorted(checks.values(), key=lambda c: c.reviewed_version)),
            coverage=tuple(
                Coverage(str(o), ov, str(a), av, value) for o, ov, a, av, value in links
            ),
        ),
    )


def mutate(
    repository: PostgresFinancialAccountRepository,
    *,
    user_id: str,
    account_id: str,
    idempotency_key: str,
    identity_hash: str,
    expected_version: int,
    planner: Planner,
    scope: OwnerScope,
) -> OperationResult:
    in_scope, in_params = sql_predicate(scope, "owner_space_id")
    with repository._pool.connection() as connection:
        with connection.transaction():
            owner = connection.execute(
                "select 1 from auth.users where id=%s and coalesce(is_anonymous,false)=false",
                (user_id,),
            ).fetchone()
            if not owner:
                raise RegisteredAccountRequired()
            locked = connection.execute(
                "select version from public.financial_accounts where id=%s and user_id=%s"
                f" and {in_scope} for update",
                (account_id, user_id, *in_params),
            ).fetchone()
            if not locked:
                raise AccountNotFound()
            receipt = connection.execute(
                "select identity_hash,record_id,revision,kind from public.financial_operation_receipts where user_id=%s and account_id=%s and idempotency_key=%s",
                (user_id, account_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt[0] != identity_hash:
                    raise IdempotencyConflict()
                return OperationResult(
                    repository._load(connection, user_id, account_id, scope=scope),
                    str(receipt[1]),
                    receipt[2],
                    receipt[3],
                    True,
                )
            if locked[0] != expected_version:
                raise StaleVersion()
            stored = repository._load(connection, user_id, account_id, scope=scope)
            mutation = planner(stored)
            record = mutation.record
            if isinstance(record, CheckRecord):
                revision = record.revision
                amount, stamp, zone, reason, by, at = (
                    record.amount_minor,
                    record.as_of,
                    record.time_zone,
                    record.reason,
                    record.recorded_by,
                    record.recorded_at,
                )
                details = {
                    "expected_minor": record.expected_minor,
                    "difference_minor": record.difference_minor,
                    "reviewed_version": record.reviewed_version,
                    "source": record.source,
                    "kind": record.kind,
                    "note": record.note,
                    "estimate_basis": record.estimate_basis,
                }
            else:
                r = record.current
                revision = r.revision
                if isinstance(record, ExpenseRecord):
                    amount, stamp = -r.amount_minor, r.occurred_at
                    details = {"note": r.note, "category_id": r.category_id}
                else:
                    amount, stamp = r.amount_minor, r.as_of
                    details = {"estimate_basis": r.estimate_basis}
                zone, reason, by, at = r.time_zone, r.reason, r.recorded_by, r.recorded_at
            connection.execute(
                "insert into public.financial_records(id,account_id,user_id,record_kind,current_revision,created_at) values(%s,%s,%s,%s,%s,%s) on conflict(id) do update set current_revision=excluded.current_revision",
                (record.id, account_id, user_id, mutation.kind, revision, at),
            )
            connection.execute(
                "insert into public.financial_record_revisions(record_id,user_id,revision,amount_minor,as_of,as_of_zone,reason,recorded_by,recorded_at,details) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    record.id,
                    user_id,
                    revision,
                    amount,
                    stamp,
                    zone,
                    reason,
                    by,
                    at,
                    Jsonb(details),
                ),
            )
            for link in mutation.coverage:
                connection.execute(
                    "insert into public.financial_observation_coverage(account_id,user_id,observation_id,observation_revision,activity_id,activity_revision,included) values(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        account_id,
                        user_id,
                        link.observation_id,
                        link.observation_revision,
                        link.activity_id,
                        link.activity_revision,
                        link.included,
                    ),
                )
            connection.execute(
                "update public.financial_accounts set version=version+1 where id=%s and user_id=%s",
                (account_id, user_id),
            )
            connection.execute(
                "insert into public.financial_operation_receipts(user_id,account_id,idempotency_key,identity_hash,record_id,revision,kind) values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    user_id,
                    account_id,
                    idempotency_key,
                    identity_hash,
                    record.id,
                    revision,
                    mutation.kind,
                ),
            )
            return OperationResult(
                repository._load(connection, user_id, account_id, scope=scope),
                record.id,
                revision,
                mutation.kind,
                False,
            )

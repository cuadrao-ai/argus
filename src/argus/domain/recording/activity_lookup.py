"""Read one owned activity without hydrating unrelated account records."""

from collections import defaultdict
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg import Connection

from argus.domain.owner_scope import OwnerScope

from .canonical_groups import Group, Membership, resolve
from .money_reads import render_activity
from .owner_funds_postgres import load as load_no_account

if TYPE_CHECKING:
    from .postgres_repository import PostgresFinancialAccountRepository


def load(
    repository: "PostgresFinancialAccountRepository",
    connection: Connection,
    user_id: str,
    activity_id: str,
    scope: OwnerScope,
) -> dict[str, Any] | None:
    try:
        if str(UUID(activity_id)) != activity_id:
            return None
    except ValueError:
        return None
    funded = load_no_account(connection, [user_id], scope, activity_id=activity_id)
    if funded:
        return funded[0].response()
    rows = connection.execute(
        """select g.current_revision,m.activity_revision,m.record_id,
        m.record_revision,m.role,m.record_owner_id,r.account_id
        from public.financial_activity_groups g
        join public.financial_activity_memberships m
        on m.activity_id=g.id and m.user_id=g.user_id
        join public.financial_records r on r.id=m.record_id
        and r.user_id=coalesce(m.record_owner_id,m.user_id)
        where g.id=%s and g.user_id=%s and g.reversed_at is null
        order by m.activity_revision,m.role""",
        (activity_id, user_id),
    ).fetchall()
    if not rows:
        return None
    account_records: dict[str, set[str]] = defaultdict(set)
    memberships = []
    for _, revision, rid, record_revision, role, record_owner, account in rows:
        if account is None or str(record_owner) != user_id:
            return None
        account_records[str(account)].add(str(rid))
        memberships.append(
            Membership(
                activity_id, user_id, revision, str(rid), record_revision, role, user_id
            )
        )
    records = []
    for account_id, record_ids in account_records.items():
        stored = repository._load(
            connection, user_id, account_id, scope=scope, record_ids=sorted(record_ids)
        )
        if stored is None:
            return None
        records.append(stored)
    canonical = resolve(records, [Group(activity_id, user_id, rows[0][0])], memberships)
    return render_activity(activity_id, canonical.history[activity_id], rows[0][0])

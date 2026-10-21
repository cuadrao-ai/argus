"""Resolve exact logical activity revisions before applying caller visibility."""

from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from psycopg import Connection

from argus.domain.owner_scope import OwnerScope, sql_predicate

from .errors import AccountNotFound
from .loop import ExpenseRecord, ExpenseRevision
from .money_postgres import load_owner
from .repository import StoredAccount

if TYPE_CHECKING:
    from .owner_funds import OwnerFundedExpense

Leg = tuple[StoredAccount, ExpenseRecord, ExpenseRevision]
History = dict[str, dict[int, list[Leg]]]


@dataclass(frozen=True)
class Group:
    activity_id: str
    owner_id: str
    current_revision: int


@dataclass(frozen=True)
class Membership:
    activity_id: str
    owner_id: str
    activity_revision: int
    record_id: str
    record_revision: int
    role: str
    record_owner_id: str | None = None


@dataclass(frozen=True)
class ResolvedGroups:
    records: list[StoredAccount]
    current: dict[str, int]
    history: History
    owners: dict[str, str]
    owner_funded: list["OwnerFundedExpense"] = field(default_factory=list)

    def current_visible(self, account_ids: Collection[str]) -> dict[str, int]:
        return {
            aid: revision
            for aid, revision in self.current.items()
            if any(
                stored.account.id in account_ids
                for stored, _, __ in self.history[aid][revision]
            )
        }


class VisibleAccounts(list):
    """Owned account positions with privileged group facts kept service-internal."""

    def __init__(self, records: list[StoredAccount], canonical: ResolvedGroups):
        super().__init__(records)
        self.canonical = canonical
        self.owner_funded = canonical.owner_funded


def resolve(
    records: list[StoredAccount],
    groups: Iterable[Group],
    memberships: Iterable[Membership],
) -> ResolvedGroups:
    headers = {group.activity_id: group for group in groups}
    revisions = {
        (stored.account.user_id, record.id, revision.revision): (stored, record, revision)
        for stored in records
        for record in stored.expenses
        for revision in record.revisions
    }
    history: History = {}
    for member in memberships:
        group = headers.get(member.activity_id)
        if group is None or member.activity_revision > group.current_revision:
            continue
        leg = revisions.get(
            (
                member.record_owner_id or member.owner_id,
                member.record_id,
                member.record_revision,
            )
        )
        if leg is None or member.owner_id != group.owner_id:
            raise AccountNotFound()
        _, record, revision = leg
        if (
            not revision.active
            or (revision.activity_id or record.id) != member.activity_id
            or (revision.activity_revision or revision.revision)
            != member.activity_revision
            or revision.role != member.role
        ):
            raise AccountNotFound()
        history.setdefault(member.activity_id, {}).setdefault(
            member.activity_revision, []
        ).append(leg)
    for aid, group in headers.items():
        if group.current_revision not in history.get(aid, {}):
            raise AccountNotFound()
        for legs in history[aid].values():
            roles = [revision.role for _, __, revision in legs]
            if sorted(roles) not in [["single"], ["destination", "source"]]:
                raise AccountNotFound()
    return ResolvedGroups(
        records,
        {aid: group.current_revision for aid, group in headers.items()},
        history,
        {aid: group.owner_id for aid, group in headers.items()},
    )


def projected(canonical: ResolvedGroups, money: Any, now: Any) -> ResolvedGroups:
    """Advance one reviewed group, preserving exact memberships of other groups."""
    from dataclasses import replace

    from .loop_storage import apply

    records = []
    for stored in canonical.records:
        aid = stored.account.id
        if aid in money.mutations:
            stored = apply(stored, money.mutations[aid], now)
        elif aid in money.affected:
            stored = replace(
                stored,
                account=replace(stored.account, version=stored.account.version + 1),
            )
        records.append(stored)
    headers = {
        aid: Group(aid, canonical.owners[aid], revision)
        for aid, revision in canonical.current.items()
    }
    primary = next(
        stored.account.user_id
        for stored in records
        if stored.account.id in money.mutations
        and money.mutations[stored.account.id].record.current.active
        and money.mutations[stored.account.id].record.current.role != "destination"
    )
    owner = canonical.owners.get(money.activity_id, primary)
    headers[money.activity_id] = Group(money.activity_id, owner, money.revision)
    memberships = [
        Membership(
            aid,
            canonical.owners[aid],
            number,
            record.id,
            rev.revision,
            rev.role,
            stored.account.user_id,
        )
        for aid, history in canonical.history.items()
        for number, legs in history.items()
        for stored, record, rev in legs
    ]
    memberships.extend(
        Membership(
            money.activity_id,
            owner,
            money.revision,
            mutation.record.id,
            mutation.record.current.revision,
            mutation.record.current.role,
            next(s.account.user_id for s in records if s.account.id == aid),
        )
        for aid, mutation in money.mutations.items()
        if mutation.record.current.active
    )
    return replace(
        resolve(records, headers.values(), memberships),
        owner_funded=canonical.owner_funded,
    )


def owner_closure(connection: Connection, owner_ids: Collection[str]) -> list[str]:
    owners = set(owner_ids)
    while owners:
        found = {
            str(value)
            for row in connection.execute(
                "select distinct g.user_id,m.record_owner_id from public.financial_activity_groups g "
                "join public.financial_activity_memberships m on m.activity_id=g.id and m.user_id=g.user_id "
                "where g.user_id=any(%s::uuid[]) or m.record_owner_id=any(%s::uuid[])",
                (sorted(owners), sorted(owners)),
            ).fetchall()
            for value in row
        }
        if found <= owners:
            break
        owners.update(found)
    return sorted(owners)


def load(
    repository: Any,
    connection: Connection,
    owner_ids: Collection[str],
    *,
    scope: OwnerScope,
) -> ResolvedGroups:
    """Groups of ``scope``. A group with a leg on an account outside it belongs
    to the other side and is left out, so neither side resolves the other's."""

    owners = owner_closure(connection, owner_ids)
    records = [
        stored
        for owner in owners
        for stored in load_owner(repository, connection, owner, scope=scope)
    ]
    in_scope, params = sql_predicate(scope, "a.owner_space_id")
    rows = connection.execute(
        f"""select g.id,g.user_id,g.current_revision,m.activity_revision,
        m.record_id,m.record_revision,m.role,m.record_owner_id
        from public.financial_activity_groups g
        left join public.financial_activity_memberships m
        on m.activity_id=g.id and m.user_id=g.user_id
        where g.user_id=any(%s::uuid[])
        and not exists (
            select 1 from public.financial_activity_memberships f
            join public.financial_records r on r.id=f.record_id and r.user_id=f.record_owner_id
            where f.activity_id=g.id and f.user_id=g.user_id and r.account_id is null
        )
        and not exists (
            select 1 from public.financial_activity_memberships o
            join public.financial_records r
            on r.id=o.record_id and r.user_id=coalesce(o.record_owner_id,o.user_id)
            join public.financial_accounts a
            on a.id=r.account_id and a.user_id=r.user_id
            where o.activity_id=g.id and o.user_id=g.user_id
            and not coalesce(({in_scope}), false)
        )
        order by g.id,m.activity_revision,m.role""",
        (owners, *params),
    ).fetchall()
    headers = {}
    memberships = []
    for aid, owner, current, revision, rid, record_revision, role, record_owner in rows:
        identifier, owner_id = str(aid), str(owner)
        headers[identifier] = Group(identifier, owner_id, current)
        if revision is not None:
            memberships.append(
                Membership(
                    identifier,
                    owner_id,
                    revision,
                    str(rid),
                    record_revision,
                    role,
                    str(record_owner),
                )
            )
    from dataclasses import replace

    from .owner_funds_postgres import load as load_funded

    return replace(
        resolve(records, headers.values(), memberships),
        owner_funded=load_funded(connection, owner_ids, scope),
    )

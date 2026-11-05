"""A live Household scope over original account ownership."""

from dataclasses import dataclass

from psycopg import Connection
from psycopg.rows import dict_row

from argus.domain.recording.money_reads import groups
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.repository import StoredAccount

from .errors import HouseholdNotFound as HouseholdUnavailable


def rows(c, query, args=()):
    with c.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, args).fetchall()


@dataclass(frozen=True)
class AccountAccess:
    owner_id: str
    owner_name: str
    permission: str


@dataclass(frozen=True)
class HouseholdFinancialScope:
    actor_id: str
    household_id: str
    membership_id: str
    authorization_version: int
    accounts: dict[str, AccountAccess]
    authors: dict[str, str]


def resolve(c: Connection, actor: str, h: dict, m: dict) -> HouseholdFinancialScope:
    shares = rows(
        c,
        """select distinct on(g.account_id) g.account_id,g.owner_user_id owner_id,o.display_name,
        case when g.owner_membership_id=%s then 'edit' else g.permission end permission
        from public.household_account_grants g
        join public.household_members o on o.id=g.owner_membership_id and o.left_at is null
        join public.household_members r on r.id=g.recipient_membership_id and r.left_at is null
        where g.household_id=%s and g.revoked_at is null
        and (g.owner_membership_id=%s or g.recipient_membership_id=%s)
        order by g.account_id,g.id""",
        (m["id"], h["id"], m["id"], m["id"]),
    )
    authors = rows(
        c,
        "select user_id,display_name,left_at departed_at from public.household_members where household_id=%s order by joined_at",
        (h["id"],),
    )
    return HouseholdFinancialScope(
        actor,
        str(h["id"]),
        str(m["id"]),
        h["version"],
        {
            str(s["account_id"]): AccountAccess(
                str(s["owner_id"]), s["display_name"], s["permission"]
            )
            for s in shares
        },
        {str(a["user_id"]): a["display_name"] for a in authors if not a["departed_at"]},
    )


def dependencies(
    records: list[StoredAccount], request: MoneyRequest, activity_id: str | None
) -> set[str]:
    required = {
        a
        for a in (
            request.account_id,
            request.source_account_id,
            request.destination_account_id,
        )
        if a
    }
    required.update(request.expected_versions)
    required.update(a.account_id for a in request.coverage)
    links = {
        a
        for a in (
            activity_id,
            request.purchase_activity_id,
            request.reversal_of_activity_id,
        )
        if a
    }
    history = groups(records)
    # Both directions and every revision matter when a correction drops old legs.
    changed = True
    while changed:
        changed = False
        for aid, revisions in history.items():
            references = {
                ref
                for legs in revisions.values()
                for _, __, rev in legs
                for ref in (rev.purchase_activity_id, rev.reversal_of_activity_id)
                if ref
            }
            if aid in links or references & links:
                before = len(links)
                links.add(aid)
                links.update(references)
                changed = changed or len(links) != before
    if links - set(history):
        raise HouseholdUnavailable()
    for aid in links:
        required.update(
            s.account.id for legs in history[aid].values() for s, _, __ in legs
        )
    return required


def require_edit(scope: HouseholdFinancialScope, ids: set[str]) -> str:
    if not ids or any(
        a not in scope.accounts or scope.accounts[a].permission != "edit" for a in ids
    ):
        raise HouseholdUnavailable()
    owners = {scope.accounts[a].owner_id for a in ids}
    if len(owners) != 1:
        raise HouseholdUnavailable()
    return next(iter(owners))

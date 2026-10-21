"""Consent references canonical definitions and immutable original revisions."""

from typing import Any

from psycopg.types.json import Jsonb

from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import model
from argus.domain.recording.errors import StaleVersion
from argus.domain.recording.money_postgres import owner_lock

from .errors import HouseholdNotFound

TABLES = {
    "budget": ("financial_budgets", "budgets", "budget_id"),
    "bill": ("financial_expectations", "expectations", "expectation_id"),
    "goal": ("financial_goals", "goals", "goal_id"),
    "debt": ("financial_debt_plans", "debts", "debt_plan_id"),
}


def table(kind: str) -> tuple[str, str, str]:
    if kind not in TABLES:
        raise HouseholdNotFound()
    return TABLES[kind]


def definition(c: Any, kind: str, identifier: str, owner: str, revision=None) -> dict:
    name, _, __ = table(kind)
    if revision is None:
        row = c.execute(
            f"select body from public.{name} where id=%s and user_id=%s",
            (identifier, owner),
        ).fetchone()
    else:
        row = c.execute(
            "select body from public.financial_plan_definition_revisions where kind=%s and definition_id=%s and owner_id=%s and revision=%s",
            (kind, identifier, owner, revision),
        ).fetchone()
    if not row or kind == "bill" and row[0]["kind"] != "bill":
        raise HouseholdNotFound()
    return row[0]


def save(c: Any, kind: str, owner: str, body: dict, actor: str) -> None:
    name, _, __ = table(kind)
    c.execute("select set_config('argus.plan_actor',%s,true)", (actor,))
    stored = {k: v for k, v in body.items() if k != "allocations"}
    if kind == "debt":
        c.execute(
            f"insert into public.{name}(id,user_id,debt_account_id,body) values(%s,%s,%s,%s) on conflict(id,user_id) do update set body=excluded.body",
            (body["id"], owner, body["debt_account_id"], Jsonb(stored)),
        )
    else:
        c.execute(
            f"insert into public.{name}(id,user_id,body) values(%s,%s,%s) on conflict(id,user_id) do update set body=excluded.body",
            (body["id"], owner, Jsonb(stored)),
        )


def binding(c: Any, actor: str, hid: str, mid: str, kind: str, identifier: str) -> dict:
    table(kind)
    row = c.execute(
        """select b.id,b.owner_user_id,b.owner_membership_id,b.publish_budget_scope,
        b.departed_at,b.retained_revision,coalesce(p.permission,'edit'),b.first_shared_revision,p.granted_revision
        from public.household_plan_bindings b
        left join public.household_plan_participants p on p.binding_id=b.id and p.membership_id=%s and p.revoked_at is null
        where b.household_id=%s and b.kind=%s and b.definition_id=%s and b.revoked_at is null
        and (b.owner_membership_id=%s or p.membership_id is not null)
        order by b.departed_at nulls first,b.first_shared_revision desc,b.id limit 1""",
        (mid, hid, kind, identifier, mid),
    ).fetchone()
    if row is None:
        raise HouseholdNotFound()
    return dict(
        id=str(row[0]),
        owner_id=str(row[1]),
        owner_mid=str(row[2]),
        publish_budget_scope=row[3],
        departed_at=row[4],
        retained_revision=row[5],
        permission=row[6],
        first_shared_revision=row[7],
        granted_revision=row[8],
        kind=kind,
        definition_id=identifier,
        household_id=hid,
        is_owner=str(row[1]) == actor and str(row[2]) == mid,
    )


def members(c: Any, hid: str) -> dict[str, dict]:
    return {
        str(mid): dict(
            membership_id=str(mid),
            user_id=str(uid),
            display_name=name,
            active=left is None,
        )
        for mid, uid, name, left in c.execute(
            "select id,user_id,display_name,left_at from public.household_members where household_id=%s order by joined_at,id",
            (hid,),
        ).fetchall()
    }


FORMER_MEMBER = {"en": "Former member", "es-419": "Exmiembro"}


def viewer_language(c: Any, user_id: str) -> str:
    row = c.execute(
        "select language from public.profiles where id = %s", (user_id,)
    ).fetchone()
    return row[0] if row and row[0] in FORMER_MEMBER else "en"


def plan_people(c: Any, b: dict, people: dict, language: str = "en") -> dict:
    """Former members (deleted accounts) are numbered per plan, in the
    viewer's language: "Former member" / "Exmiembro" when the plan shows one,
    "Former member 1", "Exmiembro 2" and so on when it shows several. Only
    former members the plan shows (as owner, contributor or with a
    responsibility) count; ended participations are not shown."""

    rows = c.execute(
        """select m.id from public.household_members m
            where m.household_id = %s and m.former_member_number is not null
              and m.id in (
                select contributor_membership_id from public.financial_plan_links
                       where binding_id = %s and contributor_membership_id is not null
                union select membership_id from public.financial_plan_responsibilities
                       where kind = %s and definition_id = %s and owner_id = %s
                union select owner_membership_id from public.household_plan_bindings where id = %s)
            order by m.former_member_number, m.id""",
        (
            b["household_id"],
            b["id"],
            b["kind"],
            b["definition_id"],
            b["owner_id"],
            b["id"],
        ),
    ).fetchall()
    if not rows:
        return people
    renamed = dict(people)
    for number, (mid,) in enumerate(rows, start=1):
        if str(mid) in renamed:
            label = FORMER_MEMBER.get(language, FORMER_MEMBER["en"])
            name = label if len(rows) == 1 else f"{label} {number}"
            renamed[str(mid)] = dict(renamed[str(mid)], display_name=name)
    return renamed


def participants(c: Any, b: dict, people: dict) -> list[dict]:
    owner = people[b["owner_mid"]]
    result = [
        dict(
            membership_id=owner["membership_id"],
            display_name=owner["display_name"],
            permission="edit",
        )
    ]
    result.extend(
        dict(
            membership_id=str(mid),
            display_name=people[str(mid)]["display_name"],
            permission=permission,
        )
        for mid, permission in c.execute(
            "select membership_id,permission from public.household_plan_participants where binding_id=%s and revoked_at is null order by membership_id",
            (b["id"],),
        ).fetchall()
        if people[str(mid)]["active"]
    )
    return result


def replace_participants(
    c: Any, b: dict, proposed: list, people: dict, now: Any, revision: int
) -> None:
    seen = set()
    for entry in proposed:
        mid = str(entry.membership_id)
        if (
            mid in seen
            or mid == b["owner_mid"]
            or mid not in people
            or not people[mid]["active"]
        ):
            model.fail("plan_participant_invalid", "Choose each current person once.")
        seen.add(mid)
    previous = {
        str(mid): version
        for mid, version in c.execute(
            "select membership_id,granted_revision from public.household_plan_participants where binding_id=%s and revoked_at is null",
            (b["id"],),
        ).fetchall()
    }
    c.execute(
        "update public.household_plan_participants set revoked_at=%s where binding_id=%s and revoked_at is null",
        (now, b["id"]),
    )
    for entry in proposed:
        c.execute(
            "insert into public.household_plan_participants(binding_id,household_id,membership_id,permission,granted_revision) values(%s,%s,%s,%s,%s) on conflict(binding_id,membership_id) do update set permission=excluded.permission,revoked_at=null,granted_revision=excluded.granted_revision",
            (
                b["id"],
                b["household_id"],
                str(entry.membership_id),
                entry.permission,
                previous.get(str(entry.membership_id), revision),
            ),
        )


def responsibilities(c: Any, b: dict, revision: int, rows=None) -> list:
    identity = (b["kind"], b["definition_id"], b["owner_id"])
    if rows is not None:
        c.execute(
            "delete from public.financial_plan_responsibilities where kind=%s and definition_id=%s and owner_id=%s and revision=%s",
            (*identity, revision),
        )
        for row in rows:
            c.execute(
                "insert into public.financial_plan_responsibilities(kind,definition_id,owner_id,revision,membership_id,amount_minor,period,occurrence_id,schedule_id,agreed_date) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (*identity, revision, *row),
            )
    return c.execute(
        "select membership_id,amount_minor,period,occurrence_id,schedule_id,agreed_date from public.financial_plan_responsibilities where kind=%s and definition_id=%s and owner_id=%s and revision=%s order by membership_id,period,occurrence_id,schedule_id,agreed_date",
        (*identity, revision),
    ).fetchall()


def require_write(b: dict, body: dict, expected: int, *, owner=False, own=False) -> None:
    if b["departed_at"] or body["archived"]:
        model.fail("plan_read_only", "This shared plan is archived and read-only.")
    if owner and not b["is_owner"] or not own and not owner and b["permission"] != "edit":
        raise HouseholdNotFound()
    if body["version"] != expected:
        raise StaleVersion()


def archive_owner(c: Any, hid: str, user_id: str, now: Any, repository: Any) -> None:
    rows = c.execute(
        "select id,kind,definition_id,publish_budget_scope from public.household_plan_bindings where household_id=%s and owner_user_id=%s and revoked_at is null and departed_at is null order by id",
        (hid, user_id),
    ).fetchall()
    if not rows:
        return
    from argus.domain.recording import canonical_groups

    from . import planning_projection as projection
    from .planning_progress import selected_budget_facts

    owners = canonical_groups.owner_closure(
        c,
        {
            str(uid)
            for (uid,) in c.execute(
                "select user_id from public.household_members where household_id=%s",
                (hid,),
            ).fetchall()
        },
    )
    for owner in owners:
        owner_lock(c, owner)
    c.execute(
        "select id from public.financial_accounts where user_id=any(%s::uuid[]) order by id for update",
        (owners,),
    ).fetchall()
    canonical = canonical_groups.load(repository, c, owners, scope=PERSONAL)
    for bid, kind, did, publish in rows:
        body = definition(c, kind, str(did), user_id)
        b = dict(
            id=str(bid),
            kind=kind,
            definition_id=str(did),
            publish_budget_scope=publish,
            departed_at=None,
        )
        claimed = projection.links(c, b)
        actual = projection.actuals(c, b, canonical, claimed)
        activity_ids = {link["activity_id"] for link in claimed.values()}
        activity_ids.update(
            aid
            for aid, item in actual.items()
            if item["purchase_activity_id"] in activity_ids
            or item["reversal_of_activity_id"] in activity_ids
        )
        if kind == "budget":
            activity_ids.update(selected_budget_facts(b, body, claimed, actual))
        for aid in sorted(activity_ids):
            if aid in canonical.current:
                owner = c.execute(
                    "select user_id from public.financial_activity_groups where id=%s",
                    (aid,),
                ).fetchone()[0]
                c.execute(
                    "insert into public.household_plan_archived_activities values(%s,%s,%s,%s) on conflict(binding_id,activity_id) do nothing",
                    (bid, aid, owner, actual[aid]["revision"]),
                )
        c.execute(
            "update public.household_plan_bindings set departed_at=%s,retained_revision=%s where id=%s",
            (now, body["version"], bid),
        )
        c.execute(
            """insert into public.household_plan_archived_claims
            (binding_id,claim_id,activity_id,activity_owner_id,activity_revision,released)
            select l.binding_id,l.claim_id,g.id,g.user_id,g.current_revision,l.released_at is not null
            from public.financial_plan_links l join public.financial_activity_groups g
            on g.id=l.activity_id and g.user_id=l.activity_owner_id where l.binding_id=%s on conflict(binding_id,claim_id) do nothing""",
            (bid,),
        )
        c.execute(
            "insert into public.household_plan_archived_allocations(binding_id,allocation_id,revision) "
            "select binding_id,id,revision from public.financial_goal_allocations where binding_id=%s "
            "on conflict(binding_id,allocation_id,revision) do update set owner_archived=true",
            (bid,),
        )

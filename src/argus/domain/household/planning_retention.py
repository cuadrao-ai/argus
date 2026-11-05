"""Ended consent pins canonical history, never a former member's live backing."""

from argus.domain.owner_scope import PERSONAL
from argus.domain.recording import canonical_groups
from argus.domain.recording.money_postgres import owner_lock

from . import planning_projection as projection
from . import planning_store as store


def retain_membership(c, hid, user_id, now, repository):
    people = store.members(c, hid)
    mid = next(
        (m for m, p in people.items() if p["user_id"] == user_id and p["active"]), None
    )
    if mid is None:
        return
    bindings = c.execute(
        """select b.owner_user_id,b.owner_membership_id,b.kind,b.definition_id
        from public.household_plan_bindings b where b.household_id=%s
        and b.owner_user_id<>%s and b.departed_at is null and b.revoked_at is null
        and (exists(select 1 from public.financial_plan_links l where l.binding_id=b.id and l.contributor_membership_id=%s)
        or exists(select 1 from public.financial_goal_allocations a where a.binding_id=b.id and a.contributor_membership_id=%s))
        order by b.id""",
        (hid, user_id, mid, mid),
    ).fetchall()
    if not bindings:
        return
    owners = canonical_groups.owner_closure(c, {p["user_id"] for p in people.values()})
    for owner in owners:
        owner_lock(c, owner)
    c.execute(
        "select id from public.financial_accounts where user_id=any(%s::uuid[]) order by id for update",
        (owners,),
    ).fetchall()
    canonical = canonical_groups.load(repository, c, owners, scope=PERSONAL)
    for owner, owner_mid, kind, did in bindings:
        b = store.binding(c, str(owner), hid, str(owner_mid), kind, str(did))
        body = store.definition(c, kind, str(did), str(owner))
        claimed = projection.links(c, b)
        authorized = projection.public(
            c,
            repository,
            b,
            body,
            people,
            str(owner),
            str(owner_mid),
            0,
            {},
            canonical,
            now.date(),
        )
        public_claims = {item["id"]: item for item in authorized["contributions"]}
        actual = projection.actuals(c, b, canonical, claimed)
        for cid, link in claimed.items():
            if link["contributor_mid"] != mid:
                continue
            aid = link["activity_id"]
            revision = canonical.current.get(aid)
            if revision is None:
                # No historical fallback may substitute an obsolete original.
                from .errors import HouseholdNotFound

                raise HouseholdNotFound()
            c.execute(
                """insert into public.household_plan_archived_claims
                (binding_id,claim_id,activity_id,activity_owner_id,activity_revision,released,membership_ended_at,last_applied_minor)
                values(%s,%s,%s,%s,%s,%s,%s,%s) on conflict(binding_id,claim_id) do nothing""",
                (
                    b["id"],
                    cid,
                    aid,
                    link["activity_owner_id"],
                    revision,
                    link["released"],
                    now,
                    public_claims[cid]["applied_minor"],
                ),
            )
            # Refunds/returns are part of the same authorized original. Capturing
            # their exact revisions also prevents a later private return leaking.
            related = {aid} | {
                key
                for key, entry in actual.items()
                if entry["purchase_activity_id"] == aid
                or entry["reversal_of_activity_id"] == aid
            }
            for key in sorted(related):
                c.execute(
                    "insert into public.household_plan_archived_activities values(%s,%s,%s,%s) on conflict(binding_id,activity_id) do nothing",
                    (b["id"], key, canonical.owners[key], actual[key]["revision"]),
                )
        support = (
            {item["id"]: item["supported_minor"] for item in authorized["allocations"]}
            if kind == "goal"
            else {}
        )
        for aid, revision in c.execute(
            "select id,revision from public.financial_goal_allocations where binding_id=%s and contributor_membership_id=%s",
            (b["id"], mid),
        ).fetchall():
            c.execute(
                """insert into public.household_plan_archived_allocations
                (binding_id,allocation_id,revision,membership_ended_at,last_supported_minor,owner_archived)
                values(%s,%s,%s,%s,%s,false) on conflict(binding_id,allocation_id,revision) do nothing""",
                (b["id"], aid, revision, now, support[str(aid)]),
            )

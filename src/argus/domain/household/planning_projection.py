"""Select consented facts before reducing; no Personal result enters this wire."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import (
    debt_model,
    goal_model,
    goal_projection,
    model,
    shared_claims,
    storage,
)
from argus.domain.recording.currency import currency_exponent
from argus.domain.recording.money_reads import activity_in_currency, render_activity
from argus.domain.recording.spending import spending

from . import planning_definitions as definitions
from . import planning_store as store
from .access import dependencies
from .errors import HouseholdNotFound
from .planning_progress import summary


def links(c, b):
    result = {}
    for (
        cid,
        oid,
        activity_owner,
        aid,
        revision,
        snapshot,
        accepted,
        mid,
        purpose,
        released,
    ) in c.execute(
        "select claim_id,occurrence_id,activity_owner_id,activity_id,activity_revision,snapshot,attribution,contributor_membership_id,purpose,released_at from public.financial_plan_links where binding_id=%s order by claim_id",
        (b["id"],),
    ).fetchall():
        result[str(cid)] = dict(
            occurrence_id=str(oid) if oid else None,
            activity_owner_id=str(activity_owner),
            activity_id=str(aid),
            activity_revision=revision,
            snapshot=snapshot,
            attribution=accepted,
            contributor_mid=str(mid),
            purpose=purpose,
            released=released is not None,
            **{store.table(b["kind"])[2]: b["definition_id"]},
        )
    return result


def original(access, canonical, actual, actor):
    if actual is None:
        return None, False
    visible = [leg for leg in actual["legs"] if leg["account_id"] in access]
    if not visible:
        return None, False
    destination = dict(
        kind="activity",
        activity_id=actual["activity_id"],
        account_id=visible[0]["account_id"],
        household_id=None
        if access[visible[0]["account_id"]][0] == actor
        else access[visible[0]["account_id"]][2],
    )
    from argus.domain.recording.canonical_groups import VisibleAccounts
    from argus.domain.recording.money_schemas import MoneyRequest

    try:
        ids = dependencies(
            VisibleAccounts(canonical.records, canonical),
            MoneyRequest(
                kind=actual["kind"],
                amount=actual["amount"],
                occurred_at=actual["occurred_at"],
            ),
            actual["activity_id"],
        )
        editable = all(aid in access and access[aid][1] == "edit" for aid in ids)
    except HouseholdNotFound:
        editable = False
    return destination, editable


def pool(c, repository, owner):
    from argus.domain.recording.money_postgres import load_owner

    state = storage.load(c, owner, repository)
    records = load_owner(repository, c, owner, scope=PERSONAL)
    amounts, _, __ = goal_projection.pool_assignments(state, records)
    return goal_projection.pool_facts(state, records, amounts)


def actuals(c, b, canonical, claimed):
    actual = {
        aid: render_activity(aid, canonical.history[aid], revision)
        for aid, revision in canonical.current.items()
    }
    frozen = c.execute(
        "select claim_id,activity_id,activity_revision,released,membership_ended_at,last_applied_minor from public.household_plan_archived_claims where binding_id=%s",
        (b["id"],),
    ).fetchall()
    roots = set()
    for cid, aid, _, released, ended, applied in frozen:
        key = str(cid)
        if key not in claimed:
            continue
        claimed[key] = claimed[key] | dict(
            released=released, retained=ended is not None, retained_applied=applied
        )
        roots.add(str(aid))
    retained = {}
    for aid, revision in c.execute(
        "select activity_id,activity_revision from public.household_plan_archived_activities where binding_id=%s",
        (b["id"],),
    ).fetchall():
        history = canonical.history.get(str(aid), {})
        if revision not in history:
            raise HouseholdNotFound()
        retained[str(aid)] = render_activity(str(aid), history, revision)
    for cid, aid, revision, _, __, ___ in frozen:
        history = canonical.history.get(str(aid), {})
        if str(cid) not in claimed:
            continue
        if revision not in history:
            raise HouseholdNotFound()
        retained[str(aid)] = render_activity(str(aid), history, revision)
    if b["departed_at"]:
        actual = retained
    else:
        # Only the ended contributor's original/dependencies are clipped. Other
        # current contributions remain live; later private refunds/returns do not.
        actual = {
            aid: entry
            for aid, entry in actual.items()
            if aid not in roots
            and entry["purchase_activity_id"] not in roots
            and entry["reversal_of_activity_id"] not in roots
        } | retained
    return actual


def allocations(c, b, people, actor_mid, repository, pools):
    if b["kind"] != "goal":
        return []
    if b["departed_at"]:
        rows = c.execute(
            """select r.allocation_id,r.contributor_membership_id,r.account_owner_id,r.account_id,r.unlinked_minor,a.membership_ended_at
            from public.household_plan_archived_allocations a join public.financial_goal_allocation_revisions r
            on r.allocation_id=a.allocation_id and r.revision=a.revision where a.binding_id=%s and a.owner_archived order by r.allocation_id""",
            (b["id"],),
        ).fetchall()
    else:
        rows = c.execute(
            "select r.id,r.contributor_membership_id,r.account_owner_id,r.account_id,r.unlinked_minor,a.membership_ended_at "
            "from public.financial_goal_allocations r left join public.household_plan_archived_allocations a "
            "on a.binding_id=r.binding_id and a.allocation_id=r.id and a.revision=r.revision "
            "where r.binding_id=%s order by r.id",
            (b["id"],),
        ).fetchall()
    result = []
    for identifier, mid, owner, aid, amount, ended in rows:
        mid, owner, aid = str(mid), str(owner), str(aid)
        if owner not in pools and not b["departed_at"] and ended is None:
            pools[owner] = pool(c, repository, owner)
        facts = pools.get(owner, {})
        supported = (
            amount
            if amount == 0
            or ended is None
            and facts.get(aid, {}).get("state") == "backed"
            else None
        )
        result.append(
            dict(
                id=str(identifier),
                person=person(people, mid),
                assigned_minor=str(amount),
                supported_minor=str(supported) if supported is not None else None,
                status="current" if supported is not None else "needs_review",
                can_edit=mid == actor_mid and not b["departed_at"] and ended is None,
            )
        )
    return result


def person(people, mid):
    return {k: people[mid][k] for k in ("membership_id", "display_name")}


def public(
    c, repository, b, body, people, actor, mid, auth_version, access, canonical, today
):
    people = store.plan_people(c, b, people, store.viewer_language(c, actor))
    claimed = links(c, b)
    actual = actuals(c, b, canonical, claimed)
    readonly = bool(b["departed_at"] or body["archived"])
    pools, contributions = {}, []
    for cid, link in claimed.items():
        entry = actual.get(link["activity_id"])
        accepted = link["attribution"]
        in_plan_currency = bool(entry and activity_in_currency(entry, body["currency"]))
        valid = bool(
            in_plan_currency
            and entry["kind"] == accepted["kind"]
            and {(leg["role"], leg["account_id"]) for leg in entry["legs"]}
            == {tuple(leg) for leg in accepted["legs"]}
        )
        applied = None
        if link["released"]:
            applied = 0
        elif valid:
            purpose = link["purpose"]
            value = shared_claims.credit(
                entry, accepted, purpose, actual, canonical.records
            )
            if purpose == "goal_saving":
                owner, aid = (
                    accepted["destination_owner_id"],
                    accepted["destination_account_id"],
                )
                if (
                    owner not in pools
                    and not b["departed_at"]
                    and not link.get("retained")
                ):
                    pools[owner] = pool(c, repository, owner)
                if (
                    value is not None
                    and not link.get("retained")
                    and pools.get(owner, {}).get(aid, {}).get("state") == "backed"
                ):
                    applied = value
            elif purpose in {"debt_payment", "bill_payment", "funding"}:
                applied = value
            else:
                relevant = [
                    entry,
                    *[
                        a
                        for a in actual.values()
                        if a["purchase_activity_id"] == entry["activity_id"]
                        or a["reversal_of_activity_id"] == entry["activity_id"]
                    ],
                ]
                applied = spending(
                    relevant,
                    currency=body["currency"],
                    start=entry["occurred_at"] - timedelta(days=36600),
                    end=entry["occurred_at"] + timedelta(days=36600),
                ).net
        navigation, editable = original(access, canonical, entry, actor)
        contributions.append(
            dict(
                id=cid,
                person=person(people, link["contributor_mid"]),
                amount_minor=str(entry["amount_minor"]) if in_plan_currency else None,
                applied_minor=str(applied) if applied is not None else None,
                currency=body["currency"],
                currency_fraction_digits=currency_exponent(body["currency"]),
                date=(
                    entry["occurred_at"].astimezone(ZoneInfo(entry["time_zone"])).date()
                    if entry
                    else date.fromisoformat(accepted["date"])
                ),
                status="released"
                if link["released"]
                else "current"
                if valid and applied is not None
                else "needs_review",
                original=navigation,
                purpose=link["purpose"],
                occurrence_id=link["occurrence_id"],
                can_correct=not readonly and mid == link["contributor_mid"] and editable,
                can_release=not readonly
                and mid == link["contributor_mid"]
                and not link["released"],
            )
        )
    shared_allocations = allocations(c, b, people, mid, repository, pools)
    if readonly:
        for allocation in shared_allocations:
            allocation["can_edit"] = False
    end = (
        b["departed_at"].date()
        if b["departed_at"]
        else today
        if readonly
        else today + timedelta(days=365)
    )
    occurrence_rows = definitions.occurrence_rows(b["kind"], body, claimed, end)
    occurrences = []
    for oid, row in sorted(
        occurrence_rows.items(), key=lambda pair: (pair[1]["due_date"], pair[0])
    ):
        if date.fromisoformat(row["due_date"]) > end:
            continue
        credits = [
            v
            for v in contributions
            if v["occurrence_id"] == oid and v["status"] != "released"
        ]
        known = all(v["applied_minor"] is not None for v in credits)
        amount = sum(int(v["applied_minor"]) for v in credits) if known else None
        expected = (
            goal_projection.scheduled_minor(row, canonical.records)
            if b["kind"] == "goal"
            else row["amount_minor"]
        )
        remaining = (
            max(0, expected - amount)
            if amount is not None and expected is not None
            else None
        )
        occurrences.append(
            dict(
                id=oid,
                date=row["due_date"],
                amount_minor=str(row["amount_minor"]),
                applied_minor=str(amount) if amount is not None else None,
                remaining_minor=str(remaining) if remaining is not None else None,
                status="archived"
                if readonly
                else "needs_review"
                if remaining is None
                else "fulfilled"
                if remaining == 0
                else "partial"
                if amount
                else "pending",
            )
        )
    progress = summary(
        b | {"_links": claimed},
        body,
        contributions,
        shared_allocations,
        actual,
        occurrences,
        access,
        canonical,
        today,
    )
    kind = b["kind"]
    definition = dict(
        name=body.get("name", body.get("title")),
        currency=body["currency"],
        currency_fraction_digits=currency_exponent(body["currency"]),
    )
    protected = {cid: link for cid, link in claimed.items() if link["occurrence_id"]}
    state = storage.empty()
    state[store.table(kind)[1]][body["id"]] = body
    state["links"] = protected
    minimum = (
        today
        if kind == "budget"
        else model.earliest(body, protected, today)
        if kind == "bill"
        else (
            goal_model.earliest(body, state, today)
            if kind == "goal"
            else debt_model.earliest(body, state, today)
        )
    )
    definition["earliest_effective_date"] = minimum.isoformat()
    if kind == "budget":
        definition |= {
            k: body[k] for k in ("month", "category_ids", "include_uncategorized")
        }
        definition |= dict(
            limit_minor=str(body["limit_minor"]),
            publish_budget_scope=b["publish_budget_scope"],
        )
    elif kind == "goal":
        part = body["segments"][-1] if body["segments"] else None
        definition |= dict(
            target_minor=str(body["target_minor"]),
            target_date=body["target_date"],
            schedule=part["schedule"] if part else None,
            planned_contribution_minor=str(part["amount_minor"]) if part else None,
        )
    else:
        part = body["segments"][-1]
        definition |= dict(
            amount_minor=str(
                body["amount_minor"] if kind == "bill" else part["amount_minor"]
            ),
            schedule=part["schedule"],
        )
    consent = store.participants(c, b, people)
    consent_ids = {p["membership_id"] for p in consent}
    responsibilities = [
        dict(
            person=person(people, str(r[0])),
            amount_minor=str(r[1]) if r[1] is not None else None,
            period=r[2],
            occurrence_id=str(r[3]) if r[3] else None,
            schedule_id=str(r[4]) if r[4] else None,
            agreed_date=r[5],
        )
        for r in store.responsibilities(c, b, body["version"])
        if str(r[0]) in consent_ids
    ]
    result = dict(
        ref=dict(kind=kind, id=body["id"]),
        version=body["version"],
        household_id=b["household_id"],
        membership_id=mid,
        authorization_version=auth_version,
        owner=person(people, b["owner_mid"]),
        permission=b["permission"],
        is_owner=b["is_owner"],
        definition=definition,
        participants=[p | {"is_self": p["membership_id"] == mid} for p in consent],
        responsibilities=responsibilities,
        occurrences=occurrences,
        contributions=contributions,
        progress=progress,
        archived=readonly,
        read_only=readonly,
        archive_reason="owner_departed" if b["departed_at"] else None,
        can_restore=body["archived"]
        and not b["departed_at"]
        and b["permission"] == "edit",
    )
    revision_meta = c.execute(
        "select actor_id,recorded_at from public.financial_plan_definition_revisions where kind=%s and definition_id=%s and owner_id=%s and revision=%s",
        (kind, body["id"], b["owner_id"], body["version"]),
    ).fetchone()
    if revision_meta:
        result["recorded_at"] = revision_meta[1]
        memberships = c.execute(
            "select id from public.household_members where household_id=%s and user_id=%s and joined_at<=%s order by joined_at desc,id desc limit 1",
            (b["household_id"], revision_meta[0], revision_meta[1]),
        ).fetchone()
        result["last_edited_by"] = (
            person(people, str(memberships[0])) if memberships else None
        )
    if kind == "goal":
        result["allocations"] = shared_allocations
    return result

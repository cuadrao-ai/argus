"""Own contribution consent composes with canonical Money and its allocation pool."""

from uuid import uuid4

from psycopg.types.json import Jsonb

from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import goal_commands, goal_projection, model
from argus.domain.recording.canonical_groups import VisibleAccounts
from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.errors import StaleVersion
from argus.domain.recording.money_plan import plan, selected
from argus.domain.recording.money_postgres import persist
from argus.domain.recording.money_reads import activity_in_currency, render_activity

from . import planning_definitions as definitions
from . import planning_projection as projection
from . import planning_store as store
from .access import dependencies
from .errors import HouseholdNotFound


def require_original(ctx, b, cid, actor, *, correct=False):
    c, _, mid, __, access, canonical = ctx
    link = projection.links(c, b).get(cid)
    if link is None or link["contributor_mid"] != mid:
        raise HouseholdNotFound()
    aid = link["activity_id"]
    revision = canonical.current.get(aid)
    if revision is None:
        raise HouseholdNotFound()
    actual = render_activity(aid, canonical.history[aid], revision)
    _, editable = projection.original(access, canonical, actual, actor)
    if correct and not editable:
        raise HouseholdNotFound()
    return link, actual


def require_activity_access(ctx, actual, actor, *, write=False, request=None):
    _, __, mid, ___, access, canonical = ctx
    records = {s.account.id: s for s in canonical.records}
    primary = actual["legs"][0]["account_id"]
    if records[primary].account.user_id != actor and actual["recorded_by"] != actor:
        raise HouseholdNotFound()
    ids = {leg["account_id"] for leg in actual["legs"]}
    if write and request is not None:
        ids = dependencies(canonical.records, request, actual["activity_id"])
    if any(aid not in access or write and access[aid][1] != "edit" for aid in ids):
        # Linking an actor-owned private source does not require destination admin.
        # Its original legs must still be independently readable.
        raise HouseholdNotFound()


def attach(service, ctx, b, current, actual, body):
    c, h, mid, people, access, canonical = ctx
    purpose = body.purpose
    from .planning import PURPOSES

    if purpose not in PURPOSES[b["kind"]] or not activity_in_currency(
        actual, current["currency"]
    ):
        model.fail("plan_contribution_mismatch", "Choose the plan purpose and currency.")
    by_id = {s.account.id: s.account for s in canonical.records}
    roles = {leg["role"]: leg["account_id"] for leg in actual["legs"]}
    required = dict(
        funding={"transfer"},
        spending={"expense", "refund", "debt_payment", "payment_reversal"},
        bill_payment={"expense"},
        goal_saving={"transfer"},
        debt_payment={"card_payment", "debt_payment"},
    )[purpose]
    if actual["kind"] not in required:
        model.fail(
            "plan_contribution_mismatch",
            "The original activity does not fulfill this purpose.",
        )
    if (
        purpose == "debt_payment"
        and roles.get("destination") != current["debt_account_id"]
    ):
        model.fail(
            "plan_contribution_mismatch", "Choose a payment for the original debt."
        )
    if purpose == "goal_saving" and any(
        by_id[aid].type not in ("cash", "checking", "savings") for aid in roles.values()
    ):
        model.fail(
            "plan_contribution_mismatch", "Choose a transfer between cash accounts."
        )
    oid = str(body.occurrence_id) if body.occurrence_id else None
    if purpose == "funding" and oid:
        model.fail(
            "plan_occurrence_invalid", "Funding alone does not fulfill an occurrence."
        )
    snapshot = (
        definitions.occurrence(
            b["kind"], current, projection.links(c, b), oid, service.clock().date()
        )
        if oid
        else {}
    )
    if purpose == "bill_payment" and not oid:
        model.fail("plan_occurrence_required", "Choose the bill occurrence paid.")
    group_owner = c.execute(
        "select user_id from public.financial_activity_groups where id=%s and current_revision=%s",
        (actual["activity_id"], actual["revision"]),
    ).fetchone()
    if group_owner is None:
        raise StaleVersion()
    if c.execute(
        "select 1 from public.financial_plan_links where activity_owner_id=%s and activity_id=%s and (released_at is null or occurrence_id is not null)",
        (group_owner[0], actual["activity_id"]),
    ).fetchone():
        model.fail(
            "activity_already_claimed", "This activity already has a plan attribution."
        )
    accepted = dict(
        kind=actual["kind"],
        currency=actual["currency"],
        legs=[(leg["role"], leg["account_id"]) for leg in actual["legs"]],
        date=actual["occurred_at"].date().isoformat(),
        counting=True,
        treatment=getattr(body, "treatment", "add"),
    )
    if purpose == "goal_saving":
        accepted |= dict(
            source_account_id=roles["source"],
            destination_account_id=roles["destination"],
            destination_owner_id=by_id[roles["destination"]].user_id,
        )
        reviewed = goal_projection.contribution_minor(actual, accepted, canonical.records)
        accepted["reviewed_personal_minor"] = reviewed
        if reviewed is None:
            model.fail("goal_contribution_unavailable", "Review the original transfer.")
        if accepted["treatment"] == "included":
            allocation = c.execute(
                "select unlinked_minor from public.financial_goal_allocations where goal_id=%s and account_id=%s and binding_id=%s and contributor_membership_id=%s",
                (current["id"], roles["destination"], b["id"], mid),
            ).fetchone()
            if allocation is None or allocation[0] < reviewed:
                model.fail(
                    "goal_included_exceeds_allocation",
                    "Review the explicitly shared residual amount.",
                )
            c.execute(
                "update public.financial_goal_allocations set unlinked_minor=unlinked_minor-%s where goal_id=%s and account_id=%s",
                (reviewed, current["id"], roles["destination"]),
            )
    cid = str(uuid4())
    columns = dict(budget_id=None, expectation_id=None, goal_id=None, debt_plan_id=None)
    columns[store.table(b["kind"])[2]] = current["id"]
    c.execute(
        """insert into public.financial_plan_links(user_id,claim_id,occurrence_id,budget_id,expectation_id,goal_id,debt_plan_id,activity_owner_id,activity_id,activity_revision,snapshot,attribution,binding_id,contributor_membership_id,purpose)
        values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            b["owner_id"],
            cid,
            oid,
            *columns.values(),
            group_owner[0],
            actual["activity_id"],
            actual["revision"],
            Jsonb(snapshot),
            Jsonb(accepted),
            b["id"],
            mid,
            purpose,
        ),
    )
    if purpose == "goal_saving":
        facts = projection.pool(
            c, service.repository, accepted["destination_owner_id"]
        ).get(roles["destination"])
        if facts is None or facts["state"] != "backed":
            model.fail(
                "goal_backing_" + (facts["state"] if facts else "unknown"),
                "Review known available money before increasing an allocation.",
            )
    return cid


def link(service, actor, hid, kind, identifier, body, key):
    def action(ctx, b, current):
        canonical = ctx[-1]
        aid = str(body.activity_id)
        revision = canonical.current.get(aid)
        if revision is None:
            raise HouseholdNotFound()
        actual = render_activity(aid, canonical.history[aid], revision)
        require_activity_access(ctx, actual, actor)
        if revision != body.activity_revision:
            raise StaleVersion()
        ids = {leg["account_id"] for leg in actual["legs"]}
        goal_commands.account_versions(
            canonical.records, body.expected_account_versions, ids
        )
        return attach(service, ctx, b, current, actual, body), False

    return service.mutation(
        actor, hid, kind, identifier, body, key, "link", action, own=True
    )


def release(service, actor, hid, kind, identifier, cid, body, key):
    def action(ctx, b, current):
        link, _ = require_original(ctx, b, cid, actor)
        ctx[0].execute(
            "update public.financial_plan_links set released_at=%s,attribution=jsonb_set(attribution,'{counting}','false') where user_id=%s and claim_id=%s",
            (service.clock(), b["owner_id"], cid),
        )
        return cid, False

    return service.mutation(
        actor, hid, kind, identifier, body, key, "release:" + cid, action, own=True
    )


def candidates(service, actor, hid, kind, identifier):
    with service.context(actor, hid) as ctx:
        c, _, mid, *_ = ctx
        b = store.binding(c, actor, hid, mid, kind, identifier)
        body = store.definition(
            c, kind, identifier, b["owner_id"], b["retained_revision"]
        )
        if b["departed_at"] or body["archived"]:
            return dict(items=[])
        claimed = {
            str(aid)
            for (aid,) in c.execute(
                "select activity_id from public.financial_plan_links where released_at is null or occurrence_id is not null"
            ).fetchall()
        }
        result = []
        canonical = ctx[-1]
        for aid, revision in canonical.current.items():
            if aid in claimed:
                continue
            actual = render_activity(aid, canonical.history[aid], revision)
            if not activity_in_currency(actual, body["currency"]):
                continue
            try:
                require_activity_access(ctx, actual, actor)
            except HouseholdNotFound:
                continue
            result.append(actual)
        result.sort(key=lambda a: (a["occurred_at"], a["activity_id"]), reverse=True)
        return dict(items=result)


def money(service, actor, hid, kind, identifier, body, key=None, cid=None):
    def prepare(ctx, b, current):
        c, _, mid, __, access, canonical = ctx
        aid = None
        if cid:
            link, actual = require_original(ctx, b, cid, actor, correct=True)
            aid = actual["activity_id"]
        request = body.activity
        if not cid and request.expected_revision is not None:
            model.fail(
                "plan_contribution_mismatch",
                "Record a new activity or correct your linked original.",
            )
        if not cid and request.kind == "payment_reversal":
            matching = next(
                (
                    claim_id
                    for claim_id, link in projection.links(c, b).items()
                    if link["activity_id"] == request.reversal_of_activity_id
                    and link["purpose"] == "debt_payment"
                ),
                None,
            )
            if body.purpose != "debt_payment" or matching is None:
                model.fail(
                    "plan_contribution_mismatch",
                    "Return the original contribution to this debt.",
                )
            require_original(ctx, b, matching, actor, correct=True)
        internal = VisibleAccounts(canonical.records, canonical)
        ids = dependencies(internal, request, aid)
        if any(i not in access or access[i][1] != "edit" for i in ids):
            raise HouseholdNotFound()
        targets = selected(request)
        by_id = {s.account.id: s.account for s in canonical.records}
        if len({by_id[i].user_id for i in targets}) > 1 and request.kind not in {
            "transfer",
            "card_payment",
            "debt_payment",
            "payment_reversal",
        }:
            raise HouseholdNotFound()
        result = plan(internal, request, aid, service.clock(), actor_id=actor)
        return result, aid

    if key is None:
        with service.context(actor, hid) as ctx:
            c, h, mid, *_ = ctx
            b = store.binding(c, actor, hid, mid, kind, identifier)
            current = store.definition(
                c, kind, identifier, b["owner_id"], b["retained_revision"]
            )
            service.require_scope(body, h, mid)
            store.require_write(b, current, body.expected_plan_version, own=True)
            result, _ = prepare(ctx, b, current)
            return dict(
                plan=service.project(ctx, actor, b, current), money=result.preview
            )

    def action(ctx, b, current):
        result, aid = prepare(ctx, b, current)
        if body.activity.expected_versions != result.preview["expected_versions"]:
            raise StaleVersion()
        if (
            not result.preview["ready"]
            or body.activity.preview_token != result.preview["preview_token"]
        ):
            model.fail(
                "preview_required",
                "Review the exact proposed Money change before saving.",
            )
        c, *_ = ctx
        owners = {s.account.id: s.account.user_id for s in ctx[-1].records}
        if aid:
            group_owner = str(
                c.execute(
                    "select user_id from public.financial_activity_groups where id=%s",
                    (aid,),
                ).fetchone()[0]
            )
        else:
            roles = selected(body.activity)
            primary = next(i for i, role in roles.items() if role != "destination")
            group_owner = owners[primary]
        persist(c, group_owner, result, owners)
        from argus.domain.recording import canonical_groups

        canonical = canonical_groups.load(
            service.repository, c, {p["user_id"] for p in ctx[3].values()}, scope=PERSONAL
        )
        actual = render_activity(
            result.activity_id, canonical.history[result.activity_id], result.revision
        )
        next_ctx = (*ctx[:-1], canonical)
        if cid:
            # A correction changes the original fact; accepted attribution remains provenance.
            return cid, False
        if body.activity.kind == "payment_reversal":
            original_claim = next(
                claim_id
                for claim_id, link in projection.links(c, b).items()
                if link["activity_id"] == body.activity.reversal_of_activity_id
                and link["purpose"] == "debt_payment"
            )
            return original_claim, False
        return attach(service, next_ctx, b, current, actual, body), False

    return service.mutation(
        actor,
        hid,
        kind,
        identifier,
        body,
        key,
        "correct:" + cid if cid else "record",
        action,
        own=True,
    )


def allocate(service, actor, hid, kind, identifier, body, key):
    if kind != "goal":
        raise HouseholdNotFound()

    def action(ctx, b, current):
        c, _, mid, __, access, canonical = ctx
        aid = str(body.account_id)
        account = next(
            (
                s.account
                for s in canonical.records
                if s.account.id == aid and s.account.user_id == actor
            ),
            None,
        )
        if account is None:
            raise HouseholdNotFound()
        goal_commands.account_versions(
            canonical.records, body.expected_account_versions, {aid}
        )
        model.cash_account(canonical.records, aid, current["currency"])
        value = parse_minor_units(body.amount, current["currency"])
        if value < 0:
            model.fail(
                "goal_allocation_negative",
                "Use zero to release this residual allocation.",
            )
        previous = c.execute(
            "select unlinked_minor from public.financial_goal_allocations where goal_id=%s and account_id=%s",
            (identifier, aid),
        ).fetchone()
        ordinal = c.execute(
            "select coalesce(max(ordinal)+1,0) from public.financial_goal_allocations where goal_id=%s and account_owner_id=%s",
            (identifier, actor),
        ).fetchone()[0]
        c.execute(
            """insert into public.financial_goal_allocations(goal_id,goal_owner_id,account_id,account_owner_id,unlinked_minor,ordinal,binding_id,contributor_membership_id)
            values(%s,%s,%s,%s,%s,%s,%s,%s) on conflict(goal_id,account_id) do update set unlinked_minor=excluded.unlinked_minor,binding_id=excluded.binding_id,contributor_membership_id=excluded.contributor_membership_id""",
            (identifier, b["owner_id"], aid, actor, value, ordinal, b["id"], mid),
        )
        if value > (previous[0] if previous else 0):
            facts = projection.pool(c, service.repository, actor).get(aid)
            if facts is None or facts["state"] != "backed":
                model.fail(
                    "goal_backing_" + (facts["state"] if facts else "unknown"),
                    "Review known available money before increasing an allocation.",
                )
        return None, False

    return service.mutation(
        actor, hid, kind, identifier, body, key, "allocate", action, own=True
    )

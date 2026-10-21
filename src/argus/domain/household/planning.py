"""One scoped shared Plan adapter over original canonical definitions and claims."""

from contextlib import contextmanager
from uuid import uuid4

from argus.domain.backtest_admission import canonical_hash
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import model, storage
from argus.domain.recording import canonical_groups
from argus.domain.recording.errors import IdempotencyConflict, StaleVersion
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.money_postgres import load_owner, owner_lock
from argus.domain.recording.money_schemas import (
    DESTINATION_ELIGIBILITY,
    ELIGIBILITY,
    SOURCE_IDS,
)
from argus.domain.recording.schemas import account_response

from . import planning_definitions as definitions
from . import planning_projection as projection
from . import planning_store as store
from .access import resolve
from .errors import HouseholdNotFound
from .financial import HouseholdFinancialService
from .planning_schemas import PlanSnapshot
from .projection import account as scoped_account

PURPOSES = dict(
    budget=["spending", "funding"],
    bill=["bill_payment", "funding"],
    goal=["goal_saving", "funding"],
    debt=["debt_payment", "funding"],
)


class SharedPlanningService:
    def __init__(self, households):
        self.households = households
        self.financial = HouseholdFinancialService(households)
        self.repository = self.financial.repository
        self.clock = households._repository._clock

    @contextmanager
    def context(self, actor, hid):
        with self.households.transaction(actor, hid) as (c, h, m):
            people = store.members(c, hid)
            owners = canonical_groups.owner_closure(
                c, {p["user_id"] for p in people.values()}
            )
            for owner in owners:
                owner_lock(c, owner)
            c.execute(
                "select id from public.financial_accounts where user_id=any(%s::uuid[]) order by id for update",
                (owners,),
            ).fetchall()
            scope = resolve(c, actor, h, m)
            access = {
                aid: (a.owner_id, a.permission, hid) for aid, a in scope.accounts.items()
            }
            owned = load_owner(self.repository, c, actor, scope=PERSONAL)
            access.update({s.account.id: (actor, "edit", None) for s in owned})
            canonical = canonical_groups.load(self.repository, c, owners, scope=PERSONAL)
            yield c, h, str(m["id"]), people, access, canonical

    @staticmethod
    def require_scope(body, h, mid):
        if str(body.membership_id) != mid:
            raise HouseholdNotFound()
        if body.expected_authorization_version != h["version"]:
            raise StaleVersion()

    def project(self, ctx, actor, b, body=None):
        c, h, mid, people, access, canonical = ctx
        body = body or store.definition(
            c, b["kind"], b["definition_id"], b["owner_id"], b["retained_revision"]
        )
        return projection.public(
            c,
            self.repository,
            b,
            body,
            people,
            actor,
            mid,
            h["version"],
            access,
            canonical,
            self.clock().date(),
        )

    def options(self, actor, hid):
        with self.context(actor, hid) as ctx:
            c, h, mid, people, access, canonical = ctx
            accounts = [
                s
                for s in canonical.records
                if s.account.id in access and access[s.account.id][1] == "edit"
            ]
            refs = []
            for kind, (table, _, __) in store.TABLES.items():
                for identifier, body in c.execute(
                    f"select id,body from public.{table} where user_id=%s order by id",
                    (actor,),
                ).fetchall():
                    if kind == "bill" and body["kind"] != "bill":
                        continue
                    refs.append(
                        dict(
                            ref=dict(kind=kind, id=str(identifier)),
                            name=body.get("name", body.get("title")),
                            version=body["version"],
                            currency=body["currency"],
                        )
                    )
            account_scope = resolve(c, actor, h, {"id": mid})
            money = dict(
                accounts=[
                    account_response(s).model_dump(mode="json")
                    if s.account.user_id == actor
                    else scoped_account(account_scope, s)["account"]
                    for s in accounts
                ],
                eligibility={kind: list(types) for kind, types in ELIGIBILITY.items()},
                destination_eligibility={
                    kind: list(types) for kind, types in DESTINATION_ELIGIBILITY.items()
                },
                categories=list(CATEGORY_IDS),
                sources=list(SOURCE_IDS),
            )
            return dict(
                membership_id=mid,
                authorization_version=h["version"],
                people=[
                    projection.person(people, p) for p in people if people[p]["active"]
                ],
                money=money,
                owned_account_ids=[
                    s.account.id for s in accounts if s.account.user_id == actor
                ],
                existing_definitions=refs,
                purposes=PURPOSES,
            )

    def get(self, actor, hid, kind, identifier):
        with self.context(actor, hid) as ctx:
            c, h, mid, *_ = ctx
            b = store.binding(c, actor, hid, mid, kind, identifier)
            return self.project(ctx, actor, b)

    def snapshot(self, actor, hid):
        with self.context(actor, hid) as ctx:
            return self.snapshot_context(ctx, actor, hid)

    def snapshot_context(self, ctx, actor, hid):
        c, h, mid, *_ = ctx
        items = []
        for kind, identifier in c.execute(
            "select distinct b.kind,b.definition_id from public.household_plan_bindings b left join public.household_plan_participants p on p.binding_id=b.id and p.membership_id=%s and p.revoked_at is null where b.household_id=%s and b.revoked_at is null and (b.owner_membership_id=%s or p.membership_id is not null) order by b.kind,b.definition_id",
            (mid, hid, mid),
        ).fetchall():
            b = store.binding(c, actor, hid, mid, kind, str(identifier))
            items.append(self.project(ctx, actor, b))
        result = dict(
            household_id=hid,
            membership_id=mid,
            authorization_version=h["version"],
            plans=items,
        )
        return PlanSnapshot.model_validate(result).model_dump(mode="json")

    def mutation(
        self,
        actor,
        hid,
        kind,
        identifier,
        body,
        key,
        operation,
        action,
        *,
        owner=False,
        own=False,
        restore=False,
    ):
        with self.context(actor, hid) as ctx:
            c, h, mid, people, access, canonical = ctx
            if str(body.membership_id) != mid:
                raise HouseholdNotFound()
            b = store.binding(c, actor, hid, mid, kind, identifier)
            current = store.definition(
                c, kind, identifier, b["owner_id"], b["retained_revision"]
            )
            allowed_restore = (
                restore
                and not b["departed_at"]
                and current["archived"]
                and b["permission"] == "edit"
            )
            if b["departed_at"] or current["archived"] and not allowed_restore:
                model.fail(
                    "plan_read_only", "This shared plan is archived and read-only."
                )
            if (
                owner
                and not b["is_owner"]
                or not own
                and not owner
                and b["permission"] != "edit"
            ):
                raise HouseholdNotFound()
            identity = canonical_hash(body.model_dump(mode="json"))
            scope = operation + ":" + kind + ":" + identifier
            receipt = c.execute(
                "select identity_hash,binding_id,claim_id from public.household_plan_receipts where actor_id=%s and membership_id=%s and operation=%s and idempotency_key=%s",
                (actor, mid, scope, key),
            ).fetchone()
            if receipt:
                if receipt[0] != identity or str(receipt[1]) != b["id"]:
                    raise IdempotencyConflict()
                if own and receipt[2]:
                    from .planning_contributions import require_original

                    require_original(
                        ctx,
                        b,
                        str(receipt[2]),
                        actor,
                        correct=operation.startswith("correct:") or operation == "record",
                    )
                    if operation == "link":
                        from .planning_contributions import require_activity_access

                        _, actual = require_original(ctx, b, str(receipt[2]), actor)
                        require_activity_access(ctx, actual, actor)
                return dict(plan=self.project(ctx, actor, b), replayed=True)
            self.require_scope(body, h, mid)
            if body.expected_plan_version != current["version"]:
                raise StaleVersion()
            before = current["version"]
            claim_id, changed_consent = action(ctx, b, current)
            if current["version"] == before:
                current["version"] += 1
            store.save(c, kind, b["owner_id"], current, actor)
            proposed = getattr(body, "responsibilities", None)
            rows = (
                definitions.responsibility_rows(
                    c, b, current, proposed, people, self.clock().date()
                )
                if proposed is not None
                else None
            )
            store.responsibilities(c, b, current["version"], rows)
            if changed_consent:
                h["version"] = c.execute(
                    "update public.households set version=version+1 where id=%s returning version",
                    (hid,),
                ).fetchone()[0]
            c.execute(
                "insert into public.household_plan_receipts(actor_id,membership_id,operation,idempotency_key,identity_hash,binding_id,claim_id) values(%s,%s,%s,%s,%s,%s,%s)",
                (actor, mid, scope, key, identity, b["id"], claim_id),
            )
            canonical = canonical_groups.load(
                self.repository,
                c,
                {p["user_id"] for p in people.values()},
                scope=PERSONAL,
            )
            return dict(
                plan=self.project(
                    (c, h, mid, people, access, canonical), actor, b, current
                ),
                replayed=False,
            )

    def create(self, actor, hid, kind, body, key):
        if body.definition.kind != kind:
            raise HouseholdNotFound()
        with self.context(actor, hid) as ctx:
            c, h, mid, people, access, canonical = ctx
            if str(body.membership_id) != mid:
                raise HouseholdNotFound()
            identity = canonical_hash(body.model_dump(mode="json"))
            receipt = c.execute(
                "select identity_hash,binding_id from public.household_plan_receipts where actor_id=%s and membership_id=%s and operation=%s and idempotency_key=%s",
                (actor, mid, "create:" + kind, key),
            ).fetchone()
            if receipt:
                if receipt[0] != identity:
                    raise IdempotencyConflict()
                identifier = c.execute(
                    "select definition_id from public.household_plan_bindings where id=%s",
                    (receipt[1],),
                ).fetchone()[0]
                b = store.binding(c, actor, hid, mid, kind, str(identifier))
                return dict(plan=self.project(ctx, actor, b), replayed=True)
            self.require_scope(body, h, mid)
            accounts = [s for s in canonical.records if s.account.user_id == actor]
            state = storage.load(c, actor, self.repository)
            current = definitions.create(kind, body.definition, accounts, state)
            store.save(c, kind, actor, current, actor)
            b = self.new_binding(
                c, actor, hid, mid, kind, current["id"], body.publish_budget_scope
            )
            store.replace_participants(
                c, b, body.participants, people, self.clock(), current["version"]
            )
            rows = definitions.responsibility_rows(
                c, b, current, body.responsibilities, people, self.clock().date()
            )
            store.responsibilities(c, b, current["version"], rows)
            h["version"] = c.execute(
                "update public.households set version=version+1 where id=%s returning version",
                (hid,),
            ).fetchone()[0]
            c.execute(
                "insert into public.household_plan_receipts(actor_id,membership_id,operation,idempotency_key,identity_hash,binding_id) values(%s,%s,%s,%s,%s,%s)",
                (actor, mid, "create:" + kind, key, identity, b["id"]),
            )
            return dict(plan=self.project(ctx, actor, b, current), replayed=False)

    @staticmethod
    def new_binding(c, actor, hid, mid, kind, identifier, publish):
        column = store.table(kind)[2]
        bid = str(uuid4())
        revision = store.definition(c, kind, identifier, actor)["version"]
        c.execute(
            f"insert into public.household_plan_bindings(id,household_id,owner_membership_id,owner_user_id,kind,{column},publish_budget_scope,first_shared_revision) values(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                bid,
                hid,
                mid,
                actor,
                kind,
                identifier,
                publish if kind == "budget" else False,
                revision,
            ),
        )
        return store.binding(c, actor, hid, mid, kind, identifier)

    def edit(self, actor, hid, kind, identifier, body, key):
        def action(ctx, b, current):
            c, _, __, people, *_ = ctx
            owner_accounts = load_owner(self.repository, c, b["owner_id"], scope=PERSONAL)
            state = storage.load(c, b["owner_id"], self.repository)
            state["links"].update(
                {
                    cid: link
                    for cid, link in projection.links(c, b).items()
                    if link["occurrence_id"]
                }
            )
            state[store.table(kind)[1]][identifier] = current
            if body.definition is not None:
                definitions.edit(
                    kind,
                    current,
                    body.definition,
                    owner_accounts,
                    state,
                    self.clock().date(),
                )
            return None, False

        restore = (
            body.definition is not None
            and body.definition.archived is False
            and body.definition.model_fields_set == {"archived"}
        )
        return self.mutation(
            actor, hid, kind, identifier, body, key, "edit", action, restore=restore
        )

    def replace_participants(self, actor, hid, kind, identifier, body, key):
        def action(ctx, b, current):
            c, _, __, people, *_ = ctx
            store.replace_participants(
                c, b, body.participants, people, self.clock(), current["version"] + 1
            )
            if body.publish_budget_scope is not None:
                if kind != "budget":
                    model.fail(
                        "plan_scope_invalid",
                        "Account spending consent belongs to budgets.",
                    )
                c.execute(
                    "update public.household_plan_bindings set publish_budget_scope=%s where id=%s",
                    (body.publish_budget_scope, b["id"]),
                )
                b["publish_budget_scope"] = body.publish_budget_scope
            return None, True

        return self.mutation(
            actor, hid, kind, identifier, body, key, "participants", action, owner=True
        )

    def history(self, actor, hid, kind, identifier):
        with self.context(actor, hid) as ctx:
            c, _, mid, *_ = ctx
            b = store.binding(c, actor, hid, mid, kind, identifier)
            floor = b["first_shared_revision"] if b["is_owner"] else b["granted_revision"]
            revisions = c.execute(
                "select body from public.financial_plan_definition_revisions where kind=%s and definition_id=%s and owner_id=%s and revision>=%s and (%s::integer is null or revision<=%s) order by revision desc",
                (
                    kind,
                    identifier,
                    b["owner_id"],
                    floor,
                    b["retained_revision"],
                    b["retained_revision"],
                ),
            ).fetchall()
            return dict(items=[self.project(ctx, actor, b, row[0]) for row in revisions])

    def link(self, *args):
        from .planning_contributions import link

        return link(self, *args)

    def share(self, *args):
        from .planning_sharing import share

        return share(self, *args)

    def release(self, *args):
        from .planning_contributions import release

        return release(self, *args)

    def candidates(self, *args):
        from .planning_contributions import candidates

        return candidates(self, *args)

    def money(self, *args, **kwargs):
        from .planning_contributions import money

        return money(self, *args, **kwargs)

    def allocate(self, *args):
        from .planning_contributions import allocate

        return allocate(self, *args)

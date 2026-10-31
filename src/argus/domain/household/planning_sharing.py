"""An owner grants new consent to an existing original definition."""

from argus.domain.idempotency import canonical_hash
from argus.domain.planning import model
from argus.domain.recording.errors import IdempotencyConflict, StaleVersion

from . import planning_definitions as definitions
from . import planning_store as store
from .errors import HouseholdNotFound


def share(service, actor, hid, kind, identifier, body, key):
    with service.context(actor, hid) as ctx:
        c, h, mid, people, *_ = ctx
        if str(body.membership_id) != mid:
            raise HouseholdNotFound()
        identity = canonical_hash(body.model_dump(mode="json"))
        operation = "share:" + kind + ":" + identifier
        receipt = c.execute(
            "select identity_hash,binding_id from public.household_plan_receipts where actor_id=%s and membership_id=%s and operation=%s and idempotency_key=%s",
            (actor, mid, operation, key),
        ).fetchone()
        if receipt:
            if receipt[0] != identity:
                raise IdempotencyConflict()
            b = store.binding(c, actor, hid, mid, kind, identifier)
            if b["id"] != str(receipt[1]) or b["departed_at"]:
                raise HouseholdNotFound()
            return dict(plan=service.project(ctx, actor, b), replayed=True)
        service.require_scope(body, h, mid)
        current = store.definition(c, kind, identifier, actor)
        if current["version"] != body.expected_plan_version:
            raise StaleVersion()
        if current["archived"]:
            model.fail("plan_read_only", "Restore the original plan before sharing it.")
        if c.execute(
            "select 1 from public.household_plan_bindings where kind=%s and definition_id=%s and revoked_at is null and departed_at is null",
            (kind, identifier),
        ).fetchone():
            model.fail("plan_already_shared", "Manage the existing shared consent.")
        # A fresh consent revision creates a history floor without copying a plan.
        current["version"] += 1
        store.save(c, kind, actor, current, actor)
        b = service.new_binding(
            c, actor, hid, mid, kind, identifier, body.publish_budget_scope
        )
        store.replace_participants(
            c, b, body.participants, people, service.clock(), current["version"]
        )
        rows = definitions.responsibility_rows(
            c, b, current, body.responsibilities, people, service.clock().date()
        )
        store.responsibilities(c, b, current["version"], rows)
        h["version"] = c.execute(
            "update public.households set version=version+1 where id=%s returning version",
            (hid,),
        ).fetchone()[0]
        c.execute(
            "insert into public.household_plan_receipts(actor_id,membership_id,operation,idempotency_key,identity_hash,binding_id) values(%s,%s,%s,%s,%s,%s)",
            (actor, mid, operation, key, identity, b["id"]),
        )
        return dict(plan=service.project(ctx, actor, b, current), replayed=False)

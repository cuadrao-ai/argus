"""Owner-serialized Plan writes compose with canonical activity persistence."""

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from argus.domain.owner_scope import PERSONAL
from argus.domain.planning import goal_allocations
from argus.domain.recording.errors import (
    IdempotencyConflict,
    RegisteredAccountRequired,
    StaleVersion,
)
from argus.domain.recording.loop_storage import apply
from argus.domain.recording.money_plan import MoneyPlan
from argus.domain.recording.money_postgres import load_owner, owner_lock, persist
from argus.domain.recording.repository import (
    InMemoryFinancialAccountRepository,
    StoredAccount,
)

Action = Callable[
    [dict[str, Any], list[StoredAccount]], tuple[dict[str, Any], MoneyPlan | None]
]


def empty() -> dict[str, Any]:
    return {
        "expectations": {},
        "budgets": {},
        "goals": {},
        "debts": {},
        "links": {},
        "selection": {
            "version": 0,
            "account_ids": [],
            "time_zone": "America/Santo_Domingo",
        },
        "receipts": {},
    }


def shared_links(connection: Any, user_id: str) -> list[dict[str, Any]]:
    """Current canonical consent supplies internal claim dependencies only."""
    return [
        dict(
            claim_id=str(cid),
            activity_owner_id=str(activity_owner),
            occurrence_id=str(oid) if oid else None,
            activity_id=str(aid),
            expectation_id=str(eid) if eid else None,
            goal_id=str(gid) if gid else None,
            debt_plan_id=str(did) if did else None,
            snapshot=snapshot,
            attribution=attribution,
            purpose=purpose,
            released=released is not None,
            retained=ended is not None,
            retained_applied=applied,
        )
        for cid, oid, activity_owner, aid, eid, gid, did, snapshot, attribution, purpose, released, ended, applied in connection.execute(
            "select l.claim_id,l.occurrence_id,l.activity_owner_id,l.activity_id,l.expectation_id,l.goal_id,l.debt_plan_id,l.snapshot,l.attribution,l.purpose,l.released_at,r.membership_ended_at,r.last_applied_minor "
            "from public.financial_plan_links l join public.household_plan_bindings b on b.id=l.binding_id "
            "left join public.household_plan_archived_claims r on r.binding_id=l.binding_id and r.claim_id=l.claim_id "
            "where l.user_id=%s and b.departed_at is null and b.revoked_at is null",
            (user_id,),
        ).fetchall()
    ]


def claim_owners(user_id: str, links: list[dict[str, Any]]) -> set[str]:
    return {
        user_id,
        *(link["activity_owner_id"] for link in links if not link["retained"]),
    }


def load(connection: Any, user_id: str, repository: Any = None) -> dict[str, Any]:
    state = empty()
    state["_owner_id"] = user_id
    for did, body in connection.execute(
        "select id,body from public.financial_debt_plans where user_id=%s order by id",
        (user_id,),
    ).fetchall():
        state["debts"][str(did)] = body
    for gid, body in connection.execute(
        "select id,body from public.financial_goals where user_id=%s order by id",
        (user_id,),
    ).fetchall():
        state["goals"][str(gid)] = body
    goal_allocations.load(connection, user_id, state["goals"])
    for bid, body in connection.execute(
        "select id,body from public.financial_budgets where user_id=%s order by id",
        (user_id,),
    ).fetchall():
        state["budgets"][str(bid)] = body
    for eid, body in connection.execute(
        "select id,body from public.financial_expectations where user_id=%s order by id",
        (user_id,),
    ).fetchall():
        state["expectations"][str(eid)] = body
    for (
        cid,
        oid,
        eid,
        gid,
        did,
        aid,
        revision,
        snapshot,
        attribution,
    ) in connection.execute(
        "select claim_id,occurrence_id,expectation_id,goal_id,debt_plan_id,activity_id,activity_revision,snapshot,attribution from public.financial_plan_links where user_id=%s and binding_id is null",
        (user_id,),
    ).fetchall():
        state["links"][str(cid)] = {
            "occurrence_id": str(oid) if oid else None,
            "expectation_id": str(eid) if eid else None,
            "goal_id": str(gid) if gid else None,
            "debt_plan_id": str(did) if did else None,
            "activity_id": str(aid),
            "activity_revision": revision,
            "snapshot": snapshot,
            "attribution": attribution,
        }
    row = connection.execute(
        "select body from public.financial_plan_selections where user_id=%s", (user_id,)
    ).fetchone()
    if row:
        state["selection"] = row[0]
    state["_pool_external"] = []
    for gid, aid, amount in connection.execute(
        "select goal_id,account_id,unlinked_minor from public.financial_goal_allocations "
        "where account_owner_id=%s and goal_owner_id<>%s",
        (user_id, user_id),
    ).fetchall():
        state["_pool_external"].append(
            dict(goal_id=str(gid), account_id=str(aid), amount=amount)
        )
    for gid, activity_id, attribution in connection.execute(
        "select goal_id,activity_id,attribution from public.financial_plan_links "
        "where goal_id is not null and purpose='goal_saving' and binding_id is not null and released_at is null "
        "and attribution->>'destination_owner_id'=%s",
        (user_id,),
    ).fetchall():
        state["_pool_external"].append(
            dict(
                goal_id=str(gid),
                activity_id=str(activity_id),
                attribution=attribution,
            )
        )
    if repository is not None:
        from argus.domain.recording import canonical_groups
        from argus.domain.recording.money_reads import render_activity

        state["_shared_links"] = shared_links(connection, user_id)
        canonical = canonical_groups.load(
            repository,
            connection,
            claim_owners(user_id, state["_shared_links"]),
            scope=PERSONAL,
        )
        state["_canonical_groups"] = canonical
        state["_canonical_records"] = canonical.records
        state["_canonical_activities"] = {
            aid: render_activity(aid, canonical.history[aid], revision)
            for aid, revision in canonical.current.items()
        }
        # Foreign pool state stays internal. The existing single pool reducer uses
        # current full groups, while public account positions remain owner-only.
        state["_claim_pool_states"] = {
            owner: load(connection, owner)
            for owner in {
                link["attribution"]["destination_owner_id"]
                for link in state["_shared_links"]
                if link["purpose"] == "goal_saving"
                and not link["released"]
                and not link["retained"]
            }
            if owner != user_id
        }
    return state


def read(repository: Any, user_id: str) -> tuple[dict[str, Any], list[StoredAccount]]:
    if isinstance(repository, InMemoryFinancialAccountRepository):
        with repository._lock:
            state = deepcopy(
                getattr(repository, "_plan_states", {}).get(user_id, empty())
            )
            return state, repository.held(user_id, PERSONAL)
    with repository._pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read read only")
        from argus.domain.recording.canonical_groups import VisibleAccounts

        state = load(connection, user_id, repository)
        return state, VisibleAccounts(
            load_owner(repository, connection, user_id, scope=PERSONAL),
            state["_canonical_groups"],
        )


def projected(
    accounts: list[StoredAccount], money: MoneyPlan, now: datetime
) -> list[StoredAccount]:
    from dataclasses import replace

    canonical = getattr(accounts, "canonical", None)
    if canonical is not None:
        from argus.domain.recording.canonical_groups import VisibleAccounts
        from argus.domain.recording.canonical_groups import projected as project_groups

        current = project_groups(canonical, money, now)
        visible = {s.account.id for s in accounts}
        return VisibleAccounts(
            [s for s in current.records if s.account.id in visible], current
        )

    result = []
    for stored in accounts:
        aid = stored.account.id
        if aid in money.mutations:
            stored = apply(stored, money.mutations[aid], now)
        elif aid in money.affected:
            stored = replace(
                stored,
                account=replace(
                    stored.account, version=stored.account.version + 1, updated_at=now
                ),
            )
        result.append(stored)
    return result


def write(
    repository: Any,
    user_id: str,
    scope: str,
    key: str,
    identity: str,
    action: Action,
    now: datetime,
) -> dict[str, Any]:
    if isinstance(repository, InMemoryFinancialAccountRepository):
        with repository._lock:
            states = getattr(repository, "_plan_states", None)
            if states is None:
                repository._plan_states = states = {}
            state = deepcopy(states.get(user_id, empty()))
            receipt = state["receipts"].get((scope, key))
            if receipt:
                if receipt[0] != identity:
                    raise IdempotencyConflict()
                return deepcopy(receipt[1]) | {"replayed": True}
            accounts = repository.held(user_id, PERSONAL)
            result, money = action(state, accounts)
            if money:
                for stored in projected(accounts, money, now):
                    repository._accounts[stored.account.id] = stored
            result = jsonable_encoder(result) | {"replayed": False}
            state["receipts"][(scope, key)] = (identity, result)
            states[user_id] = state
            return deepcopy(result)
    with repository._pool.connection() as connection, connection.transaction():
        from argus.domain.recording.canonical_groups import VisibleAccounts, owner_closure

        owners = owner_closure(
            connection, claim_owners(user_id, shared_links(connection, user_id))
        )
        for owner in owners:
            owner_lock(connection, owner)
        if not connection.execute(
            "select 1 from auth.users where id=%s and coalesce(is_anonymous,false)=false",
            (user_id,),
        ).fetchone():
            raise RegisteredAccountRequired()
        receipt = connection.execute(
            "select identity_hash,result from public.financial_plan_receipts where user_id=%s and scope=%s and idempotency_key=%s",
            (user_id, scope, key),
        ).fetchone()
        if receipt:
            if receipt[0] != identity:
                raise IdempotencyConflict()
            return receipt[1] | {"replayed": True}
        # Claims may change while waiting for locks. Retry rather than acquiring a
        # newly discovered owner out of order or reducing an incomplete original.
        if not set(
            owner_closure(
                connection, claim_owners(user_id, shared_links(connection, user_id))
            )
        ) <= set(owners):
            raise StaleVersion()
        connection.execute(
            "select id from public.financial_accounts where user_id=any(%s::uuid[]) order by id for update",
            (owners,),
        ).fetchall()
        state = load(connection, user_id, repository)
        original_claims = set(state["links"])
        accounts = VisibleAccounts(
            load_owner(repository, connection, user_id, scope=PERSONAL),
            state["_canonical_groups"],
        )
        result, money = action(state, accounts)
        if money:
            persist(connection, user_id, money)
        connection.execute("select set_config('argus.plan_actor',%s,true)", (user_id,))
        for did, body in state["debts"].items():
            connection.execute(
                "insert into public.financial_debt_plans(id,user_id,debt_account_id,body) values(%s,%s,%s,%s) on conflict(id) do update set body=excluded.body",
                (did, user_id, body["debt_account_id"], Jsonb(body)),
            )
        goal_allocations.persist(connection, user_id, state["goals"])
        for bid, body in state["budgets"].items():
            connection.execute(
                "insert into public.financial_budgets(id,user_id,body) values(%s,%s,%s) on conflict(id) do update set body=excluded.body",
                (bid, user_id, Jsonb(body)),
            )
        for eid, body in state["expectations"].items():
            connection.execute(
                "insert into public.financial_expectations(id,user_id,body) values(%s,%s,%s) on conflict(id) do update set body=excluded.body",
                (eid, user_id, Jsonb(body)),
            )
        connection.execute(
            "insert into public.financial_plan_selections(user_id,body) values(%s,%s) on conflict(user_id) do update set body=excluded.body",
            (user_id, Jsonb(state["selection"])),
        )
        for cid in original_claims - state["links"].keys():
            connection.execute(
                "delete from public.financial_plan_links where user_id=%s and claim_id=%s",
                (user_id, cid),
            )
        for cid, link in state["links"].items():
            conflict = connection.execute(
                "select user_id,claim_id from public.financial_plan_links where activity_owner_id=%s and activity_id=%s and (released_at is null or occurrence_id is not null)",
                (user_id, link["activity_id"]),
            ).fetchone()
            if conflict and (str(conflict[0]), str(conflict[1])) != (user_id, cid):
                from argus.domain.planning.model import fail

                fail(
                    "activity_already_claimed",
                    "This activity already has a plan attribution.",
                )
            connection.execute(
                "insert into public.financial_plan_links(user_id,claim_id,occurrence_id,expectation_id,goal_id,debt_plan_id,activity_id,activity_revision,snapshot,attribution) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict(user_id,claim_id) do update set occurrence_id=excluded.occurrence_id,activity_id=excluded.activity_id,activity_revision=excluded.activity_revision,snapshot=excluded.snapshot,attribution=excluded.attribution",
                (
                    user_id,
                    cid,
                    link.get("occurrence_id", cid),
                    link.get("expectation_id"),
                    link.get("goal_id"),
                    link.get("debt_plan_id"),
                    link["activity_id"],
                    link["activity_revision"],
                    Jsonb(link["snapshot"]),
                    Jsonb(link["attribution"]) if link.get("attribution") else None,
                ),
            )
        result = jsonable_encoder(result) | {"replayed": False}
        connection.execute(
            "insert into public.financial_plan_receipts(user_id,scope,idempotency_key,identity_hash,result) values(%s,%s,%s,%s,%s)",
            (user_id, scope, key, identity, Jsonb(result)),
        )
        return result

"""Direct client reads stop at Personal rows, proven on real Postgres.

An ownership transfer keeps the storage identity of a Business, so the first
owner still matches every ``user_id`` read policy after the grant is revoked.
The API checks live grants. The client role reads Personal rows only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.transfer import PostgresBusinessTransfer
from faker import Faker
from psycopg.types.json import Jsonb

from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_financial_accounts_postgres as shared

world = lifecycle.world
users = lifecycle.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")

fake = Faker("es_MX")

KEY_COLUMN = {
    "backtest_jobs": "id",
    "chat_turn_lifecycles": "turn_id",
    "conversation_read_states": "conversation_id",
    "financial_accounts": "id",
    "financial_activity_groups": "id",
    "financial_activity_memberships": "activity_id",
    "financial_activity_revisions": "activity_id",
    "financial_asset_changes": "account_id",
    "financial_asset_details": "account_id",
    "financial_debt_plans": "id",
    "financial_goal_allocations": "id",
    "financial_import_account_links": "connection_id",
    "financial_observation_coverage": "account_id",
    "financial_plan_links": "claim_id",
    "financial_record_revisions": "record_id",
    "financial_records": "id",
    "financial_source_connections": "id",
    "financial_source_gmail_senders": "connection_id",
}

CANNOT_HOLD_A_BUSINESS_ROW = {
    "financial_budgets",
    "financial_expectations",
    "financial_goals",
    "financial_plan_selections",
    "guest_workspaces",
    "profiles",
}
LIMITED_BEFORE_THIS_PROOF = {"financial_import_events", "financial_import_observations"}
THE_READERS_OWN_ACT = {"business_consent_acceptances"}


def _seed(db, person: str, space: str | None) -> dict[str, set[str]]:  # noqa: ANN001
    """Write one row in every table the client role reads. No space means Personal."""

    db.execute("set constraints all deferred")
    account, asset, debt, connection = (str(uuid4()) for _ in range(4))
    for account_id, kind in (
        (account, "cash"),
        (asset, "property"),
        (debt, "other_debt"),
    ):
        db.execute(
            "insert into public.financial_accounts(id,user_id,owner_space_id,type,currency,nickname)"
            " values(%s,%s,%s,%s,'DOP',%s)",
            (account_id, person, space, kind, fake.word()),
        )
    db.execute(
        "insert into public.financial_asset_details(account_id,user_id,related_debt_account_id)"
        " values(%s,%s,%s)",
        (asset, person, debt),
    )
    db.execute(
        "insert into public.financial_asset_changes(account_id,user_id,account_version,"
        "previous_share_bps,ownership_share_bps,related_debt_account_id,recorded_by,"
        "idempotency_key,identity_hash) values(%s,%s,2,10000,10000,%s,%s,%s,'hash')",
        (asset, person, debt, person, fake.uuid4()),
    )

    record, observation, activity = (str(uuid4()) for _ in range(3))
    for record_id in (record, observation):
        db.execute(
            "insert into public.financial_records(id,user_id,account_id,record_kind)"
            " values(%s,%s,%s,'expense')",
            (record_id, person, account),
        )
        db.execute(
            "insert into public.financial_record_revisions(record_id,user_id,revision,"
            "amount_minor,as_of,as_of_zone,reason,recorded_by,details)"
            " values(%s,%s,1,%s,now(),'America/Santo_Domingo',%s,%s,'{}')",
            (record_id, person, fake.random_int(100, 900_000), fake.word(), person),
        )
    db.execute(
        "insert into public.financial_activity_groups(id,user_id,kind,current_revision)"
        " values(%s,%s,'expense',1)",
        (activity, person),
    )
    db.execute(
        "insert into public.financial_activity_revisions(activity_id,user_id,revision)"
        " values(%s,%s,1)",
        (activity, person),
    )
    db.execute(
        "insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,"
        "record_id,record_revision,record_owner_id,role) values(%s,%s,1,%s,1,%s,'single')",
        (activity, person, record, person),
    )
    db.execute(
        "insert into public.financial_observation_coverage(account_id,user_id,observation_id,"
        "observation_revision,activity_id,activity_revision,included)"
        " values(%s,%s,%s,1,%s,1,true)",
        (account, person, observation, record),
    )

    db.execute(
        "insert into public.financial_source_connections(id,user_id,owner_space_id,source,"
        "external_ref,label) values(%s,%s,%s,'gmail',%s,%s)",
        (connection, person, space, fake.uuid4(), fake.word()),
    )
    db.execute(
        "insert into public.financial_source_gmail_senders(connection_id,user_id,sender)"
        " values(%s,%s,%s)",
        (connection, person, fake.email().lower()),
    )
    db.execute(
        "insert into public.financial_import_account_links(user_id,connection_id,account_key,"
        "account_id,created_at) values(%s,%s,'cash',%s,now())",
        (person, connection, account),
    )

    goal, allocation, debt_plan, claim = (str(uuid4()) for _ in range(4))
    db.execute(
        "insert into public.financial_goals(id,user_id,body) values(%s,%s,%s)",
        (goal, person, Jsonb({"id": goal, "version": 1, "target_minor": 100_000})),
    )
    db.execute(
        "insert into public.financial_goal_allocations(id,goal_id,goal_owner_id,account_id,"
        "account_owner_id,unlinked_minor,ordinal) values(%s,%s,%s,%s,%s,100,0)",
        (allocation, goal, person, account, person),
    )
    db.execute(
        "insert into public.financial_debt_plans(id,user_id,debt_account_id,body)"
        " values(%s,%s,%s,%s)",
        (
            debt_plan,
            person,
            debt,
            Jsonb({"id": debt_plan, "version": 1, "debt_account_id": debt}),
        ),
    )
    db.execute(
        "insert into public.financial_plan_links(claim_id,user_id,activity_id,activity_revision,"
        "activity_owner_id,snapshot,goal_id,attribution) values(%s,%s,%s,1,%s,'{}',%s,%s)",
        (claim, person, activity, person, goal, Jsonb({"counting": True})),
    )

    conversation, turn, job = (str(uuid4()) for _ in range(3))
    db.execute(
        "insert into public.conversations(id,user_id,owner_space_id,title) values(%s,%s,%s,%s)",
        (conversation, person, space, fake.sentence()),
    )
    db.execute(
        "insert into public.messages(id,conversation_id,user_id,role,content)"
        " values(%s,%s,%s,'user',%s)",
        (turn, conversation, person, fake.sentence()),
    )
    db.execute(
        "insert into public.chat_turn_lifecycles(turn_id,user_id,conversation_id,request_id)"
        " values(%s,%s,%s,%s)",
        (turn, person, conversation, fake.uuid4()),
    )
    db.execute(
        "insert into public.conversation_read_states(conversation_id,user_id) values(%s,%s)",
        (conversation, person),
    )
    db.execute(
        "insert into public.backtest_jobs(id,user_id,conversation_id,payload_hash,launch_payload)"
        " values(%s,%s,%s,%s,'{}')",
        (job, person, conversation, fake.sha256()),
    )

    rows = {
        "backtest_jobs": {job},
        "chat_turn_lifecycles": {turn},
        "conversation_read_states": {conversation},
        "financial_accounts": {account, asset, debt},
        "financial_activity_groups": {activity},
        "financial_activity_memberships": {activity},
        "financial_activity_revisions": {activity},
        "financial_asset_changes": {asset},
        "financial_asset_details": {asset},
        "financial_debt_plans": {debt_plan},
        "financial_goal_allocations": {allocation},
        "financial_import_account_links": {connection},
        "financial_observation_coverage": {account},
        "financial_plan_links": {claim},
        "financial_record_revisions": {record, observation},
        "financial_records": {record, observation},
        "financial_source_connections": {connection},
        "financial_source_gmail_senders": {connection},
    }
    if space is not None:
        accountless = str(uuid4())
        db.execute(
            "insert into public.financial_records(id,user_id,owner_space_id,funding,currency,"
            "record_kind) values(%s,%s,%s,'owner_funds','DOP','expense')",
            (accountless, person, space),
        )
        rows["financial_records"].add(accountless)
    return rows


@pytest.fixture
def graphs(world):  # noqa: ANN001
    _, space, people, _, _ = world
    with psycopg.connect(shared.DSN) as db, db.transaction():
        personal = _seed(db, people["owner"], None)
        business = _seed(db, people["owner"], space.id)
    return personal, business


def _visible(
    role: str,
    person: str,
    *graphs_seen: Mapping[str, set[str]],
    is_anonymous: bool = False,
) -> dict[str, set[str]]:
    """Read each seeded row as ``role``, the way the data API would."""

    seen: dict[str, set[str]] = {}
    with psycopg.connect(shared.DSN) as db, db.transaction(force_rollback=True):
        db.execute(
            psycopg.sql.SQL("set local role {}").format(psycopg.sql.Identifier(role))
        )
        db.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": person, "role": role, "is_anonymous": is_anonymous}),),
        )
        for table, column in KEY_COLUMN.items():
            ids = sorted(set().union(*(graph[table] for graph in graphs_seen)))
            seen[table] = {
                str(row[0])
                for row in db.execute(
                    psycopg.sql.SQL(
                        "select {} from public.{} where {} = any(%s::uuid[])"
                    ).format(
                        psycopg.sql.Identifier(column),
                        psycopg.sql.Identifier(table),
                        psycopg.sql.Identifier(column),
                    ),
                    (ids,),
                ).fetchall()
            }
    return seen


def _leaked(seen: Mapping[str, set[str]], business: Mapping[str, set[str]]) -> set[str]:
    return {table for table, ids in seen.items() if ids & business[table]}


def _transfer_then_revoke(world) -> None:  # noqa: ANN001
    pool, space, people, access, member = world
    transfers = PostgresBusinessTransfer(pool)
    pending = transfers.request(
        owner_id=people["owner"],
        space_id=space.id,
        target_grant_id=member.id,
        confirmation=space.name,
        idempotency_key=fake.uuid4(),
    )
    transfers.accept(actor_id=people["other"], transfer_id=pending.id)
    former = next(
        grant
        for grant in access.list(space.id, people["other"]).grants
        if not grant.owner
    )
    assert access.revoke_grant(space.id, people["other"], former.id) not in {
        "missing",
        "own_grant",
    }


def test_former_owner_reads_only_personal_rows_after_transfer_and_revocation(
    world, graphs
) -> None:  # noqa: ANN001
    _, space, people, _, _ = world
    personal, business = graphs
    _transfer_then_revoke(world)

    with psycopg.connect(shared.DSN) as db:
        with pytest.raises(ActionError):
            authorize(db, lifecycle._actor(people["owner"], space.id))
        assert db.execute(
            "select created_by::text from public.spaces where id=%s", (space.id,)
        ).fetchone() == (people["owner"],)

    seen = _visible("authenticated", people["owner"], personal, business)
    assert _leaked(seen, business) == set()
    assert seen == personal


def test_owner_with_a_live_grant_reads_business_rows_through_the_api_only(
    world, graphs
) -> None:  # noqa: ANN001
    _, _, people, _, _ = world
    personal, business = graphs
    seen = _visible("authenticated", people["owner"], personal, business)
    assert _leaked(seen, business) == set()
    assert seen == personal


def test_the_server_role_still_reads_every_business_row(world, graphs) -> None:  # noqa: ANN001
    _, _, people, _, _ = world
    personal, business = graphs
    _transfer_then_revoke(world)
    assert _visible("service_role", people["other"], business) == business


def test_a_guest_reads_nothing_from_a_registered_owner(world, graphs) -> None:  # noqa: ANN001
    _, _, people, _, _ = world
    personal, business = graphs
    seen = _visible(
        "authenticated", people["guest"], personal, business, is_anonymous=True
    )
    assert seen == {table: set() for table in KEY_COLUMN}


def test_every_client_readable_table_is_classified() -> None:
    with psycopg.connect(shared.DSN) as db:
        readable = {
            row[0]
            for row in db.execute(
                "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
                " where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm')"
                " and has_any_column_privilege('authenticated', c.oid, 'select')"
            ).fetchall()
        }
    assert readable == (
        set(KEY_COLUMN)
        | CANNOT_HOLD_A_BUSINESS_ROW
        | LIMITED_BEFORE_THIS_PROOF
        | THE_READERS_OWN_ACT
    )

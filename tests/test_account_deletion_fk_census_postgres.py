"""Lane 6 FK census: what a plain auth.users delete blocks on and what it takes.

Real PostgreSQL with every migration applied (``ARGUS_DISPOSABLE_DATABASE_URL``).
Builds user A who shares plans, groups, records and households with B (and a
departed C), then deletes A from auth.users inside a transaction that is always
rolled back. Each blocking constraint or trigger is recorded and lifted only
inside that transaction, so the delete can continue and show every blocker and
every cascade. Nothing here changes the schema outside the rolled-back
transaction, and no deletion command exists yet: this is the evidence Lane 6
starts from. See docs/specs/lanes/account-deletion-fk-census.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg
import pytest
from argus.domain.household import planning_schemas as wire
from argus.domain.household.schemas import CreateHouseholdRequest
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.asset_schemas import AssetDetailsRequest
from argus.domain.recording.assets import AssetService
from argus.domain.recording.service import FinancialAccountService
from psycopg_pool import ConnectionPool

from tests.account_deletion_census import PROTECTED_HISTORY, sweep, user_columns
from tests.financial_accounts.test_assets import create as create_asset
from tests.household.conftest import TEST_CODE_SECRET
from tests.household.financial_fixtures import DSN, NOW, account, key, share
from tests.household.financial_fixtures import command as household_command
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.household.shared_plan_fixtures import command as plan_command
from tests.household.shared_plan_fixtures import create, money, request, scene
from tests.household.test_shared_planning_departure import accept, invitation, leave
from tests.memory.test_postgres_reconciliation_deletion import (
    _seed_complete_memory_state,
)
from tests.test_guest_cleanup_postgres import _seed_complete_expired_guest_graph

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


@pytest.fixture(autouse=True)
def _invite_code_secret(monkeypatch):  # noqa: ANN001, ANN202
    """The world makes household invitations, whose codes need the secret (#794).

    Same test secret as tests/household; it passes the placeholder floor.
    """
    monkeypatch.setenv("ARGUS_INVITE_CODE_SECRET", TEST_CODE_SECRET)
    monkeypatch.delenv("ARGUS_INVITE_CODE_SECRET_PREVIOUS", raising=False)


CENSUS_DOC = (
    Path(__file__).resolve().parents[1] / "docs/specs/lanes/account-deletion-fk-census.md"
)
REPORT = Path(__file__).resolve().parents[1] / "temp/account-deletion-fk-census-report.md"

# Columns Priya's #782 note says the first Lane 6 census must name.
REQUIRED_COLUMNS = {
    ("public.financial_plan_links", "activity_owner_id"),
    ("public.household_plan_archived_claims", "activity_owner_id"),
    ("public.household_plan_archived_activities", "activity_owner_id"),
    ("public.financial_goal_allocations", "account_owner_id"),
    ("public.financial_goal_allocation_revisions", "account_owner_id"),
    ("public.financial_activity_memberships", "record_owner_id"),
    ("public.financial_goal_allocation_revisions", "contributor_membership_id"),
}

# Restricting keys the #782 handoff names from reading the migrations. The live
# delete must hit each of them, or the handoff is wrong.
HANDOFF_BLOCKERS = {
    ("public.financial_plan_definition_revisions", ("owner_id",)),
    ("public.financial_plan_definition_revisions", ("actor_id",)),
    ("public.household_plan_receipts", ("actor_id",)),
    ("public.household_plan_participants", ("membership_id", "household_id")),
    ("public.financial_plan_responsibilities", ("membership_id",)),
    ("public.household_plan_receipts", ("membership_id",)),
    ("public.financial_plan_links", ("contributor_membership_id",)),
    ("public.financial_goal_allocation_revisions", ("contributor_membership_id",)),
}
# Restricting in the catalog, but the live delete removes the row through the
# deleted person's own account first, so it never fires on its own.
CATALOG_ONLY_RESTRICT = (
    "public.financial_goal_allocations",
    ("contributor_membership_id",),
)


# --------------------------------------------------------------------------- #
# Scenario: A shares everything with B, C contributed to A's plan and left.
# --------------------------------------------------------------------------- #


def _plan_as(s, actor, actor_mid, kind, participants, responsibilities, definition):
    return s["plans"].create(
        actor,
        s["hid"],
        kind,
        wire.CreatePlan(
            membership_id=actor_mid,
            expected_authorization_version=s["households"]
            .get(user_id=actor, household_id=s["hid"])
            .version,
            definition=definition,
            participants=[dict(membership_id=m) for m in participants],
            responsibilities=[
                dict(membership_id=m, amount=amount, agreed_date=NOW.date())
                for m, amount in responsibilities
            ],
        ),
        key(),
    )["plan"]


def _bill(account_id):
    return dict(
        kind="bill",
        title="Shared bill",
        amount="100",
        currency="DOP",
        account_id=account_id,
        schedule=dict(cadence="once", start_date=NOW.date().isoformat()),
    )


def _goal(source, destination):
    schedule = dict(cadence="once", start_date=NOW.date().isoformat())
    return dict(
        kind="goal",
        name="Shared savings",
        target="100",
        currency="DOP",
        destination_account_id=destination,
        contribution_plan=dict(source_account_id=source, amount="100", schedule=schedule),
    )


def _occurrence(plan):
    return plan["occurrences"][0]["id"]


def _allocate(s, actor, plan, account_id, amount="15"):
    version = (
        s["records"]
        .get_account(user_id=actor, account_id=account_id, scope=PERSONAL)
        .account.version
    )
    return s["plans"].allocate(
        actor,
        s["hid"],
        "goal",
        str(plan["ref"]["id"]),
        plan_command(
            s,
            actor,
            plan,
            wire.AllocationWrite,
            account_id=account_id,
            amount=amount,
            expected_account_versions={account_id: version},
        ),
        key(),
    )


def build_world(services, pool):  # noqa: ANN001
    s = scene(services)  # H1: A admin, B member; A and B accounts
    a, b, c = s["a"], s["b"], s["c"]
    households, records = s["households"], s["records"]

    # Groups: account grants both ways inside H1.
    share(households, a, s["hid"], s["aa"], s["bmid"], "edit")
    share(households, b, s["hid"], s["ba"], s["amid"])

    # Plans A owns, shared with B: one of each kind; B contributes money.
    owned = {kind: create(s, kind) for kind in ("budget", "bill", "goal", "debt")}
    money(
        s,
        a,
        owned["bill"],
        request("expense", s["aa"], "20"),
        "bill_payment",
        _occurrence(owned["bill"]),
    )
    money(s, b, owned["budget"], request("expense", s["ba"], "15"), "spending")
    money(
        s,
        b,
        owned["bill"],
        request("expense", s["ba"], "10"),
        "bill_payment",
        _occurrence(owned["bill"]),
    )
    share(households, a, s["hid"], s["ad"], s["bmid"], "edit")
    money(
        s,
        b,
        owned["goal"],
        request("transfer", s["ba"], "25", s["ad"]),
        "goal_saving",
        _occurrence(owned["goal"]),
    )
    _allocate(s, b, owned["goal"], s["bd"])  # B's account backs A's goal

    # Plans B owns in H1 where A has a part: A's amounts, A's responsibility.
    b_bill = _plan_as(
        s,
        b,
        s["bmid"],
        "bill",
        [s["amid"]],
        [(s["bmid"], "50"), (s["amid"], "50")],
        _bill(s["ba"]),
    )
    money(
        s,
        a,
        b_bill,
        request("expense", s["aa"], "30"),
        "bill_payment",
        _occurrence(b_bill),
    )
    b_goal = _plan_as(
        s,
        b,
        s["bmid"],
        "goal",
        [s["amid"]],
        [(s["bmid"], "50"), (s["amid"], "50")],
        _goal(s["ba"], s["bd"]),
    )
    share(households, b, s["hid"], s["bd"], s["amid"], "edit")
    money(
        s,
        a,
        b_goal,
        request("transfer", s["aa"], "40", s["bd"]),
        "goal_saving",
        _occurrence(b_goal),
    )
    _allocate(s, a, b_goal, s["ad"])  # A's account backs B's goal

    # #773 archive on a plan A owns: C joins H1, contributes, then leaves.
    cmid = accept(s, c, invitation(s, a))
    ca = account(records, c)
    archived = _plan_as(
        s,
        a,
        s["amid"],
        "bill",
        [s["bmid"], cmid],
        [(s["amid"], "40"), (s["bmid"], "30"), (cmid, "30")],
        _bill(s["aa"]),
    )
    money(
        dict(s, c=c),
        c,
        archived,
        request("expense", ca, "5"),
        "bill_payment",
        _occurrence(archived),
    )
    leave(s, c)

    # H2: B is admin, A was a member who contributed to B's plan and left, so
    # the archive pins A's own activity under B's binding.
    h2 = household_command(
        households,
        b,
        "create",
        lambda: households.create(
            user_id=b, request=CreateHouseholdRequest(name="Second", display_name="Bob")
        ),
    ).household_id
    s2 = dict(s, hid=h2)
    s2["bmid"] = households.get(user_id=b, household_id=h2).membership_id
    s2["amid"] = accept(s2, a, invitation(s2, b))
    h2_bill = _plan_as(
        s2,
        b,
        s2["bmid"],
        "bill",
        [s2["amid"]],
        [(s2["bmid"], "60"), (s2["amid"], "40")],
        _bill(s["ba"]),
    )
    money(
        s2,
        a,
        h2_bill,
        request("expense", s["aa"], "12"),
        "bill_payment",
        _occurrence(h2_bill),
    )
    bx = account(records, b)
    h2_goal = _plan_as(
        s2,
        b,
        s2["bmid"],
        "goal",
        [s2["amid"]],
        [(s2["bmid"], "60"), (s2["amid"], "40")],
        _goal(s["ba"], bx),
    )
    _allocate(s2, a, h2_goal, s["aa"])
    leave(s2, a)

    # A's own private rows outside households.
    PostgresConnectionRepository(pool).create(
        user_id=a,
        source="plaid",
        external_ref="item-" + key(),
        label="Bank",
        now=NOW,
        secret=b"sealed",
        scope=PERSONAL,
    )
    with pool.connection() as conn:
        conn.execute(
            "insert into public.profiles(id,email) select id,email from auth.users where id=%s",
            (a,),
        )
        conversation = conn.execute(
            "insert into public.conversations(user_id,title) values (%s,'Census') returning id",
            (a,),
        ).fetchone()[0]
        conn.execute(
            "insert into public.messages(conversation_id,user_id,role,content) values (%s,%s,'user','hola')",
            (conversation, a),
        )
        conn.execute(
            "insert into public.feedback(user_id,type,message,context) values (%s,'account_deletion_request','Borrar',%s)",
            (a, json.dumps({"account_email": f"household-{a}@example.test"})),
        )
    with psycopg.connect(DSN, autocommit=True) as conn:
        _seed_complete_memory_state(conn, a, "pending")

    # Same-owner keys that RESTRICT or NO ACTION inside A's own cascade: an
    # asset linked to one debt and then re-linked to another, and a full
    # memory graph with a reconciliation still pending.
    accounts = FinancialAccountService(records, lambda: NOW)
    assets = AssetService(accounts)
    house = create_asset(accounts, a)
    debts = [create_asset(accounts, a, "other_debt", "1000000", 10000) for _ in range(2)]
    for debt in debts:
        version = records.get_account(
            user_id=a, account_id=house.account.id, scope=PERSONAL
        ).account.version
        assets.details(
            a,
            house.account.id,
            AssetDetailsRequest(
                expected_version=version,
                ownership_share_bps=5000,
                related_debt_account_id=debt.account.id,
            ),
            key(),
        )
    with pool.connection() as conn:
        b_side = {
            str(r[0])
            for r in conn.execute(
                "select id from public.household_members where user_id=%s", (b,)
            ).fetchall()
        }
        bindings = {
            str(r[0])
            for r in conn.execute(
                "select id from public.household_plan_bindings where household_id=any(%s::uuid[])",
                ([s["hid"], h2],),
            ).fetchall()
        }
        a_side = {
            str(r[0])
            for r in conn.execute(
                "select id from public.household_members where user_id=%s", (a,)
            ).fetchall()
        }
    return dict(
        a=a,
        b=b,
        c=c,
        households=[s["hid"], h2],
        own=a_side,
        b_markers={b, s["hid"], h2} | b_side | bindings,
    )


# --------------------------------------------------------------------------- #
# Probe: delete A, lifting each blocker inside a rolled-back transaction.
# --------------------------------------------------------------------------- #


def _primary_keys(conn, table):  # noqa: ANN001
    return [
        r[0]
        for r in conn.execute(
            "select a.attname from pg_index i join pg_attribute a on a.attrelid=i.indrelid "
            "and a.attnum=any(i.indkey) where i.indrelid=%s::regclass and i.indisprimary "
            "order by array_position(i.indkey::int2[], a.attnum)",
            (table,),
        ).fetchall()
    ]


def _snapshot(conn, tables):  # noqa: ANN001
    result = {}
    for table, pk in tables.items():
        rows = {}
        for (row,) in conn.execute(f"select row_to_json(t)::jsonb from {table} t"):
            ident = (
                tuple(str(row[c]) for c in pk) if pk else json.dumps(row, sort_keys=True)
            )
            rows[ident] = row
        result[table] = rows
    return result


_FUNCTION = re.compile(r"function (?:\w+\.)?(\w+)\(")


def probe(conn, victim, keys):  # noqa: ANN001
    tables = {
        t: _primary_keys(conn, t)
        for t in {k.table for k in keys} | {k.referenced for k in keys}
        if not t.startswith("auth.")
    }
    by_name = {(k.table, k.name): k for k in keys}
    blockers, plain_error = [], None
    with conn.transaction(force_rollback=True):
        # Deferred keys would otherwise only fire at COMMIT, which never comes.
        conn.execute("set constraints all immediate")
        before = _snapshot(conn, tables)
        while True:
            try:
                with conn.transaction():
                    conn.execute("delete from auth.users where id=%s", (victim,))
                break
            except psycopg.errors.ForeignKeyViolation as error:
                diag = error.diag
                plain_error = plain_error or str(error).splitlines()[0]
                fk = by_name.get(
                    (f"{diag.schema_name}.{diag.table_name}", diag.constraint_name)
                )
                assert fk is not None, f"blocked by a key outside the sweep: {error}"
                blockers.append(("fk", fk))
                conn.execute(f'alter table {fk.table} drop constraint "{fk.name}"')
            except (
                psycopg.errors.CheckViolation,
                psycopg.errors.NotNullViolation,
            ) as error:
                # A SET NULL action can break a check or not-null rule on the
                # referencing row; a trigger can raise a check violation too.
                diag = error.diag
                plain_error = plain_error or str(error).splitlines()[0]
                if not diag.table_name or (
                    not diag.constraint_name and not diag.column_name
                ):
                    _lift_trigger(conn, error, blockers)
                    continue
                table = f"{diag.schema_name}.{diag.table_name}"
                cause = re.search(r'SET "(\w+)" = NULL', diag.context or "")
                if diag.constraint_name:
                    detail = pg_get_check(conn, table, diag.constraint_name)
                    blockers.append(
                        (
                            "check",
                            (
                                table,
                                diag.constraint_name,
                                detail,
                                cause and cause.group(1),
                            ),
                        )
                    )
                    conn.execute(
                        f'alter table {table} drop constraint "{diag.constraint_name}"'
                    )
                else:
                    blockers.append(
                        (
                            "not null",
                            (table, diag.column_name, "not null", diag.column_name),
                        )
                    )
                    conn.execute(
                        f'alter table {table} alter column "{diag.column_name}" drop not null'
                    )
            except psycopg.errors.RaiseException as error:
                plain_error = plain_error or str(error).splitlines()[0]
                _lift_trigger(conn, error, blockers)
        after = _snapshot(conn, tables)
    return plain_error, blockers, before, after


def pg_get_check(conn, table, name):  # noqa: ANN001
    return conn.execute(
        "select pg_get_constraintdef(oid) from pg_constraint where conrelid=%s::regclass and conname=%s",
        (table, name),
    ).fetchone()[0]


def _lift_trigger(conn, error, blockers):  # noqa: ANN001
    function = _FUNCTION.search(error.diag.context or "").group(1)
    triggers = conn.execute(
        "select t.tgrelid::regclass::text, t.tgname from pg_trigger t join pg_proc p "
        "on p.oid=t.tgfoid where p.proname=%s and not t.tgisinternal and t.tgenabled<>'D'",
        (function,),
    ).fetchall()
    assert triggers, error
    for table, name in triggers:
        blockers.append(("trigger", (table, name, function, str(error).splitlines()[0])))
        conn.execute(f'alter table {table} disable trigger "{name}"')


def _is_b_visible(row, markers):  # noqa: ANN001
    return any(str(v) in markers for v in row.values())


def outcomes(keys, before, after, markers, victim, own=frozenset()):  # noqa: ANN001
    removed = {
        t: {i: r for i, r in rows.items() if i not in after[t]}
        for t, rows in before.items()
    }
    changed = {
        t: {
            i: (r, after[t][i])
            for i, r in rows.items()
            if i in after[t] and after[t][i] != r
        }
        for t, rows in before.items()
    }
    removed["auth.users"] = {(victim,): {"id": victim}}
    per_key = {}
    for k in keys:
        gone = {
            tuple(str(r.get(c)) for c in k.referenced_columns)
            for r in removed.get(k.referenced, {}).values()
        }
        children = {
            i: r
            for i, r in before.get(k.table, {}).items()
            if tuple(str(r.get(c)) for c in k.columns) in gone
        }
        # Rows that point at one of A's rows even when that row was kept,
        # because a blocker held it or the probe never removed it.
        mine = {victim} | set(own)
        owned = {
            tuple(str(r.get(c)) for c in k.referenced_columns)
            for r in before.get(k.referenced, {}).values()
            if any(str(v) in mine for v in r.values())
        } | gone
        pinned = sum(
            1
            for r in before.get(k.table, {}).values()
            if tuple(str(r.get(c)) for c in k.columns) in owned
        )
        per_key[k] = dict(
            pinned=pinned,
            referencing=len(children),
            removed=sum(1 for i in children if i in removed[k.table]),
            nulled=sum(1 for i in children if i in changed[k.table]),
            survived=sum(
                1
                for i in children
                if i not in removed[k.table] and i not in changed[k.table]
            ),
            b_visible=sum(1 for r in children.values() if _is_b_visible(r, markers)),
        )
    per_table = {
        t: dict(
            removed=len(removed[t]),
            changed=len(changed[t]),
            b_visible_removed=sum(
                1 for r in removed[t].values() if _is_b_visible(r, markers)
            ),
            b_visible_changed=sum(
                1 for r, _ in changed[t].values() if _is_b_visible(r, markers)
            ),
            protected=t in PROTECTED_HISTORY,
        )
        for t in before
        if removed[t] or changed[t]
    }
    return per_key, per_table


def _report(plain_error, blockers, per_key, per_table) -> str:
    lines = [
        "# Account deletion FK census: live probe",
        "",
        f"Plain delete error: `{plain_error}`",
        "",
    ]
    lines += [
        "## Blockers, in the order Postgres raised them",
        "",
        "| # | Kind | Table | Columns or trigger | References | Action | Referencing rows | Survived after lift | B-visible |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for n, (kind, item) in enumerate(blockers, 1):
        if kind == "fk":
            o = per_key[item]
            lines.append(
                f"| {n} | FK | `{item.table}` | `{', '.join(item.columns)}` | `{item.referenced}` | {item.on_delete} | {o['referencing']} | {o['survived']} | {o['b_visible']} |"
            )
        elif kind == "trigger":
            table, name, function, message = item
            lines.append(
                f"| {n} | trigger | `{table}` | `{name}` ({function}) | | {message} | | | |"
            )
        else:
            table, name, detail, cause = item
            lines.append(
                f"| {n} | {kind} | `{table}` | `{name}` | SET NULL of `{cause}` | `{detail}` | | | |"
            )
    lines += [
        "",
        "## Every FK the fixture exercised",
        "",
        "| Table | Columns | References | Action | Referencing rows | Removed | Nulled | Survived | B-visible |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k, o in per_key.items():
        if o["referencing"]:
            lines.append(
                f"| `{k.table}` | `{', '.join(k.columns)}` | `{k.referenced}` | {k.on_delete} | {o['referencing']} | {o['removed']} | {o['nulled']} | {o['survived']} | {o['b_visible']} |"
            )
    lines += [
        "",
        "## Rows the delete removed or changed, by table",
        "",
        "| Table | Removed | Changed | B-visible removed | B-visible changed | Protected history |",
        "|---|---|---|---|---|---|",
    ]
    for t, o in sorted(per_table.items()):
        lines.append(
            f"| `{t}` | {o['removed']} | {o['changed']} | {o['b_visible_removed']} | {o['b_visible_changed']} | {'yes' if o['protected'] else ''} |"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def _documented_rows():
    rows = set()
    for line in CENSUS_DOC.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[0].startswith("`") and cells[1].startswith("`"):
            table = cells[0].strip("`")
            referenced = cells[2].strip("`")
            rows.add(
                (
                    table if "." in table else "public." + table,
                    cells[1].strip("`").replace(" ", ""),
                    referenced if "." in referenced else "public." + referenced,
                    cells[3],
                    cells[4],
                    cells[5],
                )
            )
    return rows


def test_sweep_names_every_user_reference_and_the_census_document_matches_it():
    with psycopg.connect(DSN) as conn:
        keys = sweep(conn)
        columns = user_columns(conn, keys)
    assert keys, "the sweep found no foreign keys; are the migrations applied?"
    found = {(c.table, c.column): c for c in columns}
    missing = REQUIRED_COLUMNS - set(found)
    assert not missing, f"required user columns missing from the sweep: {missing}"
    for required in REQUIRED_COLUMNS:
        assert found[required].covered_by, f"{required} has no foreign key"
    in_db = {k.key for k in keys}
    documented = _documented_rows()
    stale = documented - in_db
    new = in_db - documented
    assert not stale and not new, (
        "docs/specs/lanes/account-deletion-fk-census.md is out of date with the "
        "schema. Run `python -m tests.account_deletion_census` against a migrated "
        "database and add or fix these rows, with a Lane 6 action for each.\n"
        f"Not in the schema any more: {sorted(stale)}\nNot in the census yet: {sorted(new)}"
    )
    unkeyed = {(c.table, c.column) for c in columns if not c.covered_by}
    documented_text = CENSUS_DOC.read_text(encoding="utf-8")
    for table, column in unkeyed:
        assert (
            f"`{table.removeprefix('public.')}.{column}`" in documented_text
        ), f"{table}.{column} holds a user id with no foreign key and is not in the census"


def test_deleting_a_sharing_user_reports_every_blocker_and_cascade(lane):  # noqa: F811
    with ConnectionPool(DSN, min_size=1, max_size=4, open=True) as pool:
        world = build_world(lane, pool)
    try:
        with psycopg.connect(DSN) as conn:
            keys = sweep(conn)
            plain_error, blockers, before, after = probe(conn, world["a"], keys)
            # The transaction was rolled back: A and the schema are intact.
            assert conn.execute(
                "select 1 from auth.users where id=%s", (world["a"],)
            ).fetchone()
            assert {k.name for k in sweep(conn)} == {k.name for k in keys}
        per_key, per_table = outcomes(
            keys, before, after, world["b_markers"], world["a"], world["own"]
        )
        digest_keys = {
            key.columns: result
            for key, result in per_key.items()
            if key.table == "argus_private.invite_code_digests"
        }
        household_digests = digest_keys[("household_invitation_id",)]
        assert household_digests["pinned"] == 3
        assert household_digests["referencing"] == 0
        assert household_digests["removed"] == 0
        beta_digests = digest_keys[("beta_invitation_id",)]
        assert beta_digests["pinned"] == beta_digests["referencing"] == 0
        report = _report(plain_error, blockers, per_key, per_table)
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(report, encoding="utf-8")
        print(report)

        # Today a plain delete fails (decision 17's "What exists today").
        assert plain_error is not None and blockers
        blocking_keys = {
            (item.table, item.columns) for kind, item in blockers if kind == "fk"
        }
        assert all(item.blocks for kind, item in blockers if kind == "fk")
        assert HANDOFF_BLOCKERS <= blocking_keys, HANDOFF_BLOCKERS - blocking_keys
        assert CATALOG_ONLY_RESTRICT not in blocking_keys
        # The record-owner key is NO ACTION and initially deferred, so it fires
        # only because the probe runs `set constraints all immediate`. If that
        # line goes, the rolled-back delete never reaches the commit-time check.
        deferred = {
            item.name
            for kind, item in blockers
            if kind == "fk" and item.initially_deferred
        }
        assert (
            "financial_activity_original_record_revision" in deferred
        ), "no deferred key fired: the probe must run `set constraints all immediate`"
        kinds = {kind for kind, _ in blockers}
        # Beyond keys: the foreign-leg trigger and the active-household admin check.
        assert {"fk", "trigger", "check"} <= kinds
        triggers = {item[1] for kind, item in blockers if kind == "trigger"}
        assert "retain_foreign_activity" in triggers
        checks = {item[1] for kind, item in blockers if kind == "check"}
        assert "households_check" in checks
        # Every blocker leaves rows behind that Lane 6 must handle before the
        # auth delete, and some of them are rows B can see.
        assert all(
            per_key[item]["referencing"] for kind, item in blockers if kind == "fk"
        )
        assert any(per_key[item]["b_visible"] for kind, item in blockers if kind == "fk")
        # Cascades reach rows B can see: B's claims in plans A owned, the
        # allocations backing goals, and A's memberships in shared households.
        for table in (
            "public.financial_plan_links",
            "public.financial_goal_allocations",
            "public.household_members",
        ):
            assert per_table[table]["b_visible_removed"], table
    finally:
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "delete from public.feedback where user_id=%s or context->>'account_email' like %s",
                (world["a"], f"%{world['a']}%"),
            )


def test_deleting_a_guest_with_a_full_chat_and_research_graph():
    """Guests use the same command. Their tree includes same-owner RESTRICT keys."""
    with psycopg.connect(DSN, autocommit=True) as conn:
        graph = _seed_complete_expired_guest_graph(conn)
    guest = graph["user_id"]
    try:
        with psycopg.connect(DSN) as conn:
            keys = sweep(conn)
            plain_error, blockers, before, after = probe(conn, guest, keys)
        per_key, _ = outcomes(keys, before, after, set(), guest)
        exercised = {k.name: o for k, o in per_key.items() if o["referencing"]}
        # run_context_packets -> context_packets RESTRICT sits inside the
        # guest's own cascade and does not block; nor does anything else.
        assert plain_error is None and not blockers, blockers
        restrict = next(
            k
            for k in keys
            if k.table == "public.run_context_packets"
            and k.columns == ("context_packet_id",)
        )
        assert (
            exercised[restrict.name]["removed"] == exercised[restrict.name]["referencing"]
        )
        # Nothing keyed to the guest by foreign key is left, but the agent
        # checkpoints, keyed by conversation id as text, are not reached.
        with psycopg.connect(DSN) as conn:
            assert (
                conn.execute(
                    "select count(*) from public.checkpoints where thread_id=%s",
                    (graph["conversation_id"],),
                ).fetchone()[0]
                == 1
            )
    finally:
        with psycopg.connect(DSN, autocommit=True) as conn:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                conn.execute(
                    f"delete from public.{table} where thread_id=%s",
                    (graph["conversation_id"],),
                )
            conn.execute(
                "delete from public.cost_ledger_entries where user_id=%s", (guest,)
            )
            conn.execute("delete from public.route_receipts where user_id=%s", (guest,))
            conn.execute("delete from public.feedback where user_id=%s", (guest,))
            conn.execute("delete from auth.users where id=%s", (guest,))

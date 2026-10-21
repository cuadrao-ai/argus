"""Lane 6: the account deletion command end to end on real PostgreSQL.

Reuses the census world (A shares plans, groups, records and households with
B; C contributed to A's plan and left) and adds a departed binding A owns, a
plan nobody else is in, a note on a shared record, and Plaid and Gmail
credentials. The Admin API is a fake that runs SQL on auth.users, here only.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import psycopg
import pytest
from argus.domain.account_deletion.auth_admin import PLACEHOLDER_DOMAIN
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    AccountDeletionRejected,
    AccountDeletionService,
    subject_hash,
)
from argus.domain.household.planning import SharedPlanningService
from argus.domain.household.schemas import CreateHouseholdRequest
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.owner_scope import PERSONAL
from argus.observability.analytics_deletion import RecordingAnalyticsDeletion
from argus.observability.product_events import actor_hash_for_user
from psycopg_pool import ConnectionPool

from tests.account_deletion_census import sweep
from tests.household.financial_fixtures import DSN, NOW, account, key
from tests.household.financial_fixtures import command as household_command
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.household.shared_cleanup import cleanup
from tests.household.shared_plan_fixtures import money, request
from tests.household.test_shared_planning_departure import accept, invitation, leave
from tests.test_account_deletion_fk_census_postgres import (
    HANDOFF_BLOCKERS,
    _bill,
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
    _occurrence,
    _plan_as,
    build_world,
    probe,
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


class Crash(Exception):
    pass


BANNED: set[str] = set()


def gotrue_admin_create(user_id: str, email: str) -> int:
    """What GoTrue's admin create writes, in its order (supabase/auth,
    internal/api/admin.go, adminUserCreate, at ce9a8eee): app_metadata is set
    to {"provider": "email", "providers": ["email"]} and tx.Create(user)
    INSERTs the row with it, so no "placeholder" key yet; then, in the same
    transaction, UpdateAppMetaData merges the caller's app_metadata, Confirm
    sets email_confirmed_at and Ban sets banned_until (the test auth schema
    has no banned_until; BANNED records it). Returns how often the guest
    handoff trigger function ran in that transaction."""

    with psycopg.connect(DSN) as c, c.transaction():
        c.execute("set local track_functions = 'all'")
        c.execute(
            "insert into auth.users(id,email,is_anonymous,raw_app_meta_data,raw_user_meta_data)"
            " values (%s,%s,false,%s,'{}')",
            (user_id, email, json.dumps({"provider": "email", "providers": ["email"]})),
        )
        c.execute(
            "update auth.users set raw_app_meta_data = raw_app_meta_data || %s::jsonb"
            " where id=%s",
            (json.dumps({"placeholder": True}), user_id),
        )
        c.execute(
            "update auth.users set email_confirmed_at = now() where id=%s", (user_id,)
        )
        calls = c.execute(
            "select pg_stat_get_xact_function_calls("
            "'argus_private.bind_guest_signup_handoff'::regproc)"
        ).fetchone()[0]
    return int(calls or 0)


class SqlAuthAdmin:
    """Test-only stand-in for the Supabase Admin API."""

    def __init__(self, *, crash_on_delete=0, after_create=None):  # noqa: ANN001
        self.crash_on_delete = crash_on_delete
        self.after_create = after_create
        self.created: list[str] = []
        self.handoff_calls: list[int] = []
        self.creates = 0
        self.deleted: list[str] = []
        self.locked: list[str] = []

    def create_placeholder(self, *, user_id: str, email: str) -> None:
        assert email.startswith("exmiembro+") and email.endswith("@" + PLACEHOLDER_DOMAIN)
        self.handoff_calls.append(gotrue_admin_create(user_id, email))
        BANNED.add(user_id)
        self.creates += 1
        self.created.append(user_id)
        if self.after_create:
            self.after_create(user_id, email)

    def user_exists(self, user_id: str) -> bool:
        with psycopg.connect(DSN) as c:
            return bool(
                c.execute("select 1 from auth.users where id=%s", (user_id,)).fetchone()
            )

    def lock_user(self, user_id: str) -> None:
        # The test auth schema has no banned_until; the ban is recorded here.
        BANNED.add(user_id)
        self.locked.append(user_id)

    def delete_user(self, user_id: str) -> None:
        if self.crash_on_delete:
            self.crash_on_delete -= 1
            raise Crash("admin api down")
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("delete from auth.users where id=%s", (user_id,))
        self.deleted.append(user_id)


class FakeRevoker:
    def __init__(self, fail=(), unreadable=()):  # noqa: ANN001
        self.fail = set(fail)
        self.unreadable = set(unreadable)
        self.calls: list[tuple[str, str, bytes | None]] = []

    def revoke_for_deletion(self, *, source, connection_id, external_ref, envelope):  # noqa: ANN001
        self.calls.append((source, connection_id, envelope))
        if source in self.unreadable:
            return "unreadable"
        return "failed" if source in self.fail else "revoked"


class FailingAnalytics(RecordingAnalyticsDeletion):
    def delete_person(self, distinct_id):  # noqa: ANN001, ANN201
        self.calls.append({"distinct_ids": [distinct_id], "delete_events": True})
        return "failed"


def _locked(user_id: str) -> tuple[bool, bool]:
    """(the auth user is banned, the run holds the id so sessions are refused)."""
    with psycopg.connect(DSN) as c:
        banned = (
            user_id in BANNED
            and c.execute("select 1 from auth.users where id=%s", (user_id,)).fetchone()
        )
        held = c.execute(
            "select 1 from argus_private.account_deletion_runs where user_id=%s",
            (user_id,),
        ).fetchone()
    return bool(banned), bool(held)


def _service(  # noqa: ANN201
    lane,  # noqa: ANN001, F811
    admin,  # noqa: ANN001
    revoker=None,  # noqa: ANN001
    analytics=None,  # noqa: ANN001
    apple=None,  # noqa: ANN001
    *,
    box=None,  # noqa: ANN001
    allow_fake=True,  # noqa: ANN001
    clock=None,  # noqa: ANN001
    source_objects=None,  # noqa: ANN001
):
    return AccountDeletionService(
        households=lane[0]._repository,
        auth_admin=admin,
        revoker=revoker or FakeRevoker(),
        analytics=analytics or RecordingAnalyticsDeletion(),
        apple=apple,
        secret_box=box,
        # Tests are where the recording fake is explicitly the adapter.
        allow_fake_analytics=allow_fake,
        source_objects=source_objects,
        clock=clock or (lambda: NOW),
    )


def _run_id(user_id: str) -> str:
    with psycopg.connect(DSN) as c:
        return str(
            c.execute(
                "select id from argus_private.account_deletion_runs where subject_hash=%s",
                (subject_hash(user_id),),
            ).fetchone()[0]
        )


def _run(run_id: str) -> tuple:
    with psycopg.connect(DSN) as c:
        return c.execute(
            "select status, user_id, subject_hash, analytics_distinct_id, steps"
            " from argus_private.account_deletion_runs where id=%s",
            (run_id,),
        ).fetchone()


def _extras(lane, world):  # noqa: ANN001, F811
    """A departed binding A owns, a plan only A is in, a noted record, sources."""
    households, records, _ = lane
    a, b = world["a"], world["b"]
    plans = SharedPlanningService(households)
    h1 = world["households"][0]
    amid = households.get(user_id=a, household_id=h1).membership_id
    aa = world["aa"]
    s1 = dict(households=households, records=records, plans=plans, hid=h1, a=a, b=b)
    solo = _plan_as(s1, a, amid, "bill", [], [(amid, "100")], _bill(aa))

    # C comes back to H1; B's plan has both A and C paying, so once both are
    # deleted it shows "Former member 1" and "Former member 2" ("Exmiembro").
    c = world["c"]
    cmid = accept(s1, c, invitation(s1, a))
    with psycopg.connect(DSN) as conn:
        ba = str(
            conn.execute(
                "select id from public.financial_accounts where user_id=%s and type <> 'other_debt' order by created_at limit 1",
                (b,),
            ).fetchone()[0]
        )
    bmid = households.get(user_id=b, household_id=h1).membership_id
    pair = _plan_as(
        s1,
        b,
        bmid,
        "bill",
        [amid, cmid],
        [(bmid, "40"), (amid, "30"), (cmid, "30")],
        _bill(ba),
    )
    money(s1, a, pair, request("expense", aa, "3"), "bill_payment", _occurrence(pair))
    money(
        dict(s1, c=c),
        c,
        pair,
        request("expense", account(records, c), "4"),
        "bill_payment",
        _occurrence(pair),
    )

    h3 = household_command(
        households,
        a,
        "create",
        lambda: households.create(
            user_id=a, request=CreateHouseholdRequest(name="Third", display_name="Alice")
        ),
    ).household_id
    s3 = dict(s1, hid=h3)
    s3["amid"] = households.get(user_id=a, household_id=h3).membership_id
    s3["bmid"] = accept(s3, b, invitation(s3, a))
    departed = _plan_as(
        s3,
        a,
        s3["amid"],
        "bill",
        [s3["bmid"]],
        [(s3["amid"], "50"), (s3["bmid"], "50")],
        _bill(aa),
    )
    money(
        s3,
        a,
        departed,
        request("expense", aa, "7", note="regalo secreto"),
        "bill_payment",
        _occurrence(departed),
    )
    household_command(
        households,
        a,
        "transfer_admin",
        lambda: households.transfer_admin(
            user_id=a, household_id=h3, new_admin_user_id=b
        ),
        h3,
    )
    leave(s3, a)

    pool_conn = PostgresConnectionRepository(lane[0]._repository._pool)
    gmail = pool_conn.create(
        user_id=a,
        source="gmail",
        external_ref="mbx-" + key(),
        label="Gmail",
        now=NOW,
        secret=b"g",
        scope=PERSONAL,
    )
    return dict(solo=solo, pair=pair, departed=departed, h3=h3, gmail=gmail.id)


def _rows_holding(conn, needle):  # noqa: ANN001
    """Every table in public or argus_private with a row whose text holds needle."""
    found = []
    for schema, table in conn.execute(
        "select table_schema, table_name from information_schema.tables"
        " where table_schema in ('public','argus_private') and table_type='BASE TABLE'"
    ).fetchall():
        if conn.execute(
            f'select 1 from "{schema}"."{table}" t where t::text like %s limit 1',
            (f"%{needle}%",),
        ).fetchone():
            found.append(f"{schema}.{table}")
    return found


def _members_of(user_ids):  # noqa: ANN001
    with psycopg.connect(DSN) as c:
        return {
            str(r[0])
            for r in c.execute(
                "select id from public.household_members where user_id=any(%s::uuid[])",
                (list(user_ids),),
            ).fetchall()
        }


def _totals(snapshot, gone):  # noqa: ANN001
    """The money B sees per plan. Two things change exactly as on an ordinary
    leave (#773), not because of the deletion: the shared debt plan becomes a
    read-only archive, which stops its future schedule, and a departed
    member's goal savings stop counting as applied (the archive keeps
    last_applied_minor, which reads do not use yet). So A's applied amounts and
    schedule-derived remainders are not compared; every amount, date and
    purpose is, and so is everyone else's applied money, except goal savings:
    a goal's backing is the destination account's balance, and A's accounts
    and balances go with A, so savings into A's accounts can no longer show as
    backed (a known gap reported with Lane 6)."""
    keep = {}
    for plan in snapshot["plans"]:
        keep[(plan["ref"]["kind"], plan["ref"]["id"])] = dict(
            actual=plan["progress"]["actual_minor"],
            contributions=sorted(
                (
                    c["amount_minor"],
                    None
                    if (c.get("person") or {}).get("membership_id") in gone
                    or c["purpose"] == "goal_saving"
                    else c["applied_minor"],
                    c["date"],
                    c["purpose"],
                )
                for c in plan["contributions"]
            ),
        )
    return keep


def _names(value):  # noqa: ANN001
    if isinstance(value, dict):
        out = {value["display_name"]} if "display_name" in value else set()
        for v in value.values():
            out |= _names(v)
        return out
    if isinstance(value, list):
        return set().union(*(_names(v) for v in value)) if value else set()
    return set()


def _side_effect_free(placeholder, email):  # noqa: ANN001
    """Marcus: a placeholder create sends no email, records no signup or
    analytics event, and makes no profile and no beta admission."""
    with psycopg.connect(DSN) as c:
        assert set(_rows_holding(c, placeholder)) == {
            "argus_private.account_placeholders",
            "argus_private.account_deletion_placeholders",
        }, placeholder
        assert _rows_holding(c, email) == []


def _cleanup(world, placeholders, hids):  # noqa: ANN001
    ids = [world["a"], world["b"], world["c"], *placeholders]
    with psycopg.connect(DSN) as c, c.transaction():
        c.execute(
            "delete from public.household_deletion_events where household_id=any(%s::uuid[])",
            (hids,),
        )
        cleanup(c, ids, hids)
        c.execute(
            "delete from public.household_account_grants where household_id=any(%s::uuid[])",
            (hids,),
        )
        c.execute(
            "delete from public.household_invitations where household_id=any(%s::uuid[])",
            (hids,),
        )
        c.execute(
            "delete from public.household_command_receipts where household_id=any(%s::uuid[])",
            (hids,),
        )
        c.execute(
            "delete from public.household_members where household_id=any(%s::uuid[])",
            (hids,),
        )
        c.execute("delete from public.households where id=any(%s::uuid[])", (hids,))
        c.execute(
            "delete from public.feedback where user_id=any(%s::uuid[]) or context->>'account_email' like %s",
            (ids, f"%{world['a']}%"),
        )
        c.execute("delete from auth.users where id=any(%s::uuid[])", (placeholders,))
        c.execute(
            "delete from argus_private.account_placeholders where id=any(%s::uuid[])",
            (placeholders,),
        )
        for uid in (world["a"], world["c"]):
            c.execute(
                "delete from argus_private.account_deletion_runs where subject_hash=%s",
                (subject_hash(uid),),
            )


@pytest.fixture
def world(lane):  # noqa: F811
    with ConnectionPool(DSN, min_size=1, max_size=4, open=True) as pool:
        built = build_world(lane, pool)
    with psycopg.connect(DSN) as c:
        built["aa"] = str(
            c.execute(
                "select id from public.financial_accounts where user_id=%s and type <> 'other_debt' order by created_at limit 1",
                (built["a"],),
            ).fetchone()[0]
        )
    built.update(_extras(lane, built))
    built["placeholders"] = []
    try:
        yield built
    finally:
        _cleanup(built, built["placeholders"], built["households"] + [built["h3"]])


def test_deleting_a_sharing_person_keeps_everyone_elses_history(lane, world):  # noqa: F811
    a, b = world["a"], world["b"]
    plans = SharedPlanningService(lane[0])
    hids = world["households"] + [world["h3"]]
    with psycopg.connect(DSN) as conn:
        plain_error, blockers, _, _ = probe(conn, a, sweep(conn))
    assert plain_error is not None
    assert HANDOFF_BLOCKERS <= {(i.table, i.columns) for k, i in blockers if k == "fk"}
    gone = _members_of([a])
    before = {h: _totals(plans.snapshot(b, h), gone) for h in hids}
    with psycopg.connect(DSN) as conn:
        email = conn.execute("select email from auth.users where id=%s", (a,)).fetchone()[
            0
        ]

    admin = SqlAuthAdmin(after_create=_side_effect_free)
    revoker = FakeRevoker()
    analytics = RecordingAnalyticsDeletion()
    outcome = _service(lane, admin, revoker, analytics).delete_account(user_id=a)
    world["placeholders"] += admin.created

    assert outcome.status == "done", outcome
    # Marcus (3): one create per placeholder, each side-effect free (checked in
    # the hook), and at least two of them: H1, H2, H3 and A's shared groups.
    assert admin.creates == len(set(admin.created)) >= 3
    # B2: on GoTrue's real create path the guest handoff trigger never ran.
    assert admin.handoff_calls and set(admin.handoff_calls) == {0}
    # One placeholder per sharing scope: every plan of A's in one household
    # shares that household's placeholder.
    with psycopg.connect(DSN) as conn:
        per_household = conn.execute(
            """select b.household_id, count(distinct b.owner_user_id) filter (where b.owner_user_id = any(%s::uuid[])),
                      count(distinct m.user_id)
                 from public.household_members m
                 join public.household_plan_bindings b on b.household_id = m.household_id
                where m.user_id = any(%s::uuid[]) group by b.household_id""",
            (admin.created, admin.created),
        ).fetchall()
        assert per_household and all(row[2] == 1 for row in per_household), per_household
    assert sorted(admin.deleted) == sorted(
        [a, *[p for p in admin.created if p in admin.deleted[1:]]]
    )
    assert {c[0] for c in revoker.calls} == {"plaid", "gmail"}
    assert analytics.calls == [
        {"distinct_ids": [actor_hash_for_user(a)], "delete_events": True}
    ]

    gone = _members_of(admin.created)
    after = {h: _totals(plans.snapshot(b, h), gone) for h in hids}
    for h in hids:
        for ref, totals in before[h].items():
            if ref in after[h]:
                assert after[h][ref] == totals, (h, ref)
    h1 = world["households"][0]
    # The plan only A was in is gone; every other plan of A's in H1 is B's now.
    with psycopg.connect(DSN) as conn:
        assert not conn.execute(
            "select 1 from public.household_plan_bindings where definition_id=%s",
            (world["solo"]["ref"]["id"],),
        ).fetchone()
        live = conn.execute(
            "select kind, owner_user_id, departed_at from public.household_plan_bindings"
            " where household_id=%s and revoked_at is null and departed_at is null",
            (h1,),
        ).fetchall()
        assert live and all(str(row[1]) == b for row in live if row[0] != "debt")
        debt = conn.execute(
            """select b.owner_user_id, d.user_id, a.user_id
                 from public.household_plan_bindings b
                 join public.financial_debt_plans d on d.id = b.definition_id and d.user_id = b.owner_user_id
                 join public.financial_accounts a on a.id = d.debt_account_id
                where b.household_id=%s and b.kind='debt'""",
            (h1,),
        ).fetchone()
        # Lucas: the shared debt plan is a read-only archive; the plan and its
        # debt account both move to H1's placeholder.
        assert debt and len({str(x) for x in debt}) == 1 and str(debt[0]) in admin.created
        # Notes are gone from every kept copy.
        assert not conn.execute(
            "select 1 from public.financial_record_revisions where user_id=any(%s::uuid[]) and details ? 'note'",
            (admin.created,),
        ).fetchone()
        assert not conn.execute(
            "select 1 from public.financial_record_revisions where details::text like '%%regalo secreto%%'"
        ).fetchone()
        # Nothing anywhere still holds A's id or email.
        assert _rows_holding(conn, a) == []
        assert _rows_holding(conn, email) == []
        assert not conn.execute("select 1 from auth.users where id=%s", (a,)).fetchone()
        # Priya 7: a done run keeps no id and neither hash (both are unsalted
        # hashes of the user id), only outcomes and counts.
        status, user_id, subject, distinct, steps = _run(outcome.run_id)
        assert (status, user_id, subject, distinct) == ("done", None, None, None)
        assert _rows_holding(conn, subject_hash(a)) == []
        assert _rows_holding(conn, actor_hash_for_user(a)) == []
        assert steps["revocations"] == {"gmail": {"revoked": 1}, "plaid": {"revoked": 1}}
        assert not conn.execute(
            "select 1 from argus_private.account_deletion_placeholders where subject_hash=%s",
            (subject_hash(a),),
        ).fetchone()
        assert not conn.execute(
            "select 1 from argus_private.account_deletion_revocations where subject_hash=%s",
            (subject_hash(a),),
        ).fetchone()
        events = {
            row[0]
            for row in conn.execute(
                "select kind from public.household_deletion_events where household_id=any(%s::uuid[])",
                (hids,),
            ).fetchall()
        }
        assert {"member_deleted", "plan_handed_over"} <= events
    # The handed-over plans are B's to edit, and A shows as a former member
    # (B has no profile language, so English).
    snapshot = plans.snapshot(b, h1)
    owned = [p for p in snapshot["plans"] if p["is_owner"] and not p["read_only"]]
    assert len(owned) >= 4
    names = _names(snapshot)
    assert "Alice" not in names and any(
        n.startswith("Former member") for n in names
    ), names

    # C is deleted too: in the plan both of them were in, they are numbered.
    c_admin = SqlAuthAdmin(after_create=_side_effect_free)
    assert _service(lane, c_admin).delete_account(user_id=world["c"]).status == "done"
    world["placeholders"] += c_admin.created

    def pair_names() -> set[str]:
        pair = [
            p
            for p in plans.snapshot(b, h1)["plans"]
            if p["ref"]["id"] == world["pair"]["ref"]["id"]
        ][0]
        return {c["person"]["display_name"] for c in pair["contributions"]}

    assert pair_names() == {"Former member 1", "Former member 2"}
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(
            "insert into public.profiles(id,email,language)"
            " select id,email,'es-419' from auth.users where id=%s"
            " on conflict (id) do update set language='es-419'",
            (b,),
        )
    assert pair_names() == {"Exmiembro 1", "Exmiembro 2"}

    # Nothing links the person to the run any more, so a rerun finds no
    # account (the API answers it as done), and placeholders are refused.
    with pytest.raises(AccountDeletionRejected, match="unknown_user"):
        _service(lane, SqlAuthAdmin()).delete_account(user_id=a)
    with pytest.raises(AccountDeletionRejected):
        _service(lane, SqlAuthAdmin()).delete_account(user_id=admin.created[0])


def test_a_crash_between_placeholders_and_the_auth_delete_resumes(lane, world):  # noqa: F811
    a = world["a"]
    admin = SqlAuthAdmin(crash_on_delete=1)
    with pytest.raises(Crash):
        _service(lane, admin).delete_account(user_id=a)
    world["placeholders"] += admin.created
    with psycopg.connect(DSN) as conn:
        run = conn.execute(
            "select user_id, status from argus_private.account_deletion_runs where subject_hash=%s",
            (subject_hash(a),),
        ).fetchone()
        assert str(run[0]) == a and run[1] == "data_deleted"
        assert conn.execute("select 1 from auth.users where id=%s", (a,)).fetchone()
    resumed = SqlAuthAdmin()
    assert _service(lane, resumed).delete_account(user_id=a).status == "done"
    # No new placeholder on resume; the same ones are kept or cleared.
    assert resumed.creates == 0
    with psycopg.connect(DSN) as conn:
        assert not conn.execute("select 1 from auth.users where id=%s", (a,)).fetchone()
        assert _rows_holding(conn, a) == []


def test_a_failed_provider_revoke_holds_the_account_delete(lane, world):  # noqa: F811
    """Third parties go before the auth delete: while Gmail fails the run stays
    data_deleted, the account stays locked, and the auth user is kept."""
    a = world["a"]
    admin = SqlAuthAdmin()
    revoker = FakeRevoker(fail={"gmail"})
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, revoker).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert raised.value.pending == ["gmail"]
    # Plaid was still revoked on the same pass.
    assert {c[0] for c in revoker.calls} == {"plaid", "gmail"}
    assert admin.deleted == [] and admin.locked == [a]
    assert _locked(a) == (True, True)
    with psycopg.connect(DSN) as conn:
        rows = conn.execute(
            "select provider, status, secret_ciphertext is not null"
            " from argus_private.account_deletion_revocations"
            " where subject_hash=%s order by provider",
            (subject_hash(a),),
        ).fetchall()
        assert ("gmail", "pending", True) in rows
        assert all(r[1] == "revoked" and not r[2] for r in rows if r[0] == "plaid")
        status = conn.execute(
            "select status from argus_private.account_deletion_runs where subject_hash=%s",
            (subject_hash(a),),
        ).fetchone()[0]
        assert status == "data_deleted"
    retry = FakeRevoker()
    outcome = _service(lane, SqlAuthAdmin(), retry).delete_account(user_id=a)
    assert [c[0] for c in retry.calls] == ["gmail"]
    assert outcome.status == "done" and outcome.pending == []
    with psycopg.connect(DSN) as conn:
        assert not conn.execute("select 1 from auth.users where id=%s", (a,)).fetchone()
        assert _rows_holding(conn, a) == []


def _age(user_id: str) -> None:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "update argus_private.account_deletion_runs set updated_at = %s"
            " where subject_hash=%s",
            (NOW - timedelta(hours=1), subject_hash(user_id)),
        )


def test_failed_analytics_deletion_holds_the_account_delete(lane, world):  # noqa: F811
    a = world["a"]
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, analytics=FailingAnalytics()).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert raised.value.pending == ["analytics"]
    assert admin.deleted == [] and _locked(a) == (True, True)
    analytics = RecordingAnalyticsDeletion()
    assert (
        _service(lane, SqlAuthAdmin(), analytics=analytics)
        .delete_account(user_id=a)
        .status
        == "done"
    )
    assert len(analytics.calls) == 1


def test_the_sweep_resumes_idle_pending_runs(lane, world):  # noqa: F811
    a = world["a"]
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete):
        _service(lane, admin, FakeRevoker(fail={"gmail"})).delete_account(user_id=a)
    world["placeholders"] += admin.created

    def age() -> None:
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute(
                "update argus_private.account_deletion_runs set updated_at = %s"
                " where subject_hash=%s",
                (NOW - timedelta(hours=1), subject_hash(a)),
            )

    # A run a request touched just now is left to that request.
    failing = _service(lane, SqlAuthAdmin(), FakeRevoker(fail={"gmail"}))
    assert failing.resume_pending()["resumed"] == 0
    age()
    # Still failing: counted pending, the account stays locked.
    assert failing.resume_pending() == {
        "resumed": 1,
        "done": 0,
        "pending": 1,
        "failed": 0,
        "busy": 0,
    }
    assert _locked(a) == (True, True)
    age()
    run_id = _run_id(a)
    healthy = _service(lane, SqlAuthAdmin(), FakeRevoker())
    assert healthy.resume_pending() == {
        "resumed": 1,
        "done": 1,
        "pending": 0,
        "failed": 0,
        "busy": 0,
    }
    with psycopg.connect(DSN) as conn:
        assert not conn.execute("select 1 from auth.users where id=%s", (a,)).fetchone()
    assert _run(run_id)[:2] == ("done", None)


def test_sender_refs_rotate_to_a_distinct_value_per_row(lane, world):  # noqa: F811
    a = world["a"]
    with psycopg.connect(DSN) as conn:
        before = {
            str(i): (str(ref), origin)
            for i, ref, origin in conn.execute(
                "select id, sender_ref, inviter_origin_id from public.invite_referrals"
                " where sender_user_id=%s",
                (a,),
            ).fetchall()
        }
    assert len(before) >= 2
    admin = SqlAuthAdmin()
    _service(lane, admin).delete_account(user_id=a)
    world["placeholders"] += admin.created
    with psycopg.connect(DSN) as conn:
        after = {
            str(i): (str(ref), origin, sender)
            for i, ref, origin, sender in conn.execute(
                "select id, sender_ref, inviter_origin_id, sender_user_id"
                " from public.invite_referrals where id = any(%s::uuid[])",
                (list(before),),
            ).fetchall()
        }
    assert set(after) == set(before)
    refs = [ref for ref, _, _ in after.values()]
    assert len(set(refs)) == len(refs)
    old = {ref for ref, _ in before.values()}
    for row, (ref, origin, sender) in after.items():
        assert ref not in old and sender is None
        assert origin == before[row][1]


def test_definers_need_the_deletion_writer_and_copies_keep_history(lane, world):  # noqa: F811
    a = world["a"]
    with psycopg.connect(DSN) as conn:
        for sql in (
            "select argus_private.deletion_finish(%s, null)",
            "select argus_private.deletion_pass_on_archives(%s)",
        ):
            with pytest.raises(psycopg.Error, match="deletion"):
                conn.execute(sql, (a,))
            conn.rollback()
        before = conn.execute(
            """select r.revision, r.amount_minor, r.as_of, r.recorded_at, rec.created_at, rec.current_revision
                 from public.financial_record_revisions r
                 join public.financial_records rec on rec.id = r.record_id
                 join public.financial_activity_memberships m on m.record_id = rec.id
                 join public.financial_plan_links l on l.activity_id = m.activity_id
                where rec.user_id=%s and l.activity_owner_id=%s and l.binding_id is not null
                order by 1,2,3,4""",
            (a, a),
        ).fetchall()
    admin = SqlAuthAdmin()
    _service(lane, admin).delete_account(user_id=a)
    world["placeholders"] += admin.created
    with psycopg.connect(DSN) as conn:
        after = conn.execute(
            """select r.revision, r.amount_minor, r.as_of, r.recorded_at, rec.created_at, rec.current_revision
                 from public.financial_record_revisions r
                 join public.financial_records rec on rec.id = r.record_id
                 join public.financial_activity_memberships m on m.record_id = rec.id
                 join public.financial_plan_links l on l.activity_id = m.activity_id
                where rec.user_id=any(%s::uuid[]) and l.activity_owner_id=rec.user_id
                order by 1,2,3,4""",
            (admin.created,),
        ).fetchall()
    # The kept copies carry the original revision numbers and timestamps.
    assert before and set(before) <= set(after)


def test_rejects_bad_ids_and_unknown_people(lane):  # noqa: F811
    service = _service(lane, SqlAuthAdmin())
    for bad in ("", "not-a-uuid", str(uuid.uuid4())):
        with pytest.raises(AccountDeletionRejected):
            service.delete_account(user_id=bad)


def test_a_guest_is_deleted_by_the_same_command(lane):  # noqa: F811
    guest = str(uuid.uuid4())
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("insert into auth.users(id,is_anonymous) values (%s,true)", (guest,))
        c.execute("insert into public.profiles(id) values (%s)", (guest,))
        c.execute(
            "insert into public.conversations(user_id,title) values (%s,'Guest')",
            (guest,),
        )
    admin = SqlAuthAdmin()
    try:
        outcome = _service(lane, admin).delete_account(user_id=guest)
        assert outcome.status == "done" and admin.creates == 0
        with psycopg.connect(DSN) as c:
            assert not c.execute(
                "select 1 from auth.users where id=%s", (guest,)
            ).fetchone()
            assert _rows_holding(c, guest) == []
    finally:
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("delete from auth.users where id=%s", (guest,))


def test_duplicate_requests_reserve_one_placeholder_per_scope(lane, world):  # noqa: F811
    import threading

    a = world["a"]
    admin = SqlAuthAdmin()
    service = _service(lane, admin)
    run = service._claim(a, subject_hash(a))  # noqa: SLF001
    errors: list[BaseException] = []

    def reserve() -> None:
        try:
            service._reserve_placeholders(a, subject_hash(a))  # noqa: SLF001
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reserve) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    world["placeholders"] += admin.created
    assert errors == []
    with psycopg.connect(DSN) as c:
        rows = c.execute(
            "select scope_kind, scope_id, count(*) from argus_private.account_deletion_placeholders"
            " where subject_hash=%s group by 1, 2",
            (subject_hash(a),),
        ).fetchall()
    assert rows and all(n == 1 for _, _, n in rows)
    assert len(set(admin.created)) == len(rows)
    service._release(run["id"], run["claim"])  # noqa: SLF001
    # The run then finishes with the placeholders it reserved.
    assert service.delete_account(user_id=a).status == "done"

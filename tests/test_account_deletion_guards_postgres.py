"""Lane 6 on real PostgreSQL: the guards from the #799 review. Placeholder
sign-ups, locked owner columns, concurrent passes, late writes and an activity
two households claim, over the same world as test_account_deletion_postgres.py."""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest
from argus.domain.account_deletion.auth_admin import PLACEHOLDER_DOMAIN
from argus.domain.account_deletion.service import (
    AccountDeletionIncomplete,
    subject_hash,
)
from argus.domain.household.access import require_edit, resolve
from argus.domain.household.errors import HouseholdNotFound as HouseholdUnavailable
from argus.domain.household.financial import HouseholdFinancialService
from argus.observability.analytics_deletion import RecordingAnalyticsDeletion

from tests.household.financial_fixtures import DSN
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
)
from tests.test_account_deletion_postgres import (
    FailingAnalytics,
    FakeRevoker,
    SqlAuthAdmin,
    _age,
    _run,
    _run_id,
    _service,
    gotrue_admin_create,
    world,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


def test_auth_user_trigger_conditions_need_no_private_schema() -> None:
    """GoTrue writes auth.users as supabase_auth_admin, which can't reach
    argus_private: no WHEN clause on any auth.users trigger may call into it.
    Every trigger that acts on a new or changed user skips placeholders by
    their email too, since GoTrue sets app_metadata only after the INSERT."""
    with psycopg.connect(DSN) as c:
        rows = c.execute(
            "select tgname, pg_get_triggerdef(oid) from pg_trigger"
            " where tgrelid = 'auth.users'::regclass and not tgisinternal"
        ).fetchall()
    assert {name for name, _ in rows} == {
        "bind_guest_signup_handoff",
        "finalize_linked_guest_identity",
        "refuse_placeholder_email",
        "business_auth_retention_guard",
        "business_fiscal_actor_retained",
    }
    for name, definition in rows:
        if name in {"business_auth_retention_guard", "business_fiscal_actor_retained"}:
            assert "BEFORE DELETE" in definition and " WHEN " not in definition
            with psycopg.connect(DSN) as c:
                assert c.execute(
                    "select prosecdef from pg_proc where oid=%s::regprocedure",
                    (f"argus_private.{name}()",),
                ).fetchone() == (True,)
            continue
        condition = definition.split(" WHEN ", 1)[1].split(" EXECUTE ", 1)[0]
        assert "argus_private" not in condition, name
        assert "cuadrao.invalid" in condition, name
        if name != "refuse_placeholder_email":
            assert "placeholder" in condition, name


def test_the_placeholder_domain_is_refused_to_everyone_else() -> None:
    """B2: a public sign-up (or an email change) at the placeholder domain is
    refused; a registered placeholder created GoTrue's way is not, and the
    guest handoff trigger never runs for it."""
    stranger = str(uuid.uuid4())
    with psycopg.connect(DSN) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "insert into auth.users(id,email,raw_app_meta_data) values (%s,%s,%s)",
                (stranger, f"exmiembro+{uuid.uuid4()}@{PLACEHOLDER_DOMAIN}", "{}"),
            )
        c.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(
                "insert into auth.users(id,email) values (%s,%s)",
                (stranger, f"Someone@{PLACEHOLDER_DOMAIN.upper()}"),
            )
        c.rollback()
    placeholder = str(uuid.uuid4())
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "insert into argus_private.account_placeholders(id) values (%s)",
            (placeholder,),
        )
        c.execute(
            "insert into auth.users(id,email) values (%s,'person@example.test')",
            (stranger,),
        )
    try:
        assert (
            gotrue_admin_create(
                placeholder, f"exmiembro+{uuid.uuid4()}@{PLACEHOLDER_DOMAIN}"
            )
            == 0
        )
        with psycopg.connect(DSN) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(
                    "update auth.users set email=%s where id=%s",
                    (f"exmiembro+x@{PLACEHOLDER_DOMAIN}", stranger),
                )
    finally:
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute(
                "delete from auth.users where id = any(%s::uuid[])",
                ([stranger, placeholder],),
            )
            c.execute(
                "delete from argus_private.account_placeholders where id=%s",
                (placeholder,),
            )


def test_locked_owner_columns_move_only_inside_the_deletion_writer(lane, world):  # noqa: F811
    """S1/S2: an owner column on locked history changes only inside the
    deletion writer (the GUC and current_user postgres). Outside it the update
    is refused (42501): with no GUC, and from a service_role or authenticated
    session that sets the GUC. The writers themselves refuse both roles."""
    a, b = world["a"], world["b"]
    tables = {
        "financial_record_revisions": "user_id",
        "household_plan_archived_claims": "activity_owner_id",
        "household_plan_archived_activities": "activity_owner_id",
        "financial_goal_allocation_revisions": "account_owner_id",
    }
    roles = ("service_role", "authenticated")
    forced = [
        [
            f"set local role {role}",
            "select set_config('argus.locked_history_writer', 'deletion', true)",
        ]
        for role in roles
    ]
    setups = ([], *forced)
    with psycopg.connect(DSN) as c:
        for table, column in tables.items():
            held = c.execute(
                f"select count(*) from public.{table} where {column}=%s", (a,)
            ).fetchone()[0]
            assert held, table
            for setup in setups:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with c.transaction():
                        for line in setup:
                            c.execute(line)
                        c.execute(
                            f"update public.{table} set {column}=%s where {column}=%s",
                            (b, a),
                        )
        for setup in forced:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with c.transaction():
                    for line in setup:
                        c.execute(line)
                    c.execute("select argus_private.deletion_finish(%s, null)", (a,))


class SlowRevoker(FakeRevoker):
    """Holds each revoke long enough for a second pass to collide."""

    def revoke_for_deletion(self, **kwargs):  # noqa: ANN003, ANN201
        import time

        time.sleep(0.4)
        return super().revoke_for_deletion(**kwargs)


def _together(*calls):  # noqa: ANN002, ANN202
    import threading

    results: list[object] = [None] * len(calls)
    barrier = threading.Barrier(len(calls))

    def go(i, call):  # noqa: ANN001
        barrier.wait()
        try:
            results[i] = call()
        except BaseException as exc:  # noqa: BLE001
            results[i] = exc

    threads = [threading.Thread(target=go, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_two_first_requests_open_one_run_and_revoke_once(lane, world):  # noqa: F811
    """Priya 3 / Marcus S3: two first POSTs at once open one run; the second
    finds it claimed (in_progress) and every provider is called once."""
    a = world["a"]
    revoker = SlowRevoker()
    analytics = RecordingAnalyticsDeletion()
    admins = [SqlAuthAdmin(), SqlAuthAdmin()]
    results = _together(
        *[
            lambda admin=admin: _service(lane, admin, revoker, analytics).delete_account(
                user_id=a
            )
            for admin in admins
        ]
    )
    world["placeholders"] += admins[0].created + admins[1].created
    done = [r for r in results if getattr(r, "status", None) == "done"]
    busy = [
        r
        for r in results
        if isinstance(r, AccountDeletionIncomplete) and r.reason == "in_progress"
    ]
    assert len(done) == 1 and len(busy) == 1, results
    assert sorted(c[0] for c in revoker.calls) == ["gmail", "plaid"]
    assert len(analytics.calls) == 1
    assert admins[0].deleted.count(a) + admins[1].deleted.count(a) == 1


def test_two_sweeps_at_once_resume_a_run_once(lane, world):  # noqa: F811
    a = world["a"]
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete):
        _service(lane, admin, FakeRevoker(fail={"gmail"})).delete_account(user_id=a)
    world["placeholders"] += admin.created
    _age(a)
    revoker = SlowRevoker()
    analytics = RecordingAnalyticsDeletion()
    sweeps = [_service(lane, SqlAuthAdmin(), revoker, analytics) for _ in range(2)]
    results = _together(*[s.resume_pending for s in sweeps])
    assert all(isinstance(r, dict) for r in results), results
    assert sum(r["done"] for r in results) == 1
    assert sum(r["pending"] + r["failed"] for r in results) == 0
    assert [c[0] for c in revoker.calls] == ["gmail"]
    # PostHog was done on the first pass; neither sweep repeats it.
    assert analytics.calls == []


def test_a_plan_edit_after_the_data_step_still_finishes(lane, world):  # noqa: F811
    """Priya 4: a write already in flight commits after the data step and
    holds the person through a RESTRICT key. The run scrubs it right before
    the Admin API delete instead of failing there."""
    a = world["a"]
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete):
        _service(lane, admin, analytics=FailingAnalytics()).delete_account(user_id=a)
    world["placeholders"] += admin.created
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "insert into public.financial_budgets(id,user_id,body) values (%s,%s,%s)",
            (str(uuid.uuid4()), a, json.dumps({"version": 1})),
        )
        assert c.execute(
            "select argus_private.deletion_auth_blockers(%s)", (a,)
        ).fetchall() == [("public.financial_plan_definition_revisions.owner_id",)]
    run_id = _run_id(a)
    outcome = _service(lane, SqlAuthAdmin()).delete_account(user_id=a)
    assert outcome.status == "done"
    assert _run(run_id)[0] == "done"
    with psycopg.connect(DSN) as c:
        assert not c.execute("select 1 from auth.users where id=%s", (a,)).fetchone()


@pytest.mark.parametrize("older", ["h2", "h1"])
def test_an_activity_two_households_pin_goes_with_the_oldest_claim(lane, world, older):  # noqa: F811
    """Decision c (Lucas, Oct 3): A's activity is claimed in H2's plan (A
    left H2, so that claim is archived) and also, released, in an H1 plan.
    The household whose claim is oldest (claim created_at, then claim id)
    gets it under its placeholder; the other household's claim stays a
    read-only reference that still resolves, and the run counts them. Nobody
    in the losing household can edit the activity through that reference."""
    a = world["a"]
    h1, h2 = world["households"][0], world["households"][1]
    with psycopg.connect(DSN, autocommit=True) as c:
        archived = c.execute(
            """select c.binding_id, c.claim_id, c.activity_id, c.activity_revision
                 from public.household_plan_archived_claims c
                 join public.household_plan_bindings b on b.id = c.binding_id
                where b.household_id=%s and c.activity_owner_id=%s limit 1""",
            (h2, a),
        ).fetchone()
        assert archived, "the world pins one of A's activities in H2"
        link = c.execute(
            """select l.user_id, l.binding_id, l.contributor_membership_id, l.purpose,
                      l.expectation_id, l.snapshot, l.attribution
                 from public.financial_plan_links l
                 join public.household_plan_bindings b on b.id = l.binding_id
                where b.household_id=%s and l.activity_owner_id=%s
                  and l.expectation_id is not null
                limit 1""",
            (h1, a),
        ).fetchone()
        assert link, "A has a claim in an H1 bill plan"
        claim = str(uuid.uuid4())
        shift = "1 day" if older == "h2" else "-1 day"
        c.execute(
            """insert into public.financial_plan_links
                 (user_id, claim_id, binding_id, contributor_membership_id, purpose,
                  expectation_id, snapshot, attribution, activity_owner_id,
                  activity_id, activity_revision, released_at, created_at)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now() + %s::interval)""",
            (
                link[0],
                claim,
                link[1],
                link[2],
                link[3],
                link[4],
                json.dumps(link[5]),
                json.dumps(link[6]),
                a,
                archived[2],
                archived[3],
                shift,
            ),
        )
    admin = SqlAuthAdmin()
    outcome = _service(lane, admin).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert outcome.counts["cross_scope_references"] >= 1
    winner, loser = (h2, h1) if older == "h2" else (h1, h2)
    with psycopg.connect(DSN) as c:
        owner = c.execute(
            "select user_id from public.financial_activity_groups where id=%s",
            (archived[2],),
        ).fetchone()[0]
        member = (
            "select 1 from public.household_members where household_id=%s and user_id=%s"
        )
        assert c.execute(member, (winner, owner)).fetchone()
        assert not c.execute(member, (loser, owner)).fetchone()
        # Both claims resolve to that same activity, under the winner's
        # placeholder; the loser's is a read-only reference.
        assert (
            c.execute(
                "select activity_owner_id from public.financial_plan_links where claim_id=%s",
                (claim,),
            ).fetchone()[0]
            == owner
        )
        assert (
            c.execute(
                "select activity_owner_id from public.household_plan_archived_claims"
                " where binding_id=%s and claim_id=%s",
                archived[:2],
            ).fetchone()[0]
            == owner
        )
        legs = {
            str(r[0])
            for r in c.execute(
                "select distinct r.account_id from public.financial_activity_memberships m"
                " join public.financial_records r on r.id = m.record_id"
                " where m.activity_id=%s",
                (archived[2],),
            ).fetchall()
        }
        loser_members = [
            str(r[0])
            for r in c.execute(
                "select user_id from public.household_members"
                " where household_id=%s and left_at is null",
                (loser,),
            ).fetchall()
        ]
        # Marcus re-check N3: the reference is read-only. The losing household
        # holds no grant on the activity's accounts, so no member there can
        # edit it through the household money path.
        assert not c.execute(
            "select 1 from public.household_account_grants where household_id=%s"
            " and account_id = any(%s::uuid[]) and revoked_at is null",
            (loser, list(legs)),
        ).fetchone()
    assert legs and loser_members
    money = HouseholdFinancialService(lane[0])
    for member in loser_members:
        with money.households.transaction(member, loser) as (c, h, m):
            scope = resolve(c, member, h, m)
            editable = {
                aid for aid, a in scope.accounts.items() if a.permission == "edit"
            }
            assert not legs & editable
            with pytest.raises(HouseholdUnavailable):
                require_edit(scope, legs)


def _take_claim(user_id: str, *, release: bool = False) -> None:
    """Another pass takes the run's claim (or lets it go)."""
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "update argus_private.account_deletion_runs"
            " set claim_id = case when %s then null else gen_random_uuid() end,"
            "     claimed_until = case when %s then null else now() + interval '1 hour' end"
            " where subject_hash = %s",
            (release, release, subject_hash(user_id)),
        )


class ClaimThief(FakeRevoker):
    """The claim lapses during the provider calls and another pass takes it."""

    def __init__(self, user_id: str) -> None:
        super().__init__()
        self.user_id = user_id

    def revoke_for_deletion(self, **kwargs):  # noqa: ANN003, ANN201
        _take_claim(self.user_id)
        return super().revoke_for_deletion(**kwargs)


class LateThief(SqlAuthAdmin):
    """The claim is taken while the account delete is in flight."""

    def __init__(self, user_id: str) -> None:
        super().__init__()
        self.user_id = user_id

    def delete_user(self, user_id: str) -> None:
        if user_id == self.user_id:
            _take_claim(user_id)
        super().delete_user(user_id)


def test_a_pass_that_lost_its_claim_never_finishes_the_run(lane, world):  # noqa: F811
    """Marcus re-check N1: the claim is renewed before the account delete, and
    the final update is fenced on it. A pass whose claim was taken stops
    before deleting the account; one that loses it during the delete leaves
    the run to the pass that holds it."""
    a = world["a"]
    admin = SqlAuthAdmin()
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, admin, ClaimThief(a)).delete_account(user_id=a)
    world["placeholders"] += admin.created
    assert raised.value.reason == "in_progress"
    assert a not in admin.deleted
    run_id = _run_id(a)
    assert _run(run_id)[0] == "data_deleted"
    _take_claim(a, release=True)
    late = LateThief(a)
    with pytest.raises(AccountDeletionIncomplete) as raised:
        _service(lane, late, FakeRevoker()).delete_account(user_id=a)
    assert raised.value.reason == "in_progress"
    assert _run(run_id)[0] == "data_deleted"
    _take_claim(a, release=True)
    outcome = _service(lane, SqlAuthAdmin(), FakeRevoker()).delete_account(user_id=a)
    assert outcome.status == "done"
    assert _run(run_id)[0] == "done"

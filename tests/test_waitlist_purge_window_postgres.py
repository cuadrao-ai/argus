"""Whole-row waitlist retention against an explicitly disposable PostgreSQL DB."""

from __future__ import annotations

import hashlib
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL is not configured")
TABLE = "public.cuadrao_early_access_signups"


@pytest.fixture()
def db():
    with psycopg.connect(DSN) as connection:
        connection.execute(f"delete from {TABLE}")
        connection.execute("set local timezone = 'UTC'")
        connection.execute(
            "select set_config('cuadrao.waitlist_retention_months', '', true)"
        )
        yield connection
        connection.rollback()


def signup(db, age: str, *, confirmed=True, personal=True, notified=False):
    email = f"{uuid.uuid4().hex}@example.test"
    digest = hashlib.sha256(email.encode()).hexdigest()
    capability = uuid.uuid4().hex + uuid.uuid4().hex
    db.execute(
        f"""insert into {TABLE}
        (email_digest,email,language,consent_version,created_at,confirmed_at,
         privacy_policy_version,verification_id,wish,notified_at)
        values (%s,%s,'es','test',now() - %s::interval,
                case when %s then now() else null end,%s,%s,'Keep my answers',
                case when %s then now() else null end)""",
        (
            digest,
            email,
            age,
            confirmed,
            "test" if personal else None,
            capability,
            notified,
        ),
    )
    return digest, capability


def exists(db, digest):
    return db.execute(
        f"select exists(select 1 from {TABLE} where email_digest=%s)", (digest,)
    ).fetchone()[0]


def purge(db, limit=100):
    return db.execute("select public.cuadrao_waitlist_purge(%s)", (limit,)).fetchone()[0]


def invited(db, capability):
    return db.execute(
        "select public.cuadrao_waitlist_invited(%s)", (capability,)
    ).fetchone()[0]


def test_default_window_deletes_at_twelve_calendar_months(db):
    before, _ = signup(db, "12 months - 4 days")
    boundary, _ = signup(db, "12 months")
    older, _ = signup(db, "13 months")
    assert purge(db) == 2
    assert exists(db, before)
    assert not exists(db, boundary)
    assert not exists(db, older)
    assert purge(db) == 0


@pytest.mark.parametrize("months", [2, 6, 18])
def test_configured_window_uses_signup_time_and_calendar_months(db, months):
    db.execute(
        "select set_config('cuadrao.waitlist_retention_months', %s, true)",
        (str(months),),
    )
    before, _ = signup(db, f"{months} months - 4 days")
    boundary, _ = signup(db, f"{months} months")
    assert purge(db) == 1
    assert exists(db, before)
    assert not exists(db, boundary)


@pytest.mark.parametrize("value", ["0", "-1", "121", "1.5", "forever", "2147483648"])
def test_invalid_window_fails_before_deleting_any_row(db, value):
    digest, _ = signup(db, "13 months")
    db.execute(
        "select set_config('cuadrao.waitlist_retention_months', %s, true)", (value,)
    )
    with db.transaction():
        with pytest.raises(psycopg.Error):
            with db.transaction():
                purge(db)
    assert exists(db, digest)


def test_seven_day_unconfirmed_rule_and_confirmation_stay_unchanged(db):
    before, _ = signup(db, "7 days - 1 second", confirmed=False)
    boundary, _ = signup(db, "7 days", confirmed=False)
    confirmed, _ = signup(db, "7 days")
    claimed, _ = signup(db, "1 day", notified=True)
    assert purge(db) == 1
    assert exists(db, before)
    assert not exists(db, boundary)
    assert exists(db, confirmed)
    assert exists(db, claimed)


def test_legacy_retention_and_removal_records_stay_outside_personal_purge(db):
    legacy, capability = signup(db, "3 years", personal=False)
    removed, _ = signup(db, "3 years", personal=False)
    db.execute(
        f"update {TABLE} set email=null,removed_at=now() where email_digest=%s",
        (removed,),
    )
    assert purge(db) == 0
    assert invited(db, capability) == 0
    assert exists(db, legacy)
    assert exists(db, removed)


def test_request_deletes_email_answers_and_digest_and_can_repeat(db):
    digest, capability = signup(db, "1 day")
    db.execute("select public.cuadrao_waitlist_leave(%s)", (capability,))
    assert not exists(db, digest)
    db.execute("select public.cuadrao_waitlist_leave(%s)", (capability,))
    assert not exists(db, digest)


def test_confirmed_invite_completion_deletes_only_the_exact_signup(db):
    digest, capability = signup(db, "1 day")
    email = db.execute(
        f"select email from {TABLE} where email_digest=%s", (digest,)
    ).fetchone()[0]
    other, _ = signup(db, "1 day")
    assert invited(db, capability) == 1
    assert not exists(db, digest)
    assert exists(db, other)
    assert invited(db, capability) == 0
    db.execute(
        f"""insert into {TABLE}
        (email_digest,email,language,consent_version,privacy_policy_version,verification_id)
        values (%s,%s,'es','test','test',%s)""",
        (digest, email, uuid.uuid4().hex + uuid.uuid4().hex),
    )
    assert invited(db, capability) == 0
    assert exists(db, digest)


def test_invite_completion_does_not_treat_an_unconfirmed_signup_as_invited(db):
    digest, capability = signup(db, "1 day", confirmed=False)
    assert invited(db, capability) == 0
    assert exists(db, digest)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_public_roles_cannot_purge_or_complete_invites(db, role):
    for function in ["cuadrao_waitlist_purge(integer)", "cuadrao_waitlist_invited(text)"]:
        assert not db.execute(
            "select has_function_privilege(%s,%s,'execute')", (role, f"public.{function}")
        ).fetchone()[0]
    assert db.execute(
        "select has_function_privilege('service_role',"
        "'public.cuadrao_waitlist_invited(text)','execute')"
    ).fetchone()[0]


@pytest.mark.parametrize("nested_loop", [False, True], ids=["default", "nested-loop"])
@pytest.mark.parametrize("requested,expected", [(1, 1), (80, 80), (1000, 100)])
def test_purge_keeps_the_requested_batch_and_hundred_row_cap(
    db, nested_loop, requested, expected
):
    if nested_loop:
        db.execute("set local enable_hashjoin = off")
        db.execute("set local enable_mergejoin = off")
    for _ in range(160):
        signup(db, "13 months")
    assert purge(db, requested) == expected
    assert db.execute(f"select count(*) from {TABLE}").fetchone()[0] == 160 - expected


@pytest.mark.parametrize("nested_loop", [False, True], ids=["default", "nested-loop"])
def test_purge_workers_each_take_one_bounded_unlocked_batch(db, nested_loop):
    with psycopg.connect(DSN, autocommit=True) as owner:
        digests = [signup(owner, "13 months")[0] for _ in range(160)]
        try:
            with psycopg.connect(DSN) as other:
                for worker in (db, other):
                    worker.execute("set local statement_timeout = '5s'")
                    if nested_loop:
                        worker.execute("set local enable_hashjoin = off")
                        worker.execute("set local enable_mergejoin = off")
                assert purge(db, 80) == 80
                assert purge(other, 80) == 80
                assert purge(db, 80) == 0
        finally:
            db.rollback()
            owner.execute(f"delete from {TABLE} where email_digest = any(%s)", (digests,))


def test_purge_skips_a_signup_locked_by_another_worker(db):
    with psycopg.connect(DSN, autocommit=True) as owner:
        digest, _ = signup(owner, "13 months")
        try:
            with psycopg.connect(DSN) as locker:
                locker.execute(
                    f"select 1 from {TABLE} where email_digest=%s for update", (digest,)
                )
                assert purge(db) == 0
                assert exists(db, digest)
            assert purge(db) == 1
            assert not exists(db, digest)
        finally:
            db.rollback()
            owner.execute(f"delete from {TABLE} where email_digest=%s", (digest,))

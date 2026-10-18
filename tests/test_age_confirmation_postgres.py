import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest


@pytest.fixture
def db():
    dsn = os.getenv("ARGUS_AGE_TEST_DATABASE_URL") or os.getenv(
        "ARGUS_DISPOSABLE_DATABASE_URL"
    )
    if not dsn:
        pytest.skip("Set ARGUS_AGE_TEST_DATABASE_URL to a disposable candidate database")
    with psycopg.connect(dsn) as connection:
        if os.getenv("ARGUS_AGE_TEST_DATABASE_URL"):
            assert connection.info.dbname == "age_confirmation_testdb"
        yield connection
        connection.rollback()


def _profile(db, instant=None):
    user_id = uuid4()
    email = f"{user_id}@example.com"
    db.execute(
        "insert into auth.users (id,email,is_anonymous) values (%s,%s,false)",
        (user_id, email),
    )
    db.execute(
        "insert into public.profiles (id,email,age_confirmed_at) values (%s,%s,%s)",
        (user_id, email, instant),
    )
    return user_id


def test_postgres_preserves_first_confirmation_and_deletes_it_with_the_profile(db):
    instant = datetime.now(timezone.utc) - timedelta(days=1)
    user_id = _profile(db, instant)
    db.execute(
        "update public.profiles set age_confirmed_at=%s where id=%s", (instant, user_id)
    )
    for other in [None, instant + timedelta(hours=1)]:
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                "update public.profiles set age_confirmed_at=%s where id=%s",
                (other, user_id),
            )
    assert (
        db.execute(
            "select age_confirmed_at from public.profiles where id=%s", (user_id,)
        ).fetchone()[0]
        == instant
    )
    db.execute("delete from auth.users where id=%s", (user_id,))
    assert (
        db.execute(
            "select age_confirmed_at from public.profiles where id=%s", (user_id,)
        ).fetchone()
        is None
    )


@pytest.mark.parametrize(
    "instant", [datetime.now(timezone.utc) + timedelta(days=1), "infinity"]
)
def test_postgres_refuses_future_and_nonfinite_confirmation(db, instant):
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _profile(db, instant)


def test_postgres_existing_profile_stays_unconfirmed_and_direct_client_cannot_set_it(db):
    user_id = _profile(db)
    assert (
        db.execute(
            "select age_confirmed_at from public.profiles where id=%s", (user_id,)
        ).fetchone()[0]
        is None
    )
    db.execute(
        "select set_config('request.jwt.claims', %s, true)",
        ('{"sub":"' + str(user_id) + '","role":"authenticated","is_anonymous":false}',),
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
        db.execute("set local role authenticated")
        db.execute(
            "update public.profiles set age_confirmed_at=now() where id=%s", (user_id,)
        )
    db.execute(
        "update public.profiles set age_confirmed_at=now() where id=%s", (user_id,)
    )
    assert db.execute(
        "select age_confirmed_at is not null from public.profiles where id=%s", (user_id,)
    ).fetchone()[0]

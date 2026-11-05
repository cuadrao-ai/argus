from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest
from faker import Faker
from psycopg_pool import ConnectionPool

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="isolated Postgres required")
fake = Faker()


@pytest.fixture
def apple_profile():
    user_id = str(uuid4())
    subject = str(uuid4())
    email = fake.email(domain="example.test")
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "insert into auth.users (id,email) values (%s,%s)",
            (user_id, email),
        )
        connection.execute(
            "insert into auth.identities (id,user_id,provider,provider_id,identity_data) "
            "values (%s,%s,'apple',%s,%s::jsonb)",
            (str(uuid4()), user_id, subject, json.dumps({"sub": subject})),
        )
        connection.execute(
            "insert into public.profiles (id,email) values (%s,%s) "
            "on conflict (id) do nothing",
            (user_id, email),
        )
    yield user_id
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "delete from argus_private.account_deletion_runs where user_id=%s", (user_id,)
        )
        connection.execute("delete from auth.users where id=%s", (user_id,))


@pytest.fixture
def pool():
    with ConnectionPool(
        DSN,
        min_size=0,
        max_size=4,
        kwargs={"application_name": f"apple-name-test-{uuid4()}"},
    ) as pool:
        yield pool


def test_initializer_is_idempotent_and_never_sets_preferred_name(apple_profile, pool):
    from argus.domain.apple_sign_in.name import initialize_apple_display_name

    name = fake.name()
    first = initialize_apple_display_name(pool, user_id=apple_profile, display_name=name)
    retry = initialize_apple_display_name(
        pool, user_id=apple_profile, display_name=fake.name()
    )
    assert first["display_name"] == retry["display_name"] == name
    assert first["preferred_name"] is retry["preferred_name"] is None


@pytest.mark.parametrize(
    "column,value", [("display_name", None), ("preferred_name", None)]
)
def test_explicit_null_clear_prevents_later_seed(apple_profile, pool, column, value):
    from argus.domain.apple_sign_in.name import initialize_apple_display_name

    with psycopg.connect(DSN) as connection:
        connection.execute(
            f"update public.profiles set {column}=%s where id=%s", (value, apple_profile)
        )
    row = initialize_apple_display_name(
        pool, user_id=apple_profile, display_name=fake.name()
    )
    assert row["display_name"] is None
    assert row["preferred_name"] is None


@pytest.mark.parametrize(
    "column,value",
    [
        ("display_name", None),
        ("display_name", "Chosen name"),
        ("preferred_name", None),
        ("preferred_name", "Chosen name"),
        ("locale", "es-419"),
        ("currency_override", "EUR"),
    ],
)
@pytest.mark.parametrize("seed_first", [False, True])
def test_concurrent_explicit_edit_always_wins(
    apple_profile, pool, column, value, seed_first
):
    from argus.domain.apple_sign_in.name import initialize_apple_display_name

    written = Event()
    release = Event()

    class HeldPool:
        @contextmanager
        def connection(self):
            with pool.connection() as connection, connection.transaction():
                yield connection
                written.set()
                assert release.wait(5)

    def seed(held=False):
        return initialize_apple_display_name(
            HeldPool() if held else pool,
            user_id=apple_profile,
            display_name=fake.name(),
        )

    def edit(held=False):
        with psycopg.connect(
            DSN, application_name=pool.kwargs["application_name"]
        ) as connection:
            connection.execute("set local lock_timeout='4s'")
            reopen = (
                ",name_initialization_closed=false"
                if column in {"display_name", "preferred_name"}
                else ""
            )
            connection.execute(
                f"update public.profiles set {column}=%s{reopen} where id=%s",
                (value, apple_profile),
            )
            if held:
                written.set()
                assert release.wait(5)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(seed if seed_first else edit, True)
        try:
            assert written.wait(5)
            second = executor.submit(edit if seed_first else seed)
            deadline = monotonic() + 3
            with psycopg.connect(DSN, autocommit=True) as observer:
                while monotonic() < deadline:
                    waiting = observer.execute(
                        "select count(*) from pg_stat_activity where application_name=%s "
                        "and cardinality(pg_blocking_pids(pid)) > 0",
                        (pool.kwargs["application_name"],),
                    ).fetchone()[0]
                    if waiting:
                        break
                    sleep(0.01)
                assert waiting == 1
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            f"select {column},name_initialization_closed,display_name from public.profiles where id=%s",
            (apple_profile,),
        ).fetchone()
    assert row[:2] == (value, True)
    if column in {"locale", "currency_override"}:
        assert row[2] is not None


@pytest.mark.parametrize(
    "column,value", [("locale", "es-419"), ("currency_override", "EUR")]
)
def test_unrelated_edit_keeps_new_profile_eligible(apple_profile, pool, column, value):
    from argus.domain.apple_sign_in.name import initialize_apple_display_name

    with psycopg.connect(DSN) as connection:
        connection.execute(
            f"update public.profiles set {column}=%s where id=%s", (value, apple_profile)
        )
    name = fake.name()
    row = initialize_apple_display_name(pool, user_id=apple_profile, display_name=name)
    assert row["display_name"] == name
    assert row[column] == value


def test_marker_is_monotonic_even_for_privileged_writer(apple_profile):
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "update public.profiles set preferred_name=preferred_name where id=%s",
            (apple_profile,),
        )
        connection.execute(
            "update public.profiles set name_initialization_closed=false where id=%s",
            (apple_profile,),
        )
        assert connection.execute(
            "select name_initialization_closed from public.profiles where id=%s",
            (apple_profile,),
        ).fetchone() == (True,)


@pytest.mark.parametrize("column", ["display_name", "preferred_name"])
@pytest.mark.parametrize("value", [None, "Chosen name"])
def test_same_statement_cannot_leave_name_eligibility_open(
    apple_profile, pool, column, value
):
    from argus.domain.apple_sign_in.name import initialize_apple_display_name

    with psycopg.connect(DSN) as connection:
        connection.execute(
            f"update public.profiles set {column}=%s,name_initialization_closed=false where id=%s",
            (value, apple_profile),
        )
        assert connection.execute(
            "select name_initialization_closed from public.profiles where id=%s",
            (apple_profile,),
        ).fetchone() == (True,)
    row = initialize_apple_display_name(
        pool, user_id=apple_profile, display_name=fake.name()
    )
    assert row[column] == value
    assert row["display_name"] == (value if column == "display_name" else None)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("operation", ["select", "update"])
def test_clients_cannot_read_or_reopen_marker(apple_profile, role, operation):
    with psycopg.connect(DSN) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                connection.execute(f"set local role {role}")
                connection.execute(
                    "select set_config('request.jwt.claims',%s,true)",
                    (
                        json.dumps(
                            {"sub": apple_profile, "role": role, "is_anonymous": False}
                        ),
                    ),
                )
                query = (
                    "select name_initialization_closed from public.profiles where id=%s"
                    if operation == "select"
                    else "update public.profiles set name_initialization_closed=false where id=%s"
                )
                connection.execute(query, (apple_profile,))


def test_direct_authenticated_preferred_edit_closes_seed(apple_profile, pool):
    from argus.domain.apple_sign_in.name import initialize_apple_display_name

    with psycopg.connect(DSN) as connection:
        connection.execute("set local role authenticated")
        connection.execute(
            "select set_config('request.jwt.claims',%s,true)",
            (
                json.dumps(
                    {"sub": apple_profile, "role": "authenticated", "is_anonymous": False}
                ),
            ),
        )
        connection.execute(
            "update public.profiles set preferred_name=null where id=%s", (apple_profile,)
        )
    row = initialize_apple_display_name(
        pool, user_id=apple_profile, display_name=fake.name()
    )
    assert row["display_name"] is None


@pytest.mark.parametrize("scope", ["guest", "stranger"])
def test_direct_non_owner_edit_has_no_side_effect(apple_profile, scope):
    with psycopg.connect(DSN) as connection:
        with connection.transaction():
            connection.execute("set local role authenticated")
            connection.execute(
                "select set_config('request.jwt.claims',%s,true)",
                (
                    json.dumps(
                        {
                            "sub": apple_profile if scope == "guest" else str(uuid4()),
                            "role": "authenticated",
                            "is_anonymous": scope == "guest",
                        }
                    ),
                ),
            )
            assert (
                connection.execute(
                    "update public.profiles set preferred_name='Other' where id=%s",
                    (apple_profile,),
                ).rowcount
                == 0
            )
        assert connection.execute(
            "select preferred_name,name_initialization_closed from public.profiles where id=%s",
            (apple_profile,),
        ).fetchone() == (None, False)


@pytest.mark.parametrize(
    "cause", ["missing", "ambiguous", "malformed", "banned", "deleted", "deletion"]
)
def test_ineligible_auth_identity_has_no_profile_write(apple_profile, pool, cause):
    from argus.domain.apple_sign_in.credentials import AppleIdentityMissing
    from argus.domain.apple_sign_in.identity import AppleIdentityUnavailable
    from argus.domain.apple_sign_in.name import (
        AppleNameAccountUnavailable,
        initialize_apple_display_name,
    )

    with psycopg.connect(DSN) as connection:
        if cause == "missing":
            connection.execute(
                "delete from auth.identities where user_id=%s", (apple_profile,)
            )
        elif cause == "malformed":
            connection.execute(
                "update auth.identities set identity_data='{}' where user_id=%s",
                (apple_profile,),
            )
        elif cause == "ambiguous":
            subject = str(uuid4())
            connection.execute(
                "insert into auth.identities (id,user_id,provider,provider_id,identity_data) "
                "values (%s,%s,'apple',%s,%s::jsonb)",
                (str(uuid4()), apple_profile, subject, json.dumps({"sub": subject})),
            )
        elif cause == "deletion":
            connection.execute(
                "insert into argus_private.account_deletion_runs "
                "(subject_hash,user_id,analytics_distinct_id,status) values (%s,%s,%s,'started')",
                (uuid4().hex + uuid4().hex, apple_profile, uuid4().hex),
            )
        else:
            column = "banned_until" if cause == "banned" else "deleted_at"
            connection.execute(
                f"update auth.users set {column}=now()+interval '1 hour' where id=%s",
                (apple_profile,),
            )
    with pytest.raises(
        (AppleNameAccountUnavailable, AppleIdentityMissing, AppleIdentityUnavailable)
    ):
        initialize_apple_display_name(
            pool, user_id=apple_profile, display_name=fake.name()
        )
    with psycopg.connect(DSN) as connection:
        assert connection.execute(
            "select display_name,name_initialization_closed from public.profiles where id=%s",
            (apple_profile,),
        ).fetchone() == (None, False)


def test_migration_preserves_historical_rows_and_named_new_rows():
    schema = f"apple_name_migration_{uuid4().hex}"
    migration = Path(
        "supabase/migrations/20261005230000_apple_name_initialization.sql"
    ).read_text()
    with psycopg.connect(DSN) as connection, connection.transaction(force_rollback=True):
        connection.execute(f"create schema {schema}")
        connection.execute(
            f"create table {schema}.profiles (id int primary key, display_name text, preferred_name text)"
        )
        connection.execute(
            f"insert into {schema}.profiles values (1,null,null),(2,'Chosen',null)"
        )
        connection.execute(migration.replace("public.", f"{schema}."))
        assert connection.execute(
            f"select name_initialization_closed from {schema}.profiles order by id"
        ).fetchall() == [(True,), (True,)]
        connection.execute(
            f"insert into {schema}.profiles (id,display_name,preferred_name,name_initialization_closed) "
            "values (3,null,null,false),(4,'Apple',null,false),"
            "(5,null,'Chosen',false),(6,'Apple','Chosen',false)"
        )
        assert connection.execute(
            f"select name_initialization_closed from {schema}.profiles where id>=3 order by id"
        ).fetchall() == [(False,), (True,), (True,), (True,)]

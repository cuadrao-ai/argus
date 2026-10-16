"""Real-Postgres proof for the Cuadrao marketing early-access signup table (#882)."""

from __future__ import annotations

import hashlib
import os

import pytest
from faker import Faker

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")
fake = Faker()

TABLE = "public.cuadrao_early_access_signups"


def _email() -> str:
    return fake.unique.email(domain="example.com").lower()


def _digest(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


@pytest.fixture()
def connection():
    with psycopg.connect(DSN, autocommit=True) as conn:
        yield conn


def _insert_ignoring_duplicates(
    connection, *, email: str | None, digest: str, language: str = "es"
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            insert into {TABLE} (email_digest, email, language, consent_version)
            values (%s, %s, %s, 'early-access-test')
            on conflict (email_digest) do nothing
            """,
            (digest, email, language),
        )
        return cursor.rowcount


def _remove(connection, digest: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"update {TABLE} set email = null, removed_at = now() where email_digest = %s",
            (digest,),
        )


def _cleanup(connection, *digests: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"delete from {TABLE} where email_digest = any(%s)", (list(digests),)
        )


def test_a_repeated_address_is_ignored_not_duplicated(connection):
    email = _email()
    digest = _digest(email)
    try:
        assert _insert_ignoring_duplicates(connection, email=email, digest=digest) == 1
        assert _insert_ignoring_duplicates(connection, email=email, digest=digest) == 0
        with connection.cursor() as cursor:
            cursor.execute(
                f"select count(*) from {TABLE} where email_digest = %s", (digest,)
            )
            assert cursor.fetchone()[0] == 1
    finally:
        _cleanup(connection, digest)


def test_a_removed_address_keeps_only_its_digest_and_blocks_reregistration(connection):
    email = _email()
    digest = _digest(email)
    try:
        _insert_ignoring_duplicates(connection, email=email, digest=digest)
        _remove(connection, digest)
        with connection.cursor() as cursor:
            cursor.execute(
                f"select email, removed_at is not null from {TABLE} where email_digest = %s",
                (digest,),
            )
            assert cursor.fetchone() == (None, True)
        assert _insert_ignoring_duplicates(connection, email=email, digest=digest) == 0
        with connection.cursor() as cursor:
            cursor.execute(
                f"select email from {TABLE} where email_digest = %s", (digest,)
            )
            assert cursor.fetchone() == (None,)
    finally:
        _cleanup(connection, digest)


@pytest.mark.parametrize(
    "case",
    [
        "digest not derived from the address",
        "address kept after removal",
        "active row without an address",
        "address not normalized",
        "address with whitespace",
        "digest not hexadecimal",
        "unsupported language",
    ],
)
def test_the_table_refuses_inconsistent_rows(connection, case):
    email = _email()
    digest = _digest(email)
    statements = {
        "digest not derived from the address": (
            f"insert into {TABLE} (email_digest, email, language, consent_version) "
            "values (%s, %s, 'es', 'v')",
            (_digest("someone-else@example.com"), email),
        ),
        "address kept after removal": (
            f"insert into {TABLE} (email_digest, email, language, consent_version, removed_at) "
            "values (%s, %s, 'es', 'v', now())",
            (digest, email),
        ),
        "active row without an address": (
            f"insert into {TABLE} (email_digest, email, language, consent_version) "
            "values (%s, null, 'es', 'v')",
            (digest,),
        ),
        "address not normalized": (
            f"insert into {TABLE} (email_digest, email, language, consent_version) "
            "values (%s, %s, 'es', 'v')",
            (_digest(email.upper()), email.upper()),
        ),
        "address with whitespace": (
            f"insert into {TABLE} (email_digest, email, language, consent_version) "
            "values (%s, %s, 'es', 'v')",
            (_digest("a b@example.com"), "a b@example.com"),
        ),
        "digest not hexadecimal": (
            f"insert into {TABLE} (email_digest, email, language, consent_version) "
            "values ('not-a-digest', %s, 'es', 'v')",
            (email,),
        ),
        "unsupported language": (
            f"insert into {TABLE} (email_digest, email, language, consent_version) "
            "values (%s, %s, 'fr', 'v')",
            (digest, email),
        ),
    }
    statement, params = statements[case]
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
    finally:
        _cleanup(connection, digest)


def test_only_service_role_can_reach_the_table(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
              role_name,
              privilege,
              has_table_privilege(role_name, %s, privilege)
            from unnest(array['anon', 'authenticated', 'service_role']) as role_name,
                 unnest(array['select', 'insert', 'update', 'delete']) as privilege
            """,
            (TABLE,),
        )
        grants = {(role, privilege): held for role, privilege, held in cursor.fetchall()}
    for role in ("anon", "authenticated"):
        for privilege in ("select", "insert", "update", "delete"):
            assert grants[(role, privilege)] is False, (role, privilege)
    for privilege in ("select", "insert", "update", "delete"):
        assert grants[("service_role", privilege)] is True


@pytest.mark.parametrize("role", ["anon", "authenticated", "service_role"])
@pytest.mark.parametrize("operation", ["operator", "leave", "purge"])
def test_personal_waitlist_deletion_requires_service_role(connection, role, operation):
    email, legacy_email = _email(), _email()
    digest, legacy_digest = _digest(email), _digest(legacy_email)
    verification_id = _digest(fake.uuid4())
    statements = {
        "operator": (f"delete from {TABLE} where email_digest = %s", (digest,)),
        "leave": ("select public.cuadrao_waitlist_leave(%s)", (verification_id,)),
        "purge": ("select public.cuadrao_waitlist_purge(100)", ()),
    }
    with connection.transaction(force_rollback=True):
        connection.execute(
            "select * from public.cuadrao_waitlist_register(%s, %s, %s, %s, %s)",
            (email, "No los llevo", "Private answer", verification_id, "test-policy"),
        )
        connection.execute(
            f"update {TABLE} set created_at = now() - interval '8 days' "
            "where email_digest = %s",
            (digest,),
        )
        _insert_ignoring_duplicates(connection, email=legacy_email, digest=legacy_digest)
        _remove(connection, legacy_digest)
        assert connection.execute(
            f"select count(*) from {TABLE} where email_digest = any(%s)",
            ([digest, legacy_digest],),
        ).fetchone() == (2,)
        statement, params = statements[operation]
        with connection.transaction(force_rollback=True):
            connection.execute(
                psycopg.sql.SQL("set local role {}").format(psycopg.sql.Identifier(role))
            )
            if role == "service_role":
                connection.execute(statement, params)
                assert connection.execute(
                    f"select email_digest from {TABLE} where email_digest = any(%s)",
                    ([digest, legacy_digest],),
                ).fetchall() == [(legacy_digest,)]
            else:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    connection.execute(statement, params)
        assert connection.execute(
            f"select count(*) from {TABLE} where email_digest = any(%s)",
            ([digest, legacy_digest],),
        ).fetchone() == (2,)


def test_row_level_security_is_on_with_no_policy(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "select relrowsecurity from pg_class where oid = %s::regclass", (TABLE,)
        )
        assert cursor.fetchone() == (True,)
        cursor.execute(
            "select count(*) from pg_policies where schemaname = 'public' "
            "and tablename = 'cuadrao_early_access_signups'"
        )
        assert cursor.fetchone() == (0,)

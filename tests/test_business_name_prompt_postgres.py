import os
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.access import ensure_owner_grant
from argus.domain.business.memberships import MembershipError
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests.business_cleanup import delete_spaces

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable Postgres is not configured")


@pytest.fixture
def naming():
    owners = [str(uuid4()), str(uuid4())]
    with psycopg.connect(DSN) as connection:
        for owner in owners:
            connection.execute("insert into auth.users (id) values (%s)", (owner,))
        spaces = [
            str(
                connection.execute(
                    "insert into public.spaces (kind, name, created_by) values ('business', 'Mi negocio', %s) returning id",
                    (owner,),
                ).fetchone()[0]
            )
            for owner in owners
        ]
        for owner, space_id in zip(owners, spaces, strict=False):
            ensure_owner_grant(connection, space_id, owner)
    with ConnectionPool(DSN, min_size=1, max_size=8) as pool:
        yield PostgresSpaceStore(pool), owners, spaces
    with psycopg.connect(DSN) as connection:
        # A Business still naming its creator refuses the bare Auth delete.
        delete_spaces(connection, "created_by = any(%s::uuid[])", (owners,))
        connection.execute("delete from auth.users where id = any(%s::uuid[])", (owners,))


def test_rename_clears_the_default_and_refuses_another_owner(naming):
    store, owners, spaces = naming
    assert store.open_space(owners[0]).name_required
    with pytest.raises(MembershipError):
        store.rename(owners[1], "Changed", spaces[0])
    store.rename(owners[0], "Colmado La Esquina", spaces[0])
    with ConnectionPool(DSN, min_size=1, max_size=1) as pool:
        assert not PostgresSpaceStore(pool).open_space(owners[0]).name_required


def test_closed_business_cannot_be_renamed(naming):
    store, owners, spaces = naming
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "update public.spaces set closed_at = now() where id = %s", (spaces[0],)
        )
        new = str(
            connection.execute(
                "insert into public.spaces (kind,name,created_by) values ('business','Mi negocio',%s) returning id",
                (owners[0],),
            ).fetchone()[0]
        )
        ensure_owner_grant(connection, new, owners[0])
    with pytest.raises(MembershipError):
        store.rename(owners[0], "Changed", spaces[0])
    assert store.open_space(owners[0]).id == new


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_clients_cannot_read_or_write_naming_state(naming, role):
    _, _, spaces = naming
    for query in [
        "select business_name_prompt_seen_at from public.spaces where id = %s",
        "update public.spaces set business_name_prompt_seen_at = now() where id = %s",
    ]:
        with psycopg.connect(DSN) as connection:
            connection.execute(f"set local role {role}")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(query, (spaces[0],))


def test_additive_column_and_rls_are_present(naming):
    with psycopg.connect(DSN) as connection:
        assert connection.execute(
            "select data_type,is_nullable,column_default from information_schema.columns where table_schema='public' and table_name='spaces' and column_name='business_name_prompt_seen_at'"
        ).fetchone() == ("timestamp with time zone", "YES", None)
        assert connection.execute(
            "select relrowsecurity from pg_class where oid='public.spaces'::regclass"
        ).fetchone() == (True,)

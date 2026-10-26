"""Business country and currency (20261021020000) on real Postgres, and over
HTTP on the real app, Auth and Postgres."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.business.country import COUNTRIES
from argus.domain.business.spaces import PostgresSpaceStore
from fastapi.testclient import TestClient

from tests import test_financial_accounts_postgres as shared
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_scope_switch_routes_postgres import (
    API,
    ENV,
    PERIOD,
    _as,
    _grant,
    _person,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

psycopg = pytest.importorskip("psycopg")
psycopg_pool = pytest.importorskip("psycopg_pool")

users = shared.users
pytestmark = _local_supabase


@pytest.fixture
def db(users) -> Iterator:  # noqa: ANN001
    with psycopg.connect(shared.DSN) as connection:
        with connection.transaction(force_rollback=True):
            yield connection


@contextmanager
def _raises(db, match: str):  # noqa: ANN001, ANN202
    with pytest.raises(psycopg.Error, match=match), db.transaction():
        yield


def _insert(db, owner: str, **columns: str) -> tuple[str, str, str]:  # noqa: ANN001
    names = ", ".join(["kind", "name", "created_by", *columns])
    marks = ", ".join(["'business'", "'Colmado'", "%s", *["%s"] * len(columns)])
    return db.execute(
        f"insert into public.spaces ({names}) values ({marks})"
        " returning id::text, country, currency",
        (owner, *columns.values()),
    ).fetchone()


def test_a_space_without_a_country_is_dominican_in_pesos(db, users) -> None:  # noqa: ANN001
    _, country, currency = _insert(db, users["owner"])
    assert (country, currency) == ("DO", "DOP")


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("country", "XX", "business_country_known"),
        ("country", "do", "business_country_known"),
        ("currency", "dop", "business_currency_shape"),
    ],
)
def test_unknown_countries_and_malformed_currencies_are_refused(
    db,  # noqa: ANN001
    users,  # noqa: ANN001
    column: str,
    value: str,
    constraint: str,
) -> None:
    with _raises(db, constraint):
        _insert(db, users["owner"], **{column: value})


def test_the_country_cannot_change_but_the_currency_can(db, users) -> None:  # noqa: ANN001
    space_id, _, _ = _insert(db, users["owner"], country="US", currency="USD")
    with _raises(db, "business_country_immutable"):
        db.execute("update public.spaces set country = 'CA' where id = %s", (space_id,))
    db.execute("update public.spaces set currency = 'EUR' where id = %s", (space_id,))
    assert db.execute(
        "select country, currency from public.spaces where id = %s", (space_id,)
    ).fetchone() == ("US", "EUR")


def test_the_database_admits_exactly_the_registry_countries(db) -> None:  # noqa: ANN001
    definition = db.execute(
        "select pg_get_constraintdef(oid) from pg_constraint"
        " where conname = 'business_country_known'"
        " and conrelid = 'public.spaces'::regclass"
    ).fetchone()[0]
    admitted = re.search(r"country = ANY \(ARRAY\[(.*?)\]", definition).group(1)
    assert set(re.findall(r"'([^']+)'", admitted)) == set(COUNTRIES)


def test_spaces_stay_closed_to_browser_roles(db) -> None:  # noqa: ANN001
    assert db.execute(
        "select relrowsecurity from pg_class where oid = 'public.spaces'::regclass"
    ).fetchone()[0]
    for role in ("anon", "authenticated"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert not db.execute(
                "select has_table_privilege(%s, 'public.spaces', %s)", (role, privilege)
            ).fetchone()[0], (role, privilege)
    for privilege in ("SELECT", "UPDATE"):
        assert db.execute(
            "select has_table_privilege('service_role', 'public.spaces', %s)",
            (privilege,),
        ).fetchone()[0], privilege
    assert not db.execute(
        "select has_column_privilege('anon', 'public.spaces', 'country', 'SELECT')"
    ).fetchone()[0]


def test_the_store_keeps_the_country_and_its_currency(users) -> None:  # noqa: ANN001
    with psycopg_pool.ConnectionPool(shared.DSN, min_size=0, max_size=2) as pool:
        spaces = PostgresSpaceStore(pool)
        space, created = spaces.create(users["owner"], "Taller", "US")
        assert created
        assert (space.country, space.currency) == ("US", "USD")
        assert spaces.open_space(users["owner"]) == space
        assert spaces.get(space.id) == space
        renamed = spaces.rename(users["owner"], "Taller Rivera")
        assert renamed is not None
        assert (renamed.name, renamed.country, renamed.currency) == (
            "Taller Rivera",
            "US",
            "USD",
        )


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    created: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            yield SimpleNamespace(
                client=client,
                **{
                    label: _person(client, gateway, label, created)
                    for label in ("alice", "bob")
                },
            )
    finally:
        with psycopg.connect(shared.DSN) as db:
            for user_id in created:
                db.execute(
                    "update public.spaces set closed_at=coalesce(closed_at,clock_timestamp()) where created_by=%s and kind='business'",
                    (user_id,),
                )
                db.execute(
                    "delete from public.business_client_grants"
                    " where grantee_id = %s or issuer_id = %s",
                    (user_id, user_id),
                )
            db.execute("set constraints all deferred")
            db.execute(
                "delete from public.financial_activity_groups where user_id=any(%s::uuid[])",
                (created,),
            )
            db.execute("delete from public.spaces where created_by=any(%s::uuid[])", (created,))
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _identity(response) -> tuple[str, str]:  # noqa: ANN001
    assert response.status_code in (200, 201), response.text
    body = response.json()
    return body["country"], body["currency"]


def _business_reads(web, person) -> list[tuple[str, str]]:  # noqa: ANN001
    return [
        _identity(web.client.get(f"{API}/business/space", headers=person.headers)),
        _identity(web.client.get(f"{API}/business/workspace", headers=person.headers)),
        _identity(
            web.client.get(
                f"{API}/business/overview", params=PERIOD, headers=person.headers
            )
        ),
    ]


def test_the_person_home_country_never_decides_the_business(web) -> None:  # noqa: ANN001
    profile = web.client.patch(
        f"{API}/me", json={"country": "US"}, headers=web.alice.headers
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["user"]["currency"] == "USD"
    started = web.client.post(f"{API}/business/space", json={}, headers=web.alice.headers)
    assert started.status_code == 201
    assert _identity(started) == ("DO", "DOP")
    assert _business_reads(web, web.alice) == [("DO", "DOP")] * 3


def test_a_canadian_business_is_stored_and_served_in_dollars(web) -> None:  # noqa: ANN001
    started = web.client.post(
        f"{API}/business/space", json={"country": "CA"}, headers=web.bob.headers
    )
    assert started.status_code == 201
    assert _identity(started) == ("CA", "CAD")
    assert _business_reads(web, web.bob) == [("CA", "CAD")] * 3
    with psycopg.connect(shared.DSN) as db:
        assert db.execute(
            "select country, currency from public.spaces where id = %s",
            (started.json()["id"],),
        ).fetchone() == ("CA", "CAD")


def test_a_grant_reads_the_owners_country_not_the_readers(web) -> None:  # noqa: ANN001
    started = web.client.post(
        f"{API}/business/space",
        json={"name": "Ferretería Prueba", "country": "US"},
        headers=web.alice.headers,
    )
    assert started.status_code == 201, started.text
    web.alice.space_id = started.json()["id"]
    own = web.client.post(
        f"{API}/business/space", json={"country": "CA"}, headers=web.bob.headers
    )
    assert own.status_code == 201, own.text
    grant = _grant(web, web.alice, web.bob)
    as_client = web.client.get(f"{API}/business/workspace", headers=_as(web.bob, grant))
    assert _identity(as_client) == ("US", "USD")
    overview = web.client.get(
        f"{API}/business/overview", params=PERIOD, headers=_as(web.bob, grant)
    )
    assert _identity(overview) == ("US", "USD")
    assert _identity(
        web.client.get(f"{API}/business/workspace", headers=web.bob.headers)
    ) == ("CA", "CAD")

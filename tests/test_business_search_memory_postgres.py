"""Over HTTP on the real app, Auth and Postgres: Business search memory is
per member and per Business. The owner and a grantee working in the same
Business each keep their own recents and their own opens ranking; a client
role reads and writes neither table, and a member's rows go with the member."""

from __future__ import annotations

import json
from uuid import uuid4

import psycopg
import pytest
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_fiscal_routes_postgres import pytestmark, world  # noqa: F401
from tests.test_business_scope_switch_routes_postgres import API, _as

TABLES = ("business_search_recents", "business_search_opens")


def _call(app, method: str, path: str, headers: dict, body: dict | None = None):  # noqa: ANN001, ANN202
    return app.client.request(
        method, f"{API}/business/search{path}", json=body, headers=headers
    )


def _recents(app, headers: dict) -> list[str]:  # noqa: ANN001
    listed = _call(app, "GET", "/recents", headers)
    assert listed.status_code == 200, listed.text
    return [item["q"] for item in listed.json()["items"]]


def _accounts(app, headers: dict) -> list[str]:  # noqa: ANN001
    found = app.client.get(
        f"{API}/business/search", params={"q": "caja"}, headers=headers
    )
    assert found.status_code == 200, found.text
    return [item["nickname"] for item in found.json()["accounts"]]


def test_each_member_keeps_their_own_recents_and_ranking(world) -> None:  # noqa: ANN001, F811
    alice, bob = world.alice.headers, _as(world.bob, world.grant)
    ids = {}
    for nickname in ("Caja chica", "Caja grande"):
        made = world.client.post(
            f"{API}/business/accounts",
            json={"nickname": nickname, "type": "cash", "currency": "DOP"},
            headers={**alice, "Idempotency-Key": str(uuid4())},
        )
        assert made.status_code == 201, made.text
        ids[nickname] = made.json()["id"]

    mine = _call(world, "POST", "/recents", alice, {"q": "colmado"})
    assert mine.status_code == 201, mine.text
    assert _call(world, "POST", "/recents", bob, {"q": "taller"}).status_code == 201
    assert _recents(world, alice) == ["colmado"]
    assert _recents(world, bob) == ["taller"]
    refused = _call(world, "DELETE", f"/recents/{mine.json()['id']}", bob)
    assert refused.status_code == 404, refused.text
    assert _call(world, "DELETE", "/recents", bob).status_code == 204
    assert (_recents(world, alice), _recents(world, bob)) == (["colmado"], [])

    for nickname in ("Caja grande", "Caja grande", "Caja chica"):
        opened = _call(
            world, "POST", "/opens", bob, {"kind": "accounts", "id": ids[nickname]}
        )
        assert opened.status_code == 204, opened.text
    # Opened more often wins over opened more recently.
    assert _accounts(world, bob) == ["Caja grande", "Caja chica"]
    assert _accounts(world, alice) == ["Caja chica", "Caja grande"]

    with Connection.connect(shared.DSN) as db:
        rows = db.execute(
            "select space_id::text, user_id::text, kind, record_id::text, opened_count"
            " from public.business_search_opens where space_id=%s",
            (world.alice.space_id,),
        ).fetchall()
    assert sorted(rows) == sorted(
        [
            (world.alice.space_id, world.bob.id, "accounts", ids["Caja grande"], 2),
            (world.alice.space_id, world.bob.id, "accounts", ids["Caja chica"], 1),
        ]
    )

    for n in range(11):
        assert (
            _call(world, "POST", "/recents", alice, {"q": f"gasto {n}"}).status_code
            == 201
        )
    assert _recents(world, alice) == [f"gasto {n}" for n in reversed(range(11))][:10]


@pytest.mark.parametrize("table", TABLES)
def test_a_client_role_reads_and_writes_none_of_it(world, table: str) -> None:  # noqa: ANN001, F811
    assert (
        _call(world, "POST", "/recents", world.alice.headers, {"q": "x"}).status_code
        == 201
    )
    claims = json.dumps({"sub": world.alice.id, "role": "authenticated"})
    for role in ("anon", "authenticated"):
        for statement in (
            f"select count(*) from public.{table}",
            f"delete from public.{table}",
        ):
            with (
                Connection.connect(shared.DSN) as db,
                db.transaction(force_rollback=True),
            ):
                db.execute(f"set local role {role}")
                db.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    db.execute(statement)


def test_a_members_memory_goes_with_the_member(world) -> None:  # noqa: ANN001, F811
    bob = _as(world.bob, world.grant)
    assert _call(world, "POST", "/recents", bob, {"q": "taller"}).status_code == 201
    opened = _call(world, "POST", "/opens", bob, {"kind": "expenses", "id": str(uuid4())})
    assert opened.status_code == 204, opened.text
    with Connection.connect(shared.DSN) as db, db.transaction(force_rollback=True):
        db.execute(
            "delete from public.business_client_grants where grantee_id=%s",
            (world.bob.id,),
        )
        db.execute("delete from auth.users where id=%s", (world.bob.id,))
        for table in TABLES:
            count = db.execute(
                f"select count(*) from public.{table} where user_id=%s", (world.bob.id,)
            ).fetchone()
            assert count == (0,), table

"""Over HTTP, on the real app, Auth and Postgres: once a draft is approved and
someone other than the owner marks it Personal, every route that carries the
record's marks answers 200 with the same marks (the expense list and detail,
search, the receipt list and the dossier), and a read-only grant is refused."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_scope_switch_routes_postgres import (
    API,
    ENV,
    PERIOD,
    _as,
    _grant,
    _note,
    _person,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
MARKS = ("personal", "personal_marked_by", "fiscal_known", "include_606")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Alice owns the Business; Bob holds read and prepare on it."""

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
            people = {
                label: _person(client, gateway, label, created)
                for label in ("alice", "bob")
            }
            started = client.post(
                f"{API}/business/space",
                json={"name": "Ferretería Prueba"},
                headers=people["alice"].headers,
            )
            assert started.status_code == 201, started.text
            people["alice"].space_id = started.json()["id"]
            found = SimpleNamespace(client=client, **people)
            found.grant = _grant(found, found.alice, found.bob)
            yield found
    finally:
        with Connection.connect(shared.DSN) as db:
            for user_id in created:
                db.execute(
                    "delete from public.business_client_grants where grantee_id=%s or issuer_id=%s",
                    (user_id, user_id),
                )
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _post(world, path: str, body: dict, headers: dict):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}{path}", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
    )


def test_every_route_carrying_marks_answers_200_with_the_same_marks(world) -> None:  # noqa: ANN001
    client, alice, bob = world.client, world.alice, world.bob
    note = _note(world, alice, "Pagué 850 en Ferretería Prueba")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    dossier = client.get(f"{API}/business/drafts/{draft}/dossier", headers=alice.headers)
    assert dossier.status_code == 200, dossier.text
    facts = {
        name: {"state": "known", "value": value}
        for name, value in {
            "kind": "expense",
            "amount": "850",
            "currency": "DOP",
            "occurred_on": "2026-10-09",
            "counterparty": "Ferretería Prueba",
            "funding": {"kind": "owner_funds"},
            "business_share": {"kind": "all"},
        }.items()
    }
    reviewed = client.patch(
        f"{API}/business/drafts/{draft}/review",
        json={"version": dossier.json()["version"], "facts": facts},
        headers={**alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert reviewed.status_code == 200, reviewed.text
    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        {"version": reviewed.json()["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    version = client.get(
        f"{API}/business/drafts/{draft}/dossier", headers=alice.headers
    ).json()["version"]
    marked = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": version, "personal": True},
        _as(bob, world.grant),
    )
    assert marked.status_code == 200, marked.text

    expenses = client.get(
        f"{API}/business/expenses", params=PERIOD, headers=alice.headers
    )
    assert expenses.status_code == 200, expenses.text
    [expense] = expenses.json()["items"]
    detail = client.get(f"{API}/business/expenses/{expense['id']}", headers=alice.headers)
    assert detail.status_code == 200, detail.text
    search = client.get(
        f"{API}/business/search", params={"q": "Prueba"}, headers=alice.headers
    )
    assert search.status_code == 200, search.text
    [found] = search.json()["expenses"]
    record = client.get(f"{API}/business/drafts/{draft}/dossier", headers=alice.headers)
    assert record.status_code == 200, record.text
    receipts = client.get(
        f"{API}/business/receipts", params={"view": "all"}, headers=alice.headers
    )
    assert receipts.status_code == 200, receipts.text
    overview = client.get(
        f"{API}/business/overview", params=PERIOD, headers=alice.headers
    )
    assert overview.status_code == 200, overview.text

    def marks(body: dict) -> dict:
        # List wires leave out a false or empty mark; the dossier states it.
        found = {key: body.get(key) for key in MARKS}
        return {**found, "personal": bool(found["personal"])}

    assert marks(expense)["personal"] is True
    assert marks(expense)["fiscal_known"] is True
    assert marks(expense)["personal_marked_by"]
    assert marks(expense) == marks(detail.json()) == marks(found) == marks(record.json())
    # Left out of Gastos reales, kept in the list with its mark.
    assert overview.json()["totals"] == []

    # The owner takes the accountant's mark back in one action; every view follows.
    back = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": record.json()["version"], "personal": False},
        alice.headers,
    )
    assert back.status_code == 200, back.text
    [expense] = client.get(
        f"{API}/business/expenses", params=PERIOD, headers=alice.headers
    ).json()["items"]
    record = client.get(f"{API}/business/drafts/{draft}/dossier", headers=alice.headers)
    assert marks(expense) == marks(record.json())
    assert (marks(expense)["personal"], expense.get("personal_marked_by")) == (
        False,
        None,
    )

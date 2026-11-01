"""Over HTTP, on the real app, Auth and Postgres: once a draft is approved and
someone other than the owner marks it Personal, every route that carries the
record's marks answers 200 with the same marks (the expense list and detail,
search, the receipt list and the dossier), and a read-only grant is refused.

The review write path, end to end: a read's RNC printed with dashes saves, the
owner approves with no 606 data, adds the 606 data on the approved record,
exports the ready line, and the next 606 write is refused with a clear code."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.business_cleanup import delete_spaces
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
                    "update public.spaces set closed_at=coalesce(closed_at,clock_timestamp()) where created_by=%s and kind='business'",
                    (user_id,),
                )
                db.execute(
                    "delete from public.business_client_grants where grantee_id=%s or issuer_id=%s",
                    (user_id, user_id),
                )
            db.execute("set constraints all deferred")
            db.execute(
                "delete from public.financial_activity_groups where user_id=any(%s::uuid[])",
                (created,),
            )
            delete_spaces(db, "created_by=any(%s::uuid[])", (created,))
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _post(world, path: str, body: dict, headers: dict):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}{path}", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
    )


def _review(world, draft: str, body: dict, headers: dict):  # noqa: ANN001, ANN202
    return world.client.patch(
        f"{API}/business/drafts/{draft}/review",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def _known(values: dict) -> dict:
    return {name: {"state": "known", "value": value} for name, value in values.items()}


def test_review_write_path_from_capture_to_frozen_606_line(world) -> None:  # noqa: ANN001
    client, alice = world.client, world.alice
    note = _note(world, alice, "Pagué 1180 en Ferretería Prueba")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    version = client.get(
        f"{API}/business/drafts/{draft}/dossier", headers=alice.headers
    ).json()["version"]

    # The read's RNC and NCF as printed; the server keeps the digits.
    reviewed = _review(
        world,
        draft,
        {
            "version": version,
            "facts": _known(
                {
                    "kind": "expense",
                    "amount": "1180.00",
                    "currency": "DOP",
                    "occurred_on": "2026-09-03",
                    "counterparty": "Ferretería Prueba",
                    "funding": {"kind": "owner_funds"},
                    "business_share": {"kind": "all"},
                }
            ),
            "dgii": {
                "fiscal": {
                    "rnc": "1-99-99002-1",
                    "ncf": "b0100000011",
                    "itbis": "180.00",
                },
                # The fiscal form's shape: every 606 field present, unknown ones null.
                "declaration": {
                    **{name: None for name in PurchaseDeclaration.model_fields},
                    "form": "606",
                    "actual_refund": False,
                    "category_suggested": False,
                },
            },
        },
        alice.headers,
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["facts"]["fiscal"]["rnc"]["value"] == "199990021"
    assert body["facts"]["fiscal"]["ncf"]["value"] == "B0100000011"
    assert body["approval_available"] is True
    assert body["dgii"]["category"] is None and body["dgii"]["payment_method"] is None

    # Approval needs no 606 data: Tipo Id is filled from the RNC, nothing else.
    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        {"version": body["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    recorded = approved.json()
    assert recorded["review_state"] == "accepted"
    assert recorded["dgii"]["id_type"] == "1"
    assert recorded["dgii"]["category"] is None
    assert recorded["dgii"]["payment_method"] is None
    assert recorded["declaration_editable"] is True

    added = _review(
        world,
        draft,
        {
            "version": recorded["version"],
            "purchase": {"category": "02", "payment_method": "01"},
        },
        alice.headers,
    )
    assert added.status_code == 200, added.text
    declared = added.json()
    assert declared["dgii"]["category"] == "02"
    assert declared["dgii"]["payment_method"] == "01"
    assert declared["dgii"]["services_amount"] == "1000.00"
    assert len(declared["history"]) == len(recorded["history"]) + 1
    assert declared["approval_result"] == recorded["approval_result"]

    locked = _review(
        world,
        draft,
        {
            "version": declared["version"],
            "facts": _known({"counterparty": "Otro comercio"}),
        },
        alice.headers,
    )
    assert locked.status_code == 422, locked.text
    assert locked.json()["code"] == "recorded_correction_unsupported"

    profile = client.patch(
        f"{API}/business/fiscal-profile",
        json={
            "name": "Ferretería Prueba",
            "previous_name": "Ferretería Prueba",
            "tax_id": {"type": "rnc", "value": "199990013"},
            "previous_tax_id": None,
        },
        headers={**alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert profile.status_code == 200, profile.text
    exported = client.get(
        f"{API}/business/exports",
        params={"start": "2026-09-01", "end": "2026-09-30"},
        headers=alice.headers,
    )
    assert exported.status_code == 200, exported.text
    with ZipFile(io.BytesIO(exported.content)) as archive:
        assert "dgii/DGII_F_606_199990013_202609.TXT" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))["dgii"]
    [placed] = [item for item in manifest["reconciliation"] if item["draft_id"] == draft]
    assert placed["disposition"] == "606"

    frozen = client.get(f"{API}/business/drafts/{draft}/dossier", headers=alice.headers)
    assert frozen.json()["declaration_editable"] is False
    refused = _review(
        world,
        draft,
        {
            "version": frozen.json()["version"],
            "purchase": {"payment_method": "04"},
        },
        alice.headers,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "fiscal_declaration_exported"
    assert (
        client.get(
            f"{API}/business/drafts/{draft}/dossier", headers=alice.headers
        ).json()["dgii"]["payment_method"]
        == "01"
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

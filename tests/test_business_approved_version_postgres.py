"""Over HTTP, on the real app, Auth and Postgres: a recorded receipt keeps
naming the revision a person approved, and when, after later marks add
revisions to its history."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from psycopg import Connection
from pydantic import TypeAdapter

from tests import test_financial_accounts_postgres as shared
from tests.test_business_fiscal_routes_postgres import (  # noqa: F401
    _post,
    pytestmark,
    world,
)
from tests.test_business_scope_switch_routes_postgres import API, _as, _note


def test_recorded_approval_names_the_approved_revision_after_later_marks(world) -> None:  # noqa: ANN001, F811
    client, alice, bob = world.client, world.alice, world.bob
    note = _note(world, alice, "Pagué 850 en Ferretería Prueba")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    opened = client.get(f"{API}/business/drafts/{draft}/dossier", headers=alice.headers)
    assert opened.status_code == 200, opened.text
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
        json={"version": opened.json()["version"], "facts": facts},
        headers={**alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert reviewed.status_code == 200, reviewed.text
    approved_revision = reviewed.json()["version"]
    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        {"version": approved_revision, "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    after_approval = client.get(
        f"{API}/business/drafts/{draft}/dossier", headers=alice.headers
    ).json()["version"]
    marked = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": after_approval, "personal": True},
        _as(bob, world.grant),
    )
    assert marked.status_code == 200, marked.text

    record = client.get(f"{API}/business/drafts/{draft}/dossier", headers=alice.headers)
    assert record.status_code == 200, record.text
    body = record.json()
    result = body["approval_result"]
    assert set(result) == {
        "status",
        "activity_id",
        "reviewed_version",
        "approved_revision",
        "approved_at",
        "actor",
    }
    assert result["status"] == "recorded"
    assert result["reviewed_version"] == approved_revision
    assert result["approved_revision"] == approved_revision
    assert max(row["version"] for row in body["history"]) == after_approval + 1
    assert after_approval + 1 > approved_revision
    with Connection.connect(shared.DSN) as db:
        [(created_at,)] = db.execute(
            "select created_at from public.business_action_receipts"
            " where command->>'action'='approve_expense' and command->>'draft_id'=%s",
            (draft,),
        ).fetchall()
    assert TypeAdapter(datetime).validate_python(result["approved_at"]) == created_at

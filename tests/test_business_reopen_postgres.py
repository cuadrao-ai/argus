"""Reabrir over HTTP, on the real app, Auth and Postgres. An approved record
returns to the Bandeja with everything it holds; the money row it recorded
stops counting everywhere and stays as history; a second approval records it
once more and nothing doubles, in the totals, the month close, the 606 TXT or
Registros. Only the owner may, a replay changes nothing, a stale version is
refused, and a record a bank match or a credit note points at stays as it is.
All values are made up."""

from __future__ import annotations

import json
from uuid import uuid4

from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_approve_unpaid_postgres import (
    BUYER_OR_SUPPLIER,
    SPAN,
    _approve,
    _block,
    _declaration,
    _declare,
    _export,
    _fiscal_profile,
    _get,
    _ledger,
    _month,
    _reviewed,
    _settle,
    world,  # noqa: F401
)
from tests.test_business_bank_movements_postgres import (
    _checking,
    _import,
    _movements,
    _statement,
    bank,  # noqa: F401
)
from tests.test_business_bank_outcomes_postgres import _post as _bank_post
from tests.test_business_fiscal_routes_postgres import _known, _review
from tests.test_business_open_items_postgres import _record
from tests.test_business_scope_switch_routes_postgres import (  # noqa: F401
    API,
    _as,
    _note,
    web,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
#: A second supplier RNC whose check digit holds, so the fix is a real one.
CORRECTED_SUPPLIER = "199990031"


def _reopen(world, draft: str, version: int, key: str | None = None, headers=None):  # noqa: ANN001, ANN202, F811
    return world.client.post(
        f"{API}/business/drafts/{draft}/reopen",
        json={"version": version},
        headers={
            **(headers or world.alice.headers),
            "Idempotency-Key": key or str(uuid4()),
        },
    )


def _dossier(world, draft: str) -> dict:  # noqa: ANN001, F811
    return _get(world, f"/business/drafts/{draft}/dossier").json()


def _rows(world) -> list[dict]:  # noqa: ANN001, F811
    answer = world.client.post(
        f"{API}/business/reports/query", json={}, headers=world.alice.headers
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["items"]


def _waiting(world) -> int:  # noqa: ANN001, F811
    """How many rows the Bandeja holds for review: the sidebar's number."""

    return _get(world, "/business/receipts", view="inbox").json()["activity"][
        "pending_review_count"
    ]


def _group(activity: str) -> tuple:
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select reversed_at is not null, current_revision"
            " from public.financial_activity_groups where id=%s",
            (activity,),
        ).fetchone()


def _reopen_receipts(space: str, draft: str) -> list[dict]:
    with Connection.connect(shared.DSN) as db:
        return [
            row[0]
            for row in db.execute(
                "select outcome from public.business_action_receipts"
                " where space_id=%s and command->>'action'='reopen_draft'"
                " and command->>'draft_id'=%s order by created_at",
                (space, draft),
            ).fetchall()
        ]


def _txt_lines(files: dict[str, str]) -> list[str]:
    """The 606 TXT's rows after its header; none when no TXT shipped."""

    return files["606"].strip().split("\r\n")[1:] if "606" in files else []


def test_approve_export_reopen_fix_reapprove_export_counts_once(world) -> None:  # noqa: ANN001, F811
    """The full cycle on one purchase whose supplier RNC was wrong: the first
    TXT carries the wrong RNC, the reopened record leaves every read while it
    is open, the fixed and reapproved record is the only one anywhere, and the
    second TXT carries the right RNC on one line."""

    _fiscal_profile(world)
    draft, dossier = _reviewed(world, "expense", "B0100000031")
    waiting = _waiting(world)
    approved = _approve(world, draft, dossier["version"], "expense").json()
    first = approved["approval_result"]["activity_id"]
    assert approved["reopen_available"] is True
    assert _waiting(world) == waiting - 1, "the approved row left the Bandeja"
    approved = _declare(world, draft, category="02", payment_method="01")
    _, _, files = _export(world)
    assert len(_txt_lines(files)) == 1 and BUYER_OR_SUPPLIER in _txt_lines(files)[0]
    assert _block(_month(world))["expense_before_itbis_minor"] == 100000

    reopened = _reopen(world, draft, approved["version"]).json()
    assert reopened["review_state"] == "open"
    assert reopened["version"] == approved["version"] + 1
    assert reopened["approval_result"] is None
    assert reopened["reopen_available"] is False
    assert reopened["approval_available"] is True
    assert reopened["dgii"]["category"] == "02", "the 606 data travels with the draft"
    assert reopened["facts"]["fiscal"]["ncf"]["value"] == "B0100000031"
    assert _group(first) == (True, 1), "the money row stays, marked reversed"
    assert _ledger(first) == [(None, None, "expense", "expense", "DOP", 118000)]
    month = _month(world)
    assert month["currencies"] == [] or _block(month)["expense_before_itbis_minor"] == 0
    assert _get(world, "/business/expenses", **SPAN).json()["items"] == []
    assert _get(world, "/business/overview", **SPAN).json()["totals"] == []
    _, csv_rows, files = _export(world)
    assert _txt_lines(files) == [] and csv_rows == []
    [row] = _rows(world)
    assert (row["draft_id"], row["stage"]) == (draft, "awaiting_approval")
    assert _waiting(world) == waiting, "the reopened row is back in the Bandeja"
    [receipt] = _reopen_receipts(world.alice.space_id, draft)
    assert (receipt["outcome"], receipt["activity_id"]) == ("applied", first)
    assert draft in _get(world, "/business/activity").text

    fixed = _review(
        world,
        draft,
        {
            "version": reopened["version"],
            "dgii": {
                "fiscal": {
                    "rnc": CORRECTED_SUPPLIER,
                    "ncf": "B0100000031",
                    "itbis": "180.00",
                },
                "declaration": reopened["dgii"],
            },
        },
        world.alice.headers,
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["dgii"]["category"] == "02", "the fix keeps the 606 data"
    again = _approve(world, draft, fixed.json()["version"], "expense")
    assert again.status_code == 200, again.text
    second = again.json()["approval_result"]["activity_id"]
    assert second != first
    assert _group(second) == (False, 1) and _group(first) == (True, 1)
    assert _block(_month(world))["expense_before_itbis_minor"] == 100000
    assert _get(world, "/business/overview", **SPAN).json()["totals"] == [
        {"currency": "DOP", "amount": "1180.00", "count": 1}
    ]
    [expense] = _get(world, "/business/expenses", **SPAN).json()["items"]
    assert expense["id"] == second
    [row] = _rows(world)
    assert (row["draft_id"], row["stage"]) == (draft, "ready_for_export")
    _, csv_rows, files = _export(world)
    [line] = _txt_lines(files)
    assert CORRECTED_SUPPLIER in line and BUYER_OR_SUPPLIER not in line
    assert len(csv_rows) == 1
    with Connection.connect(shared.DSN) as db:
        exported = db.execute(
            "select activity_id::text from public.business_dgii_export_lines"
            " where space_id=%s order by exported_at",
            (world.alice.space_id,),
        ).fetchall()
    assert [row[0] for row in exported] == [
        first,
        second,
    ], "both downloads stay on record"


def test_a_replay_changes_nothing_and_a_second_reopen_is_refused(world) -> None:  # noqa: ANN001, F811
    draft, dossier = _reviewed(world, "expense", "B0100000032")
    approved = _approve(world, draft, dossier["version"], "expense").json()
    activity = approved["approval_result"]["activity_id"]
    key = str(uuid4())
    first = _reopen(world, draft, approved["version"], key)
    assert first.status_code == 200, first.text
    replay = _reopen(world, draft, approved["version"], key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["version"] == first.json()["version"]
    assert len(_reopen_receipts(world.alice.space_id, draft)) == 1
    assert _group(activity) == (True, 1)

    stale = _reopen(world, draft, approved["version"])
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    opened = _reopen(world, draft, first.json()["version"])
    assert (opened.status_code, opened.json()["code"]) == (
        422,
        "business_draft_not_recorded",
    )
    assert _dossier(world, draft)["version"] == first.json()["version"]


def test_only_the_owner_reopens(world) -> None:  # noqa: ANN001, F811
    """Bob holds read and prepare on Alice's Business. He reads the record with
    no Reabrir, and the route refuses him; a read-only grant the same; without
    the grant header the record is not his to see."""

    draft, dossier = _reviewed(world, "expense", "B0100000033")
    approved = _approve(world, draft, dossier["version"], "expense").json()
    as_bob = _as(world.bob, world.grant)
    seen = world.client.get(f"{API}/business/drafts/{draft}/dossier", headers=as_bob)
    assert seen.status_code == 200 and seen.json()["reopen_available"] is False
    refused = _reopen(world, draft, approved["version"], headers=as_bob)
    assert (refused.status_code, refused.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set business_role='viewer',"
            " capabilities=%s where id=%s",
            (["read"], world.grant),
        )
        db.commit()
    viewer = _reopen(world, draft, approved["version"], headers=as_bob)
    assert (viewer.status_code, viewer.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    own = world.client.post(
        f"{API}/business/space", json={"name": "Taller de Bob"}, headers=world.bob.headers
    )
    assert own.status_code == 201, own.text
    stranger = _reopen(world, draft, approved["version"], headers=_as(world.bob))
    assert (stranger.status_code, stranger.json()["code"]) == (
        404,
        "business_record_not_found",
    )
    assert _dossier(world, draft)["review_state"] == "accepted"
    assert _reopen_receipts(world.alice.space_id, draft) == []


def test_a_credit_note_naming_the_record_holds_it(world) -> None:  # noqa: ANN001, F811
    draft, dossier = _reviewed(world, "expense", "B0100000034")
    approved = _approve(world, draft, dossier["version"], "expense").json()
    purchase = approved["approval_result"]["activity_id"]
    note = _note(world, world.alice, "Nota de crédito B0400000034")
    assert note.status_code == 200, note.text
    credit = note.json()["draft_id"]
    linked = _review(
        world,
        credit,
        {
            "version": _dossier(world, credit)["version"],
            "facts": _known(
                {
                    "kind": "refund",
                    "amount": "1180.00",
                    "currency": "DOP",
                    "occurred_on": "2026-09-05",
                }
            ),
            "dgii": {
                "fiscal": {
                    "rnc": BUYER_OR_SUPPLIER,
                    "ncf": "B0400000034",
                    "itbis": "180.00",
                },
                "declaration": _declaration(
                    "expense", actual_refund=True, purchase_activity_id=purchase
                ),
            },
        },
        world.alice.headers,
    )
    assert linked.status_code == 200, linked.text
    assert _dossier(world, draft)["reopen_available"] is False
    refused = _reopen(world, draft, approved["version"])
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_refund_linked",
    )
    assert _dossier(world, draft)["review_state"] == "accepted"
    assert _group(purchase) == (False, 1)


def test_a_bank_match_holds_the_record(bank) -> None:  # noqa: ANN001, F811
    checking = _checking(bank)
    receipt = _record(bank, checking, "expense", "150", "DOP", "2026-10-12", "Banco")
    _import(bank, checking, _statement([("12/10/2026", "COMISION A", "150.00", "")]))
    line = next(
        item
        for item in _movements(bank, bank.alice.headers)["items"]
        if "COMISION A" in json.dumps(item)
    )
    matched = _bank_post(
        bank,
        f"/movements/{line['id']}/match",
        bank.alice.headers,
        {"activity_id": receipt},
    )
    assert matched.status_code == 200, matched.text
    with Connection.connect(shared.DSN) as db:
        draft, version = db.execute(
            "select id::text,version from public.financial_import_events"
            " where activity_id=%s",
            (receipt,),
        ).fetchone()
    assert _dossier(bank, draft)["reopen_available"] is False
    refused = _reopen(bank, draft, version)
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "business_record_matched",
    )
    assert _group(receipt) == (False, 1)


def test_payment_status_and_marks_after_a_reopen(world) -> None:  # noqa: ANN001, F811
    """A payment mark stays on the reversed row as history and the reapproved
    record starts pendiente; the Personal mark and the remembered tipo de gasto
    travel with the draft."""

    draft, dossier = _reviewed(world, "expense", "B0100000035", category="04")
    approved = _approve(world, draft, dossier["version"], "expense").json()
    activity = approved["approval_result"]["activity_id"]
    _settle(world, activity, "pagado", "efectivo")
    assert [item["activity_id"] for item in _month(world)["cuentas_por_pagar"]] == []
    marked = world.client.post(
        f"{API}/business/drafts/{draft}/personal",
        json={"version": approved["version"], "personal": True},
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert marked.status_code == 200, marked.text

    reopened = _reopen(world, draft, marked.json()["version"]).json()
    assert reopened["personal"] is True
    sibling, _ = _reviewed(world, "expense", "B0100000036")
    assert _dossier(world, sibling)["expense_type_suggestion"] == "04"

    unmarked = world.client.post(
        f"{API}/business/drafts/{draft}/personal",
        json={"version": reopened["version"], "personal": False},
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert unmarked.status_code == 200, unmarked.text
    again = _approve(world, draft, unmarked.json()["version"], "expense").json()
    second = again["approval_result"]["activity_id"]
    month = _month(world)
    assert [item["activity_id"] for item in month["cuentas_por_pagar"]] == [second]
    with Connection.connect(shared.DSN) as db:
        kept = db.execute(
            "select activity_id::text,status from public.business_document_settlements"
            " where space_id=%s order by updated_at",
            (world.alice.space_id,),
        ).fetchall()
    assert kept == [(activity, "pagado")], "the mark stays on the reversed row"


def test_reversed_at_is_the_servers_alone(world) -> None:  # noqa: ANN001, F811
    """A Business money row is the server's: the row-level policy on
    financial_activity_groups shows it to no signed-in person, the owner
    included, and authenticated holds no update privilege, so reversed_at is
    written only by the reopen. The service role reads it."""

    draft, dossier = _reviewed(world, "expense", "B0100000037")
    approved = _approve(world, draft, dossier["version"], "expense").json()
    activity = approved["approval_result"]["activity_id"]
    assert _reopen(world, draft, approved["version"]).status_code == 200

    def claims(user_id: str) -> str:
        return json.dumps(
            {"sub": user_id, "role": "authenticated", "is_anonymous": False}
        )

    with Connection.connect(shared.DSN) as db, db.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('authenticated',"
            " 'public.financial_activity_groups', 'UPDATE')"
        )
        assert cursor.fetchone() == (False,)
        cursor.execute("set local role service_role")
        cursor.execute(
            "select reversed_at is not null from public.financial_activity_groups where id=%s",
            (activity,),
        )
        assert cursor.fetchone() == (True,)
        cursor.execute("set local role authenticated")
        for person in (world.alice, world.bob):
            cursor.execute(
                "select set_config('request.jwt.claims', %s, true)", (claims(person.id),)
            )
            cursor.execute(
                "select count(*) from public.financial_activity_groups where id=%s",
                (activity,),
            )
            assert cursor.fetchone() == (0,), person.email
        db.rollback()

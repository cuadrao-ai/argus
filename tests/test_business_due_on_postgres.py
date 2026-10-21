"""Over HTTP on the real app, Auth and Postgres: a person sets and clears a
record's due date in review, each change is a revision, nothing else fills it,
it locks once approved, and the dossier, the receipt detail, the month close
and the open items carry it, soonest due first. A local stub stands in for the
provider."""

from __future__ import annotations

import os

import pytest

from tests import test_financial_accounts_postgres as shared
from tests.test_business_document_type_postgres import (  # noqa: F401
    API,
    SUPPLIER_RNC,
    _account,
    _approve,
    _dossier,
    _facts,
    _receipt,
    _review,
    _upload,
    web,
)

pytestmark = pytest.mark.skipif(
    not (shared.DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)


def _due(value: str) -> dict:
    return {"due_on": {"state": "known", "value": value}}


def _revision(view: dict) -> tuple:
    last = view["history"][-1]
    return last["before_due_on"], last["after_due_on"]


def _pending_bills(world) -> list[tuple]:  # noqa: ANN001
    found = world.client.get(f"{API}/business/open-items", headers=world.alice.headers)
    assert found.status_code == 200, found.text
    return [
        (item["activity_id"], item["due_on"])
        for item in found.json()["cuentas_por_pagar"]["items"]
    ]


def test_a_person_sets_and_clears_the_due_date_and_it_locks_once_approved(web) -> None:  # noqa: ANN001, F811
    account = _account(web)
    receipt = _upload(web, SUPPLIER_RNC)
    draft = receipt["draft_id"]
    assert receipt["due_on"] is None
    assert _dossier(web, draft)["due_on"] is None

    dated = _review(web, draft, _due("2026-10-15"))
    assert dated.status_code == 200, dated.text
    view = dated.json()
    assert view["due_on"] == "2026-10-15"
    assert _revision(view) == (None, "2026-10-15")
    assert view["history"][-1]["before"] == view["history"][-1]["after"]
    assert _receipt(web, receipt["id"])["due_on"] == "2026-10-15"

    reviewed = _review(
        web, draft, {"facts": _facts("expense", "1180.00", "2026-09-03", account)}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["due_on"] == "2026-10-15"
    assert _revision(reviewed.json()) == ("2026-10-15", "2026-10-15")

    cleared = _review(web, draft, {"due_on": {"state": "unknown"}})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["due_on"] is None
    assert _revision(cleared.json()) == ("2026-10-15", None)
    assert _receipt(web, receipt["id"])["due_on"] is None

    bare_null = _review(web, draft, {"due_on": None})
    assert bare_null.status_code == 422, bare_null.text

    assert _review(web, draft, _due("2026-10-20")).status_code == 200
    _approve(web, draft, "record_expense")
    approved = _dossier(web, draft)
    assert approved["review_state"] == "accepted"
    assert approved["due_on"] == "2026-10-20"
    assert _revision(approved) == ("2026-10-20", "2026-10-20")

    locked = _review(web, draft, _due("2026-12-01"))
    assert (locked.status_code, locked.json()["code"]) == (
        422,
        "recorded_correction_unsupported",
    )
    cleared_late = _review(web, draft, {"due_on": {"state": "unknown"}})
    assert cleared_late.status_code == 422, cleared_late.text
    assert _dossier(web, draft)["due_on"] == "2026-10-20"
    assert _receipt(web, receipt["id"])["due_on"] == "2026-10-20"

    listed = web.client.get(
        f"{API}/business/receipts", params={"view": "all"}, headers=web.alice.headers
    )
    assert listed.status_code == 200, listed.text
    assert all("due_on" not in item for item in listed.json()["items"])


def test_open_items_put_the_due_bill_first_and_an_unset_due_date_stays_null(
    web,  # noqa: ANN001, F811
) -> None:
    account = _account(web)
    # No printed RNC, so the two share no comprobante.
    undated = _upload(web, None, occurred_on="2026-08-04", total="590.00")
    dated = _upload(web, SUPPLIER_RNC, occurred_on="2026-09-03", total="1180.00")
    activities = {}
    for receipt, amount, day, due in (
        (undated, "590.00", "2026-08-04", None),
        (dated, "1180.00", "2026-09-03", "2026-10-20"),
    ):
        draft = receipt["draft_id"]
        body = {"facts": _facts("expense", amount, day, account)}
        if due is not None:
            body.update(_due(due))
        reviewed = _review(web, draft, body)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["due_on"] == due
        _approve(web, draft, "record_expense")
        recorded = _dossier(web, draft)
        assert recorded["due_on"] == due
        activities[recorded["approval_result"]["activity_id"]] = due

    by_due = sorted(activities.items(), key=lambda item: item[1] is None)
    assert _pending_bills(web) == by_due

    month = web.client.get(
        f"{API}/business/month-close",
        params={"month": "2026-09"},
        headers=web.alice.headers,
    )
    assert month.status_code == 200, month.text
    assert [
        (item["activity_id"], item["due_on"])
        for item in month.json()["cuentas_por_pagar"]
    ] == [item for item in by_due if item[1] is not None]

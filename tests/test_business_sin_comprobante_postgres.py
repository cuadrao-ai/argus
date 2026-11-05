"""Sin comprobante over HTTP, on the real app, Auth and Postgres.

A purchase or a sale the owner states has no comprobante fiscal counts in the
month's income and expense, stays out of the 606 and the 607, and never holds
the month open. A record with a comprobante whose number is missing still
holds it open. The mark is a fact on the draft: editable while the draft is
open, kept in its history, and locked once the draft is approved.
"""

from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from argus.api.business_drafts import receipt_detail, receipt_summaries
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.month_close_store import read_month

from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_business_single_candidate_postgres as single
from tests.test_business_multi_purchase_postgres import _account as cash_account
from tests.test_business_receipt_views_postgres import _web as receipt_web
from tests.test_business_scope_switch_routes_postgres import (  # noqa: F401
    API,
    _code,
    web,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

actions = bridge.actions
users = bridge.users
pytestmark = _local_supabase
FIXTURES = Path(__file__).parent / "dgii/fixtures"
PRACTICE = {
    row["record_id"]: row["input"]
    for row in json.loads((FIXTURES / "practice-inputs.json").read_text())["records"]
}


def _send(world, method: str, path: str, body: dict, headers: dict):  # noqa: ANN001, ANN202
    answer = world.client.request(
        method,
        f"{API}{path}",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code in (200, 201), (path, answer.text)
    return answer.json()


def _get(world, path: str, **params):  # noqa: ANN001, ANN202
    answer = world.client.get(f"{API}{path}", params=params, headers=world.alice.headers)
    assert answer.status_code == 200, (path, answer.text)
    return answer


def _draft(world, account: str, kind: str, amount: str, day: str, name: str, **extra):  # noqa: ANN001, ANN202
    """Capture a typed entry and review it as the owner; the draft id and version."""

    owner = world.alice.headers
    note = _send(world, "POST", "/business/captures", {"text": name}, owner)
    facts = {
        field: {"state": "known", "value": value}
        for field, value in {
            "kind": kind,
            "amount": amount,
            "occurred_on": day,
            "counterparty": name,
            "funding": {"kind": "business_account", "account_id": account},
            "business_share": {"kind": extra.pop("share", "all")},
            "currency": extra.pop("currency", "DOP"),
        }.items()
    }
    receipt_state = extra.pop("receipt_state", None)
    if receipt_state:
        facts["receipt_state"] = {"state": "known", "value": receipt_state}
    body = {"version": note["version"], "facts": facts, **extra}
    reviewed = _send(
        world, "PATCH", f"/business/drafts/{note['draft_id']}/review", body, owner
    )
    return note["draft_id"], reviewed["version"]


def _stated_itbis(practice: str, itbis: str, **declared: str) -> dict:
    """A fiscal review that states ITBIS and no RNC or fiscal number."""

    declaration = {**PRACTICE[practice]["declaration"], **declared}
    return {
        "fiscal": {"rnc": None, "ncf": None, "itbis": itbis},
        "declaration": declaration,
    }


def _approve(world, draft: str, version: int, kind: str) -> str:  # noqa: ANN001
    approved = _send(
        world,
        "POST",
        f"/business/drafts/{draft}/approve",
        {"version": version, "action": f"record_{kind}"},
        world.alice.headers,
    )
    return approved["approval_result"]["activity_id"]


def _record(world, account, kind, amount, day, name, **extra) -> tuple[str, str]:  # noqa: ANN001
    draft, version = _draft(world, account, kind, amount, day, name, **extra)
    return draft, _approve(world, draft, version, kind)


def _close(world, month: str) -> dict:  # noqa: ANN001
    return _get(world, "/business/month-close", month=month).json()


def _packet(world, start: str, end: str) -> dict:  # noqa: ANN001
    answer = _get(world, "/business/exports", start=start, end=end)
    with zipfile.ZipFile(io.BytesIO(answer.content)) as archive:
        return json.loads(archive.read("dgii/summary.json"))


def test_sin_comprobante_counts_in_the_month_and_stays_out_of_the_606_and_607(
    web,  # noqa: ANN001, F811
) -> None:
    pesos = _send(
        web,
        "POST",
        "/business/accounts",
        {"nickname": "Caja", "type": "cash", "currency": "DOP"},
        web.alice.headers,
    )["id"]
    # Editable while open: first stated as a fiscal receipt, then corrected.
    draft, version = _draft(
        web,
        pesos,
        "expense",
        "500",
        "2026-09-08",
        "Colmado",
        receipt_state="fiscal_receipt",
        dgii=_stated_itbis("P01", "76.27", goods_amount="423.73", paid_on="2026-09-08"),
    )
    dossier = _get(web, f"/business/drafts/{draft}/dossier").json()
    assert dossier["sin_comprobante"] is False
    corrected = _send(
        web,
        "PATCH",
        f"/business/drafts/{draft}/review",
        {
            "version": version,
            "facts": {"receipt_state": {"state": "known", "value": "no_receipt"}},
        },
        web.alice.headers,
    )
    assert corrected["sin_comprobante"] is True
    assert corrected["facts"]["receipt_state"]["origin"] == "member_set"
    last = corrected["history"][-1]
    assert last["before"]["receipt_state"]["value"] == "fiscal_receipt"
    assert last["after"]["receipt_state"]["value"] == "no_receipt"
    cash_purchase = _approve(web, draft, corrected["version"], "expense")
    _, cash_sale = _record(
        web,
        pesos,
        "income",
        "300",
        "2026-09-09",
        "Venta en efectivo",
        receipt_state="informal_receipt",
        dgii=_stated_itbis("S01", "45.76", billed_amount="254.24", bank="300.00"),
    )
    _, fiscal_purchase = _record(
        web, pesos, "expense", "1180", "2026-09-03", "PRÁCTICA P01", dgii=PRACTICE["P01"]
    )
    _, fiscal_sale = _record(
        web, pesos, "income", "2360", "2026-09-16", "PRÁCTICA S01", dgii=PRACTICE["S01"]
    )
    dollars = _send(
        web,
        "POST",
        "/business/accounts",
        {"nickname": "Caja USD", "type": "cash", "currency": "USD"},
        web.alice.headers,
    )["id"]
    _, dollar_purchase = _record(
        web,
        dollars,
        "expense",
        "80",
        "2026-09-10",
        "Tienda en Miami",
        currency="USD",
        receipt_state="no_receipt",
    )
    personal_draft, personal_purchase = _record(
        web,
        pesos,
        "expense",
        "900",
        "2026-09-11",
        "Supermercado",
        share="none",
        receipt_state="no_receipt",
    )
    personal = _get(web, f"/business/drafts/{personal_draft}/dossier").json()
    assert (personal["personal"], personal["sin_comprobante"]) == (True, True)

    september = _close(web, "2026-09")
    assert september["closed"] is True
    assert september["reasons"] == []
    assert september["missing_rnc"] == september["missing_ncf"] == []
    dop, usd = september["currencies"]
    assert (usd["currency"], usd["expense_before_itbis_minor"]) == ("USD", 8000)
    assert (usd["itbis_paid_minor"], usd["income_before_itbis_minor"]) == (0, 0)
    # P01 is 1000.00 before 180.00 ITBIS and S01 2000.00 before 360.00. The cash
    # purchase's 76.27 ITBIS cannot be credited, so its whole 500.00 is cost. The
    # cash sale counts 254.24 and its stated 45.76 ITBIS stays charged.
    assert (dop["expense_before_itbis_minor"], dop["income_before_itbis_minor"]) == (
        150000,
        225424,
    )
    assert (dop["itbis_paid_minor"], dop["itbis_charged_minor"]) == (18000, 40576)
    amounts = {
        line["activity_id"]: (line["before_itbis_minor"], line["itbis_minor"])
        for line in september["cuentas_por_pagar"] + september["cuentas_por_cobrar"]
    }
    assert amounts[cash_purchase] == (50000, 7627)
    assert amounts[cash_sale] == (25424, 4576)
    lines = {
        line["activity_id"]: line["sin_comprobante"]
        for line in september["cuentas_por_pagar"] + september["cuentas_por_cobrar"]
    }
    assert lines == {
        cash_purchase: True,
        cash_sale: True,
        dollar_purchase: True,
        fiscal_purchase: False,
        fiscal_sale: False,
    }
    opened = _get(web, "/business/open-items").json()
    assert {
        item["activity_id"]: item["sin_comprobante"]
        for side in ("cuentas_por_pagar", "cuentas_por_cobrar")
        for item in opened[side]["items"]
    } == lines

    packet = _packet(web, "2026-09-01", "2026-09-30")
    assert (
        packet["forms"]["606"]["record_count"],
        packet["forms"]["607"]["record_count"],
    ) == (1, 1)
    bridge_rows = {row["activity_id"]: row for row in packet["reconciliation"]}
    for activity in (cash_purchase, cash_sale, dollar_purchase):
        assert (
            bridge_rows[activity]["disposition"],
            bridge_rows[activity]["reason"],
        ) == (
            "excluded",
            "no_fiscal_number",
        )
    # The Personal mark keeps a record out before its missing number is looked at.
    assert (
        bridge_rows[personal_purchase]["disposition"],
        bridge_rows[personal_purchase]["reason"],
    ) == ("excluded", "personal")
    assert {bridge_rows[a]["disposition"] for a in (fiscal_purchase, fiscal_sale)} == {
        "606",
        "607",
    }
    named = {issue.get("activity_id") for issue in packet["issues"]}
    assert not named & {cash_purchase, cash_sale, dollar_purchase, personal_purchase}

    # Every read carries the mark: the dossier, the expense list and the detail.
    assert (
        _get(web, f"/business/drafts/{draft}/dossier").json()["sin_comprobante"] is True
    )
    expenses = {
        item["id"]: item
        for item in _get(
            web, "/business/expenses", **{"from": "2026-09-01", "to": "2026-09-30"}
        ).json()["items"]
    }
    assert expenses[cash_purchase]["sin_comprobante"] is True
    assert "sin_comprobante" not in expenses[fiscal_purchase]
    detail = _get(web, f"/business/expenses/{cash_purchase}").json()
    assert detail["sin_comprobante"] is True

    # Locked after approval, like every other fact.
    locked = web.client.patch(
        f"{API}/business/drafts/{draft}/review",
        json={
            "version": _get(web, f"/business/drafts/{draft}/dossier").json()["version"],
            "facts": {"receipt_state": {"state": "known", "value": "fiscal_receipt"}},
        },
        headers={**web.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert _code(locked) == (422, "recorded_correction_unsupported"), locked.text
    assert (
        _get(web, f"/business/drafts/{draft}/dossier").json()["sin_comprobante"] is True
    )
    assert _close(web, "2026-09") == september


def test_a_record_with_a_comprobante_and_no_number_still_holds_the_month_open(
    web,  # noqa: ANN001, F811
) -> None:
    pesos = _send(
        web,
        "POST",
        "/business/accounts",
        {"nickname": "Caja", "type": "cash", "currency": "DOP"},
        web.alice.headers,
    )["id"]
    _, with_comprobante = _record(
        web,
        pesos,
        "expense",
        "700",
        "2026-08-04",
        "Ferretería",
        receipt_state="fiscal_receipt",
    )
    _, never_said = _record(web, pesos, "expense", "200", "2026-08-05", "Papelería")
    _record(
        web, pesos, "expense", "100", "2026-08-06", "Colmado", receipt_state="no_receipt"
    )

    august = _close(web, "2026-08")
    assert august["closed"] is False
    blocked = [(reason["code"], reason["activity_id"]) for reason in august["reasons"]]
    assert blocked == [
        ("missing_rnc", with_comprobante),
        ("missing_ncf", with_comprobante),
        ("missing_rnc", never_said),
        ("missing_ncf", never_said),
    ]
    assert [line["activity_id"] for line in august["missing_ncf"]] == [
        with_comprobante,
        never_said,
    ]
    [dop] = august["currencies"]
    assert dop["expense_before_itbis_minor"] == 10000


@pytest.mark.owner_acts
@pytest.mark.parametrize(
    ("receipt", "marked", "expense", "itbis_paid"),
    [
        # 4676.47 ITBIS without a comprobante cannot be credited: the whole
        # 33254.91 is cost. With the e-CF it is creditable ITBIS paid.
        # The e-CF case uses an RNC whose check digit passes, so approve
        # needs no review-flag confirmation.
        ({"rnc": None, "ecf": None}, True, 3325491, 0),
        ({"rnc": "131111221"}, False, 2857844, 467647),
    ],
    ids=["read-without-a-fiscal-number", "read-with-an-e-cf"],
)
def test_an_uploaded_receipt_reads_its_mark_after_prepare(
    actions,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
    receipt: dict,
    marked: bool,
    expense: int,
    itbis_paid: int,
) -> None:
    monkeypatch.setattr(single, "RECEIPT", {**single.RECEIPT, **receipt})
    saved = single._saved(actions, "expense")
    service, context, _, cid, _, _ = saved
    bridge.bind(saved)
    prepared = bridge.finish(saved)
    assert prepared.outcome == "applied", prepared
    funding = cash_account(service, context)
    reviewed = service.review(
        context,
        prepared.draft_id,
        ReviewDraft(
            version=service.dossier(context, prepared.draft_id).version,
            facts=BusinessFactPatch.model_validate(
                {
                    "funding": {
                        "state": "known",
                        "value": {"kind": "business_account", "account_id": funding},
                    },
                    "business_share": {"state": "known", "value": {"kind": "all"}},
                    "receipt_state": {"state": "known", "value": "no_receipt"},
                }
            ),
        ),
        "sin-comprobante",
    )
    assert reviewed.outcome == "applied", reviewed
    approved = service.approve(
        context,
        prepared.draft_id,
        ApproveExpense(version=reviewed.version, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied", approved
    views = receipt_web(service, context)
    [row] = [item for item in receipt_summaries(views, "all") if item["id"] == cid]
    detail = receipt_detail(views, views.service.receipt(views.scope, cid))
    assert Decimal(row["amount"]) == Decimal("33254.91")
    assert row.get("sin_comprobante", False) is marked
    assert detail.get("sin_comprobante", False) is marked
    assert service.dossier(context, prepared.draft_id).sin_comprobante is marked
    october = read_month(service.authority, context, "2026-10")
    [dop] = october["currencies"]
    assert (dop["expense_before_itbis_minor"], dop["itbis_paid_minor"]) == (
        expense,
        itbis_paid,
    )
    [line] = october["cuentas_por_pagar"]
    assert line["sin_comprobante"] is marked

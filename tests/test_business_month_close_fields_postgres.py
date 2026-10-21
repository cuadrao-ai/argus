"""Over HTTP on the real app, Auth and Postgres: the month close and the open
items carry the server's today, overdue over every open item, the ITBIS
cobrado, the per-currency final mark, the payment methods, the earliest month
and the 606 and 607 statuses the export packet itself writes. A second approval
of one sale NCF is refused by the database when the read misses it.
"""

from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
from zipfile import ZipFile

from argus.domain.business import ledger
from argus.domain.business.actions import approval
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_open_items_postgres import (  # noqa: F401
    API,
    PRACTICE,
    _account,
    _open,
    _send,
    _settle,
    web,
)
from tests.test_business_open_items_postgres import pytestmark as _local_supabase

pytestmark = _local_supabase
OWN_RNC = "199990013"
METHODS = ["efectivo", "transferencia", "tarjeta", "credito", "otro"]
FORMS = ("606", "607")


def _reviewed(
    world,  # noqa: ANN001
    account: str,
    kind: str,
    amount: str,
    currency: str,
    day: str,
    counterparty: str,
    practice: str | None = None,
    due_on: str | None = None,
) -> tuple[str, int]:
    """Capture and review one document as the owner; its draft id and version."""

    owner = world.alice.headers
    note = _send(world, "POST", "/business/captures", {"text": counterparty}, owner)
    facts = {
        name: {"state": "known", "value": value}
        for name, value in {
            "kind": kind,
            "amount": amount,
            "currency": currency,
            "occurred_on": day,
            "counterparty": counterparty,
            "funding": {"kind": "business_account", "account_id": account},
            "business_share": {"kind": "all"},
        }.items()
    }
    review = {"version": note["version"], "facts": facts}
    if practice:
        review["dgii"] = PRACTICE[practice]
    if due_on:
        review["due_on"] = {"state": "known", "value": due_on}
    reviewed = _send(
        world, "PATCH", f"/business/drafts/{note['draft_id']}/review", review, owner
    )
    return note["draft_id"], reviewed["version"]


def _approve(world, draft: str, version: int, kind: str, key: str | None = None):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/business/drafts/{draft}/approve",
        json={"version": version, "action": f"record_{kind}"},
        headers={**world.alice.headers, "Idempotency-Key": key or str(uuid4())},
    )


def _record(world, *args, **kwargs) -> str:  # noqa: ANN001, ANN002, ANN003
    draft, version = _reviewed(world, *args, **kwargs)
    approved = _approve(world, draft, version, args[1])
    assert approved.status_code in (200, 201), approved.text
    return approved.json()["approval_result"]["activity_id"]


def _month(world, month: str) -> dict:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/month-close",
        params={"month": month},
        headers=world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _export_forms(world, start: str, end: str) -> dict[str, str]:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/exports",
        params={"start": start, "end": end},
        headers=world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    with ZipFile(io.BytesIO(answer.content)) as archive:
        forms = json.loads(archive.read("manifest.json"))["dgii"]["forms"]
    return {form: forms[form]["status"] for form in FORMS}


def _set_own_rnc(world) -> None:  # noqa: ANN001
    name = f"Negocio de {world.alice.email}"
    saved = world.client.patch(
        f"{API}/business/fiscal-profile",
        json={
            "name": name,
            "previous_name": name,
            "tax_id": {"type": "rnc", "value": OWN_RNC},
            "previous_tax_id": None,
        },
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text


def test_the_month_and_the_open_items_carry_the_server_owned_fields(web) -> None:  # noqa: ANN001, F811
    today = ledger.today()
    owner = web.alice.headers
    pesos, dollars = _account(web, "DOP"), _account(web, "USD")
    collected = _record(
        web, pesos, "income", "2360", "DOP", "2026-09-16", "PRÁCTICA S01", "S01"
    )
    _settle(web, collected, "cobrado", owner)
    _record(
        web,
        pesos,
        "income",
        "590",
        "DOP",
        "2026-09-18",
        "PRÁCTICA S02",
        "S02",
        due_on=(today - timedelta(days=1)).isoformat(),
    )
    _record(web, pesos, "expense", "1180", "DOP", "2026-09-03", "PRÁCTICA P01", "P01")
    _record(
        web,
        dollars,
        "income",
        "150",
        "USD",
        "2026-10-02",
        "Cliente en dólares",
        due_on=(today + timedelta(days=10)).isoformat(),
    )

    september = _month(web, "2026-09")
    assert september["today"] == today.isoformat()
    assert september["payment_methods"] == METHODS
    assert september["earliest_month"] == "2026-09"
    assert september["dgii_forms"] == {"606": "no_aplica", "607": "no_aplica"}
    [block] = september["currencies"]
    assert block["currency"] == "DOP"
    # S01 states 360.00 of ITBIS and is the only sale marked cobrado.
    assert (block["itbis_cobrado_minor"], block["itbis_cobrado"]) == (36000, "360.00")
    assert block["itbis_charged_minor"] == 36000 + 9000
    assert block["net_result_final"] is False

    october = _month(web, "2026-10")
    [usd] = october["currencies"]
    assert (usd["currency"], usd["net_result_final"], usd["itbis_cobrado_minor"]) == (
        "USD",
        False,
        0,
    )
    assert october["earliest_month"] == "2026-09"

    opened = _open(web, owner)
    assert opened["today"] == today.isoformat()
    cobrar, pagar = opened["cuentas_por_cobrar"], opened["cuentas_por_pagar"]
    assert cobrar["count"] == 2
    assert cobrar["overdue"] == {
        "count": 1,
        "totals": [{"currency": "DOP", "total_minor": 59000, "total": "590.00"}],
    }
    # The bill has no due date, so nothing in Por pagar is overdue.
    assert pagar["overdue"] == {"count": 0, "totals": []}

    _set_own_rnc(web)
    for month, start, end in (
        ("2026-09", "2026-09-01", "2026-09-30"),
        ("2026-10", "2026-10-01", "2026-10-31"),
    ):
        statuses = _month(web, month)["dgii_forms"]
        assert statuses == _export_forms(web, start, end), month
        assert set(statuses.values()) <= {
            "needs_review",
            "summary_only",
            "no_operations",
            "prepared_candidate",
        }


def test_a_second_approval_of_one_sale_ncf_is_refused_by_the_database(
    web,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    # With the approval's own read switched off, only the index stands between
    # two approvals of the same comprobante.
    monkeypatch.setattr(approval, "require_distinct_fiscal_document", lambda *_: None)
    pesos = _account(web, "DOP")
    first = _reviewed(web, pesos, "income", "2360", "DOP", "2026-09-16", "Uno", "S01")
    second = _reviewed(web, pesos, "income", "2360", "DOP", "2026-09-17", "Dos", "S01")
    keys = (str(uuid4()), str(uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(
            pool.map(
                lambda pair: _approve(web, pair[0][0], pair[0][1], "income", pair[1]),
                zip((first, second), keys, strict=True),
            )
        )
    statuses = sorted(answer.status_code for answer in answers)
    assert statuses == [200, 422], [answer.text for answer in answers]
    [refused] = [answer for answer in answers if answer.status_code == 422]
    assert refused.json()["code"] == "fiscal_duplicate_document"
    [won] = [answer for answer in answers if answer.status_code == 200]
    assert won.json()["approval_result"]["activity_id"]

    # The refusal is a stored receipt: the same key replays it.
    index = answers.index(refused)
    replay = _approve(
        web, (first, second)[index][0], (first, second)[index][1], "income", keys[index]
    )
    assert (replay.status_code, replay.json()["code"]) == (
        422,
        "fiscal_duplicate_document",
    )

    with Connection.connect(shared.DSN) as db:
        approved = db.execute(
            """select count(*) from public.financial_import_events
               where owner_space_id = %s and state in ('accepting', 'accepted')
                 and resolution->'business'->'facts'->'fiscal'->'ncf'->>'value' = %s""",
            (web.alice.space_id, PRACTICE["S01"]["fiscal"]["ncf"]),
        ).fetchone()[0]
    assert approved == 1

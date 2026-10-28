"""The Personal mark after approval, on every reader at once, over HTTP on the
real app, Auth and Postgres.

The mark lives on the draft as it stands now and changes after approval.
Registros, month close, the export handoff and the DGII packet all read it
there, so marking, unmarking and marking again moves the record out of and
back into the Business on every surface in one step.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

from tests.test_business_scope_switch_routes_postgres import API, web  # noqa: F401
from tests.test_business_sin_comprobante_postgres import (
    PRACTICE,
    _close,
    _get,
    _record,
    _send,
)
from tests.test_business_sin_comprobante_postgres import pytestmark as _local_supabase

pytestmark = _local_supabase
MONTH, START, END = "2026-09", "2026-09-01", "2026-09-30"


def _registros(world) -> dict:  # noqa: ANN001
    answer = world.client.post(
        f"{API}/business/reports/query", json={}, headers=world.alice.headers
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _package(world) -> tuple[list[dict], list[dict], dict, dict]:  # noqa: ANN001
    answer = _get(world, "/business/exports", start=START, end=END)
    with zipfile.ZipFile(io.BytesIO(answer.content)) as archive:

        def sheet(name: str) -> list[dict]:
            return list(
                csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig")))
            )

        return (
            sheet("records.csv"),
            sheet("personal.csv"),
            json.loads(archive.read("dgii/summary.json")),
            json.loads(archive.read("manifest.json")),
        )


def _mark(world, draft: str, personal: bool) -> None:  # noqa: ANN001
    version = _get(world, f"/business/drafts/{draft}/dossier").json()["version"]
    _send(
        world,
        "POST",
        f"/business/drafts/{draft}/personal",
        {"version": version, "personal": personal},
        world.alice.headers,
    )


def _everywhere(world, activity: str) -> dict:  # noqa: ANN001
    """What each reader says about ``activity`` beside the one business record."""

    registros = _registros(world)
    rows = {row["linked_activity_ids"][0]: row for row in registros["items"]}
    totals = {
        total["basis"]: (total["matching_count"], total["amount"])
        for total in registros["totals"]
        if total["kind"] == "expense" and total["currency"] == "DOP"
    }
    close = _close(world, MONTH)
    [pesos] = close["currencies"]
    records, personal, summary, manifest = _package(world)
    disposition = {
        item["activity_id"]: (item["disposition"], item["reason"])
        for item in summary["reconciliation"]
    }
    canonical = {row["activity_id"]: row for row in manifest["records"]}
    return {
        "row": (rows[activity]["personal"], rows[activity]["include_606"]),
        "registros": (
            totals["recorded_activity_amount"],
            totals["document_family_amount"],
        ),
        "close": (
            pesos["expense_before_itbis_minor"],
            pesos["itbis_paid_minor"],
            sorted(line["activity_id"] for line in close["cuentas_por_pagar"]),
        ),
        "handoff": (
            sorted(row["Total"] for row in records),
            [row["Registro"] for row in personal],
            canonical[activity]["personal"],
        ),
        "packet": (disposition[activity], summary["forms"]["606"]["record_count"]),
    }


def test_the_mark_moves_the_record_on_every_reader_at_once(web) -> None:  # noqa: ANN001, F811
    pesos = _send(
        web,
        "POST",
        "/business/accounts",
        {"nickname": "Caja", "type": "cash", "currency": "DOP"},
        web.alice.headers,
    )["id"]
    # P01 is 1000.00 before 180.00 ITBIS; the informal receipt costs its whole 500.00.
    draft, purchase = _record(
        web, pesos, "expense", "1180", "2026-09-03", "PRÁCTICA P01", dgii=PRACTICE["P01"]
    )
    _, informal = _record(
        web,
        pesos,
        "expense",
        "500",
        "2026-09-08",
        "Colmado",
        receipt_state="informal_receipt",
    )
    business = {
        "row": (False, None),
        "registros": ((2, "1680.00"), (2, "1680.00")),
        "close": (150000, 18000, sorted([purchase, informal])),
        "handoff": (["1180.00", "500.00"], [], "no"),
        "packet": (("606", "included"), 1),
    }
    personal = {
        "row": (True, None),
        "registros": ((1, "500.00"), (1, "500.00")),
        "close": (50000, 0, [informal]),
        "handoff": (["500.00"], [purchase], "yes"),
        "packet": (("excluded", "personal"), 0),
    }
    assert _everywhere(web, purchase) == business

    _mark(web, draft, True)
    assert _everywhere(web, purchase) == personal
    _, handed, _, manifest = _package(web)
    originals = {source["source_id"]: source["file"] for source in manifest["sources"]}
    assert handed[0]["Originales"] and set(handed[0]["Originales"].split(";")) <= set(
        originals.values()
    )

    _mark(web, draft, False)
    assert _everywhere(web, purchase) == business

    _mark(web, draft, True)
    assert _everywhere(web, purchase) == personal

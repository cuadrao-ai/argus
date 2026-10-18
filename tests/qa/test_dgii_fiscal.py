"""Practice 606/607 rows, the bank CSV, and the lines Plaid should mirror."""

from __future__ import annotations

import csv
import importlib
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "scripts" / "qa"
FIXTURES = ROOT / "fixtures" / "dgii"
sys.path.insert(0, str(QA))
fiscal = importlib.import_module("dgii_fiscal")

CANON = fiscal.Period(date(2026, 9, 1), date(2026, 9, 30))
DRY = fiscal.Period(fiscal.DRY_RUN_START, fiscal.DRY_RUN_END)


def test_check_digits_match_the_practice_header() -> None:
    header = (FIXTURES / "606_mock_202609.txt").read_bytes().split(b"\r\n", 1)[0].decode()
    assert fiscal.dv_rnc("13999900") == 1
    assert fiscal.EMPRESA == header.split("|")[1]
    assert fiscal.valid_rnc(fiscal.EMPRESA)
    assert fiscal.valid_cedula(fiscal.CEDULA_CLIENTE)
    assert fiscal.rnc("00000000") == "000000002"
    assert fiscal.valid_rnc("139999000") is False


def test_ncf_widths_and_607_rejects_electronic() -> None:
    assert len(fiscal.ncf("01", 1)) == 11
    assert len(fiscal.encf("31", 1)) == 13
    assert fiscal.RX_NCF_606.match(fiscal.encf("31", 1234))
    assert fiscal.RX_NCF_607.match(fiscal.encf("31", 1)) is None


def test_itbis_and_resumen_match_the_practice_note() -> None:
    assert fiscal.q(Decimal(1000) * fiscal.ITBIS_RATE) == Decimal("180.00")
    assert fiscal.q(0) == Decimal("0.00")
    note = (FIXTURES / "resumen_ITBIS_202609.md").read_text(encoding="utf-8")
    totals = fiscal.summary()
    shown = {
        "ventas_monto": "841,000.00",
        "consumo_monto": "180,550.00",
        "ingresos": "1,021,550.00",
        "itbis_facturado": "173,079.00",
        "itbis_adelantar": "31,896.00",
        "itbis_neto": "134,703.00",
        "itbis_enterar": "138,303.00",
        "resultado": "823,450.00",
        "resultado_sin_activos": "888,450.00",
    }
    for key, text in shown.items():
        assert f"{totals[key]:,.2f}" == text
        assert text in note


def test_september_catalog_matches_the_practice_files() -> None:
    assert fiscal.practice_606() == (FIXTURES / "606_mock_202609.txt").read_bytes()
    assert fiscal.practice_607() == (FIXTURES / "607_mock_202609.txt").read_bytes()
    assert (
        fiscal.practice_606()
        == (FIXTURES / "DGII_F_606_139999001_202609.TXT").read_bytes()
    )
    assert (
        fiscal.practice_607()
        == (FIXTURES / "DGII_F_607_139999001_202609.TXT").read_bytes()
    )


def test_practice_files_and_shifted_period_share_layout() -> None:
    september = fiscal.build_plan(CANON)
    october = fiscal.build_plan(DRY)
    for payload in (
        september.practica_606,
        september.practica_607,
        october.practica_606,
        october.practica_607,
        (FIXTURES / "606_mock_202609.txt").read_bytes(),
        (FIXTURES / "607_mock_202609.txt").read_bytes(),
    ):
        assert fiscal.layout_issues(payload) == []
    assert october.practica_606 != september.practica_606
    assert (
        october.practica_606.split(b"\r\n", 1)[0]
        .decode()
        .startswith("606|139999001|202610|")
    )
    assert (
        october.practica_607.split(b"\r\n", 1)[0]
        .decode()
        .startswith("607|139999001|202610|")
    )


def test_valid_rows_pass_and_small_consumo_stays_out_of_607() -> None:
    assert fiscal.issues_for(fiscal.purchases(), "606") == []
    assert fiscal.issues_for(fiscal.sales(), "607") == []
    detail = fiscal.practice_607().decode().split("\r\n")[1:]
    consumo = [line for line in detail if "|B02" in line]
    assert len(consumo) == 1
    assert "300000.00" in consumo[0]
    assert len(fiscal.consumo_amounts()) == 40
    assert all(amount < fiscal.B02_THRESHOLD for amount in fiscal.consumo_amounts())


@pytest.mark.parametrize(
    "code",
    [
        "id-longitud",
        "id-tipo",
        "ncf-longitud",
        "encf-en-607",
        "b02-bajo-umbral",
        "pagos-no-cuadran",
        "retencion-sin-fecha",
        "sin-rnc",
        "ncf-duplicado",
        "rnc-digito",
    ],
)
def test_each_broken_row_names_its_rejection(code: str) -> None:
    rows = fiscal.defect_rows()[code]
    if code == "retencion-sin-fecha":
        assert "retencion-sin-fecha" in fiscal.issues_for([rows[0]], "607")
        assert "retencion-sin-fecha" in fiscal.issues_for([rows[1]], "606")
        return
    assert code in fiscal.issues_for(rows, rows[0]["formato"])


def test_seed_tags_the_same_breaks_and_keeps_the_older_ones() -> None:
    documents = fiscal.documents_for(DRY)
    tags = {document.tag for document in documents}
    for code in (
        "id-longitud",
        "id-tipo",
        "ncf-longitud",
        "encf-en-607",
        "b02-bajo-umbral",
        "pagos-no-cuadran",
        "retencion-sin-fecha",
        "sin-rnc",
        "ncf-duplicado",
        "rnc-digito",
    ):
        assert code in tags
    broken = [
        document for document in documents if document.tag not in {None, "consumo-ofv"}
    ]
    assert all(document.counterparty.startswith("QA-SEED roto:") for document in broken)
    assert all(document.filename.startswith("qa-seed-") for document in documents)
    assert all(len(document.filename) <= 80 for document in documents)
    notes = [document for document in documents if document.kind == "refund"]
    assert notes
    assert all(document.approval == "unsupported" for document in notes)


def test_period_shift_keeps_september_and_lands_inside_october() -> None:
    september = fiscal.documents_for(CANON)
    october = fiscal.documents_for(DRY)
    assert any(document.occurred_on == date(2026, 9, 3) for document in september)
    assert all(DRY.start <= document.occurred_on <= DRY.end for document in october)
    assert [document.ncf for document in september] == [
        document.ncf for document in october
    ]


def test_names_follow_the_seed_and_fiscal_ids_do_not() -> None:
    first = fiscal.documents_for(DRY, seed=202609)
    again = fiscal.documents_for(DRY, seed=202609)
    other = fiscal.documents_for(DRY, seed=7)
    assert [document.body for document in first] == [document.body for document in again]
    assert [document.rnc for document in first] == [document.rnc for document in other]
    assert [document.counterparty for document in first] != [
        document.counterparty for document in other
    ]


def test_bank_csv_layout_matches_plaid_and_the_manifest() -> None:
    plan = fiscal.build_plan(DRY, seed=202609)
    rows = list(csv.DictReader(plan.csv_body.splitlines()))
    assert list(rows[0]) == ["date", "description", "amount", "type"]
    assert {row["type"] for row in rows} <= {"débito", "crédito"}
    plaid = fiscal.plaid_transactions(plan.lines)
    assert len(rows) == len(plaid) == len(plan.lines)
    documents = {document.filename: document for document in plan.documents}
    paired = {pair["filename"] for pair in plan.manifest["pairs"]}
    debits = [line for line in plan.lines if line.type == "débito"]
    purchase_pairs = [
        line
        for line in debits
        if line.tag is None and documents[line.filename].kind == "expense"
    ]
    assert purchase_pairs
    assert len(purchase_pairs) > len(debits) / 2
    sin_comprobante = [line for line in plan.lines if line.tag == "sin-comprobante"]
    assert len(sin_comprobante) >= 2
    assert all(line.filename is None for line in sin_comprobante)
    assert {line.tag for line in plan.lines} >= {
        "sin-comprobante",
        "ruido:comision",
        "ruido:pago-parcial",
        "ruido:cerca",
    }
    amounts = {document.amount for document in plan.documents}
    for line, row, transaction in zip(plan.lines, rows, plaid, strict=False):
        assert (
            row["date"] == line.occurred_on.isoformat() == transaction["date_transacted"]
        )
        assert row["description"] == line.description == transaction["description"]
        assert Decimal(row["amount"]) == line.amount
        assert transaction["iso_currency_code"] == "DOP"
        assert "QA-SEED" in line.description
        signed = Decimal(str(transaction["amount"]))
        if line.type == "débito":
            assert signed == line.amount
        else:
            assert signed == -line.amount
        assert DRY.start <= line.occurred_on <= DRY.end
        if line.tag == "sin-comprobante":
            assert line.amount not in amounts
        if line.tag is None:
            document = documents[line.filename]
            assert line.filename in paired
            assert line.amount == document.amount
            assert (
                abs((line.occurred_on - document.occurred_on).days)
                <= fiscal.MATCH_WINDOW_DAYS
            )
            assert document.counterparty in line.description
    partial = next(line for line in plan.lines if line.tag == "ruido:pago-parcial")
    assert partial.filename not in paired
    assert partial.amount == documents[partial.filename].amount / 2
    reasons = {row["reason"] for row in plan.manifest["unmatched_documents"]}
    assert "sin-rnc" in reasons
    assert "ncf-duplicado" in reasons
    assert "b02-bajo-umbral" in reasons
    assert "pago-parcial" in reasons


def test_review_cannot_store_the_practice_declaration_columns() -> None:
    from argus.domain.business.contracts.facts import BusinessFactPatch
    from argus.domain.recording.payments import PAYMENT_KINDS

    assert set(BusinessFactPatch.model_fields) == {
        "amount",
        "business_share",
        "category_id",
        "counterparty",
        "currency",
        "funding",
        "kind",
        "occurred_on",
        "receipt_state",
    }
    for name in fiscal.UNSUPPORTED_DECLARATION_FIELDS:
        assert name not in BusinessFactPatch.model_fields
    assert PAYMENT_KINDS == {"card_payment", "debt_payment"}


def test_dry_run_writes_the_files_and_does_not_open_a_database(tmp_path: Path) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "SUPABASE_URL": "https://lgdhvepyrzbnscqssgqq.supabase.co",
        "DATABASE_URL": "postgresql://postgres:secret-should-not-print@db.lgdhvepyrzbnscqssgqq.supabase.co:5432/postgres",
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(QA / "business_month_seed.py"),
            "--dry-run",
            "--from",
            "2026-10-01",
            "--to",
            "2026-10-17",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "secret-should-not-print" not in completed.stdout
    assert "not in the product" in completed.stdout
    assert "declaration-facts:" in completed.stdout
    assert "approved-books: not cleared" in completed.stdout
    assert "intake: not run" in completed.stdout
    folder = tmp_path / "temp" / "qa-seed" / "2026-10-01_2026-10-17"
    assert (folder / "estado-cuenta.csv").is_file()
    assert (folder / "conciliacion.json").is_file()
    assert fiscal.layout_issues((folder / "practica-606.txt").read_bytes()) == []
    assert fiscal.layout_issues((folder / "practica-607.txt").read_bytes()) == []


def test_a_normal_email_is_refused_before_intake(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(QA / "business_month_seed.py"),
            "--dry-run",
            "--email",
            "owner@example.com",
        ],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2, completed.stdout
    assert "QA seed account" in completed.stderr
    assert "intake: not run" not in completed.stdout
    assert not (tmp_path / "temp").exists()

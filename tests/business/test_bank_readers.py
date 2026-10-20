"""Synthetic statement layouts. Amounts and dates are literals. Names are incidental."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from argus.domain.business.bank.model import (
    AmountAndSignColumns,
    BankMatchingError,
    CsvMapping,
    DebitAndCreditColumns,
)
from argus.domain.business.bank.readers import select_reader
from faker import Faker

Faker.seed(17)
_FAKER = Faker("es_ES")


def _bytes(text: str) -> bytes:
    return text.encode()


def _popular(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    buf = io.StringIO()
    buf.write("# synthetic\n")
    writer = csv.writer(buf)
    writer.writerow(["Fecha", "Descripcion", "Debito", "Credito", "Moneda"])
    writer.writerows(rows)
    return buf.getvalue().encode()


def _bhd(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    buf = io.StringIO()
    buf.write("# synthetic\n")
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Fecha Transaccion", "Detalle", "Monto", "Tipo", "Moneda"])
    writer.writerows(rows)
    return buf.getvalue().encode()


def test_banco_popular_debits_and_credits_on_a_synthetic_file() -> None:
    merchant = _FAKER.company()
    content = _popular(
        [
            ("01/10/2026", merchant, "1500.00", "", "DOP"),
            ("10/10/2026", merchant, "", "5000.00", "dop"),
        ]
    )
    reader = select_reader(content, None, None)
    rows = reader.read(content, None)
    assert reader.id == "banco_popular"
    assert [(row.occurred_on.isoformat(), row.amount, row.currency) for row in rows] == [
        ("2026-10-01", Decimal("-1500.0000"), "DOP"),
        ("2026-10-10", Decimal("5000.0000"), "DOP"),
    ]
    assert rows[0].description == merchant
    assert rows[0].raw_line["Descripcion"] == merchant


def test_bhd_tipo_marks_the_sign() -> None:
    content = _bhd(
        [
            ("03/10/2026", _FAKER.company(), "800.00", "D", "DOP"),
            ("15/10/2026", _FAKER.company(), "1200.00", "C", "DOP"),
        ]
    )
    rows = select_reader(content, None, None).read(content, None)
    assert [row.amount for row in rows] == [Decimal("-800.0000"), Decimal("1200.0000")]


def test_mercury_keeps_the_signed_amount() -> None:
    content = _bytes(
        "# synthetic\n"
        "Date,Description,Amount,Currency,Bank Description,Status\n"
        f"2026-10-07,{_FAKER.company()},-250.00,USD,card,sent\n"
    )
    reader = select_reader(content, None, "mercury")
    row = reader.read(content, None)[0]
    assert reader.id == "mercury"
    assert (row.amount, row.currency, row.occurred_on.isoformat()) == (
        Decimal("-250.0000"),
        "USD",
        "2026-10-07",
    )


def test_sandbox_csv_reads_signed_lines() -> None:
    content = _bytes(
        "# synthetic\n"
        "date,name,amount,iso_currency_code,pending\n"
        f"2026-10-01,{_FAKER.company()},-42.50,DOP,false\n"
    )
    reader = select_reader(content, None, None)
    assert reader.id == "sandbox_csv"
    assert reader.read(content, None)[0].amount == Decimal("-42.5000")


def test_mapped_csv_accepts_either_money_convention() -> None:
    signed = CsvMapping(
        "fecha",
        "detalle",
        AmountAndSignColumns("monto", "signo"),
    )
    split = CsvMapping(
        "fecha",
        "detalle",
        DebitAndCreditColumns("debito", "credito"),
        currency_column="moneda",
    )
    signed_file = _bytes(
        "# synthetic\nfecha,detalle,monto,signo\n01/10/2026,Cargo,10.00,cargo\n"
    )
    split_file = _bytes(
        "# synthetic\nfecha,detalle,debito,credito,moneda\n"
        "02/10/2026,Abono,,20.00,DOP\n"
    )
    assert select_reader(signed_file, signed, "mapped_csv").read(signed_file, signed)[
        0
    ].amount == Decimal("-10.0000")
    credited = select_reader(split_file, split, "mapped_csv").read(split_file, split)[0]
    assert (credited.amount, credited.currency) == (Decimal("20.0000"), "DOP")


def test_pilot_slot_never_parses() -> None:
    content = _bytes("# synthetic\nFecha,Descripcion\n")
    with pytest.raises(BankMatchingError) as raised:
        select_reader(content, None, "pilot_bank")
    assert raised.value.code == "layout_not_ready"


def test_a_bad_row_rejects_the_whole_file() -> None:
    content = _popular([("01/10/2026", "Both", "1.00", "1.00", "DOP")])
    with pytest.raises(BankMatchingError) as raised:
        select_reader(content, None, "banco_popular").read(content, None)
    assert raised.value.code == "invalid_statement"


def test_an_unknown_layout_without_a_mapping_is_refused() -> None:
    with pytest.raises(BankMatchingError) as raised:
        select_reader(_bytes("# synthetic\na,b\n1,2\n"), None, None)
    assert raised.value.code == "unsupported_layout"

"""An approved record exports what was saved. Each line and file row below is
the one the export gave before the 606 line was shown at upload (#2307), but
for a saved Tipo Id left blank: it takes the one the supplier's RNC states."""

from dataclasses import replace
from datetime import date
from uuid import UUID

import pytest
from argus.domain.business.amount_inheritance import (
    APPROVED,
    inherit_amounts,
    inheritance_state,
    saved_declaration,
    written_from,
)
from argus.domain.business.contracts.facts import Known
from argus.domain.business.dgii_export import line_values
from argus.domain.business.reporting_file import RecordsExport, build_file

from tests.business.test_records_file import report, row, source
from tests.dgii.test_packet import practice_records

PURCHASE, _, _, CREDIT_NOTE, *_ = practice_records()
COSTO = "09 - COMPRAS Y GASTOS QUE FORMARAN PARTE DEL COSTO DE VENTA"
EFECTIVO, CHEQUE, CREDITO = (
    "01 - EFECTIVO",
    "02 - CHEQUES/TRANSFERENCIAS/DEPÓSITO",
    "04 - COMPRA A CREDITO",
)
#: What a save left on a purchase of goods: the amounts of the receipt.
SAVED = {"legal_tip": None, "itbis": "180.00", "services_amount": None, "paid_on": None}
PAID = "Factura pagada"
DOLLARS = replace(
    PURCHASE,
    currency="USD",
    facts=PURCHASE.facts.model_copy(
        update={"currency": Known(value="USD", origin="member_set", source_ids=(UUID(int=7),))}
    ),
)

# (record, saved declaration, recorded overrides, bill mark, 606 line, file row)
CASES = [
    pytest.param(
        PURCHASE, SAVED, (), None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||01",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{EFECTIVO}",
        id="efectivo with no fecha pago",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "payment_method": "02"}, (), None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||02",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CHEQUE}",
        id="cheque with no fecha pago",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "payment_method": "04"}, (), None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CREDITO}",
        id="credito",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "paid_on": date(2026, 9, 20)}, ("paid_on",), None,
        "199990021|1|09|B0100000001||20260903|20260920||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||01",
        f"199990021,1,{COSTO},B0100000001,,202609,03,202609,20,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{EFECTIVO}",
        id="fecha pago typed",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "payment_method": "04", "paid_on": date(2026, 9, 3)}, (), PAID,
        "199990021|1|09|B0100000001||20260903|20260903||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0100000001,,202609,03,202609,03,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CREDITO}",
        id="credito approved while marked paid",
    ),
    pytest.param(
        DOLLARS, SAVED, (), None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||01",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{EFECTIVO}",
        id="dollars",
    ),
    pytest.param(
        PURCHASE,
        {**SAVED, "goods_amount": "400.00", "services_amount": "600.00"},
        ("goods_amount", "services_amount"),
        None,
        "199990021|1|09|B0100000001||20260903||600.00|400.00|1000.00|180.00|0.00|||180.00|||0.00|||||01",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,600.00,400.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{EFECTIVO}",
        id="montos overridden",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "payment_method": "04", "itbis": "150.00"}, ("itbis",), None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|150.00|0.00|||150.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,150.00,0.00,,,150.00,,,0.00,,,,,{CREDITO}",
        id="itbis overridden",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "payment_method": "04", "id_type": "2"}, (), None,
        "199990021|2|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||04",
        f"199990021,2,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CREDITO}",
        id="tipo id chosen against the rnc",
    ),
    pytest.param(
        PURCHASE, {**SAVED, "payment_method": "04", "id_type": None}, (), None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CREDITO}",
        id="tipo id blank",
    ),
    pytest.param(
        CREDIT_NOTE,
        {**SAVED, "itbis": "18.00", "payment_method": "04", "modified_ncf": "B0100000009"},
        (),
        None,
        "199990021|1|09|B0400000001|B0100000009|20260912|||100.00|100.00|18.00|0.00|||18.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0400000001,B0100000009,202609,12,,,,100.00,100.00,18.00,0.00,,,18.00,,,0.00,,,,,{CREDITO}",
        id="credit note with a typed ncf modificado",
    ),
    # Saved before overrides were recorded: the export has always filled its blanks.
    pytest.param(
        PURCHASE, {**SAVED, "itbis": None, "goods_amount": None}, None, None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||01",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{EFECTIVO}",
        id="old save with blank montos",
    ),
    pytest.param(
        PURCHASE,
        {"payment_method": "04", "paid_on": None, "id_type": None},
        None,
        None,
        "199990021|1|09|B0100000001||20260903|||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0100000001,,202609,03,,,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CREDITO}",
        id="old save with a blank tipo id",
    ),
    pytest.param(
        PURCHASE, {"payment_method": "04", "paid_on": None}, None, PAID,
        "199990021|1|09|B0100000001||20260903|20260903||1000.00|1000.00|180.00|0.00|||180.00|||0.00|||||04",
        f"199990021,1,{COSTO},B0100000001,,202609,03,202609,03,,1000.00,1000.00,180.00,0.00,,,180.00,,,0.00,,,,,{CREDITO}",
        id="old save marked paid",
    ),
]


@pytest.mark.parametrize(("record", "saved", "overrides", "bill_mark", "line", "file_row"), CASES)
def test_an_approved_record_exports_the_line_it_always_did(
    faker, record, saved, overrides, bill_mark, line, file_row
):
    stored = record.declaration.model_copy(update=saved)
    projected = row(faker, fiscal_data="complete")
    exported = replace(
        record,
        activity_id=projected.linked_activity_ids[0],
        declaration=saved_declaration(record.facts, stored, overrides, bill_mark),
        fiscal_overrides=overrides,
    )

    assert "|".join(line_values(exported)) == line
    built = build_file(
        source(projected, approved={exported.activity_id: exported}),
        RecordsExport(report=report(), mode="dgii", format="csv"),
    )
    assert built.content.decode("utf-8-sig").splitlines()[1] == file_row


def test_a_saved_declaration_with_recorded_overrides_is_exported_untouched():
    stored = PURCHASE.declaration.model_copy(
        update={**SAVED, "id_type": "2", "goods_amount": None, "itbis": None}
    )
    assert saved_declaration(PURCHASE.facts, stored, (), PAID) is stored


def test_only_the_amounts_follow_once_a_record_is_approved():
    stored = PURCHASE.declaration.model_copy(update={**SAVED, "id_type": "2"})
    links = inheritance_state(PURCHASE.facts, stored, (), APPROVED)
    assert set(links) == {"goods_amount", "services_amount", "itbis", "legal_tip"}
    assert inherit_amounts(PURCHASE.facts, stored, (), APPROVED) == stored


@pytest.mark.parametrize(("record", "saved", "overrides", "bill_mark"), [
    pytest.param(*case.values[:4], id=case.id) for case in CASES
])
def test_an_approved_record_shows_the_declaration_it_exports(record, saved, overrides, bill_mark):
    stored = record.declaration.model_copy(update=saved)
    assert written_from(record.facts, stored, overrides, bill_mark, APPROVED) == saved_declaration(
        record.facts, stored, overrides, bill_mark
    )


def test_an_approved_record_shows_a_saved_amount_that_left_its_receipt():
    stored = PURCHASE.declaration.model_copy(update={**SAVED, "itbis": "150.00"})
    assert written_from(PURCHASE.facts, stored, (), None, APPROVED) is stored

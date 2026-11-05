"""Public 606 workbook v2020.2 source contract; no native macro execution.

The source XLS is not a test dependency.
"""

import io
import unicodedata
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts, Known
from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS
from argus.domain.business.dgii_export import build_fiscal_packet
from argus.domain.business.dgii_validation import FiscalRecord
from faker import Faker


@pytest.fixture
def synthetic():
    fake = Faker()
    fake.seed_instance(1440)
    rnc_base = "1" + fake.numerify("#######")
    remainder = (
        sum(int(a) * int(b) for a, b in zip(rnc_base, "79865432", strict=False)) % 11
    )
    rnc = rnc_base + str(2 if remainder == 0 else 1 if remainder == 1 else 11 - remainder)
    cedula_base = "1" + fake.numerify("#########")
    products = [int(a) * int(b) for a, b in zip(cedula_base, "1212121212", strict=False)]
    cedula = cedula_base + str(-sum(divmod(n, 10)[0] + n % 10 for n in products) % 10)
    source = UUID(fake.uuid4())

    def known(value):
        return Known(value=value, origin="member_set", source_ids=(source,))

    amounts = {
        name: f"{Decimal(fake.random_int(100, 9999)) / 100:.2f}"
        for name in (
            "services_amount",
            "goods_amount",
            "itbis_withheld",
            "itbis_proportionality",
            "income_withheld",
            "selective_tax",
            "other_taxes",
            "legal_tip",
        )
    }
    base = Decimal(amounts["services_amount"]) + Decimal(amounts["goods_amount"])
    tax = (base * Decimal("0.18")).quantize(Decimal("0.01"))
    amounts["itbis_cost"] = f"{tax / 3:.2f}"
    amounts["itbis_withheld"] = f"{tax / 2:.2f}"
    gross = (
        base
        + tax
        + sum(Decimal(amounts[n]) for n in ("selective_tax", "other_taxes", "legal_tip"))
    )
    occurred = fake.date_between(date(2026, 9, 1), date(2026, 9, 9))
    declaration = PurchaseDeclaration(
        form="606",
        id_type="1",
        category="02",
        payment_method="01",
        modified_ncf="B01" + fake.numerify("########"),
        paid_on=occurred,
        income_withholding_type="02",
        itbis_perceived=None,
        income_perceived=None,
        **amounts,
    )
    facts = BusinessFacts(
        kind=known("expense"),
        amount=known(f"{gross:.2f}"),
        currency=known("DOP"),
        occurred_on=known(occurred),
        fiscal=FiscalFacts(
            rnc=known(rnc),
            ncf=known("B03" + fake.numerify("########")),
            itbis=known(f"{tax:.2f}"),
        ),
    )
    record = FiscalRecord(
        fake.uuid4(),
        1,
        fake.uuid4(),
        1,
        occurred,
        f"{gross:.2f}",
        "DOP",
        "expense",
        "recibo",
        facts,
        declaration,
        (str(source),),
    )
    return record, {"1": rnc, "2": cedula}, fake.word()


def packet(record, reporter, name):
    return build_fiscal_packet(
        (record,),
        rnc=reporter,
        business_name=name,
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        captured_on=date(2026, 10, 1),
    )


def detail(result):
    assert result.manifest["issues"] == []
    txt = next(value for name, value in result.files.items() if name.endswith(".TXT"))
    return txt.decode("ascii").split("\r\n")[1].split("|")


@pytest.mark.parametrize("category", [f"{n:02}" for n in range(1, 12)])
@pytest.mark.parametrize("payment", [f"{n:02}" for n in range(1, 8)])
@pytest.mark.parametrize("id_type", ("1", "2"))
def test_every_code_pair_emits_the_official_23_fields(
    synthetic, category, payment, id_type
):
    record, identities, name = synthetic
    record = replace(
        record,
        declaration=record.declaration.model_copy(
            update={
                "category": category,
                "payment_method": payment,
                "id_type": id_type,
            }
        ),
        facts=record.facts.model_copy(
            update={
                "fiscal": record.facts.fiscal.model_copy(
                    update={
                        "rnc": record.facts.fiscal.rnc.model_copy(
                            update={"value": identities[id_type]}
                        )
                    }
                )
            }
        ),
    )
    result = packet(record, identities["1"], name)
    d = record.declaration
    f = record.facts.fiscal
    expected = [
        identities[id_type],
        id_type,
        category,
        f.ncf.value,
        d.modified_ncf,
        record.occurred_on.strftime("%Y%m%d"),
        d.paid_on.strftime("%Y%m%d"),
        d.services_amount,
        d.goods_amount,
        f"{Decimal(d.services_amount) + Decimal(d.goods_amount):.2f}",
        f.itbis.value,
        d.itbis_withheld,
        d.itbis_proportionality,
        d.itbis_cost,
        f"{Decimal(f.itbis.value) - Decimal(d.itbis_cost):.2f}",
        "",
        "02",
        d.income_withheld,
        "",
        d.selective_tax,
        d.other_taxes,
        d.legal_tip,
        payment,
    ]
    assert detail(result) == expected
    txt = result.files[f"dgii/DGII_F_606_{identities['1']}_202609.TXT"]
    assert txt == (f"606|{identities['1']}|202609|1\r\n" + "|".join(expected)).encode(
        "ascii"
    )
    assert result.manifest["official_validation"] == "NOT RUN"
    assert result.manifest["physical_format"]["official_tool_verified"] is False


@pytest.mark.parametrize("value", (None, "0", "0.00"))
def test_optional_blanks_and_zeroes_keep_their_positions(synthetic, value):
    record, identities, name = synthetic
    d = record.declaration.model_copy(
        update={
            "modified_ncf": None,
            "paid_on": None,
            "goods_amount": value,
            "itbis_withheld": value,
            "itbis_proportionality": value,
            "itbis_cost": value,
            "income_withholding_type": None,
            "income_withheld": value,
            "itbis_perceived": value,
            "income_perceived": value,
            "selective_tax": value,
            "other_taxes": value,
            "legal_tip": value,
        }
    )
    gross = f"{Decimal(d.services_amount) + Decimal(record.facts.fiscal.itbis.value):.2f}"
    facts = record.facts.model_copy(
        update={
            "amount": record.facts.amount.model_copy(update={"value": gross}),
            "fiscal": record.facts.fiscal.model_copy(
                update={
                    "ncf": record.facts.fiscal.ncf.model_copy(
                        update={
                            "value": "B01" + record.facts.fiscal.ncf.value[3:],
                        }
                    ),
                }
            ),
        }
    )
    row = detail(
        packet(
            replace(record, amount=gross, facts=facts, declaration=d),
            identities["1"],
            name,
        )
    )
    assert len(row) == 23
    assert all(row[i] == "" for i in (4, 6, 8, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21))
    assert row[7] == row[9] == d.services_amount
    assert row[10] == row[14] == facts.fiscal.itbis.value


@pytest.mark.parametrize("field", ("id_type", "category", "payment_method"))
def test_required_codes_do_not_become_blank_txt_fields(synthetic, field):
    record, identities, name = synthetic
    record = replace(
        record, declaration=record.declaration.model_copy(update={field: None})
    )
    result = packet(record, identities["1"], name)
    assert not any(path.endswith(".TXT") for path in result.files)
    assert any(item["field"] == field for item in result.manifest["issues"])


@pytest.mark.parametrize("places", (0, 1, 2))
def test_amounts_are_emitted_with_two_decimals(synthetic, places):
    record, identities, name = synthetic
    old = Decimal(record.declaration.services_amount)
    written = f"{old:.{places}f}"
    gross = f"{Decimal(record.amount) - old + Decimal(written):.2f}"
    record = replace(
        record,
        amount=gross,
        declaration=record.declaration.model_copy(update={"services_amount": written}),
        facts=record.facts.model_copy(
            update={
                "amount": record.facts.amount.model_copy(update={"value": gross}),
            }
        ),
    )
    row = detail(packet(record, identities["1"], name))
    assert row[7] == f"{Decimal(written):.2f}"


def test_zero_tax_stays_numeric_in_required_and_calculated_fields(synthetic):
    record, identities, name = synthetic
    gross = f"{Decimal(record.amount) - Decimal(record.facts.fiscal.itbis.value):.2f}"
    record = replace(
        record,
        amount=gross,
        declaration=record.declaration.model_copy(
            update={
                "itbis_cost": "0",
                "itbis_withheld": "0",
                "itbis_proportionality": "0",
            }
        ),
        facts=record.facts.model_copy(
            update={
                "amount": record.facts.amount.model_copy(update={"value": gross}),
                "fiscal": record.facts.fiscal.model_copy(
                    update={
                        "itbis": record.facts.fiscal.itbis.model_copy(
                            update={"value": "0"}
                        ),
                    }
                ),
            }
        ),
    )
    row = detail(packet(record, identities["1"], name))
    assert row[10] == row[14] == "0.00"
    assert row[11:14] == ["", "", ""]


@pytest.mark.parametrize("field", ("itbis_perceived", "income_perceived"))
def test_unsupported_perceptions_are_refused_instead_of_silently_omitted(
    synthetic, field
):
    record, identities, name = synthetic
    record = replace(
        record,
        declaration=record.declaration.model_copy(
            update={
                field: record.declaration.services_amount,
            }
        ),
    )
    result = packet(record, identities["1"], name)
    assert not any(path.endswith(".TXT") for path in result.files)
    assert any(
        item["code"] == "fiscal_perception_regime_unsupported" and item["field"] == field
        for item in result.manifest["issues"]
    )


def test_review_sheet_retains_txt_values_without_claiming_native_grid_compatibility(
    synthetic,
):
    record, identities, name = synthetic
    result = packet(record, identities["1"], name)
    expected = detail(result)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(io.BytesIO(result.files["dgii/606-607.xlsx"])) as archive:
        strings = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        text = [item.find("m:t", ns).text or "" for item in strings]
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet2.xml"))
        row = sheet.findall("m:sheetData/m:row", ns)[1]
        assert [text[int(cell.find("m:v", ns).text)] for cell in row] == expected
        assert all(cell.attrib["t"] == "s" for cell in row)


@pytest.mark.parametrize(
    ("table", "source_labels"),
    (
        (
            EXPENSE_TYPES,
            (
                "GASTOS DE PERSONAL",
                "GASTOS POR TRABAJOS, SUMINISTROS Y SERVICIOS",
                "ARRENDAMIENTOS",
                "GASTOS DE ACTIVOS FIJO",
                "GASTOS DE REPRESENTACIÓN",
                "OTRAS DEDUCCIONES ADMITIDAS",
                "GASTOS FINANCIEROS",
                "GASTOS EXTRAORDINARIOS",
                "COMPRAS Y GASTOS QUE FORMARAN PARTE DEL COSTO DE VENTA",
                "ADQUISICIONES DE ACTIVOS",
                "GASTOS DE SEGUROS",
            ),
        ),
        (
            PAYMENT_FORMS,
            (
                "EFECTIVO",
                "CHEQUES/TRANSFERENCIAS/DEPÓSITO",
                "TARJETA CRÉDITO/DÉBITO",
                "COMPRA A CREDITO",
                "PERMUTA",
                "NOTA DE CREDITO",
                "MIXTO",
            ),
        ),
    ),
)
def test_code_lists_match_the_workbook_ranges(table, source_labels):
    def normalized(label):
        return "".join(
            c
            for c in unicodedata.normalize("NFD", label.casefold())
            if not unicodedata.combining(c)
        ).strip()

    assert tuple(table) == tuple(f"{n:02}" for n in range(1, len(source_labels) + 1))
    assert [normalized(label) for label in table.values()] == [
        normalized(label) for label in source_labels
    ]

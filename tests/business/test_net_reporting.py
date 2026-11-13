import json
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    Unknown,
)
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.export import sheet_rows
from argus.domain.business.month_close import (
    Settlement,
    formato_totals,
    month_period,
    project_documents,
    read_fiscal,
    sales_base,
)
from argus.domain.business.reporting import ReportRow
from argus.domain.business.reporting_file import _table_cell
from argus.domain.business.reporting_preferences import Presentation
from argus.domain.business.reporting_projection import project
from argus.domain.business.reporting_store import RecordedRecord

from tests.business.test_business_export import activity
from tests.business.test_business_reporting_query import record, run
from tests.business.test_month_close import document
from tests.dgii.test_packet import practice_records


def known(value):
    return Known(value=value, origin="extracted", source_ids=(UUID(int=3),))


def facts(**changes):
    return BusinessFacts(
        amount=known("1280"),
        legal_tip=known("100"),
        fiscal=FiscalFacts(itbis=known("180")),
        **changes,
    )


def test_month_close_uses_net_after_legal_tip_and_keeps_informal_cost_gross():
    parts = read_fiscal({"business": {"facts": facts().model_dump(mode="json")}}, "DOP")
    purchase = document(
        role="receipt",
        total_minor=128000,
        itbis_minor=18000,
        net_amount_minor=parts.net_amount_minor,
    )
    start, end = month_period("2026-10")
    assert formato_totals([purchase], start, end)["DOP"].expense_before_itbis == 100000
    informal = replace(purchase, sin_comprobante=True, ncf=None)
    assert formato_totals([informal], start, end)["DOP"].expense_before_itbis == 128000
    sale = replace(purchase, role="invoice")
    assert formato_totals([sale], start, end)["DOP"].income_before_itbis == 100000


def test_report_totals_keep_net_known_state_separate_from_gross():
    answer = run(
        [
            record(
                "one",
                gross_amount="1280.00",
                net_amount="1000.00",
                net_amount_source="calculated",
            ),
            record("two", gross_amount="50.00", net_amount=None),
        ]
    )
    totals = {total.basis: total for total in answer.totals}
    assert totals["document_family_amount"].amount == "1330.00"
    net = totals["document_net_family_amount"]
    assert (net.known_amount, net.amount, net.unknown_count, net.complete) == (
        "1000.00",
        None,
        1,
        False,
    )


def test_report_net_credit_adjustment_is_negative():
    answer = run(
        [
            record("one", net_amount="1000.00"),
            record(
                "credit",
                net_amount="200.00",
                document_kind="credit_note",
                adjustment_effect="known",
            ),
        ]
    )
    net = next(
        total for total in answer.totals if total.basis == "document_net_family_amount"
    )
    assert net.amount == "800.00"


def test_file_column_uses_server_net_and_columns_are_adjacent():
    row = record(net_amount="1000.00", gross_amount="1280.00", itbis_amount="180")
    assert _table_cell(row, "net_amount", "es-419") == Decimal("1000")
    order = Presentation().order
    assert order[order.index("net_amount") : order.index("net_amount") + 3] == (
        "net_amount",
        "itbis_amount",
        "gross_amount",
    )
    assert "itbis_amount" not in Presentation().hidden


def test_read_subtotal_stays_authoritative_for_month_close_and_sheet():
    purchase_facts = facts(net_amount=known("990"))
    parts = read_fiscal(
        {"business": {"facts": purchase_facts.model_dump(mode="json")}}, "DOP"
    )
    assert parts.net_amount_minor == 99000
    saved = FiscalRecord(
        activity_id=str(UUID(int=1)),
        activity_revision=1,
        draft_id="draft",
        approved_revision=1,
        occurred_on=document().occurred_on,
        amount="1280.00",
        currency="DOP",
        kind="expense",
        document_type="recibo",
        facts=purchase_facts,
        declaration=None,
        source_ids=(),
    )
    [row] = sheet_rows(
        [
            {
                "activity_id": str(UUID(int=1)),
                "occurred_on": "2026-10-05",
                "amount": "1280.00",
                "currency": "DOP",
                "kind": "expense",
                "personal": "no",
            }
        ],
        [saved],
        [],
        {},
    )
    assert row["Subtotal"] == "990.00"
    assert row["Total"] == "1280.00"
    assert list(row)[list(row).index("Subtotal") : list(row).index("Subtotal") + 3] == [
        "Subtotal",
        "ITBIS",
        "Total",
    ]


def test_sales_manual_base_and_credit_sign_stay_authoritative():
    sale = document(
        total_minor=128000,
        itbis_minor=18000,
        net_amount_minor=100000,
        declared_base_minor=95000,
    )
    assert sales_base(sale) == 95000
    assert sales_base(replace(sale, ncf="B0400000001")) == -95000


def test_registros_projects_read_net_difference_and_fiscal_override_separately():
    base = practice_records()[0]
    supplied = facts(net_amount=known("990"))
    declaration = base.declaration.model_copy(update={"itbis": "200.00"})
    approved = replace(
        base, facts=supplied, declaration=declaration, fiscal_overrides=("itbis",)
    )
    recorded = RecordedRecord(
        row=ReportRow(
            base.activity_id, 1, base.occurred_on, "expense", "DOP", 128000, "known"
        ),
        activity_json=json.dumps({"amount": "1280.00"}),
        approved=approved,
        settlement=None,
        sources=(),
    )
    result = project(recorded, None, {}, None)
    assert (result.net_amount, result.net_amount_source) == ("990", "read")
    assert result.amounts_difference == "10.00"
    assert result.itbis_amount == "180"
    assert result.inheritance["itbis"].value == "180"
    assert result.inheritance["itbis"].inherited is False
    credit_facts = supplied.model_copy(
        update={
            "kind": known("credit_purchase"),
            "occurred_on": known(base.occurred_on),
        }
    )
    credit = replace(recorded, approved=replace(approved, facts=credit_facts))
    assert project(credit, None, {}, None).inheritance["paid_on"].value is None
    settled = replace(
        credit, settlement=Settlement("pagado", base.occurred_on, "efectivo")
    )
    paid_on = project(settled, None, {}, None).inheritance["paid_on"]
    assert (paid_on.value, paid_on.inherited) == (base.occurred_on.isoformat(), True)


def test_negative_calculated_net_is_signed_without_changing_gross_totals():
    answer = run([record(net_amount="-25.00", gross_amount="100.00")])
    totals = {total.basis: total for total in answer.totals}
    assert totals["document_net_family_amount"].amount == "-25.00"
    assert totals["document_family_amount"].amount == "100.00"


def test_legacy_activity_total_keeps_read_tip_when_fact_total_is_unknown():
    purchase_facts = facts().model_copy(update={"amount": Unknown()})
    saved = activity(amount="1280.00", amount_minor=128000)
    [projected] = project_documents(
        [saved],
        [
            {
                "activity_id": saved["activity_id"],
                "resolution": {
                    "business": {"facts": purchase_facts.model_dump(mode="json")}
                },
            }
        ],
        {},
        "space",
    )
    assert projected.net_amount_minor == 100000
    assert projected.total_minor == 128000

"""Fiscal summary amounts keep the table's scope and the fiscal source's truth."""

from dataclasses import replace
from decimal import Decimal

import pytest
from argus.domain.business.reporting_query import Purchase606, ReportFilters

from tests.business.test_business_reporting_query import record, run


def purchase(identifier="purchase", **changes):
    return record(
        identifier,
        **(
            dict(
                dgii_606=Purchase606(expense_type=None, payment_form=None),
                itbis_amount="18.00",
                goods_amount="70.00",
                services_amount="30.00",
            )
            | changes
        ),
    )


def totals(answer):
    return {(item.currency, item.kind, item.basis): item for item in answer.fiscal_totals}


def test_partial_coverage_distinguishes_missing_zero_and_entered_values():
    answer = run(
        [
            purchase("entered", goods_amount="12.34", services_amount="7.89"),
            purchase("zero", goods_amount="0.00", services_amount=None),
            purchase(
                "missing", goods_amount=None, services_amount=None, itbis_amount=None
            ),
        ]
    )
    result = totals(answer)
    goods = result["DOP", "expense", "goods"]
    assert (goods.applicable_count, goods.populated_count) == (3, 2)
    assert (goods.known_amount_minor, goods.known_amount) == (1234, "12.34")
    assert (goods.unknown_count, goods.amount_minor, goods.amount, goods.complete) == (
        1,
        None,
        None,
        False,
    )
    services = result["DOP", "expense", "services"]
    assert (services.applicable_count, services.populated_count) == (3, 1)
    assert services.known_amount_minor == 789
    tax = result["DOP", "expense", "itbis"]
    assert (tax.known_amount_minor, tax.populated_count, tax.applicable_count) == (
        3600,
        2,
        3,
    )


def test_missing_is_not_a_complete_zero():
    missing = totals(run([purchase(goods_amount=None)]))["DOP", "expense", "goods"]
    zero = totals(run([purchase(goods_amount="0")]))["DOP", "expense", "goods"]
    assert (missing.populated_count, missing.amount_minor, missing.complete) == (
        0,
        None,
        False,
    )
    assert (zero.populated_count, zero.amount_minor, zero.complete) == (1, 0, True)
    assert run([]).fiscal_totals == ()


@pytest.mark.parametrize(
    "filters",
    [
        ReportFilters(q="chosen"),
        ReportFilters(currencies=("DOP",)),
        ReportFilters(record_families=("purchase",)),
        ReportFilters(review_stages=("needs_fiscal_data",)),
        ReportFilters(counterparties=("chosen",)),
        ReportFilters(currencies=("DOP",), amount_min="100", amount_max="100"),
        ReportFilters(
            period={"kind": "custom", "from_date": "2026-10-01", "to_date": "2026-10-31"}
        ),
    ],
)
def test_every_total_uses_all_filtered_table_records_before_paging(filters):
    from datetime import date

    rows = [
        purchase(
            f"chosen-{i:02}",
            counterparty="chosen",
            counterparty_key="chosen",
            stage="needs_fiscal_data",
        )
        for i in range(30)
    ]
    rows.append(
        record(
            "outside",
            currency="USD",
            family="sale",
            report_date=date(2026, 9, 1),
            counterparty="outside",
            gross_amount="999",
            itbis_amount="999",
        )
    )
    first, second = run(rows, filters), run(rows, filters, page=2)
    assert first.matching_count == 30
    assert len(first.items) == 25 and len(second.items) == 5
    assert first.fiscal_totals == second.fiscal_totals
    goods = totals(first)["DOP", "expense", "goods"]
    assert (goods.amount_minor, goods.populated_count, goods.applicable_count) == (
        210000,
        30,
        30,
    )
    assert set(totals(first)) == {
        ("DOP", "expense", metric) for metric in ("itbis", "goods", "services")
    }


def test_currencies_and_families_stay_separate_and_sales_have_no_purchase_coverage():
    answer = run(
        [
            purchase("dop"),
            purchase("usd", currency="USD", goods_amount="999999999.99"),
            record("sale", family="sale", itbis_amount="5.67"),
            purchase(
                "sin-comprobante", dgii_606=None, goods_amount=None, services_amount=None
            ),
        ]
    )
    result = totals(answer)
    assert result["DOP", "expense", "goods"].amount_minor == 7000
    assert result["USD", "expense", "goods"].amount_minor == 99999999999
    assert result["DOP", "expense", "goods"].applicable_count == 1
    assert result["DOP", "income", "itbis"].amount_minor == 567
    assert ("DOP", "income", "goods") not in result
    assert ("DOP", "income", "services") not in result
    assert {
        item.basis
        for item in run([record("sale", family="sale", itbis_amount="0")]).fiscal_totals
    } == {"itbis"}


@pytest.mark.parametrize(
    "effect,expected,unknown,unsupported",
    [
        ("known", 5400, 0, 0),
        ("unknown", 7000, 1, 0),
        ("unsupported", 7000, 0, 1),
    ],
)
def test_credit_sign_and_incomplete_adjustments_follow_existing_document_totals(
    effect, expected, unknown, unsupported
):
    answer = run(
        [
            purchase(),
            purchase(
                "credit",
                document_kind="credit_note",
                adjustment_effect=effect,
                goods_amount="16",
                gross_amount="20",
            ),
        ]
    )
    goods = totals(answer)["DOP", "expense", "goods"]
    assert goods.known_amount_minor == expected
    assert (goods.unknown_count, goods.unsupported_count) == (unknown, unsupported)
    assert goods.populated_count == goods.applicable_count == 2
    assert goods.complete is (effect == "known")
    gross = next(item for item in answer.totals if item.basis == "document_family_amount")
    assert gross.complete == goods.complete
    if effect == "known":
        assert gross.amount == "80.00"
        assert goods.amount == "54.00"


def test_personal_admission_and_unknown_currency_follow_existing_totals():
    answer = run(
        [
            purchase("excluded", personal=True),
            purchase("included", personal=True, include_606=True),
            purchase("unknown", currency=None),
        ]
    )
    result = totals(answer)
    assert result["DOP", "expense", "goods"].applicable_count == 1
    unknown = result[None, "expense", "goods"]
    assert (unknown.populated_count, unknown.applicable_count) == (1, 1)
    assert unknown.amount is None and unknown.known_amount is None
    assert not unknown.complete
    assert answer.excluded_personal.expense == 1


def test_fiscal_changes_change_fingerprint_without_changing_gross_total():
    before = run([purchase()])
    after = run([purchase(goods_amount="79.13")])
    assert before.fingerprint != after.fingerprint
    assert before.totals == after.totals
    assert Decimal(totals(after)["DOP", "expense", "goods"].amount) == Decimal("79.13")


def test_projection_reads_export_itbis_and_keeps_hand_entered_purchase_amounts():
    from argus.domain.business.contracts.dgii import PurchaseReview
    from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
    from argus.domain.business.dgii_export import _row
    from argus.domain.business.purchase_review import apply_purchase
    from argus.domain.business.reporting_projection import project

    from tests.business.test_registros_notes import recorded
    from tests.dgii.test_606_review_and_rnc import purchase as fiscal_purchase

    approved = fiscal_purchase()
    approved = replace(
        approved,
        declaration=apply_purchase(
            approved.declaration,
            PurchaseReview(goods_amount="12.34", services_amount="56.78"),
        ),
    )
    row = project(recorded("Synthetic receipt", approved), None, {}, None)
    exported = dict(
        zip((name for name, _ in PURCHASE_COLUMNS), _row(approved), strict=True)
    )
    assert Decimal(row.itbis_amount) == Decimal(exported["itbis"])
    assert row.goods_amount == exported["goods_amount"] == "12.34"
    assert row.services_amount == exported["services_amount"] == "56.78"
    result = totals(run([row]))
    assert result["DOP", "expense", "goods"].amount_minor == 1234
    assert result["DOP", "expense", "services"].populated_count == 1
    assert row.gross_amount != str(
        Decimal(row.goods_amount)
        + Decimal(row.services_amount)
        + Decimal(row.itbis_amount)
    )


def test_projection_missing_declaration_is_applicable_but_sin_comprobante_is_not():
    from argus.domain.business.contracts.facts import Unknown
    from argus.domain.business.reporting_projection import project

    from tests.business.test_registros_notes import recorded
    from tests.dgii.test_606_review_and_rnc import purchase as fiscal_purchase

    approved = replace(fiscal_purchase(), declaration=None)
    row = project(recorded("Synthetic receipt", approved), None, {}, None)
    assert row.dgii_606 is not None
    total = totals(run([row]))["DOP", "expense", "goods"]
    assert (total.populated_count, total.applicable_count, total.amount_minor) == (
        0,
        1,
        None,
    )
    no_receipt = approved.facts.amount.model_copy(update={"value": "no_receipt"})
    facts = approved.facts.model_copy(
        update={
            "receipt_state": no_receipt,
            "fiscal": approved.facts.fiscal.model_copy(
                update={"ncf": Unknown(), "ecf": Unknown()}
            ),
        }
    )
    row = project(
        recorded("Synthetic entry", replace(approved, facts=facts)), None, {}, None
    )
    assert row.dgii_606 is None
    assert {item.basis for item in run([row]).fiscal_totals} == {"itbis"}


def test_projection_sales_take_export_tax_without_inventing_goods_or_services():
    from argus.domain.business.dgii_columns import SALES_COLUMNS
    from argus.domain.business.dgii_export import _row
    from argus.domain.business.reporting_projection import project

    from tests.business.test_registros_notes import recorded
    from tests.dgii.test_packet import practice_records

    sale = next(item for item in practice_records() if item.declaration.form == "607")
    row = project(recorded("Synthetic sale", sale), None, {}, None)
    exported = dict(zip((name for name, _ in SALES_COLUMNS), _row(sale), strict=True))
    assert Decimal(row.itbis_amount) == Decimal(exported["itbis"])
    assert row.dgii_606 is row.goods_amount is row.services_amount is None
    assert {item.basis for item in run([row]).fiscal_totals} == {"itbis"}

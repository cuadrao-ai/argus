"""The month-close and open-items fields the server owns: today, overdue,
ITBIS cobrado, the per-currency final mark, the payment methods, the earliest
month, the form statuses, and the peso gate on the 606 and 607."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from argus.api.business_month_close_schemas import MonthClose, OpenItems
from argus.domain.business.dgii_export import build_fiscal_packet, fiscal_manifest
from argus.domain.business.dgii_validation import declarable
from argus.domain.business.month_close import (
    PAYMENT_METHODS,
    formato_totals,
    in_606,
    in_607,
    month_period,
    open_items,
    overdue,
    plan_settlement,
    summarize,
)

from tests.business.test_month_close import DAY, document, pending
from tests.dgii.test_packet import practice_records

OCTOBER = month_period("2026-10")


def test_overdue_is_pending_past_the_due_date_and_never_without_one():
    late = pending("late", "invoice", DAY, due_on=DAY - timedelta(days=1))
    assert overdue(late, DAY)
    assert not overdue(pending("due-today", "invoice", DAY, due_on=DAY), DAY)
    assert not overdue(
        pending("ahead", "invoice", DAY, due_on=DAY + timedelta(days=1)), DAY
    )
    assert not overdue(pending("undated", "invoice", DAY), DAY)
    settled = document(activity_id="paid", due_on=DAY - timedelta(days=30))
    assert not overdue(settled, DAY)


def test_open_items_carry_today_and_overdue_over_every_item_per_currency():
    yesterday = DAY - timedelta(days=1)
    documents = [
        pending("late-peso-a", "invoice", DAY, total_minor=100, due_on=yesterday),
        pending("late-peso-b", "invoice", DAY, total_minor=200, due_on=yesterday),
        pending(
            "late-usd", "invoice", DAY, currency="USD", total_minor=5, due_on=yesterday
        ),
        pending(
            "on-time", "invoice", DAY, total_minor=1000, due_on=DAY + timedelta(days=3)
        ),
        pending("undated", "invoice", DAY, total_minor=2000),
        pending("late-bill", "receipt", DAY, total_minor=700, due_on=yesterday),
    ]
    opened = open_items(documents, DAY, cap=1)
    assert opened["today"] == "2026-10-05"
    cobrar = opened["cuentas_por_cobrar"]
    assert len(cobrar["items"]) == 1 and cobrar["count"] == 5
    assert cobrar["overdue"] == {
        "count": 3,
        "totals": [
            {"currency": "DOP", "total_minor": 300, "total": "3.00"},
            {"currency": "USD", "total_minor": 5, "total": "0.05"},
        ],
    }
    assert opened["cuentas_por_pagar"]["overdue"] == {
        "count": 1,
        "totals": [{"currency": "DOP", "total_minor": 700, "total": "7.00"}],
    }
    OpenItems.model_validate(opened)


def test_itbis_cobrado_is_the_charged_itbis_of_collected_sales_only():
    documents = [
        document(activity_id="collected", total_minor=11800, itbis_minor=1800),
        pending("open", "invoice", DAY, total_minor=5900, itbis_minor=900),
        document(
            activity_id="credit-collected",
            total_minor=1180,
            itbis_minor=180,
            ncf="B0400000001",
        ),
        document(
            activity_id="informal-collected",
            total_minor=300,
            itbis_minor=46,
            ncf=None,
            sin_comprobante=True,
        ),
        document(
            activity_id="paid-bill",
            role="receipt",
            status="pagado",
            total_minor=2360,
            itbis_minor=360,
        ),
    ]
    totals = formato_totals(documents, *OCTOBER)["DOP"]
    assert totals.itbis_charged == 1800 + 900 - 180 + 46
    assert totals.itbis_collected == 1800 - 180 + 46
    [block] = summarize(documents, *OCTOBER)["currencies"]
    assert (block["itbis_cobrado_minor"], block["itbis_cobrado"]) == (1666, "16.66")


def test_net_result_is_final_per_currency_while_that_currency_has_no_pending_document():
    documents = [
        document(activity_id="peso-collected", total_minor=1000, itbis_minor=0),
        document(
            activity_id="usd-collected", currency="USD", total_minor=2000, itbis_minor=0
        ),
        pending("usd-open", "receipt", DAY, currency="USD", total_minor=50),
    ]
    blocks = {
        block["currency"]: block for block in summarize(documents, *OCTOBER)["currencies"]
    }
    assert blocks["DOP"]["net_result_final"] is True
    assert blocks["USD"]["net_result_final"] is False


def test_payment_methods_are_the_documented_set_in_order_and_still_gate_settlement():
    assert list(PAYMENT_METHODS) == [
        "efectivo",
        "transferencia",
        "tarjeta",
        "credito",
        "otro",
    ]
    from argus.domain.business.authority import ActionError
    from argus.domain.business.month_close import IMPLICIT, Settlement

    with pytest.raises(ActionError) as refused:
        plan_settlement("invoice", IMPLICIT, Settlement("cobrado", DAY, "bitcoin"))
    assert refused.value.code == "business_payment_method_invalid"


def test_earliest_month_is_the_first_month_the_close_would_show():
    assert summarize([], *OCTOBER)["earliest_month"] is None
    documents = [
        document(activity_id="old-personal", occurred_on=date(2024, 3, 9), personal=True),
        document(activity_id="first", occurred_on=date(2025, 7, 31)),
        pending("later", "receipt", date(2026, 10, 2)),
    ]
    # A personal sale never shows, so it does not open the picker earlier.
    assert summarize(documents, *OCTOBER)["earliest_month"] == "2025-07"


def test_a_dollar_document_with_a_comprobante_is_on_neither_form_in_both_owners():
    assert declarable("DOP") and not declarable("USD")
    usd_bill = document(
        activity_id="usd-bill",
        role="receipt",
        status="pagado",
        currency="USD",
        total_minor=1180,
        itbis_minor=180,
    )
    usd_sale = document(
        activity_id="usd-sale", currency="USD", total_minor=2360, itbis_minor=360
    )
    assert not in_606(usd_bill) and not in_607(usd_sale)
    assert in_606(
        document(
            activity_id="peso-bill",
            role="receipt",
            status="pagado",
            total_minor=1180,
            itbis_minor=180,
        )
    )
    assert "USD" not in formato_totals([usd_bill, usd_sale], *OCTOBER)
    blocks = {
        b["currency"]: b for b in summarize([usd_bill, usd_sale], *OCTOBER)["currencies"]
    }
    assert blocks["USD"]["itbis_paid_minor"] == blocks["USD"]["itbis_charged_minor"] == 0
    assert blocks["USD"]["by_status"]["receipts"]["pagado"]["count"] == 1

    records = practice_records()
    dollar = [r.__class__(**{**r.__dict__, "currency": "USD"}) for r in records[:1]]
    manifest, rows = fiscal_manifest(
        dollar,
        rnc="131000001",
        business_name="Práctica",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        captured_on=DAY,
    )
    [bridge] = manifest["reconciliation"]
    assert bridge["reason"] == "fiscal_conversion_required"
    assert rows == {"606": [], "607": []}
    # The dollar gross never enters the peso totals, and the record is an
    # issue that keeps its form in review, not a silent exclusion.
    assert manifest["totals_dop"]["purchase_invoice_gross"] == "0.00"
    assert manifest["totals_dop"]["sales_gross"] == "0.00"
    assert [issue["code"] for issue in manifest["issues"]] == ["fiscal_conversion_required"]
    assert manifest["forms"][dollar[0].declaration.form]["status"] == "needs_review"


def test_the_packet_writes_files_from_the_same_summary_month_close_reads():
    records = practice_records()
    kwargs = dict(
        rnc="131000001",
        business_name="Práctica",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        captured_on=DAY,
    )
    manifest, rows = fiscal_manifest(records, **kwargs)
    packet = build_fiscal_packet(records, **kwargs)
    assert packet.manifest == manifest
    statuses = {form: shape["status"] for form, shape in manifest["forms"].items()}
    written = {name[12:15] for name in packet.files if name.endswith(".TXT")}
    assert written == {
        form for form, status in statuses.items() if status == "prepared_candidate"
    }
    assert set(packet.files) >= {"dgii/summary.json", "dgii/606-607.xlsx"}
    MonthClose.model_validate(
        {
            "month": "2026-09",
            "today": DAY,
            "payment_methods": list(PAYMENT_METHODS),
            "dgii_forms": statuses,
            **summarize([], date(2026, 9, 1), date(2026, 9, 30)),
        }
    )

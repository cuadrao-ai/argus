"""Each currency block of the month close: how many of the month's documents
its figures count, how many there are in all and how many wait in the Bandeja;
whether the Business holds a second currency in any month; a net that is final
in its own currency; and a Bandeja draft counted in the currency it names."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from argus.api.business_month_close_schemas import MonthClose
from argus.api.business_receipt_activity import unreviewed_days
from argus.domain.business.month_close import (
    formato_totals,
    month_period,
    summarize,
    unreviewed_in_month,
    with_unreviewed,
)
from argus.domain.business.month_close_store import empty_month

from tests.business.test_month_close import DAY, document, october
from tests.business.test_month_close_unreviewed import NO_STORE, _view
from tests.business.test_settlement_switch import _october as _settled_october


def _documents_by_currency(summary: dict) -> dict[str, tuple[int, int, int]]:
    return {
        block["currency"]: (
            block["documents_counted"],
            block["documents_total"],
            block["documents_in_bandeja"],
        )
        for block in summary["currencies"]
    }


def test_each_currency_counts_the_months_documents_from_the_figures_own_list():
    """The figures leave out a purchase with no NCF and a personal one; the
    month still counts the first, never the second, and the Bandeja's drafts
    join the total in their own currency."""

    start, end = month_period("2026-10")
    summary = summarize(october(), start, end, bandeja={"DOP": 2, "USD": 1})
    assert _documents_by_currency(summary) == {"DOP": (4, 7, 2), "USD": (1, 2, 1)}
    counted = [d for d in october() if d.currency == "DOP" and d.activity_id != "purchase-open"]
    figures = formato_totals(counted, start, end)["DOP"]
    [pesos] = [block for block in summary["currencies"] if block["currency"] == "DOP"]
    assert pesos["expense_before_itbis_minor"] == figures.expense_before_itbis


def test_a_currency_only_the_bandeja_holds_gets_its_own_block_of_zeros():
    start, end = month_period("2026-10")
    summary = summarize([], start, end, bandeja={"EUR": 3, "USD": 0})
    [euros] = summary["currencies"]
    assert (euros["currency"], euros["income_before_itbis"], euros["net_result"]) == ("EUR", "0.00", "0.00")
    assert _documents_by_currency(summary) == {"EUR": (0, 3, 3)}
    assert MonthClose.model_validate(
        {"month": "2026-10", "today": DAY, "dgii_forms": {"606": "no_operations", "607": "no_operations"}, **summary}
    ).currencies[0].documents_in_bandeja == 3


def test_more_than_one_currency_is_any_month_of_the_business_not_only_this_one():
    """The currency choice stays visible in a month of one currency when
    another month holds a second one."""

    september = date(2026, 9, 10)
    start, end = month_period("2026-10")
    pesos = document(activity_id="peso", total_minor=1000)
    dollars = document(activity_id="usd-september", currency="USD", occurred_on=september)
    assert summarize([pesos], start, end)["more_than_one_currency"] is False
    october = summarize([pesos, dollars], start, end)
    assert [block["currency"] for block in october["currencies"]] == ["DOP"]
    assert october["more_than_one_currency"] is True
    assert summarize([pesos], start, end, bandeja={"USD": 1})["more_than_one_currency"] is True
    personal = replace(dollars, personal=True, include_606=False)
    assert summarize([pesos, personal], start, end)["more_than_one_currency"] is False


def test_off_a_dollar_net_shown_in_dollars_is_final() -> None:
    dollars = [document(activity_id="usd", currency="USD", status="cobrado")]
    [usd] = _settled_october(dollars, settlement=False)["currencies"]
    assert usd["net_result_final"] is True


def test_on_a_dollar_net_waits_only_on_its_own_marks() -> None:
    settled = [document(activity_id="usd", currency="USD", status="cobrado")]
    [usd] = _settled_october(settled, settlement=True)["currencies"]
    assert usd["net_result_final"] is True


def test_each_draft_counts_in_its_reads_currency_and_a_note_names_none():
    start, end = month_period("2026-10")
    views = [
        _view("review_ready", "2026-10-12", currency="USD"),
        _view("needs_attention", "2026-10-13", currency="DOP"),
        _view("saved", "2026-10-14"),
        _view("review_ready", "2026-11-02", currency="USD"),
    ]
    days = unreviewed_days(NO_STORE, views)
    assert [currency for _, currency in days] == ["USD", "DOP", None, "USD"]
    counted = unreviewed_in_month(
        ((day, currency or "DOP") for day, currency in days), start, end
    )
    assert counted == {"USD": 1, "DOP": 2}
    blocks = with_unreviewed(empty_month("2026-10", bandeja=counted))["currencies"]
    assert [
        (b["currency"], b["documents_in_bandeja"], b["documents_total"], b["documents_counted"])
        for b in blocks
    ] == [("DOP", 2, 2, 0), ("USD", 1, 1, 0)]

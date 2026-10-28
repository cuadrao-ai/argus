from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from argus.domain.business.reporting import ReportIdentity
from argus.domain.business.reporting_query import (
    ReportFilters,
    ReportRecord,
    ReportRequest,
    run_query,
)
from pydantic import ValidationError

IDENTITY = ReportIdentity("business", "actor", "owner", "grant", "")
NOW = datetime(2026, 10, 31, 23, tzinfo=timezone.utc)


def record(identifier="draft:one", **changes):
    values = dict(
        row_id=identifier,
        revision=1,
        report_date=date(2026, 10, 1),
        date_basis="document_issue",
        currency="DOP",
        gross_amount="100.00",
        family="purchase",
        money_kind="expense",
    )
    return ReportRecord(**(values | changes))


def run(rows, filters=None, **changes):
    return run_query(
        IDENTITY, rows, ReportRequest(filters=filters or ReportFilters(), **changes), NOW
    )


def test_all_matches_are_counted_before_page_and_unknown_dates_are_honest():
    rows = [record(f"draft:{i:02}") for i in range(30)] + [
        record("unknown").model_copy(update={"report_date": None})
    ]
    result = run(rows, page=2)
    assert result.matching_count == 31
    assert result.page_count == 2
    assert len(result.items) == 6
    assert result.items[-1].row_id == "unknown"
    bounded = run(
        rows,
        ReportFilters(
            period={"kind": "custom", "from_date": "2026-10-01", "to_date": "2026-10-31"}
        ),
    )
    assert bounded.matching_count == 30
    assert bounded.excluded_unknown_dates == 1


def test_amount_uses_original_gross_and_exact_currency():
    row = record(recorded_amount="25.00", linked_activity_ids=("activity",))
    assert (
        run(
            [row],
            ReportFilters(currencies=("DOP",), amount_min="100.00", amount_max="100.00"),
        ).matching_count
        == 1
    )
    assert (
        run([row], ReportFilters(currencies=("DOP",), amount_max="25.00")).matching_count
        == 0
    )
    with pytest.raises(ValidationError):
        ReportFilters(amount_min="1.00")
    with pytest.raises(ValidationError):
        ReportFilters(currencies=("DOP",), amount_min="1.001")
    with pytest.raises(ValidationError):
        ReportFilters(currencies=("DOP", "USD"), amount_min="1")


def test_literal_search_and_exact_counterparty_do_not_merge_names():
    one = record("one", counterparty="Same % shop", counterparty_key="101234567")
    two = record("two", counterparty="Same % shop", counterparty_key=None)
    assert run([one, two], ReportFilters(q="%")).matching_count == 2
    assert run([one, two], ReportFilters(q="_")).matching_count == 0
    assert (
        run([one, two], ReportFilters(counterparties=("101234567",))).matching_count == 1
    )
    assert run([one, two]).matching_count == 2


def test_relative_recipe_rolls_forward_and_fingerprint_ignores_page():
    request = ReportRequest(filters={"period": {"kind": "this_month"}})
    rows = [record()]
    first = run_query(IDENTITY, rows, request, NOW)
    second = run_query(
        IDENTITY, rows, request, datetime(2026, 11, 1, 5, tzinfo=timezone.utc)
    )
    assert first.resolved_period.from_date == date(2026, 10, 1)
    assert second.resolved_period.from_date == date(2026, 11, 1)
    assert first.fingerprint != second.fingerprint
    assert (
        first.fingerprint
        == run_query(
            IDENTITY, rows, request.model_copy(update={"page": 2}), NOW
        ).fingerprint
    )


def test_filter_groups_and_unknown_categories():
    rows = [
        record("a", family="purchase", category_key="uncategorized"),
        record("b", family="sale", category_key="travel"),
    ]
    filters = ReportFilters(
        record_families=("purchase", "sale"), categories=("uncategorized",)
    )
    assert [row.row_id for row in run(rows, filters).items] == ["a"]
    with pytest.raises(ValidationError):
        ReportFilters(payment_status="paid")
    with pytest.raises(ValidationError):
        ReportRequest(page_size=20)


def test_currency_totals_distinguish_gross_recorded_and_proposed():
    rows = [
        record(
            "one",
            recorded_amount="25.00",
            linked_activity_ids=("a",),
            money_kind="expense",
        ),
        record("two", proposed_amount="100.00", money_kind="expense"),
        record("usd", proposed_amount="10.00", money_kind="expense").model_copy(
            update={"currency": "USD", "gross_amount": "10.00"}
        ),
        record("credit", document_kind="credit_note", adjustment_effect="unknown"),
    ]
    result = run(rows)
    buckets = {(item.currency, item.basis): item for item in result.totals}
    assert buckets["DOP", "recorded_activity_amount"].known_amount_minor == 2500
    assert buckets["DOP", "proposed_activity_amount"].known_amount_minor == 10000
    assert buckets["DOP", "document_gross_amount"].known_amount_minor == 20000
    assert buckets["DOP", "document_credit_adjustment"].amount_minor is None
    assert Decimal(buckets["USD", "proposed_activity_amount"].amount_minor) == 1000


def test_a_personal_row_counts_only_as_a_purchase_the_accountant_put_in_the_606():
    rows = [
        record("business", recorded_amount="5.00", linked_activity_ids=("a",)),
        record(
            "personal", recorded_amount="25.00", linked_activity_ids=("b",), personal=True
        ),
        record(
            "included",
            recorded_amount="40.00",
            linked_activity_ids=("c",),
            personal=True,
            include_606=True,
        ),
        record(
            "sale",
            recorded_amount="70.00",
            linked_activity_ids=("d",),
            family="sale",
            money_kind="income",
            personal=True,
            include_606=True,
        ),
    ]
    buckets = {(item.kind, item.basis): item for item in run(rows).totals}
    assert buckets["expense", "recorded_activity_amount"].known_amount_minor == 4500
    assert buckets["expense", "recorded_activity_amount"].matching_count == 2
    assert ("income", "recorded_activity_amount") not in buckets


def test_duplicate_public_anchor_and_effect_are_refused():
    with pytest.raises(ValueError, match="duplicate"):
        run([record(), record()])
    with pytest.raises(ValueError, match="duplicate"):
        run(
            [
                record("a", linked_activity_ids=("effect",)),
                record("b", linked_activity_ids=("effect",)),
            ]
        )


def test_sale_and_validated_credit_have_signed_document_adjustment_not_cash_net():
    rows = [
        record(
            "sale",
            family="sale",
            money_kind="income",
            gross_amount="100.00",
            recorded_amount="100.00",
            linked_activity_ids=("income",),
        ),
        record(
            "credit",
            family="sale",
            money_kind="income",
            gross_amount="20.00",
            recorded_amount="20.00",
            linked_activity_ids=("credit-effect",),
            document_kind="credit_note",
            adjustment_effect="known",
        ),
    ]
    result = run(rows)
    buckets = {item.basis: item for item in result.totals}
    assert buckets["document_gross_amount"].amount_minor == 10000
    assert buckets["document_credit_adjustment"].amount_minor == -2000
    assert buckets["document_credit_adjustment"].amount == "-20.00"
    assert buckets["document_credit_adjustment"].known_amount == "-20.00"
    assert buckets["document_family_amount"].amount_minor == 8000
    assert buckets["recorded_activity_amount"].amount_minor == 12000
    assert (
        run(rows, ReportFilters(currencies=("DOP",), amount_max="20.00")).matching_count
        == 1
    )


def test_unknown_currency_and_filtered_unknown_date_count_are_explicit():
    rows = [
        record("missing", currency=None, report_date=None),
        record("other", family="sale", report_date=None),
    ]
    result = run(
        rows, ReportFilters(record_families=("purchase",), period={"kind": "this_month"})
    )
    assert result.excluded_unknown_dates == 1
    unknown = run(rows).totals
    assert any(total.currency is None and total.amount_minor is None for total in unknown)
    assert not any(total.currency == "unknown" for total in unknown)


def test_same_tax_identity_keeps_aliases_and_same_name_never_merges_identities():
    rows = [
        record("a", counterparty="First label", counterparty_key="101234567"),
        record("b", counterparty="Second label", counterparty_key="101234567"),
        record("c", counterparty="First label", counterparty_key="109876543"),
    ]
    result = run(rows, ReportFilters(counterparties=("101234567",)))
    assert {row.row_id for row in result.items} == {"a", "b"}
    assert result.counterparties[0].labels == ("First label", "Second label")


def test_unlinked_credit_makes_document_family_final_incomplete():
    rows = [
        record("sale", family="sale", money_kind="income"),
        record(
            "unlinked",
            family=None,
            document_kind="credit_note",
            gross_amount="20.00",
            adjustment_effect="unknown",
        ),
    ]
    answer = run(rows)
    sale = next(
        total
        for total in answer.totals
        if total.basis == "document_family_amount" and total.kind == "income"
    )
    assert sale.known_amount == "100.00"
    assert sale.amount is None
    assert sale.unknown_count == 1


def test_exact_amount_strings_survive_large_values_and_aggregate_over_bigint():
    rows = [
        record(
            "large",
            gross_amount="92233720368547758.07",
            recorded_amount="92233720368547758.07",
            linked_activity_ids=("large-effect",),
        ),
        record(
            "small",
            gross_amount="1.00",
            recorded_amount="1.00",
            linked_activity_ids=("small-effect",),
        ),
    ]
    single = run(rows[:1]).model_dump(mode="json")
    aggregate = run(rows).model_dump(mode="json")
    for basis in ("recorded_activity_amount", "document_gross_amount"):
        first = next(total for total in single["totals"] if total["basis"] == basis)
        combined = next(total for total in aggregate["totals"] if total["basis"] == basis)
        assert first["amount_minor"] > 2**53
        assert first["known_amount"] == first["amount"] == "92233720368547758.07"
        assert combined["amount_minor"] > 2**63 - 1
        assert combined["known_amount"] == combined["amount"] == "92233720368547759.07"

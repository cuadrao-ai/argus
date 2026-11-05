"""One matched record set owns report pages, totals and change detection."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone

import pytest
from argus.domain.business.reporting import (
    DuplicateActivity,
    ReportIdentity,
    ReportRow,
    summarize,
)
from faker import Faker

DAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


@pytest.fixture
def identity() -> ReportIdentity:
    fake = Faker()
    return ReportIdentity(
        business_id=fake.uuid4(),
        actor_id=fake.uuid4(),
        owner_id=fake.uuid4(),
        grant_id=fake.uuid4(),
        query_fingerprint="approved-semantic-query",
    )


def row(activity_id: str, amount_minor: int | None = 100, **changes) -> ReportRow:
    values = dict(
        activity_id=activity_id,
        revision=1,
        occurred_on=DAY,
        kind="income",
        currency="DOP",
        amount_minor=amount_minor,
        effect="known",
        dependency_fingerprints=("approved-facts-v1", "visible-source-v1"),
    )
    return ReportRow(**(values | changes))


def read(identity: ReportIdentity, rows, **changes):
    options = dict(page_number=1, page_size=2, observed_at=NOW)
    return summarize(identity, rows, **(options | changes))


def test_pages_and_export_rows_share_full_count_and_currency_kind_totals(identity):
    rows = (
        row("sale-a", 100),
        row("sale-b", 250),
        row("purchase", 90, kind="expense"),
        row("refund", 30, kind="refund"),
        row("foreign-sale", 700, currency="USD"),
    )
    first = read(identity, rows)
    last = read(identity, rows, page_number=3)

    assert first.matching_count == last.matching_count == 5
    assert first.page_count == last.page_count == 3
    assert len(first.items) == 2
    assert len(last.items) == 1
    assert len(first.rows) == 5
    assert first.totals == last.totals
    assert {
        (total.currency, total.kind): (total.matching_count, total.amount_minor)
        for total in first.totals
    } == {
        ("DOP", "income"): (2, 350),
        ("DOP", "expense"): (1, 90),
        ("DOP", "refund"): (1, 30),
        ("USD", "income"): (1, 700),
    }
    assert {total.basis for total in first.totals} == {"recorded_activity_amount"}


def test_same_day_ties_and_input_order_cannot_shuffle_numbered_pages(identity):
    rows = (row("b"), row("old", occurred_on=DAY - timedelta(days=1)), row("a"))
    result = read(identity, rows)
    reordered = read(identity, reversed(rows), observed_at=NOW + timedelta(hours=1))

    assert [item.activity_id for item in result.items] == ["a", "b"]
    assert [item.activity_id for item in result.rows] == ["a", "b", "old"]
    assert result.fingerprint == reordered.fingerprint


def test_fingerprint_ignores_page_size_number_and_observation_time(identity):
    rows = (row("a"), row("b"), row("c"))
    first = read(identity, rows)
    other = read(
        identity, rows, page_number=2, page_size=1, observed_at=NOW + timedelta(days=1)
    )
    assert first.fingerprint == other.fingerprint
    assert first.observed_at != other.observed_at


@pytest.mark.parametrize(
    "changes",
    [
        {"amount_minor": 101},
        {"revision": 2},
        {"dependency_fingerprints": ("approved-facts-v2", "visible-source-v1")},
        {"dependency_fingerprints": ("approved-facts-v1", "visible-source-v2")},
        {"effect": "unknown"},
        {"currency": "USD"},
        {"kind": "refund"},
        {"occurred_on": DAY - timedelta(days=1)},
    ],
)
def test_changes_beyond_visible_page_change_fingerprint(identity, changes):
    rows = (row("a"), row("b"), row("c"))
    before = read(identity, rows)
    after = read(identity, (*rows[:2], replace(rows[2], **changes)))
    assert before.items == after.items
    assert before.fingerprint != after.fingerprint


@pytest.mark.parametrize(
    "field", ["business_id", "actor_id", "owner_id", "grant_id", "query_fingerprint"]
)
def test_fingerprint_binds_trusted_scope_and_semantic_query(identity, field):
    before = read(identity, (row("a"),))
    after = read(replace(identity, **{field: "different"}), (row("a"),))
    assert before.fingerprint != after.fingerprint


def test_added_and_removed_matches_change_fingerprint(identity):
    before = read(identity, (row("a"), row("b")))
    added = read(identity, (row("a"), row("b"), row("c")))
    removed = read(identity, (row("a"),))
    assert len({before.fingerprint, added.fingerprint, removed.fingerprint}) == 3


@pytest.mark.parametrize("revision", [1, 2])
def test_duplicate_canonical_activity_is_refused_before_any_total(identity, revision):
    with pytest.raises(DuplicateActivity):
        read(identity, (row("same"), row("same", revision=revision)))


def test_unknown_effects_preserve_rows_and_cannot_be_reported_as_final_zero(identity):
    result = read(
        identity,
        (
            row("known", 400),
            row("unresolved-credit", 60, effect="unknown"),
            row("unsupported", 90, effect="unsupported"),
            row("missing-amount", None, kind="refund", effect="unknown"),
            row("other-currency", 100, currency="USD"),
        ),
    )
    totals = {(total.currency, total.kind): total for total in result.totals}
    income = totals["DOP", "income"]
    assert result.matching_count == 5
    assert income.matching_count == 3
    assert income.known_amount_minor == 400
    assert income.unknown_count == income.unsupported_count == 1
    assert income.amount_minor is None
    assert income.complete is False
    assert totals["DOP", "refund"].amount_minor is None
    assert totals["USD", "income"].amount_minor == 100
    assert totals["USD", "income"].complete is True


def test_fiscal_dependency_never_changes_the_sign_of_recorded_money(identity):
    result = read(
        identity,
        (
            row("sale-credit", 11800, dependency_fingerprints=("approved-credit-note",)),
            row("payment-return", 500, kind="payment_reversal"),
        ),
    )
    assert {total.kind: total.amount_minor for total in result.totals} == {
        "income": 11800,
        "payment_reversal": 500,
    }


def test_unsupported_kind_remains_visible_without_a_final_amount(identity):
    result = read(identity, (row("a", 300, kind="unrecognized", effect="unsupported"),))
    assert result.items[0].amount_minor == 300
    assert result.totals[0].amount_minor is None
    assert result.totals[0].unsupported_count == 1
    with pytest.raises(ValueError):
        row("a", 300, kind="unrecognized", effect="known")


def test_totals_preserve_minor_units_beyond_floating_point_precision(identity):
    result = read(identity, (row("a", 9007199254740993), row("b", 7)))
    assert result.totals[0].amount_minor == 9007199254741000


def test_empty_and_out_of_range_pages_keep_truthful_metadata(identity):
    empty = read(identity, ())
    beyond = read(identity, (row("a"),), page_number=10)
    assert (empty.matching_count, empty.page_count, empty.items, empty.totals) == (
        0,
        0,
        (),
        (),
    )
    assert (beyond.matching_count, beyond.page_count, beyond.items) == (1, 1, ())
    assert beyond.totals[0].amount_minor == 100


@pytest.mark.parametrize(
    "options",
    [{"page_number": 0}, {"page_size": 0}, {"page_number": 1.5}, {"page_size": True}],
)
def test_invalid_page_cannot_silently_slice_another_record_set(identity, options):
    with pytest.raises(ValueError):
        read(identity, (row("a"),), **options)


def test_report_does_not_change_when_input_collection_changes(identity):
    rows = [row("a")]
    result = read(identity, rows)
    rows.append(row("b"))
    assert result.matching_count == len(result.rows) == 1
    with pytest.raises(FrozenInstanceError):
        result.rows[0].amount_minor = 200


@pytest.mark.parametrize("amount", [None, 1.5, True, -100])
def test_known_recorded_amount_requires_exact_nonnegative_minor_units(amount):
    with pytest.raises(ValueError):
        row("a", amount)

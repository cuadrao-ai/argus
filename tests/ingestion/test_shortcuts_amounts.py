"""Formatted Wallet amounts: read only when one value is possible, never guessed."""

import pytest
from argus.domain.ingestion.shortcuts.amounts import parse_amount


@pytest.mark.parametrize(
    ("text", "amount", "currency"),
    [
        ("RD$1,250.00", "1250.00", "DOP"),
        ("RD$ 1 250,00", "1250.00", "DOP"),
        ("US$ 12.50", "12.50", "USD"),
        ("1.250,00 €", "1250.00", "EUR"),
        ("12,50 €", "12.50", "EUR"),
        ("£3.20", "3.20", "GBP"),
        ("USD 3", "3", "USD"),
        ("DOP 1.250,75", "1250.75", "DOP"),
        ("1,250,000.50 USD", "1250000.50", "USD"),
        ("RD$ 1 250,00", "1250.00", "DOP"),
    ],
)
def test_unambiguous_amounts_parse_deterministically(text, amount, currency):
    parsed = parse_amount(text)
    assert (parsed.amount, parsed.currency, parsed.uncertain) == (
        amount,
        currency,
        frozenset(),
    )


@pytest.mark.parametrize("text", ["$12.50", "$ 1,250.00", "¥1.000,5", "C$4.00"])
def test_ambiguous_symbol_keeps_currency_open_and_uncertain(text):
    parsed = parse_amount(text)
    assert parsed.amount is not None
    assert parsed.currency is None
    assert parsed.uncertain == frozenset({"currency"})


def test_explicit_iso_code_settles_only_a_bare_dollar_or_no_marker():
    assert parse_amount("$12.50", currency_code="usd").currency == "USD"
    assert parse_amount("$12.50", currency_code="DOP").currency == "DOP"
    assert parse_amount("12.50", currency_code="DOP").uncertain == frozenset()


@pytest.mark.parametrize(
    ("text", "code"),
    [("R$ 5,00", "DOP"), ("€5.00", "DOP"), ("¥1.000,5", "JPY"), ("C$4.00", "USD")],
)
def test_explicit_code_never_settles_another_marker(text, code):
    parsed = parse_amount(text, currency_code=code)
    assert parsed.currency is None and "currency" in parsed.uncertain


def test_explicit_code_never_overrides_a_marker_that_disagrees():
    parsed = parse_amount("RD$5.00", currency_code="USD")
    assert parsed.currency is None and parsed.uncertain == frozenset({"currency"})


@pytest.mark.parametrize(
    "text",
    ["1,250", "1.250", "$1.250", "1,25,000", "$.99", "12.", "abc", "1-250", "١٢٣"],
)
def test_amounts_with_more_than_one_reading_stay_unresolved(text):
    parsed = parse_amount(text)
    assert parsed.amount is None
    assert "amount" in parsed.uncertain


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("3,450", "3450"),
        ("RD$ 3,450", "3450"),
        ("1,234,567", "1234567"),
        ("3,450.00", "3450.00"),
        ("3,45", "3.45"),
    ],
)
def test_a_named_grouping_separator_reads_groups_of_three_as_thousands(text, amount):
    assert parse_amount(text, grouping=",").amount == amount


@pytest.mark.parametrize("text", ["3.450", "1234,567", "1,25,000", "1,2500"])
def test_a_named_grouping_separator_settles_nothing_else(text):
    parsed = parse_amount(text, grouping=",")
    assert parsed.amount == parse_amount(text).amount


def test_no_marker_is_missing_currency_not_a_guess():
    parsed = parse_amount("12.50")
    assert (parsed.amount, parsed.currency, parsed.uncertain) == (
        "12.50",
        None,
        frozenset(),
    )


def test_unlisted_three_letter_word_is_not_a_currency():
    parsed = parse_amount("ABC 3")
    assert parsed.currency is None and parsed.uncertain == frozenset({"currency"})


@pytest.mark.parametrize("text", ["-$4.00", "($4.00)", "+US$4.00", "US$ 4.00-"])
def test_a_sign_is_doubt_about_direction_not_a_direction(text):
    parsed = parse_amount(text)
    assert parsed.amount == "4.00"
    assert "direction" in parsed.uncertain


def test_unsigned_amount_adds_no_direction_doubt():
    assert "direction" not in parse_amount("US$4.00").uncertain


@pytest.mark.parametrize(
    "text", ["1" * 19, "RD$1234567890123456.789", "9,999,999,999,999,999,999.00"]
)
def test_more_than_eighteen_digits_stays_unresolved(text):
    parsed = parse_amount(text)
    assert parsed.amount is None and "amount" in parsed.uncertain


def test_eighteen_digits_still_parse():
    assert parse_amount("1234567890123456.78").amount == "1234567890123456.78"


def test_missing_and_oversized_amounts():
    assert parse_amount(None).amount is None and parse_amount("").uncertain == set()
    assert parse_amount("9" * 65).uncertain == frozenset({"amount", "currency"})

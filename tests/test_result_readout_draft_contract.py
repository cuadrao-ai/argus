"""Declared run references stay grounded without per-occurrence bookkeeping."""

import pytest
from argus.domain.result_readout_grounding import accepted_readout_text


@pytest.fixture
def fact_sheet():
    values = {
        "portfolio.total_return": (15.126, "percent"),
        "portfolio.annualized_return": (6.846, "percent"),
        "portfolio.annualized_volatility": (28.567, "percent"),
        "portfolio.executed_fills": (13, "count"),
        "portfolio.max_drawdown": (-31.234, "percent"),
        "portfolio.profit": (1234.56, "currency"),
        "window.start": ("2023-09-01", "date"),
    }
    return {
        "facts": {
            key: {"value": value, "unit": unit}
            for key, (value, unit) in values.items()
        }
    }


def figure(key, value):
    return {"fact_key": key, "value": value}


def draft(text, figures=(), language="en"):
    return {"language": language, "text": text, "figures": list(figures)}


@pytest.mark.parametrize("language", ["en", "es-419"])
@pytest.mark.parametrize(
    "key,value",
    [
        ("portfolio.annualized_return", 6.8),
        ("portfolio.annualized_volatility", 28.57),
        ("portfolio.executed_fills", 13),
        ("portfolio.profit", 1235),
        ("window.start", "2023-09-01"),
    ],
)
def test_declared_reference_accepts_stored_value_with_display_rounding(
    fact_sheet, language, key, value
):
    response = draft(f"{value}.", [figure(key, value)], language)
    assert accepted_readout_text(response, facts=fact_sheet, language=language) == (
        response["text"], None
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("unknown.fact", 6.8),
        ("portfolio.total_return", 6.8),
        ("portfolio.annualized_return", 15.1),
        ("portfolio.executed_fills", 12),
        ("portfolio.profit", 1234),
        ("window.start", "2023-10-01"),
    ],
)
def test_false_or_unknown_declared_reference_rejects_complete_draft(
    fact_sheet, key, value
):
    assert accepted_readout_text(
        draft(f"{value}.", [figure(key, value)]), facts=fact_sheet, language="en"
    ) == (None, "invalid_figure_reference")


@pytest.mark.parametrize("language", ["en", "es-419"])
def test_repeated_fill_count_needs_only_one_reference(fact_sheet, language):
    text = (
        "13 executed fills, not 13 completed round trips."
        if language == "en"
        else "13 ejecuciones, no 13 operaciones completas."
    )
    assert accepted_readout_text(
        draft(text, [figure("portfolio.executed_fills", 13)], language),
        facts=fact_sheet,
        language=language,
    ) == (text, None)


@pytest.mark.parametrize(
    "text",
    [
        "The benchmark follows the S&P 500.",
        "Reported revenue grew 18% in 2025.",
        "There were thirteen fills.",
        "The return was 99.9%.",
    ],
)
def test_unreferenced_number_does_not_discard_the_draft(fact_sheet, text):
    assert accepted_readout_text(draft(text), facts=fact_sheet, language="en") == (
        text, None
    )


def test_reported_language_mismatch_rejects_the_complete_draft(fact_sheet):
    assert accepted_readout_text(
        draft("An uneven ride.", language="en"), facts=fact_sheet, language="es-419"
    ) == (None, "language_mismatch")


def test_readout_without_figures_is_valid_without_required_mentions(fact_sheet):
    response = draft("An uneven historical ride.")
    assert accepted_readout_text(response, facts=fact_sheet, language="en-US") == (
        response["text"], None
    )


@pytest.mark.parametrize(
    "value", [True, False, float("nan"), float("inf"), -float("inf")]
)
def test_reference_value_must_be_finite_and_not_boolean(fact_sheet, value):
    assert accepted_readout_text(
        draft("Return: 15.1%.", [figure("portfolio.total_return", value)]),
        facts=fact_sheet,
        language="en",
    ) == (None, "invalid_draft")


@pytest.mark.parametrize("unit", ["unknown", "text", "boolean"])
def test_nonnumeric_row_cannot_justify_numeric_reference(fact_sheet, unit):
    fact_sheet["facts"]["portfolio.total_return"]["unit"] = unit
    assert accepted_readout_text(
        draft("Return: 15.1%.", [figure("portfolio.total_return", 15.1)]),
        facts=fact_sheet,
        language="en",
    ) == (None, "invalid_figure_reference")


def test_empty_draft_selects_complete_fallback(fact_sheet):
    assert accepted_readout_text(draft("  "), facts=fact_sheet, language="en") == (
        None, "empty_draft"
    )


def test_punctuation_normalization_preserves_the_whole_draft(fact_sheet):
    assert accepted_readout_text(
        draft("An uneven ride — with a recovery."), facts=fact_sheet, language="en"
    ) == ("An uneven ride, with a recovery.", None)


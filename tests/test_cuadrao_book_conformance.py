"""The iPhone device book (ios/Packages/CuadraoBook) agrees with the server on money.

The Swift package reads the same vector files, so a change on either side that
moves an amount, a share, a category or the currency set fails here or in
`swift test --package-path ios/Packages/CuadraoBook`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from argus.domain.home_country import currency_codes
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    parse_minor_units,
)
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.loop_reads import personal_share
from argus.domain.recording.loop_schemas import CATEGORY_IDS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ios/Packages/CuadraoBook"
VECTORS = json.loads((PACKAGE / "Vectors/conformance.json").read_text())

INT64_MAX = 2**63 - 1
UINT64_MAX = 2**64 - 1

# Digits are passed to the server through a currency that has them.
CURRENCY_FOR_DIGITS = {0: "JPY", 2: "USD", 3: "KWD"}


@pytest.mark.parametrize("row", VECTORS["parse"], ids=lambda row: f"{row['text']!r}@{row['digits']}")
def test_parse_vectors_match_the_server_parser(row):
    currency = CURRENCY_FOR_DIGITS[row["digits"]]
    assert currency_exponent(currency) == row["digits"]
    if "minor" in row:
        assert parse_minor_units(row["text"], currency) == row["minor"]
    else:
        with pytest.raises(RecordingInputError) as caught:
            parse_minor_units(row["text"], currency)
        assert caught.value.code == row["error"]


@pytest.mark.parametrize("row", VECTORS["format"], ids=lambda row: f"{row['minor']}@{row['digits']}")
def test_format_vectors_match_the_server_formatter(row):
    currency = CURRENCY_FOR_DIGITS[row["digits"]]
    assert format_minor_units(row["minor"], currency) == row["text"]


@pytest.mark.parametrize("row", VECTORS["share"], ids=lambda row: f"{row['amount']}x{row['bps']}")
def test_share_vectors_match_the_server_rounding(row):
    exact = personal_share(row["amount"], row["bps"])
    if row["result"] is not None:
        assert exact == row["result"]
    else:
        # null means the Swift side refuses: its 64-bit arithmetic cannot hold the exact answer.
        assert abs(exact) > INT64_MAX or abs(row["amount"]) * row["bps"] > UINT64_MAX


def test_category_vector_matches_the_server_ids():
    assert tuple(VECTORS["categories"]) == CATEGORY_IDS


def test_currency_vector_is_the_server_set_and_exponents():
    table = json.loads((PACKAGE / "Vectors/currencies.json").read_text())
    assert set(table) == set(currency_codes())
    assert table == {code: currency_exponent(code) for code in table}


def test_generated_currency_files_are_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "ios/scripts/generate_book_currencies.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

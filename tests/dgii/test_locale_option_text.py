"""Spanish UI choices and the official 606 tables are the same fact."""

import json
from pathlib import Path

import pytest
from argus.domain.business.dgii_codes import EXPENSE_TYPES, PAYMENT_FORMS


@pytest.mark.parametrize(
    ("field", "official"),
    [("category", EXPENSE_TYPES), ("payment_method", PAYMENT_FORMS)],
)
def test_spanish_option_codes_and_text_match_official_tables(
    field: str, official: dict[str, str]
) -> None:
    locale = Path(__file__).resolve().parents[2] / "web/public/locales/es-419/common.json"
    options = json.loads(locale.read_text(encoding="utf-8"))["business"]["dgii"]["option"]
    assert set(options[field]) == set(official)
    assert options[field] == official

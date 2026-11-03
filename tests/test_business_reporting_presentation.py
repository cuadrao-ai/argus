"""A saved table setup from before the 606 columns still opens: Categoría's
slot becomes Tipo de gasto and Forma de pago joins the order hidden."""

import pytest
from argus.domain.business.reporting_preferences import (
    HIDDEN_COLUMNS,
    TABLE_COLUMNS,
    Presentation,
)
from pydantic import ValidationError

LEGACY_ORDER = [
    "counterparty",
    "date",
    "gross_amount",
    "currency",
    "family",
    "category",
    "stage",
    "note",
    "attachment",
    "funding",
]


def test_default_presentation_shows_tipo_de_gasto_and_hides_forma_de_pago():
    presentation = Presentation()
    assert presentation.order == TABLE_COLUMNS
    assert "category" not in TABLE_COLUMNS
    assert presentation.hidden == HIDDEN_COLUMNS == ("funding", "payment_form")


def test_legacy_category_order_upgrades_in_place():
    presentation = Presentation.model_validate(
        {"order": LEGACY_ORDER, "hidden": ["category"], "density": 40}
    )
    assert presentation.order == (
        "counterparty",
        "date",
        "gross_amount",
        "currency",
        "family",
        "expense_type",
        "payment_form",
        "stage",
        "note",
        "attachment",
        "funding",
    )
    assert presentation.hidden == ("expense_type", "payment_form")
    assert presentation.density == 40


def test_current_order_is_not_rewritten():
    order = list(reversed(TABLE_COLUMNS[1:]))
    presentation = Presentation.model_validate(
        {"order": ["counterparty", *order], "hidden": []}
    )
    assert presentation.order == ("counterparty", *order)
    assert presentation.hidden == ()


def test_category_is_no_longer_a_column():
    with pytest.raises(ValidationError):
        Presentation.model_validate({"order": TABLE_COLUMNS, "hidden": ["category"]})
    with pytest.raises(ValidationError):
        Presentation.model_validate({"order": [*TABLE_COLUMNS, "category"]})

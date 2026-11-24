"""Registros keeps Estado and marks the fields its readiness verdict names."""

import pytest
from argus.domain.business import reporting_projection
from argus.domain.business.missing_reasons import REASONS
from argus.domain.business.reporting_columns import (
    COLUMNS,
    TABLE_COLUMNS,
    missing_columns,
)
from argus.domain.business.reporting_preferences import Presentation
from argus.domain.business.reporting_query import ReportRecord
from pydantic import ValidationError

FIELD_COLUMNS = {
    "rnc": "counterparty_id",
    "counterparty": "counterparty",
    "occurred_on": "date",
    "category": "expense_type",
    "billed_amount": "net_amount",
    "itbis": "itbis_amount",
    "amount": "gross_amount",
    "ncf": "fiscal_number",
    "payment_method": "payment_form",
}
FIELDS_WITHOUT_COLUMNS = {
    None,
    "currency",
    "itbis_cost",
    "itbis_proportionality",
    "itbis_withheld",
    "legal_tip",
    "modified_ncf",
    "paid_on",
}


def test_estado_is_the_only_status_column():
    assert "stage" in TABLE_COLUMNS
    assert {"missing", "funding"}.isdisjoint(TABLE_COLUMNS)


def test_each_reason_field_has_one_column_or_an_explicit_omission():
    mapped = [(spec.reason_field, spec.key) for spec in COLUMNS if spec.reason_field]
    assert len(mapped) == len(FIELD_COLUMNS)
    assert dict(mapped) == FIELD_COLUMNS
    assert not FIELD_COLUMNS.keys() & FIELDS_WITHOUT_COLUMNS
    assert {reason.field for reason in REASONS.values()} == (
        FIELD_COLUMNS.keys() | FIELDS_WITHOUT_COLUMNS
    )


@pytest.mark.parametrize("code", REASONS)
@pytest.mark.parametrize("family", ["purchase", "sale"])
def test_each_reason_marks_the_report_row_column_its_family_offers(
    code, family, monkeypatch
):
    row = ReportRecord(
        row_id="activity:synthetic",
        linked_activity_ids=("synthetic",),
        revision=1,
        report_date=None,
        date_basis="activity_effective",
        family=family,
    )
    monkeypatch.setattr(reporting_projection, "readiness", lambda *_: (False, (code,)))
    [judged] = reporting_projection.with_export_verdicts((row,), {}, frozenset())
    expected = FIELD_COLUMNS.get(REASONS[code].field)
    if family == "sale" and expected in {"expense_type", "payment_form"}:
        expected = None
    assert judged.missing_fields == ((expected,) if expected else ())


def test_missing_columns_follow_registry_order_and_are_unique():
    assert missing_columns((), "purchase") == ()
    assert missing_columns(
        ("missing_ncf", "invalid_rnc", "missing_date", "missing_rnc"), "purchase"
    ) == ("counterparty_id", "date", "fiscal_number")


def test_layout_with_only_hidden_columns_drops_the_retired_keys():
    layout = Presentation.model_validate(
        {"hidden": ["funding", "note", "missing"], "density": 56}
    )
    assert layout.order == TABLE_COLUMNS
    assert layout.hidden == ("note",)
    assert layout.density == 56


def test_only_retired_columns_visible_restores_stage_at_its_saved_position():
    current = list(reversed(TABLE_COLUMNS))
    legacy = ["missing", *current, "funding"]
    layout = Presentation.model_validate(
        {"order": legacy, "hidden": [*current, "funding"], "density": 40}
    )
    assert layout.order == tuple(current)
    assert layout.hidden == tuple(key for key in current if key != "stage")
    assert layout.density == 40
    with pytest.raises(ValidationError):
        Presentation.model_validate({"order": legacy, "hidden": legacy})
    with pytest.raises(ValidationError):
        Presentation.model_validate({"order": legacy, "hidden": [*current, "stage"]})

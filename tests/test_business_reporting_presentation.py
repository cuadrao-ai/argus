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


def test_default_presentation_has_eight_visible_columns():
    presentation = Presentation()
    assert presentation.order == TABLE_COLUMNS
    assert "category" not in TABLE_COLUMNS
    assert (
        presentation.hidden
        == HIDDEN_COLUMNS
        == ("funding", "payment_form", "expense_type", "fiscal_number", "itbis_amount")
    )


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
        "fiscal_number",
        "itbis_amount",
    )
    assert presentation.hidden == (
        "expense_type",
        "payment_form",
        "fiscal_number",
        "itbis_amount",
    )
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


def test_legacy_order_with_no_hidden_key_hides_forma_de_pago_once():
    presentation = Presentation.model_validate({"order": LEGACY_ORDER})
    assert presentation.hidden == (
        "funding",
        "payment_form",
        "expense_type",
        "fiscal_number",
        "itbis_amount",
    )


@pytest.mark.parametrize("version", [1, 2])
def test_query_returns_backend_default_presentation(version):
    from datetime import datetime, timezone

    from argus.domain.business.reporting import ReportIdentity
    from argus.domain.business.reporting_preferences import ReportRequestV2
    from argus.domain.business.reporting_query import ReportRequest, run_query

    request = ReportRequest() if version == 1 else ReportRequestV2()
    answer = run_query(
        ReportIdentity(
            "synthetic-business", "synthetic-actor", "synthetic-owner", None, ""
        ),
        (),
        request,
        datetime(2026, 11, 6, tzinfo=timezone.utc),
    )
    assert answer.presentation == Presentation()
    assert [
        key for key in answer.presentation.order if key not in answer.presentation.hidden
    ] == [
        "counterparty",
        "date",
        "gross_amount",
        "currency",
        "family",
        "stage",
        "note",
        "attachment",
    ]
    assert answer.presentation.hidden == (
        "funding",
        "payment_form",
        "expense_type",
        "fiscal_number",
        "itbis_amount",
    )


def test_query_preserves_explicit_layout_without_changing_fingerprint():
    from datetime import datetime, timezone

    from argus.domain.business.reporting import ReportIdentity
    from argus.domain.business.reporting_preferences import ReportRequestV2
    from argus.domain.business.reporting_query import run_query

    identity = ReportIdentity(
        "synthetic-business", "synthetic-actor", "synthetic-owner", None, ""
    )
    observed_at = datetime(2026, 11, 6, tzinfo=timezone.utc)
    presentation = Presentation(
        order=("counterparty", *reversed(TABLE_COLUMNS[1:])), hidden=(), density=40
    )
    answer = run_query(
        identity, (), ReportRequestV2(presentation=presentation), observed_at
    )
    assert answer.presentation == presentation
    assert (
        answer.fingerprint
        == run_query(identity, (), ReportRequestV2(), observed_at).fingerprint
    )


def test_v1_still_rejects_presentation():
    from argus.domain.business.reporting_query import ReportRequest

    with pytest.raises(ValidationError):
        ReportRequest.model_validate({"presentation": Presentation().model_dump()})


def test_recorded_preview_answer_matches_backend():
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    from argus.domain.business.reporting import ReportIdentity
    from argus.domain.business.reporting_query import ReportRequest, run_query

    answer = run_query(
        ReportIdentity(
            "synthetic-business", "synthetic-actor", "synthetic-owner", None, ""
        ),
        (),
        ReportRequest(),
        datetime(2026, 11, 6, tzinfo=timezone.utc),
    )
    fixture = (
        Path(__file__).resolve().parents[1]
        / "web/test-fixtures/records-default-report-answer.json"
    )
    assert json.loads(fixture.read_text()) == answer.model_dump(mode="json")


def test_saved_order_appends_fiscal_columns_hidden_without_moving_existing_columns():
    order = ["counterparty", *reversed(LEGACY_ORDER[1:])]
    order[order.index("category")] = "expense_type"
    order.insert(2, "payment_form")
    presentation = Presentation.model_validate(
        {"order": order, "hidden": ["date"], "density": 56}
    )
    assert presentation.order == (*order, "fiscal_number", "itbis_amount")
    assert presentation.hidden == ("date", "fiscal_number", "itbis_amount")
    assert presentation.density == 56


def test_selected_fiscal_columns_stay_visible_and_keep_their_order():
    order = ("counterparty", *reversed(TABLE_COLUMNS[1:]))
    presentation = Presentation(order=order, hidden=())
    assert presentation.order == order
    assert presentation.hidden == ()


@pytest.mark.parametrize(
    "selected,missing",
    [("fiscal_number", "itbis_amount"), ("itbis_amount", "fiscal_number")],
)
def test_partial_fiscal_upgrade_preserves_selected_column(selected, missing):
    order = [key for key in TABLE_COLUMNS if key != missing]
    presentation = Presentation.model_validate({"order": order, "hidden": []})
    assert presentation.order == (*order, missing)
    assert presentation.hidden == (missing,)
    assert selected not in presentation.hidden


@pytest.mark.parametrize(
    "invalid",
    [
        {"order": [*TABLE_COLUMNS, "fiscal_number"]},
        {"order": [*TABLE_COLUMNS[1:], "counterparty"]},
        {"order": [*TABLE_COLUMNS, "unknown"]},
        {"hidden": ["fiscal_number", "fiscal_number"]},
        {"hidden": ["unknown"]},
    ],
)
def test_fiscal_migration_keeps_presentation_validation(invalid):
    with pytest.raises(ValidationError):
        Presentation.model_validate(invalid)

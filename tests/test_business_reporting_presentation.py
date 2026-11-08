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
        == ("funding", "payment_form", "expense_type")
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


def test_legacy_order_with_no_hidden_key_hides_forma_de_pago_once():
    presentation = Presentation.model_validate({"order": LEGACY_ORDER})
    assert presentation.hidden == ("funding", "payment_form", "expense_type")


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
    assert answer.presentation.hidden == ("funding", "payment_form", "expense_type")


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
    expected = json.loads(fixture.read_text())
    actual = answer.model_dump(mode="json")
    expected.pop("fingerprint")
    fingerprint = actual.pop("fingerprint")
    assert expected == actual
    assert (
        fingerprint
        == run_query(
            ReportIdentity(
                "synthetic-business", "synthetic-actor", "synthetic-owner", None, ""
            ),
            (),
            ReportRequest(),
            datetime(2026, 11, 6, tzinfo=timezone.utc),
        ).fingerprint
    )
    assert (
        fingerprint
        != run_query(
            ReportIdentity(
                "synthetic-business", "synthetic-actor", "synthetic-owner", None, ""
            ),
            (),
            ReportRequest(filters={"record_families": ["sale"]}),
            datetime(2026, 11, 6, tzinfo=timezone.utc),
        ).fingerprint
    )

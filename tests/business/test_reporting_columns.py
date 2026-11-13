"""The column registry is the one owner of every Registros column fact."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import pytest
from argus.domain.business import country
from argus.domain.business.reporting import ReportIdentity
from argus.domain.business.reporting_columns import (
    COLUMNS,
    CURRENCY_LABEL,
    REQUIRED_COLUMNS,
    TABLE_COLUMNS,
    TableColumn,
)
from argus.domain.business.reporting_preferences import (
    RecipeInput,
    ReportRequest,
    ReportRequestV2,
)
from argus.domain.business.reporting_query import run_query
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "web" / "public" / "locales"
IDENTITY = ReportIdentity(
    "synthetic-business", "synthetic-actor", "synthetic-owner", None, ""
)
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def answer(request, **options):
    return run_query(IDENTITY, (), request, NOW, **options)


def test_the_registry_is_the_one_ordered_key_list():
    assert get_args(TableColumn) == TABLE_COLUMNS
    assert len({spec.key for spec in COLUMNS}) == len(COLUMNS)


@pytest.mark.parametrize(
    "language", sorted(path.name for path in LOCALES.iterdir() if path.is_dir())
)
def test_every_column_has_a_name_in_every_locale(language):
    words = json.loads((LOCALES / language / "common.json").read_text("utf-8"))
    for path in (*(spec.label for spec in COLUMNS), CURRENCY_LABEL):
        value = words
        for part in path.split("."):
            value = value[part]
        assert isinstance(value, str) and value.strip(), (language, path)


@pytest.mark.parametrize("code", sorted(country.COUNTRIES))
def test_a_country_omits_only_optional_registry_columns(code):
    omitted = country.business_country(code).omitted_columns
    assert omitted <= set(TABLE_COLUMNS)
    assert not omitted & REQUIRED_COLUMNS


def test_the_answer_carries_each_offered_column_with_its_rules():
    columns = answer(ReportRequestV2(filters={"record_families": ["purchase"]})).columns
    assert [column.key for column in columns] == list(TABLE_COLUMNS)
    counterparty, gross = columns[0], columns[TABLE_COLUMNS.index("gross_amount")]
    assert (counterparty.label_key, counterparty.required, counterparty.pinned) == (
        "business.transactions.columns.contraparte",
        True,
        True,
    )
    assert (gross.label_key, gross.required, gross.pinned) == (
        "business.terms.total",
        True,
        False,
    )
    assert [column.key for column in columns if not column.shown] == [
        "fiscal_number",
        "expense_type",
        "payment_form",
        "funding",
    ]


def test_ventas_offers_no_purchase_columns():
    keys = [
        column.key
        for column in answer(
            ReportRequestV2(filters={"record_families": ["sale"]})
        ).columns
    ]
    assert "expense_type" not in keys and "payment_form" not in keys
    assert "funding" in keys


def test_a_country_omission_leaves_the_answer(monkeypatch):
    monkeypatch.setitem(
        country.COUNTRIES,
        "DO",
        country.BusinessCountry("DO", "DOP", frozenset({"funding"})),
    )
    request = ReportRequestV2(filters={"record_families": ["purchase"]})
    assert "funding" not in [c.key for c in answer(request, country="DO").columns]
    assert "funding" in [c.key for c in answer(request, country="US").columns]


def test_a_link_missing_the_net_amount_shows_it_before_the_total():
    order = [key for key in TABLE_COLUMNS if key != "net_amount"]
    request = ReportRequestV2.model_validate(
        {"presentation": {"order": order, "hidden": []}}
    )
    result = answer(request)
    gross = result.presentation.order.index("gross_amount")
    assert result.presentation.order[gross - 1] == "net_amount"
    assert "net_amount" not in result.presentation.hidden
    shown = {column.key: column.shown for column in result.columns}
    assert shown["net_amount"] is True


def test_a_layout_missing_any_other_column_gets_it_last_and_hidden():
    order = [key for key in TABLE_COLUMNS if key != "note"]
    result = answer(
        ReportRequestV2.model_validate({"presentation": {"order": order, "hidden": []}})
    )
    assert result.presentation.order[-1] == "note"
    assert result.presentation.hidden == ("note",)
    assert next(c for c in result.columns if c.key == "note").shown is False


@pytest.mark.parametrize("version", [1, 2])
def test_the_first_tables_columns_list_is_accepted_and_dropped(version):
    stored = {
        "schema_version": version,
        "columns": ["date", "family", "stage", "counterparty", "currency"],
    }
    recipe = TypeAdapter(RecipeInput).validate_python(stored)
    assert "columns" not in recipe.model_dump()
    request = ReportRequest.model_validate({"columns": ["date"], "page": 2})
    assert request.page == 2 and "columns" not in request.model_dump()


@pytest.mark.parametrize("family", ["purchase", "sale"])
def test_recorded_preview_columns_match_backend(family):
    fixture = ROOT / "web/test-fixtures/records-columns-by-family.json"
    request = ReportRequestV2(filters={"record_families": [family]})
    recorded = json.loads(fixture.read_text("utf-8"))[family]
    assert recorded == [c.model_dump(mode="json") for c in answer(request).columns]

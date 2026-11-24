"""The column registry is the one owner of every Registros column fact."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import pytest
from argus.domain.business import country
from argus.domain.business.reporting import ReportIdentity
from argus.domain.business.reporting_columns import (
    COLUMN_LABELS,
    COLUMNS,
    CURRENCY_LABEL,
    HIDDEN_COLUMNS,
    SPECS,
    TABLE_COLUMNS,
    Family,
    TableColumn,
)
from argus.domain.business.reporting_file import RecordsExport, build_file
from argus.domain.business.reporting_preferences import (
    Presentation,
    RecipeInput,
    ReportRequest,
    ReportRequestV2,
)
from argus.domain.business.reporting_query import run_query
from argus.domain.business.reporting_store import ExportSource
from pydantic import TypeAdapter, ValidationError

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
    for path in (*COLUMN_LABELS, CURRENCY_LABEL):
        value = words
        for part in path.split("."):
            value = value[part]
        assert isinstance(value, str) and value.strip(), (language, path)


@pytest.mark.parametrize("code", sorted(country.COUNTRIES))
def test_a_country_omits_only_registry_columns(code):
    assert country.business_country(code).omitted_columns <= set(TABLE_COLUMNS)


#: The 12 columns a layout named before RNC o Cédula joined the table.
OLD_ORDER = [
    "counterparty",
    "fiscal_number",
    "date",
    "net_amount",
    "itbis_amount",
    "gross_amount",
    "stage",
    "note",
    "attachment",
    "expense_type",
    "payment_form",
    "funding",
]
OLD_HIDDEN = ["fiscal_number", "expense_type", "payment_form", "funding"]


@pytest.mark.parametrize(
    "family,shown,menu",
    [
        (
            "purchase",
            [
                "counterparty_id",
                "date",
                "expense_type",
                "net_amount",
                "itbis_amount",
                "gross_amount",
                "stage",
            ],
            [
                "counterparty",
                "fiscal_number",
                "note",
                "attachment",
                "payment_form",
            ],
        ),
        (
            "sale",
            [
                "counterparty_id",
                "date",
                "net_amount",
                "itbis_amount",
                "gross_amount",
                "stage",
            ],
            ["counterparty", "fiscal_number", "note", "attachment"],
        ),
    ],
)
def test_the_default_table_starts_with_the_taxpayer_id(family, shown, menu):
    columns = answer(ReportRequestV2(filters={"record_families": [family]})).columns
    assert [column.key for column in columns if column.shown] == shown
    assert [column.key for column in columns if not column.shown] == menu
    assert columns[0].label_key == "business.transactions.columns.rnc_cedula"


@pytest.mark.parametrize(
    ("family", "language", "name"),
    [
        ("purchase", "es-419", "Emisor"),
        ("sale", "es-419", "Cliente"),
        ("purchase", "en", "Supplier"),
        ("sale", "en", "Customer"),
    ],
)
def test_the_name_column_is_emisor_on_compras_and_cliente_on_ventas(
    family, language, name
):
    words = json.loads((LOCALES / language / "common.json").read_text("utf-8"))
    request = ReportRequestV2(filters={"record_families": [family]})
    path = next(c.label_key for c in answer(request).columns if c.key == "counterparty")
    value = words
    for part in path.split("."):
        value = value[part]
    assert value == name

    def header(mode: str, locale: str) -> list[str]:
        columns = ("counterparty",) if mode == "table" else ()
        choice = RecordsExport(report=request, mode=mode, columns=columns, format="csv")
        built = build_file(ExportSource((), {}, NOW), choice, locale=locale)
        return next(csv.reader(io.StringIO(built.content.decode("utf-8-sig"))))

    assert header("table", language)[0] == name
    assert header("dgii", language) == header("dgii", "es-419")
    assert name not in header("dgii", language)


def test_the_answer_names_no_column_the_person_cannot_hide_or_move():
    columns = answer(ReportRequestV2()).columns
    assert set(columns[0].model_dump()) == {"key", "label_key", "shown", "families"}


def test_the_answer_says_which_tables_offer_each_column():
    for column in answer(ReportRequestV2()).columns:
        assert set(column.families) == SPECS[column.key].families


@pytest.mark.parametrize("key", TABLE_COLUMNS)
def test_any_column_can_be_hidden_and_any_column_can_lead(key):
    order = [key, *(other for other in TABLE_COLUMNS if other != key)]
    first = Presentation.model_validate({"order": order, "hidden": []})
    assert first.order[0] == key
    assert key in Presentation.model_validate({"hidden": [key]}).hidden


def test_a_layout_keeps_one_column_shown():
    with pytest.raises(ValidationError):
        Presentation.model_validate({"hidden": list(TABLE_COLUMNS)})


def shown_per_table(layout: Presentation, code: str = "DO") -> list[int]:
    return [
        sum(
            column.shown
            for column in answer(
                ReportRequestV2(
                    presentation=layout, filters={"record_families": [family]}
                ),
                country=code,
            ).columns
        )
        for family in get_args(Family)
    ]


@pytest.mark.parametrize("key", TABLE_COLUMNS)
def test_an_accepted_layout_shows_a_column_in_every_table(key):
    alone = {"hidden": [other for other in TABLE_COLUMNS if other != key]}
    if SPECS[key].families == set(get_args(Family)):
        assert shown_per_table(Presentation.model_validate(alone)) == [1, 1]
    else:
        with pytest.raises(ValidationError):
            Presentation.model_validate(alone)


def test_columns_one_table_lacks_cannot_be_the_only_ones_shown():
    partial = [spec.key for spec in COLUMNS if spec.families != set(get_args(Family))]
    assert partial, "the registry has columns only some tables offer"
    hidden = [key for key in TABLE_COLUMNS if key not in partial]
    with pytest.raises(ValidationError):
        Presentation.model_validate({"hidden": hidden})
    kept = Presentation.model_validate({"hidden": hidden[1:]})
    assert min(shown_per_table(kept)) == 1


def test_a_column_one_country_omits_cannot_be_the_only_one_shown(monkeypatch):
    monkeypatch.setitem(
        country.COUNTRIES,
        "US",
        country.BusinessCountry("US", "USD", frozenset({"date"})),
    )
    with pytest.raises(ValidationError):
        Presentation.model_validate(
            {"hidden": [key for key in TABLE_COLUMNS if key != "date"]}
        )


def test_a_layout_from_before_the_taxpayer_id_still_loads():
    stored = {"order": OLD_ORDER, "hidden": OLD_HIDDEN, "density": 40}
    result = answer(ReportRequestV2.model_validate({"presentation": stored}))
    order = [key for key in OLD_ORDER if key != "funding"]
    hidden = [key for key in OLD_HIDDEN if key != "funding"]
    assert result.presentation.order == (*order, "counterparty_id")
    assert result.presentation.hidden == (*hidden, "counterparty_id")
    assert result.presentation.density == 40
    assert result.columns[0].key == "counterparty" and result.columns[0].shown


def test_an_old_saved_view_and_an_old_link_still_load():
    recipe = {
        "schema_version": 2,
        "presentation": {"order": OLD_ORDER, "hidden": OLD_HIDDEN},
    }
    view = TypeAdapter(RecipeInput).validate_python(recipe)
    link = ReportRequestV2.model_validate_json(json.dumps({**recipe, "page": 1}))
    assert view.presentation == link.presentation
    assert link.presentation.order[-1] == "counterparty_id"


def test_the_registry_default_is_the_one_default_layout():
    assert Presentation().order == TABLE_COLUMNS
    assert Presentation().hidden == HIDDEN_COLUMNS
    assert {spec.file for spec in SPECS.values()} == {"as_shown", "always", "default"}


def test_ventas_offers_no_purchase_columns():
    keys = [
        column.key
        for column in answer(
            ReportRequestV2(filters={"record_families": ["sale"]})
        ).columns
    ]
    assert "expense_type" not in keys and "payment_form" not in keys


def test_a_country_omission_leaves_the_answer(monkeypatch):
    monkeypatch.setitem(
        country.COUNTRIES,
        "DO",
        country.BusinessCountry("DO", "DOP", frozenset({"note"})),
    )
    request = ReportRequestV2(filters={"record_families": ["purchase"]})
    assert "note" not in [c.key for c in answer(request, country="DO").columns]
    assert "note" in [c.key for c in answer(request, country="US").columns]


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

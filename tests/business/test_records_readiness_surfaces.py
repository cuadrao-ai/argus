"""Inicio, table files and export previews render the report readiness verdict."""

from datetime import date

import pytest
from argus.domain.business import month_close_store
from argus.domain.business.reporting_columns import SPECS
from argus.domain.business.reporting_file import _table_cell, summarize_export
from argus.domain.business.reporting_preferences import Presentation
from faker import Faker

from tests.business.test_records_file import NOW, report, row, source


@pytest.fixture
def fake():
    result = Faker()
    result.seed_instance(2169)
    return result


def test_reason_is_visible_after_state_in_new_and_existing_layouts():
    assert SPECS["missing"].label == "business.transactions.layout.column_reason"
    assert not SPECS["missing"].hidden
    before = Presentation().model_dump(mode="json")
    before["order"] = [key for key in before["order"] if key != "missing"]
    upgraded = Presentation.model_validate(before)
    assert upgraded.order[upgraded.order.index("stage") + 1] == "missing"
    assert "missing" not in upgraded.hidden


@pytest.mark.parametrize("ready,expected", [(True, "Listo"), (False, "Faltan datos")])
def test_table_file_state_uses_only_ready(fake, ready, expected):
    record = row(fake, ready=ready, stage="exported", missing=("ncf_missing",))
    assert _table_cell(record, "stage", "es-419") == expected


@pytest.mark.parametrize(
    "ready,missing,expected",
    [
        (True, ("ncf_missing",), ""),
        (False, ("ncf_missing",), "Falta el NCF"),
        (False, ("ncf_missing", "rnc_missing", "date_missing"), "Falta el NCF +2"),
        (False, ("future_reason",), "Falta un dato"),
        (False, (), ""),
    ],
)
def test_table_file_reason_uses_ordered_missing(fake, ready, missing, expected):
    record = row(fake, ready=ready, missing=missing, export_missing="rnc_missing")
    assert _table_cell(record, "missing", "es-419") == expected


@pytest.mark.parametrize("ready,expected", [(None, 2), (False, 2), (True, 0)])
def test_preview_count_matches_the_current_report_filters(fake, ready, expected):
    dataset = source(
        row(fake, ready=False, counterparty="selected"),
        row(fake, ready=False, counterparty="selected", stage="exported"),
        row(fake, ready=True, counterparty="selected"),
        row(fake, ready=False, counterparty="outside"),
        row(fake, ready=False, counterparty="selected", currency="USD"),
        row(fake, ready=False, counterparty="selected", family="sale"),
        row(fake, ready=False, counterparty="selected", report_date=date(2026, 8, 1)),
    )
    preview = summarize_export(
        dataset, report(q="selected", currencies=["DOP"], ready=ready)
    )
    assert preview.not_ready == expected


def test_inicio_groups_current_month_report_readiness_by_family_and_currency(fake):
    records = (
        row(fake, ready=False, currency="DOP"),
        row(fake, ready=False, currency="DOP", stage="exported"),
        row(fake, ready=False, currency="USD"),
        row(fake, ready=False, family="sale", currency="USD"),
        row(fake, ready=True),
        row(fake, ready=False, report_date=date(2026, 8, 1)),
    )
    result = month_close_store.not_ready_rows(records, "2026-09", NOW)
    assert result == [
        {"family": "purchase", "currency": "DOP", "count": 2, "by_currency": True},
        {"family": "purchase", "currency": "USD", "count": 1, "by_currency": True},
        {"family": "sale", "currency": "USD", "count": 1, "by_currency": False},
    ]
    for item in result:
        preview = summarize_export(
            source(*records),
            report(
                record_families=[item["family"]],
                currencies=[item["currency"]],
                ready=False,
            ),
        )
        assert preview.not_ready == item["count"]


@pytest.mark.parametrize("family", ["purchase", "sale"])
def test_month_reader_uses_projected_readiness_on_its_authorized_snapshot(
    fake, monkeypatch, family
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from argus.api.business_month_close_schemas import MonthClose
    from argus.domain.business import reporting_store

    connection = object()
    context = object()
    authority = object()

    @contextmanager
    def session(received_authority, received_context, capability):
        assert (received_authority, received_context, capability) == (
            authority,
            context,
            "read",
        )
        yield connection, SimpleNamespace(context=context)

    def projected(received_authority, received_context, received_connection):
        assert (received_authority, received_context, received_connection) == (
            authority,
            context,
            connection,
        )
        return (
            SimpleNamespace(observed_at=NOW),
            (row(fake, ready=False, family=family),),
            None,
        )

    monkeypatch.setattr(month_close_store, "_session", session)
    monkeypatch.setattr(month_close_store, "_collect", lambda *_args: ((), {}))
    monkeypatch.setattr(reporting_store, "_projected", projected)
    monkeypatch.setattr(
        month_close_store,
        "_form_statuses",
        lambda *_args: (
            {"606": "no_operations", "607": "no_operations"},
            {},
            frozenset(),
            {},
        ),
    )
    answer = MonthClose.model_validate(
        month_close_store.read_month(authority, context, "2026-09", settlement=False)
    )
    assert answer.missing_fiscal_rows == []
    assert [item.model_dump() for item in answer.not_ready_rows] == [
        {"family": family, "currency": "DOP", "count": 1, "by_currency": False}
    ]

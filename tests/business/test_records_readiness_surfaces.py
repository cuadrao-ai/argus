"""Inicio, table files and overview render the report readiness verdict."""

from datetime import date

import pytest
from argus.domain.business import month_close_store
from argus.domain.business.reporting import ReportIdentity
from argus.domain.business.reporting_columns import SPECS
from argus.domain.business.reporting_file import _table_cell
from argus.domain.business.reporting_preferences import Presentation
from argus.domain.business.reporting_query import run_query
from faker import Faker

from tests.business.test_month_close import document
from tests.business.test_records_file import NOW, report, row


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
    record = row(fake, ready=ready, stage="exported", missing=("missing_ncf",))
    assert _table_cell(record, "stage", "es-419") == expected


@pytest.mark.parametrize(
    "ready,missing,expected",
    [
        (True, ("missing_ncf",), ""),
        (False, ("missing_ncf",), "Falta el NCF"),
        (False, ("missing_ncf", "missing_rnc", "missing_date"), "Falta el NCF +2"),
        (False, ("future_reason",), "Falta un dato"),
        (False, (), ""),
    ],
)
def test_table_file_reason_uses_ordered_missing(fake, ready, missing, expected):
    record = row(fake, ready=ready, missing=missing, export_missing="missing_rnc")
    assert _table_cell(record, "missing", "es-419") == expected


@pytest.mark.parametrize("ready,expected", [(None, 2), (False, 2), (True, 0)])
def test_overview_count_matches_the_current_report_filters(fake, ready, expected):
    dataset = (
        row(fake, ready=False, counterparty="selected"),
        row(fake, ready=False, counterparty="selected", stage="exported"),
        row(fake, ready=True, counterparty="selected"),
        row(fake, ready=False, counterparty="outside"),
        row(fake, ready=False, counterparty="selected", currency="USD"),
        row(fake, ready=False, counterparty="selected", family="sale"),
        row(fake, ready=False, counterparty="selected", report_date=date(2026, 8, 1)),
    )
    answer = run_query(
        ReportIdentity("b", "a", "o", "g", ""),
        dataset,
        report(q="selected", currencies=["DOP"], ready=ready),
        NOW,
    )
    assert answer.overview.not_ready == expected


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
        answer = run_query(
            ReportIdentity("b", "a", "o", "g", ""),
            records,
            report(
                record_families=[item["family"]],
                currencies=[item["currency"]],
                ready=False,
            ),
            NOW,
        )
        assert answer.overview.not_ready == item["count"]


@pytest.mark.parametrize("settlement", [False, True])
@pytest.mark.parametrize("family", ["purchase", "sale"])
@pytest.mark.parametrize("refusal", [None, "business_report_too_large", "permission_denied"])
def test_month_reader_uses_projected_readiness_on_its_authorized_snapshot(
    fake, monkeypatch, family, refusal, settlement
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from argus.api.business_month_close_schemas import MonthClose
    from argus.domain.business import reporting_store
    from argus.domain.business.authority import ActionError

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
        if refusal:
            raise ActionError("invalid_input", refusal)
        return (
            SimpleNamespace(observed_at=NOW),
            (row(fake, ready=False, family=family),),
            None,
        )

    monkeypatch.setattr(month_close_store, "_session", session)
    documents = (
        document(
            occurred_on=date(2026, 9, 15),
            total_minor=11800,
            itbis_minor=1800,
        ),
    )
    monkeypatch.setattr(month_close_store, "_collect", lambda *_args: (documents, {}))
    monkeypatch.setattr(reporting_store, "projected_records", projected)
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
    if refusal == "permission_denied":
        with pytest.raises(ActionError, match=refusal):
            month_close_store.read_month(authority, context, "2026-09", settlement=settlement)
        return
    answer = MonthClose.model_validate(
        month_close_store.read_month(authority, context, "2026-09", settlement=settlement)
    )
    assert answer.missing_fiscal_rows == []
    assert answer.month == "2026-09"
    assert answer.dgii_forms.model_dump(by_alias=True) == {
        "606": "no_operations", "607": "no_operations"
    }
    assert answer.closed is True
    assert len(answer.currencies) == 1
    assert answer.currencies[0].income_before_itbis_minor == 10000
    assert answer.currencies[0].itbis_charged_minor == 1800
    assert answer.currencies[0].documents_counted == 1
    if refusal:
        assert answer.not_ready_rows is None
        return
    assert [item.model_dump() for item in answer.not_ready_rows] == [
        {"family": family, "currency": "DOP", "count": 1, "by_currency": False}
    ]

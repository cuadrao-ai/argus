"""Registros sales use document facts; fiscal assessments retain their own rules."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from argus.domain.business.actions import accepted_edit, approval
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_export import line_assessments
from argus.domain.business.fact_blockers import blockers
from argus.domain.business.reporting_file import summarize_export
from argus.domain.business.reporting_projection import readiness, with_export_verdicts
from faker import Faker
from fastapi.testclient import TestClient

from tests.business.test_records_export_filename import (
    client as export_client,  # noqa: F401
)
from tests.business.test_records_file import NOW, report, row, source
from tests.dgii.test_packet import practice_records


@pytest.mark.parametrize(
    "number,identity,day,expected",
    [
        ("B0200000001", None, date(2026, 9, 1), ()),
        ("B0100000001", None, date(2026, 9, 1), ("missing_rnc",)),
        ("E310000000001", None, date(2026, 9, 1), ("missing_rnc",)),
        (None, None, date(2026, 9, 1), ("missing_ncf",)),
        ("B0200000001", None, None, ("missing_date",)),
        ("B0100000001", None, None, ("missing_rnc", "missing_date")),
        (None, None, None, ("missing_date", "missing_ncf")),
        (" b0100000001 ", "131000001", date(2026, 9, 1), ()),
        ("E310000000001", "131000001", date(2026, 9, 1), ()),
        ("B3100000001", None, date(2026, 9, 1), ()),
        ("E010000000001", None, date(2026, 9, 1), ()),
    ],
)
def test_sale_light_check(
    faker: Faker,
    number: str | None,
    identity: str | None,
    day: date | None,
    expected: tuple[str, ...],
) -> None:
    sale = replace(practice_records()[4], declaration=None)
    assessment = line_assessments((sale,), rnc="199990013", captured_on=NOW.date())[
        sale.activity_id
    ]
    projected = row(
        faker,
        family="sale",
        fiscal_number=number,
        counterparty_key=identity,
        report_date=day,
        linked_activity_ids=(sale.activity_id,),
    )
    (judged,) = with_export_verdicts(
        (projected,), {sale.activity_id: assessment}, frozenset()
    )
    assert (judged.ready, judged.missing) == (not expected, expected)
    assert readiness(projected, None) == (not expected, expected)
    assert judged.missing_fields == tuple(
        dict.fromkeys(
            "counterparty_id"
            if code == "missing_rnc"
            else "date"
            if code == "missing_date"
            else "fiscal_number"
            for code in expected
        )
    )


@pytest.mark.parametrize(
    "technical", [None, "approval_provenance_unavailable", "report_effect_incomplete"]
)
def test_sale_complete_facts_ignore_workflow_and_technical_holds(
    faker: Faker, technical: str | None
) -> None:
    projected = row(
        faker,
        family="sale",
        fiscal_number="B0200000001",
        workflow_blockers=("possible_duplicate", "future_blocker"),
        technical_state=technical,
    )
    assert readiness(projected, None) == (True, ())


@pytest.mark.parametrize("family,expected", [("purchase", "606"), ("sale", None)])
def test_preview_offers_only_available_files(
    faker: Faker, family: str, expected: str | None
) -> None:
    preview = summarize_export(
        source(row(faker, family=family)), report(record_families=[family])
    )
    assert (preview.dgii.form if preview.dgii else None) == expected
    if family == "sale":
        assert preview.model_dump()["dgii"] is None


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_sales_dgii_export_returns_clear_422(export_client: TestClient, format: str) -> None:  # noqa: F811
    @export_client.app.middleware("http")
    async def request_id(request: Any, call_next: Any) -> Any:
        request.state.request_id = "synthetic-r8"
        return await call_next(request)

    response = export_client.post(
        "/reports/export",
        json={
            "report": report(record_families=["sale"]).model_dump(mode="json"),
            "mode": "dgii",
            "format": format,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "business_export_dgii_sales_unavailable"


def test_sale_cannot_be_approved_without_total(monkeypatch: pytest.MonkeyPatch) -> None:
    facts = practice_records()[4].facts.model_copy(update={"amount": Unknown()})
    held = blockers(facts, ())
    assert any(item.code == "fact_required" and item.field == "amount" for item in held)
    monkeypatch.setattr(approval.mutations, "event_at", lambda *args: object())
    monkeypatch.setattr(
        approval.dossier, "dossier", lambda *args: SimpleNamespace(blockers=held)
    )
    tx: Any = object()
    with pytest.raises(ActionError) as refused:
        approval._reviewed_facts(tx, UUID(int=1), 1, "income")
    assert refused.value.result.code == "fact_required"


def test_accepted_sale_cannot_lose_total() -> None:
    before = practice_records()[4].facts
    after = before.model_copy(update={"amount": Unknown()})
    unused: Any = None
    with pytest.raises(ActionError) as refused:
        accepted_edit.revise_activity(
            unused, unused, before, after, "venta", None, unused
        )
    assert refused.value.result.code == "fact_required"


@pytest.mark.parametrize(
    "held,technical,expected",
    [
        ((), None, ()),
        (("possible_duplicate",), None, ("duplicate",)),
        (("fact_required",), None, ("detail_missing",)),
        ((), "report_effect_incomplete", ("detail_missing",)),
        (("possible_duplicate", "fact_required"), None, ("duplicate", "detail_missing")),
    ],
)
def test_purchase_readiness_remains_unchanged(
    faker: Faker, held: tuple[str, ...], technical: str | None, expected: tuple[str, ...]
) -> None:
    projected = row(faker, workflow_blockers=held, technical_state=technical)
    assert readiness(projected, None) == (not expected, expected)

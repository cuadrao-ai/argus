"""The export preview counts the documents the Bandeja still holds in the
export's period, with the month close's own count."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api import business_receipt_activity, business_reports
from argus.api.business import require_business_person, require_business_surface
from argus.api.business_drafts import require_drafts
from argus.api.business_receipt_activity import unreviewed_days
from argus.domain.business import reporting_file
from argus.domain.business.authority import ActionError
from argus.domain.business.month_close import (
    month_period,
    unreviewed_in_month,
    with_unreviewed,
)
from argus.domain.business.month_close_store import empty_month
from argus.domain.business.reporting_file import summarize_export
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.business.test_records_file import SEPTEMBER, report, row, source

NO_STORE = SimpleNamespace(service=SimpleNamespace(imports=SimpleNamespace(store=None)))
BANDEJA = [
    (date(2026, 8, 31), "DOP"),
    (date(2026, 9, 1), "DOP"),
    (date(2026, 9, 17), "USD"),
    (date(2026, 9, 30), None),
    (date(2026, 10, 1), None),
]


def _period(**period) -> dict:
    return {"period": period}


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"period": SEPTEMBER}, 3),
        (_period(kind="custom", from_date="2026-08-15", to_date="2026-09-01"), 2),
        (_period(kind="custom", from_date="2026-09-30", to_date="2026-10-31"), 2),
        (_period(kind="this_month"), 1),
        (_period(kind="last_month"), 3),
        (_period(kind="all"), 5),
        (_period(kind="custom", from_date="2026-07-01", to_date="2026-07-31"), 0),
    ],
)
def test_the_preview_counts_the_bandeja_in_the_resolved_period(faker, filters, expected):
    preview = summarize_export(source(row(faker)), report(**filters), bandeja=BANDEJA)
    assert preview.bandeja_count == expected


def test_the_count_covers_the_whole_bandeja_whatever_the_tab_and_filters(faker):
    books = source(row(faker), row(faker, family="sale"))
    filtered = report(q="nothing matches this", currencies=["USD"], has_document=True)
    sales = report(record_families=["sale"])
    for request in (report(), filtered, sales):
        assert summarize_export(books, request, bandeja=BANDEJA).bandeja_count == 3


def test_a_preview_with_no_bandeja_counts_zero(faker):
    assert summarize_export(source(row(faker)), report()).bandeja_count == 0


def test_the_preview_count_is_the_month_closes_documents_in_bandeja(faker):
    arrived = "2026-09-30T15:00:00Z"
    views = [
        {"status": "review_ready", "occurred_on": "2026-09-12", "received_at": arrived},
        {"status": "saved", "occurred_on": None, "received_at": arrived},
        {
            "status": "needs_attention",
            "occurred_on": "2026-09-02",
            "received_at": arrived,
            "currency": "USD",
        },
        {"status": "review_ready", "occurred_on": "2026-10-02", "received_at": arrived},
        {"status": "confirmed", "occurred_on": "2026-09-12", "received_at": arrived},
    ]
    days = unreviewed_days(NO_STORE, views)
    start, end = month_period("2026-09")
    month = with_unreviewed(
        empty_month(
            "2026-09",
            bandeja=unreviewed_in_month(
                ((day, currency or "DOP") for day, currency in days), start, end
            ),
        )
    )
    closing = sum(block["documents_in_bandeja"] for block in month["currencies"])
    preview = summarize_export(source(row(faker)), report(), bandeja=days)
    assert preview.bandeja_count == closing == 3


@pytest.fixture
def route(faker, monkeypatch):
    """The preview route over the dependencies it had before it counted the
    Bandeja, with the Bandeja reader recorded."""

    business = SimpleNamespace(scope=SimpleNamespace(currency="DOP"))
    actor = SimpleNamespace(actor=SimpleNamespace(space_id=uuid4(), actor_id=uuid4()))
    actions = SimpleNamespace(authority=None)
    read = []

    def reader(request, service, context):
        read.append((service, context))
        return business

    monkeypatch.setattr(business_reports, "grant_reader", reader)
    monkeypatch.setattr(
        business_receipt_activity,
        "bandeja_days",
        lambda context: BANDEJA if context is business else [],
    )
    monkeypatch.setattr(
        reporting_file, "read_export_source", lambda *args: source(row(faker))
    )
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-bandeja"
        return await call_next(request)

    app.include_router(business_reports.router)
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        service=actions, for_space=lambda request, spaces: actor
    )
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        person_id=str(actor.actor.actor_id),
        spaces=SimpleNamespace(get=lambda space_id: None),
    )

    def post():
        return TestClient(app).post(
            "/reports/export/preview",
            json={"report": report().model_dump(mode="json")},
        )

    return post, read, (actions, actor)


def test_the_preview_route_counts_the_bandeja_as_the_grant_it_resolved(route):
    post, read, resolved = route
    answer = post()
    assert answer.status_code == 200, answer.text
    assert answer.json()["bandeja_count"] == 3
    assert read == [resolved]


@pytest.mark.parametrize(
    ("outcome", "code", "status"),
    [
        ("permission_denied", "business_permission_denied", 403),
        ("not_found", "business_record_not_found", 404),
    ],
)
def test_a_reader_the_export_refuses_never_reaches_the_bandeja(
    route, monkeypatch, outcome, code, status
):
    post, read, _ = route

    def refuse(*args):
        raise ActionError(outcome, code)

    monkeypatch.setattr(reporting_file, "read_export_source", refuse)
    answer = post()
    assert answer.status_code == status
    assert answer.json()["detail"]["code"] == code
    assert read == []

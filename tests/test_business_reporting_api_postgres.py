import csv
import io
import json
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business import require_business_person, require_business_surface
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.business_reports import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_actions_postgres as shared
from tests.test_business_reporting_postgres import record_expense, viewer_context

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


@pytest.fixture
def client(actions):
    service, context, _ = actions
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-report"
        return await call_next(request)

    app.include_router(router, prefix="/business")
    selected = [context]
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service,
        selected[0].actor.actor_id,
        str(selected[0].actor.space_id),
        selected[0].grant_id,
    )
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        spaces=None
    )
    app.dependency_overrides[require_business_surface] = lambda: None
    with TestClient(app) as http:
        yield http, selected


def query(http, **payload):
    response = http.post("/business/reports/query", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_query_rejects_authority_and_unsupported_fields(client, actions):
    http, _ = client
    for payload in (
        {"actor_id": str(uuid4())},
        {"filters": {"payment_status": "paid"}},
        {"page_size": 20},
        {"filters": {"amount_min": 1.1}},
    ):
        assert http.post("/business/reports/query", json=payload).status_code == 422
    assert query(http)["matching_count"] == 0


def test_export_is_full_filtered_answer_and_explicitly_records_only(client, actions):
    http, _ = client
    service, context, _ = actions
    for _ in range(26):
        shared.ready(service, context)
    answer = query(http)
    assert len(answer["items"]) == 25
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": answer["fingerprint"], "report": {}},
    )
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"records.csv", "records.xlsx", "manifest.json"}
        rows = list(
            csv.DictReader(io.StringIO(archive.read("records.csv").decode("utf-8-sig")))
        )
        manifest = json.loads(archive.read("manifest.json"))
    assert len(rows) == manifest["matching_count"] == 26
    assert manifest["scope"] == "filtered_records_only"
    assert manifest["fingerprint"] == answer["fingerprint"]
    assert all(row["stage"] == "awaiting_approval" for row in rows)


def test_stale_export_requires_explicit_refresh(client, actions):
    http, _ = client
    service, context, _ = actions
    answer = query(http)
    shared.ready(service, context)
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": answer["fingerprint"], "report": {}},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "business_report_changed"


def test_viewer_can_read_but_not_export_and_revocation_stops_reads(
    client, actions, users
):
    http, selected = client
    service, context, _ = actions
    selected[0] = viewer_context(service, context, users["other"])
    answer = query(http)
    assert (
        http.post(
            "/business/reports/export",
            json={"expected_fingerprint": answer["fingerprint"], "report": {}},
        ).status_code
        == 403
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (selected[0].grant_id,),
        )
    denied = http.post("/business/reports/query", json={})
    assert denied.status_code == 404
    assert denied.json()["detail"]["code"] == "business_record_not_found"


def test_export_rechecks_facts_after_build_before_release(client, actions, monkeypatch):
    from argus.domain.business import reporting_export

    http, _ = client
    service, context, _ = actions
    answer = query(http)
    original = reporting_export.build_archive

    def changed(*args, **kwargs):
        data = original(*args, **kwargs)
        shared.ready(service, context)
        return data

    monkeypatch.setattr(reporting_export, "build_archive", changed)
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": answer["fingerprint"], "report": {}},
    )
    assert response.status_code == 409


def test_view_recipe_reopens_current_page_one(client, actions):
    http, _ = client
    service, context, _ = actions
    response = http.post(
        "/business/report-views",
        json={
            "name": "Expenses",
            "recipe": {"columns": ["gross_amount", "counterparty"]},
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    assert "page" not in saved["recipe"]
    record_expense(service, context)
    result = query(http, **saved["recipe"])
    assert result["page"] == 1
    assert result["matching_count"] == 1


def test_validation_and_authorization_errors_are_never_cached(client, actions, users):
    http, selected = client
    invalid = http.post("/business/reports/query", json={"page": 0})
    missing_header = http.post("/business/report-views", json={"name": "Saved"})
    for response in (invalid, missing_header):
        assert response.status_code == 422
        assert response.headers.get("cache-control") == "no-store"
    service, context, _ = actions
    selected[0] = viewer_context(service, context, users["other"])
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": query(http)["fingerprint"], "report": {}},
    )
    assert response.status_code == 403
    assert response.headers.get("cache-control") == "no-store"


def test_xlsx_contains_server_totals_and_scope_without_formulas(client, actions):
    from tests.business.test_business_export import sheet_rows

    http, _ = client
    service, context, _ = actions
    record_expense(service, context)
    answer = query(http)
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": answer["fingerprint"], "report": {}},
    )
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        workbook = archive.read("records.xlsx")
        manifest = json.loads(archive.read("manifest.json"))
    totals = sheet_rows(workbook, 2)
    scope = dict(sheet_rows(workbook, 3)[1:])
    assert "basis" in totals[0]
    assert "recorded_activity_amount" in [
        row[totals[0].index("basis")] for row in totals[1:]
    ]
    assert scope["fingerprint"] == manifest["fingerprint"]
    assert scope["matching_count"] == str(manifest["matching_count"])
    assert scope["generated_at"] == manifest["generated_at"]


def test_export_refuses_scope_that_cannot_fit_a_spreadsheet_cell(client):
    http, _ = client
    keys = [str(index).zfill(3) + "x" * 125 for index in range(200)]
    report = {"filters": {"categories": keys, "funding_sources": keys}}
    answer = query(http, **report)
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": answer["fingerprint"], "report": report},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "business_report_cell_too_large"

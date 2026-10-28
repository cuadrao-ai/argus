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
    assert all((row["personal"], row["include_606"]) == ("False", "") for row in rows)


def test_export_marks_personal_rows_and_the_totals_leave_them_out(client, actions):
    http, _ = client
    service, context, _ = actions
    business = document_backed_expense(service, context, personal=False)
    personal = document_backed_expense(service, context, personal=True)
    answer = query(http)
    response = http.post(
        "/business/reports/export",
        json={"expected_fingerprint": answer["fingerprint"], "report": {}},
    )
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        rows = {
            json.loads(row["linked_activity_ids"])[0]: row
            for row in csv.DictReader(
                io.StringIO(archive.read("records.csv").decode("utf-8-sig"))
            )
        }
        manifest = json.loads(archive.read("manifest.json"))
    assert (rows[business]["personal"], rows[personal]["personal"]) == ("False", "True")
    assert manifest["matching_count"] == 2
    for total in manifest["totals"]:
        assert (total["matching_count"], total["amount"]) == (1, "850.00")


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


def test_http_amount_strings_preserve_large_money_and_aggregate_over_bigint(
    client, actions
):
    from datetime import datetime, timezone

    from argus.domain.recording.money_schemas import MoneyRequest, OwnerFunds

    http, _ = client
    service, context, _ = actions
    for amount in ("92233720368547758.07", "1.00"):
        service.imports.money.write_entered(
            user_id=context.owner_id,
            request=MoneyRequest(
                kind="expense",
                owner_funding=OwnerFunds(
                    owner_space_id=context.actor.space_id, currency="DOP"
                ),
                amount=amount,
                occurred_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
            ),
            idempotency_key=str(uuid4()),
            scope=context.scope,
        )
    single = query(
        http, filters={"currencies": ["DOP"], "amount_min": "92233720368547758.07"}
    )
    aggregate = query(http)
    assert single["matching_count"] == 1
    assert single["items"][0]["recorded_amount"] == "92233720368547758.07"
    first = next(
        total
        for total in single["totals"]
        if total["basis"] == "recorded_activity_amount"
    )
    combined = next(
        total
        for total in aggregate["totals"]
        if total["basis"] == "recorded_activity_amount"
    )
    assert first["amount_minor"] > 2**53
    assert first["known_amount"] == first["amount"] == "92233720368547758.07"
    assert combined["amount_minor"] > 2**63 - 1
    assert combined["known_amount"] == combined["amount"] == "92233720368547759.07"


def test_http_credit_amount_strings_are_signed_and_money_refund_stays_separate(
    client, actions
):
    from tests.test_business_dgii_postgres import ORACLE, approve, cash_account, reviewed

    http, _ = client
    service, context, _ = actions
    account = cash_account(service, context)
    purchase = approve(service, context, reviewed(service, context, account, 0))
    refund = approve(
        service, context, reviewed(service, context, account, 3, purchase.activity_id)
    )
    assert refund.outcome == "applied"
    answer = query(http)
    credit = next(
        total
        for total in answer["totals"]
        if total["basis"] == "document_credit_adjustment"
    )
    cash_refund = next(
        total
        for total in answer["totals"]
        if total["basis"] == "recorded_activity_amount" and total["kind"] == "refund"
    )
    expected = ORACLE["P04"]["gross"]
    assert credit["known_amount"] == credit["amount"] == "-" + expected
    assert cash_refund["known_amount"] == cash_refund["amount"] == expected


def document_backed_expense(service, context, *, personal):
    from argus.domain.business.contracts.actions import (
        ApproveExpense,
        MarkPersonal,
        ProposeActivity,
    )
    from argus.domain.business.contracts.facts import BusinessFactPatch

    evidence = shared.source(service, context)
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "expense",
                "amount": "850",
                "currency": "DOP",
                "occurred_on": "2026-10-01",
                "funding": {"kind": "owner_funds"},
                "business_share": {"kind": "all"},
                "receipt_state": "informal_receipt",
            }.items()
        }
    )
    key, lease = shared.prepare(
        service, context, [ProposeActivity(facts=facts, source_ids=(evidence,))]
    )
    proposed = service.execute(context, key, 0, lease=lease)
    assert proposed.outcome == "applied", proposed
    draft = proposed.draft_id
    version = service.dossier(context, draft).version
    if personal:
        marked = service.mark_personal(
            context, draft, MarkPersonal(version=version, personal=True), str(uuid4())
        )
        assert marked.outcome == "applied", marked
        version += 1
    approved = service.approve(
        context,
        draft,
        ApproveExpense(version=version, action="record_expense"),
        str(uuid4()),
    )
    assert approved.outcome == "applied", approved
    return str(approved.activity_id)


def test_personal_rows_stay_listed_but_count_in_no_total(client, actions):
    http, _ = client
    service, context, _ = actions
    business = document_backed_expense(service, context, personal=False)
    personal = document_backed_expense(service, context, personal=True)
    answer = query(http)
    assert answer["matching_count"] == 2
    rows = {row["linked_activity_ids"][0]: row for row in answer["items"]}
    assert (rows[business]["personal"], rows[personal]["personal"]) == (False, True)
    assert rows[personal]["date_basis"] == "document_issue"
    expenses = [total for total in answer["totals"] if total["kind"] == "expense"]
    assert {total["basis"] for total in expenses} >= {
        "recorded_activity_amount",
        "document_family_amount",
    }
    for total in expenses:
        assert (total["currency"], total["matching_count"], total["amount"]) == (
            "DOP",
            1,
            "850.00",
        )

import csv
import io
import re
from urllib.parse import unquote
from uuid import uuid4

import pytest
from argus.api.business import (
    BusinessPerson,
    require_business_person,
    require_business_surface,
)
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.business_reports import router
from argus.domain.business.spaces import PostgresSpaceStore
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_actions_postgres as shared
from tests.test_business_dgii_postgres import cash_account
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
    spaces = PostgresSpaceStore(service.authority.pool)
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(selected[0].actor.actor_id), spaces
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


PURCHASES = {"record_families": ["purchase"], "currencies": ["DOP"]}
SEPTEMBER = {"kind": "custom", "from_date": "2026-09-01", "to_date": "2026-09-30"}


def export(http, filters=None, *, headers=None, **choice):
    body = {
        "report": {"schema_version": 2, "filters": filters or PURCHASES},
        "mode": "table",
        "columns": ["date", "gross_amount"],
        "format": "csv",
        **choice,
    }
    return http.post("/business/reports/export", json=body, headers=headers)


def preview(http, filters=None):
    response = http.post(
        "/business/reports/export/preview",
        json={"report": {"schema_version": 2, "filters": filters or PURCHASES}},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def lines(response):
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_table_export_is_one_file_of_every_matching_record(client, actions):
    http, _ = client
    service, context, _ = actions
    for _ in range(26):
        record_expense(service, context)
    assert len(query(http, filters=PURCHASES)["items"]) == 25
    summary = preview(http)
    assert summary["table"]["current"] == {"record_count": 26, "currencies": ["DOP"]}
    assert summary["table"]["all"]["record_count"] == 26
    response = export(http)
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    written = lines(response)
    fallback, encoded = response.headers["content-disposition"].split(
        "; filename*=UTF-8''"
    )
    assert re.fullmatch(
        r"Colmado - Compras \d{4}-\d{2}-\d{2} a \d{4}-\d{2}-\d{2} - Registros - \d{4}-\d{2}-\d{2} \d{4}\.csv",
        unquote(encoded),
    )
    assert fallback == f'attachment; filename="{unquote(encoded)}"'
    assert written[0] == ["Contraparte", "Fecha", "Monto", "Moneda"]
    assert len(written) == 27
    assert {line[3] for line in written[1:]} == {"DOP"}
    excel = export(http, format="xlsx")
    assert excel.status_code == 200, excel.text
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert excel.content.startswith(b"PK")


def test_dgii_export_formats_the_same_606_records_and_ignores_other_filters(
    client, actions
):
    from zipfile import ZipFile

    from argus.domain.business.export import export_package
    from argus.domain.business.fiscal_profile import set_profile
    from argus.domain.ingestion.documents.objects import InMemorySourceObjects

    from tests.test_business_declaration_after_approval_postgres import (
        FILER,
        PERIOD,
        TXT_606,
        account_funding,
        approved,
        captured,
        declared,
    )
    from tests.test_business_dgii_postgres import PRACTICE_NAME, filer_change

    http, _ = client
    service, context, _ = actions
    PostgresSpaceStore(service.authority.pool).rename(context.owner_id, PRACTICE_NAME)
    set_profile(service.authority, context, filer_change(FILER), "rnc")
    funding = account_funding(cash_account(service, context))
    complete, version = captured(service, context, "B0100000031", funding)
    view = approved(service, context, complete, version)
    assert declared(service, context, complete, view.version, category="02").outcome == (
        "applied"
    )
    # With nothing pending the month ships its TXT; the file holds the same line.
    package = export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    with ZipFile(io.BytesIO(package)) as archive:
        txt = archive.read(TXT_606).decode().split("\r\n")[1:]
    pending, version = captured(service, context, "B0100000032", funding)
    approved(service, context, pending, version)
    month = {**PURCHASES, "period": SEPTEMBER}
    card = query(http, filters=month)["overview"]["needs_fiscal_data"]
    unrelated = {**month, "q": "nothing matches this", "has_document": True}
    summary = preview(http, unrelated)["dgii"]
    assert summary == {
        "form": "606",
        "currency": "DOP",
        "record_count": 1,
        "pending_fiscal_count": card,
        "pending_rate_count": 0,
        "pending_rate_currencies": [],
    }
    assert card == 1
    response = export(
        http, unrelated, mode="dgii", columns=[], headers={"Accept-Language": "en"}
    )
    written = lines(response)
    header = response.headers["content-disposition"]
    fallback, encoded = header.split("; filename*=UTF-8''")
    assert re.fullmatch(
        r'attachment; filename="PRACTICA Jose - Purchases 2026-09 - DGII - \d{4}-\d{2}-\d{2} \d{4}\.csv"',
        fallback,
    )
    assert unquote(encoded) == fallback.removeprefix('attachment; filename="')[
        :-1
    ].replace("PRACTICA Jose", PRACTICE_NAME)
    assert written[0][:2] == ["RNC o Cédula", "Tipo Id"]
    (official,) = [line.split("|") for line in txt if line]
    assert (official[2], official[11], official[17], official[22]) == ("02", "", "", "01")
    official[2] = "02-GASTOS POR TRABAJOS, SUMINISTROS Y SERVICIOS "
    official[11] = official[17] = "0"
    official[22] = "01 - EFECTIVO"
    assert written[1:] == [official]


def test_viewer_can_read_but_not_export_and_revocation_stops_reads(
    client, actions, users
):
    http, selected = client
    service, context, _ = actions
    selected[0] = viewer_context(service, context, users["other"])
    query(http)
    assert export(http).status_code == 403
    assert (
        http.post(
            "/business/reports/export/preview", json={"report": {"filters": PURCHASES}}
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


def test_export_rechecks_access_after_build_before_release(
    client, actions, users, monkeypatch
):
    from argus.domain.business import reporting_file
    from argus.domain.business.contracts.authority import TrustedActor

    http, selected = client
    service, context, _ = actions
    record_expense(service, context)
    with service.authority.pool.connection() as db:
        grant = db.execute(
            "insert into public.business_client_grants"
            " (space_id,grantee_id,issuer_id,business_role,capabilities)"
            " values (%s,%s,%s,'editor',array['read','prepare','download','export'])"
            " returning id",
            (context.actor.space_id, users["other"], context.owner_id),
        ).fetchone()[0]
    selected[0] = service.resolve_actor(
        TrustedActor(
            actor_id=users["other"], actor_kind="member", space_id=context.actor.space_id
        ),
        grant_id=grant,
    )
    assert export(http).status_code == 200
    original = reporting_file.build_file

    def revoked(*args, **kwargs):
        built = original(*args, **kwargs)
        with service.authority.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
                (grant,),
            )
        return built

    monkeypatch.setattr(reporting_file, "build_file", revoked)
    response = export(http)
    assert response.status_code == 404
    assert "content-disposition" not in response.headers


def test_export_refuses_a_column_the_tab_does_not_offer(client):
    http, _ = client
    sales = {"record_families": ["sale"], "currencies": ["DOP"]}
    response = export(http, sales, columns=["expense_type"])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "business_export_column_unavailable"


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
    response = export(http)
    assert response.status_code == 403
    assert response.headers.get("cache-control") == "no-store"


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


def test_fiscal_totals_use_current_hand_entered_declaration_and_filtered_records(
    client, actions
):
    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.business.contracts.dgii import PurchaseReview

    from tests.test_business_dgii_postgres import approve, cash_account, reviewed

    http, _ = client
    service, context, _ = actions
    account = cash_account(service, context)
    first = approve(service, context, reviewed(service, context, account, 0))
    second = approve(service, context, reviewed(service, context, account, 1))
    sale = approve(service, context, reviewed(service, context, account, 4))
    assert first.outcome == second.outcome == sale.outcome == "applied"
    before = query(http, filters={"q": "P01"})
    changed = service.review(
        context,
        first.draft_id,
        ReviewDraft(
            version=service.dossier(context, first.draft_id).version,
            purchase=PurchaseReview(goods_amount="12.34", services_amount="56.78"),
        ),
        str(uuid4()),
    )
    assert changed.outcome == "applied", changed
    after = query(http, filters={"q": "P01"})
    assert after["matching_count"] == 1
    assert after["items"][0]["draft_id"] == str(first.draft_id)
    assert after["fingerprint"] != before["fingerprint"]
    assert after["totals"] == before["totals"]
    totals = {item["basis"]: item for item in after["fiscal_totals"]}
    for basis, expected in (("goods", 1234), ("services", 5678), ("itbis", 18000)):
        total = totals[basis]
        assert (total["currency"], total["kind"]) == ("DOP", "expense")
        assert total["amount_minor"] == expected
        assert (total["populated_count"], total["applicable_count"]) == (1, 1)
    sales = query(http, filters={"record_families": ["sale"]})
    assert sales["matching_count"] == 1
    assert {item["basis"] for item in sales["fiscal_totals"]} == {"itbis"}

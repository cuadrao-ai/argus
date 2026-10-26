"""Over HTTP on the real app, Auth and Postgres: the read sets a Bandeja
upload's type when the person named none (a Venta when the issuer RNC is the
Business's own, in any printed format), a named type wins, the owner changes
it while the draft is open, the change is a revision, it is locked once
approved, and the 606 and 607 follow the type. A local stub stands in for the
provider."""

from __future__ import annotations

import io
import json
import os
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from argus.api import state as api_state
from argus.api.documents import documents_service
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import DETAILS, PURCHASE, ReceiptStub
from tests.business.test_business_api import RECEIPT
from tests.business_reading_support import ROUTE
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_reading_setting_postgres import _reading
from tests.test_business_scope_switch_routes_postgres import (
    API,
    ENV,
    GRANT,
    _person,
)

pytestmark = pytest.mark.skipif(
    not (shared.DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)
OWN_RNC = "199990013"
CLIENT_RNC = "199990056"
SUPPLIER_RNC = "199990021"
NAME = "PRÁCTICA Taller"


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    created: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            documents = documents_service()
            stub = ReceiptStub()
            monkeypatch.setattr(documents, "extractor", stub)
            monkeypatch.setattr(
                documents.business_receipt_consent, "route_resolver", lambda: ROUTE
            )
            monkeypatch.setattr(
                "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
                lambda: ROUTE,
            )
            alice = _person(client, gateway, "alice", created)
            started = client.post(
                f"{API}/business/space", json={"name": NAME}, headers=alice.headers
            )
            assert started.status_code == 201, started.text
            alice.space_id = started.json()["id"]
            world = SimpleNamespace(
                client=client,
                alice=alice,
                bob=_person(client, gateway, "bob", created),
                stub=stub,
                uploads=0,
            )
            assert _reading(world, True).status_code == 200
            yield world
    finally:
        with Connection.connect(shared.DSN) as db:
            for user_id in created:
                db.execute(
                    "update public.spaces set closed_at=coalesce(closed_at,clock_timestamp()) where created_by=%s and kind='business'",
                    (user_id,),
                )
                db.execute(
                    "delete from public.business_client_grants"
                    " where grantee_id=%s or issuer_id=%s",
                    (user_id, user_id),
                )
            db.execute("set constraints all deferred")
            db.execute(
                "delete from public.financial_activity_groups where user_id=any(%s::uuid[])",
                (created,),
            )
            db.execute("delete from public.spaces where created_by=any(%s::uuid[])", (created,))
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _headers(world) -> dict:  # noqa: ANN001
    return {**world.alice.headers, "Idempotency-Key": str(uuid4())}


def _own_rnc(world, value: str = OWN_RNC) -> None:  # noqa: ANN001
    saved = world.client.patch(
        f"{API}/business/fiscal-profile",
        json={
            "name": NAME,
            "previous_name": NAME,
            "tax_id": {"type": "rnc", "value": value},
            "previous_tax_id": None,
        },
        headers=_headers(world),
    )
    assert saved.status_code == 200, saved.text


def _upload(
    world,  # noqa: ANN001
    rnc: str | None,
    document_type: str | None = None,
    *,
    occurred_on: str = "2026-09-03",
    total: str = "1180.00",
) -> dict:
    """One read receipt: the stub prints ``rnc`` as the RNC the read found."""

    world.stub.rows = [{**PURCHASE, "amount": total, "occurred_on": occurred_on}]
    world.stub.details = {
        **DETAILS,
        "occurred_on": occurred_on,
        "total": total,
        "subtotal": None,
        "tax": None,
        "items": [],
        "rnc": rnc,
        "ncf": "B0100000001",
    }
    world.uploads += 1
    headers = {
        **_headers(world),
        "Content-Type": "image/png",
        "X-Document-Filename": "documento.png",
    }
    if document_type is not None:
        headers["X-Document-Type"] = document_type
    uploaded = world.client.post(
        f"{API}/business/receipts",
        content=RECEIPT + world.uploads.to_bytes(2, "big"),
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    return _receipt(world, uploaded.json()["id"])


def _receipt(world, receipt_id: str) -> dict:  # noqa: ANN001
    found = world.client.get(
        f"{API}/business/receipts/{receipt_id}", headers=world.alice.headers
    )
    assert found.status_code == 200, found.text
    return found.json()


def _dossier(world, draft_id: str) -> dict:  # noqa: ANN001
    found = world.client.get(
        f"{API}/business/drafts/{draft_id}/dossier", headers=world.alice.headers
    )
    assert found.status_code == 200, found.text
    return found.json()


def _typed(view: dict) -> tuple:
    return (
        view["document_type"],
        view.get("document_type_detected", False),
        view.get("document_type_editable", False),
    )


def _review(world, draft_id: str, body: dict):  # noqa: ANN001, ANN202
    version = _dossier(world, draft_id)["version"]
    return world.client.patch(
        f"{API}/business/drafts/{draft_id}/review",
        json={"version": version, **body},
        headers=_headers(world),
    )


@pytest.mark.parametrize(
    "printed", [OWN_RNC, "199-99001-3", "1 9999 0013", " 199-990013 "]
)
def test_the_business_own_rnc_in_any_format_reads_as_a_detected_venta(
    web,
    printed: str,  # noqa: ANN001
) -> None:
    _own_rnc(web, "199-99001-3")
    receipt = _upload(web, printed)
    assert _typed(receipt) == ("venta", True, True)
    dossier = _dossier(web, receipt["draft_id"])
    assert _typed(dossier) == ("venta", True, True)
    kind, rnc = dossier["facts"]["kind"], dossier["facts"]["fiscal"]["rnc"]
    assert (kind["value"], kind["origin"]) == ("income", "extracted")
    # The Business's own number is the issuer; the client's RNC is still to fill.
    assert (rnc["state"], rnc["value"]) == ("unknown", None)
    assert dossier["bill_mark"] is None
    named = {"counterparty": {"state": "known", "value": "PRÁCTICA cliente"}}
    reviewed = _review(web, receipt["draft_id"], {"facts": named})
    assert reviewed.status_code == 200, reviewed.text
    assert _typed(reviewed.json()) == ("venta", True, True)


@pytest.mark.parametrize("own", [OWN_RNC, None])
def test_another_rnc_or_no_profile_reads_as_a_detected_receipt(web, own) -> None:  # noqa: ANN001
    if own is not None:
        _own_rnc(web, own)
    receipt = _upload(web, SUPPLIER_RNC if own else OWN_RNC)
    assert _typed(receipt) == ("recibo", True, True)
    dossier = _dossier(web, receipt["draft_id"])
    assert _typed(dossier) == ("recibo", True, True)
    assert dossier["facts"]["kind"]["value"] == "expense"


@pytest.mark.parametrize("printed,named", [(OWN_RNC, "recibo"), (SUPPLIER_RNC, "venta")])
def test_a_named_type_wins_over_the_read(web, printed: str, named: str) -> None:  # noqa: ANN001
    _own_rnc(web)
    receipt = _upload(web, printed, named)
    assert _typed(receipt) == (named, False, True)
    assert _typed(_dossier(web, receipt["draft_id"])) == (named, False, True)


def _account(world) -> str:  # noqa: ANN001
    made = world.client.post(
        f"{API}/business/accounts",
        json={"nickname": "PRÁCTICA caja", "type": "cash", "currency": "DOP"},
        headers=_headers(world),
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def _facts(kind: str, amount: str, occurred_on: str, account: str) -> dict:
    return {
        name: {"state": "known", "value": value}
        for name, value in {
            "kind": kind,
            "amount": amount,
            "currency": "DOP",
            "occurred_on": occurred_on,
            "counterparty": "PRÁCTICA cliente",
            "funding": {"kind": "business_account", "account_id": account},
            "business_share": {"kind": "all"},
            "receipt_state": "fiscal_receipt",
        }.items()
    }


ZERO = "0.00"
PURCHASE_606 = {
    "fiscal": {"rnc": SUPPLIER_RNC, "ncf": "B0100000001", "itbis": "180.00"},
    "declaration": {
        "form": "606",
        "id_type": "1",
        "modified_ncf": None,
        "selective_tax": ZERO,
        "other_taxes": ZERO,
        "legal_tip": ZERO,
        "category": "09",
        "paid_on": "2026-09-03",
        "services_amount": ZERO,
        "goods_amount": "1000.00",
        "itbis_withheld": ZERO,
        "itbis_proportionality": ZERO,
        "itbis_cost": ZERO,
        "itbis_perceived": ZERO,
        "income_withholding_type": None,
        "income_withheld": ZERO,
        "income_perceived": ZERO,
        "payment_method": "01",
        "actual_refund": False,
        "purchase_activity_id": None,
    },
}
SALE_607 = {
    "fiscal": {"rnc": CLIENT_RNC, "ncf": "B0100000002", "itbis": "360.00"},
    "declaration": {
        "form": "607",
        "id_type": "1",
        "modified_ncf": None,
        "selective_tax": ZERO,
        "other_taxes": ZERO,
        "legal_tip": ZERO,
        "income_type": "01",
        "withheld_on": None,
        "billed_amount": "2000.00",
        "itbis_withheld_by_third_parties": ZERO,
        "itbis_perceived": ZERO,
        "income_withheld_by_third_parties": ZERO,
        "income_perceived": ZERO,
        "cash": ZERO,
        "bank": "2360.00",
        "card": ZERO,
        "credit": ZERO,
        "gift": ZERO,
        "barter": ZERO,
        "other_payment": ZERO,
    },
}


def _approve(world, draft_id: str, action: str) -> None:  # noqa: ANN001
    approved = world.client.post(
        f"{API}/business/drafts/{draft_id}/approve",
        json={"version": _dossier(world, draft_id)["version"], "action": action},
        headers=_headers(world),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_result"]["status"] == "recorded"


def test_the_owner_retypes_open_drafts_and_the_606_and_607_follow_the_type(
    web,  # noqa: ANN001
) -> None:
    _own_rnc(web)
    account = _account(web)
    # Named Venta at upload, really a purchase: the owner makes it a receipt.
    bought = _upload(web, SUPPLIER_RNC, "venta")["draft_id"]
    # Nothing named and a client's RNC printed: read as a receipt, really a sale.
    sold = _upload(web, CLIENT_RNC, occurred_on="2026-09-16", total="2360.00")["draft_id"]
    assert _dossier(web, sold)["document_type_detected"] is True
    before = _dossier(web, sold)

    key = str(uuid4())
    body = {"version": before["version"], "document_type": "venta"}

    def send(payload: dict):  # noqa: ANN202
        return web.client.patch(
            f"{API}/business/drafts/{sold}/review",
            json=payload,
            headers={**web.alice.headers, "Idempotency-Key": key},
        )

    retyped = send(body)
    assert retyped.status_code == 200, retyped.text
    replayed = send(body)
    assert replayed.json()["version"] == retyped.json()["version"]
    conflict = send({**body, "document_type": "recibo"})
    assert conflict.status_code == 409, conflict.text
    view = retyped.json()
    assert _typed(view) == ("venta", False, True)
    assert view["facts"]["kind"]["value"] == "income"
    assert view["facts"]["kind"]["origin"] == "member_set"
    assert view["facts"]["fiscal"] == before["facts"]["fiscal"]
    revision = view["history"][-1]
    assert revision["version"] == before["version"] + 1
    assert (revision["before"]["kind"]["value"], revision["after"]["kind"]["value"]) == (
        "expense",
        "income",
    )
    [named] = [
        source for source in view["sources"] if source["id"] in revision["source_ids"]
    ]
    assert json.loads(named["text"])["request"]["document_type"] == "venta"
    listed = _receipt(web, view["sources"][0]["connection_id"])
    assert _typed(listed) == ("venta", False, True)

    back = _review(web, bought, {"document_type": "recibo"})
    assert back.status_code == 200, back.text
    assert _typed(back.json()) == ("recibo", False, True)
    assert back.json()["facts"]["kind"]["value"] == "expense"

    for draft, kind, amount, day, fiscal in (
        (bought, "expense", "1180.00", "2026-09-03", PURCHASE_606),
        (sold, "income", "2360.00", "2026-09-16", SALE_607),
    ):
        reviewed = _review(
            web, draft, {"facts": _facts(kind, amount, day, account), "dgii": fiscal}
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["approval_available"] is True, reviewed.json()["blockers"]
        _approve(web, draft, f"record_{kind}")

    for draft, other in ((sold, "recibo"), (bought, "venta")):
        assert _typed(_dossier(web, draft)) == (
            {"recibo": "venta", "venta": "recibo"}[other],
            False,
            False,
        )
        locked = _review(web, draft, {"document_type": other})
        assert locked.status_code == 422, locked.text
        assert locked.json()["code"] == "document_type_locked"
    listed = _receipt(web, view["sources"][0]["connection_id"])
    assert _typed(listed) == ("venta", False, False)

    exported = web.client.get(
        f"{API}/business/exports",
        params={"start": "2026-09-01", "end": "2026-09-30"},
        headers=web.alice.headers,
    )
    assert exported.status_code == 200, exported.text
    with ZipFile(io.BytesIO(exported.content)) as archive:
        dgii = json.loads(archive.read("manifest.json"))["dgii"]
    placed = {
        item["draft_id"]: (item["kind"], item["disposition"])
        for item in dgii["reconciliation"]
    }
    assert placed == {bought: ("expense", "606"), sold: ("income", "607")}
    assert dgii["forms"]["606"]["record_count"] == 1
    assert dgii["forms"]["607"]["record_count"] == 1


def _capture(world, body: dict):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/business/captures", json=body, headers=_headers(world)
    )


@pytest.mark.parametrize(
    "named,expected,kind",
    [
        (None, ("recibo", True, True), None),
        ("recibo", ("recibo", False, True), None),
        ("venta", ("venta", False, True), "income"),
    ],
)
def test_a_typed_capture_takes_the_same_type_rules(web, named, expected, kind) -> None:  # noqa: ANN001
    body = {"text": "Vendí 2,360 a PRÁCTICA cliente"}
    if named is not None:
        body["document_type"] = named
    captured = _capture(web, body)
    assert captured.status_code == 200, captured.text
    assert _typed(captured.json()) == expected
    assert captured.json()["facts"]["kind"]["value"] == kind


def test_a_capture_is_retyped_while_open_and_lands_in_the_607(web) -> None:  # noqa: ANN001
    _own_rnc(web)
    account = _account(web)
    captured = _capture(web, {"text": "Vendí 2,360 a PRÁCTICA cliente"})
    assert captured.status_code == 200, captured.text
    draft = captured.json()["draft_id"]
    retyped = _review(web, draft, {"document_type": "venta"})
    assert retyped.status_code == 200, retyped.text
    view = retyped.json()
    assert _typed(view) == ("venta", False, True)
    assert view["facts"]["kind"]["value"] == "income"
    assert view["history"][-1]["version"] == captured.json()["version"] + 1
    reviewed = _review(
        web,
        draft,
        {
            "facts": _facts("income", "2360.00", "2026-09-16", account),
            "dgii": SALE_607,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    _approve(web, draft, "record_income")
    locked = _review(web, draft, {"document_type": "recibo"})
    assert (locked.status_code, locked.json()["code"]) == (422, "document_type_locked")
    added = _capture(
        web,
        {
            "text": "Otra nota",
            "draft": {"draft_id": draft, "version": 1},
            "document_type": "recibo",
        },
    )
    assert added.status_code == 422, added.text
    exported = web.client.get(
        f"{API}/business/exports",
        params={"start": "2026-09-01", "end": "2026-09-30"},
        headers=web.alice.headers,
    )
    assert exported.status_code == 200, exported.text
    with ZipFile(io.BytesIO(exported.content)) as archive:
        dgii = json.loads(archive.read("manifest.json"))["dgii"]
    placed = {item["draft_id"]: item["disposition"] for item in dgii["reconciliation"]}
    assert placed == {draft: "607"}
    assert dgii["forms"]["606"]["record_count"] == 0


def test_a_read_only_grant_sees_the_type_and_cannot_change_it(web) -> None:  # noqa: ANN001
    _own_rnc(web)
    receipt = _upload(web, OWN_RNC)
    with Connection.connect(shared.DSN) as db:
        [grant] = db.execute(
            "insert into public.business_client_grants"
            " (space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,array['read']) returning id",
            (web.alice.space_id, web.bob.id, web.alice.id),
        ).fetchone()
    reader = {**web.bob.headers, GRANT: str(grant)}
    dossier = web.client.get(
        f"{API}/business/drafts/{receipt['draft_id']}/dossier", headers=reader
    )
    assert dossier.status_code == 200, dossier.text
    assert _typed(dossier.json()) == ("venta", True, False)
    listed = web.client.get(f"{API}/business/receipts/{receipt['id']}", headers=reader)
    assert listed.status_code == 200, listed.text
    assert _typed(listed.json()) == ("venta", True, False)
    refused = web.client.patch(
        f"{API}/business/drafts/{receipt['draft_id']}/review",
        json={"version": dossier.json()["version"], "document_type": "recibo"},
        headers={**reader, "Idempotency-Key": str(uuid4())},
    )
    assert refused.status_code == 403, refused.text

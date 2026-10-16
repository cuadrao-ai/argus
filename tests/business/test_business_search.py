"""GET /api/v1/business/search: Business records only, through the canonical search."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from argus.api.documents import documents_service
from argus.api.financial_accounts import financial_accounts_service
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService

from tests.business.test_business_api import (  # noqa: F401
    RECEIPT,
    Owner,
    alice,
    bob,
    prepared,
)

FERRETERIA = "Ferretería La Esquina"


def personal_expense(owner: Owner, merchant: str) -> str:
    """A Personal account and expense, written the way Personal writes them."""

    created = owner.client.post(
        "/api/v1/financial-accounts",
        json={"type": "checking", "currency": "DOP", "nickname": "Casa"},
        headers={**owner.auth, "Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 201, created.text
    service = financial_accounts_service()
    assert service is not None
    zone = "America/Santo_Domingo"
    written = MoneyService(service).write_entered(
        user_id=owner.person,
        request=MoneyRequest(
            kind="expense",
            account_id=created.json()["id"],
            amount="99.00",
            occurred_at=datetime(2026, 10, 6, 9, 0, tzinfo=ZoneInfo(zone)),
            time_zone=zone,
            note=merchant,
        ),
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )
    return written["activity"]["activity_id"]


def confirmed(owner: Owner, account: str, merchant: str) -> tuple[str, str]:
    receipt_id = prepared(owner)
    version = owner.review(
        receipt_id,
        owner.detail(receipt_id)["version"],
        account_id=account,
        merchant=merchant,
    ).json()["version"]
    body = owner.confirm(receipt_id, version, str(uuid4())).json()
    assert body["status"] == "confirmed", body
    return receipt_id, body["expense_id"]


def test_finds_the_business_expense_and_never_the_personal_one(alice: Owner) -> None:  # noqa: F811
    personal_id = personal_expense(alice, FERRETERIA)
    account = alice.account("DOP", "Caja")
    receipt_id, expense_id = confirmed(alice, account, FERRETERIA)

    found = alice.get("/search", q="ferreteria")

    assert found.status_code == 200, found.text
    assert found.headers["Cache-Control"] == "no-store"
    assert found.json() == {
        "expenses": [
            {
                "id": expense_id,
                "merchant": FERRETERIA,
                "amount": "3450.00",
                "currency": "DOP",
                "category_id": None,
                "account_id": account,
                "occurred_on": "2026-10-06",
                "receipt_id": receipt_id,
                "fiscal_known": True,
            }
        ],
        "receipts": [],
        "accounts": [],
    }
    assert alice.get(f"/receipts/{receipt_id}/source").json()["code"] == "document_source_unavailable"
    personal = alice.client.get(
        "/api/v1/financial-search", params={"q": "ferreteria"}, headers=alice.auth
    ).json()["items"]
    assert [hit["activity"]["activity_id"] for hit in personal] == [personal_id]


def test_receipts_match_merchant_filename_and_amount(alice: Owner) -> None:  # noqa: F811
    receipt_id = prepared(alice)
    by_hand = alice.upload(RECEIPT + b"\0", consent=False, name="factura-taller.pdf")
    saved_id = by_hand.json()["id"]

    def receipt_ids(q: str) -> list[str]:
        return [r["id"] for r in alice.get("/search", q=q).json()["receipts"]]

    assert receipt_ids("FERRETERIA esquina") == [receipt_id]
    assert receipt_ids("3450") == [receipt_id]
    assert receipt_ids("factura-taller") == [saved_id]
    assert receipt_ids("png pdf") == []
    assert receipt_ids("recibo") == [receipt_id]
    [summary] = alice.get("/search", q="factura").json()["receipts"]
    assert (summary["status"], summary["merchant"], summary["expense_id"]) == (
        "saved",
        None,
        None,
    )


def test_a_receipt_reachable_from_its_expense_is_listed_once(alice: Owner) -> None:  # noqa: F811
    account = alice.account()
    receipt_id, expense_id = confirmed(alice, account, "Colmado Don Pedro")

    by_filename = alice.get("/search", q="recibo").json()
    by_merchant = alice.get("/search", q="colmado").json()

    assert [r["id"] for r in by_filename["receipts"]] == [receipt_id]
    assert by_filename["expenses"] == []
    assert [e["id"] for e in by_merchant["expenses"]] == [expense_id]
    assert by_merchant["receipts"] == []


def test_manual_expenses_and_accounts_newest_first_and_capped(alice: Owner) -> None:  # noqa: F811
    caja = alice.account("DOP", "Caja chica")
    ids = []
    for day in ("2026-10-02", "2026-10-04", "2026-10-03"):
        made = alice.post(
            "/expenses",
            {
                "account_id": caja,
                "amount": "100.00",
                "occurred_on": day,
                "merchant": "Gasolina Shell",
                "category_id": "transport",
            },
            key=str(uuid4()),
        )
        ids.append((day, made.json()["id"]))
    newest = [expense_id for _, expense_id in sorted(ids, reverse=True)]

    found = alice.get("/search", q="gasolina", limit="2").json()
    assert [e["id"] for e in found["expenses"]] == newest[:2]
    assert {e["receipt_id"] for e in found["expenses"]} == {None}
    assert alice.get("/search", q="caja").json()["accounts"] == [
        {"id": caja, "nickname": "Caja chica", "type": "checking", "currency": "DOP"}
    ]


def test_a_receipt_whose_expense_is_past_the_cap_is_still_listed(alice: Owner) -> None:  # noqa: F811
    account = alice.account()
    receipt_id = prepared(alice)
    version = alice.review(
        receipt_id,
        alice.detail(receipt_id)["version"],
        account_id=account,
        merchant="Gasolina Shell",
        occurred_on="2026-09-01",
    ).json()["version"]
    assert (
        alice.confirm(receipt_id, version, str(uuid4())).json()["status"] == "confirmed"
    )
    for day in ("2026-10-02", "2026-10-03"):
        made = alice.post(
            "/expenses",
            {
                "account_id": account,
                "amount": "100.00",
                "occurred_on": day,
                "merchant": "Gasolina Shell",
                "category_id": "transport",
            },
            key=str(uuid4()),
        )
        assert made.status_code == 201, made.text

    found = alice.get("/search", q="gasolina", limit="2").json()

    assert [e["receipt_id"] for e in found["expenses"]] == [None, None]
    assert [r["id"] for r in found["receipts"]] == [receipt_id]


def test_another_owner_finds_nothing(alice: Owner, bob: Owner) -> None:  # noqa: F811
    account = alice.account("DOP", "Caja")
    confirmed(alice, account, FERRETERIA)
    prepared(alice)
    bob.account("DOP", "Otra caja")

    assert bob.get("/search", q="ferreteria").json() == {
        "expenses": [],
        "receipts": [],
        "accounts": [],
    }
    assert bob.get("/search", q="caja").json()["accounts"][0]["nickname"] == "Otra caja"


def test_query_bounds(alice: Owner) -> None:  # noqa: F811
    refused = [
        alice.get("/search"),
        alice.get("/search", q=""),
        alice.get("/search", q="x" * 513),
        alice.get("/search", q="caja", limit="0"),
        alice.get("/search", q="caja", limit="21"),
    ]
    assert [r.status_code for r in refused] == [422] * 5


def test_the_match_sees_the_receipt_as_the_person_sees_it(alice: Owner) -> None:  # noqa: F811
    """With the hosted bridge a linked draft owns merchant, amount and expense;
    the search matches on that view, never on the pre-overlay legacy fields."""
    from argus.api.business import _captured
    from argus.domain.business.service import BusinessService

    receipt_id = prepared(alice)
    documents = documents_service()
    assert documents is not None
    service = BusinessService(documents, documents.hub.sink, _captured)
    scope = alice.scope()
    [receipt] = [r for r in service.receipts(scope) if r.id == receipt_id]
    view = {
        **receipt.summary(),
        "status": "review_ready",
        "merchant": "Hotel Brisa del Este SRL",
        "amount": "33254.91",
    }
    assert service.search(scope, "Brisa", 5)["receipts"] == []
    [hit] = service.search(scope, "Brisa", 5, {receipt_id: view})["receipts"]
    assert (hit["id"], hit["status"], hit["merchant"]) == (
        receipt_id,
        "review_ready",
        "Hotel Brisa del Este SRL",
    )
    # The view's amount is matched too, and a view already saved as a listed
    # expense is left out: its expense opens it.
    assert [
        r["id"] for r in service.search(scope, "33254", 5, {receipt_id: view})["receipts"]
    ] == [receipt_id]

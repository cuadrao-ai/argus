"""GET /api/v1/business/search: Business records only, through the canonical search."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from argus.api.documents import documents_service
from argus.api.financial_accounts import financial_accounts_service
from argus.domain.business.search import parse
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
from tests.business.test_business_email_api import UNREADABLE, runtime  # noqa: F401

FERRETERIA = "Ferretería La Esquina"
KINDS = (
    "expenses",
    "ventas",
    "receipts",
    "accounts",
    "email_deliveries",
    "email_senders",
)
NOTHING = {**{kind: [] for kind in KINDS}, "next_cursors": dict.fromkeys(KINDS)}


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
        **NOTHING,
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
    }
    source = alice.get(f"/receipts/{receipt_id}/source")
    assert source.status_code == 200
    assert source.headers["content-type"] == "image/jpeg"
    assert source.content.startswith(b"\xff\xd8")
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


def manual(owner: Owner, account: str, day: str, amount: str = "100.00") -> str:
    made = owner.post(
        "/expenses",
        {
            "account_id": account,
            "amount": amount,
            "occurred_on": day,
            "merchant": "Gasolina Shell",
            "category_id": "transport",
        },
        key=str(uuid4()),
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def test_load_more_pages_one_kind_until_its_cursor_is_null(alice: Owner) -> None:  # noqa: F811
    account = alice.account()
    receipt_id = prepared(alice)
    version = alice.review(
        receipt_id,
        alice.detail(receipt_id)["version"],
        account_id=account,
        merchant="Gasolina Shell",
        occurred_on="2026-09-01",
    ).json()["version"]
    confirmed_expense = alice.confirm(receipt_id, version, str(uuid4())).json()
    newest = [manual(alice, account, day) for day in ("2026-10-03", "2026-10-02")]

    first = alice.get("/search", q="gasolina", limit="2").json()
    assert [e["id"] for e in first["expenses"]] == newest
    # The receipt is under its expense, on the next page: never listed twice.
    assert first["receipts"] == []
    cursor = first["next_cursors"]["expenses"]
    assert cursor is not None
    assert {k: v for k, v in first["next_cursors"].items() if k != "expenses"} == (
        dict.fromkeys(KINDS[1:])
    )

    more = alice.get(
        "/search", q="gasolina", limit="2", kind="expenses", cursor=cursor
    ).json()
    assert [(e["id"], e["receipt_id"]) for e in more["expenses"]] == [
        (confirmed_expense["expense_id"], receipt_id)
    ]
    assert more == {**NOTHING, "expenses": more["expenses"]}

    only = alice.get("/search", q="gasolina", limit="1", kind="expenses").json()
    assert [e["id"] for e in only["expenses"]] == newest[:1]
    assert only["accounts"] == [] and only["next_cursors"]["expenses"] is not None


def test_a_cursor_needs_its_own_kind_query_and_records(alice: Owner) -> None:  # noqa: F811
    account = alice.account()
    for day in ("2026-10-01", "2026-10-02"):
        manual(alice, account, day)
    cursor = alice.get("/search", q="gasolina", limit="1").json()["next_cursors"][
        "expenses"
    ]

    def code(**params: str) -> tuple[int, str]:
        answered = alice.get("/search", **{"q": "gasolina", "limit": "1", **params})
        return answered.status_code, answered.json().get("code")

    invalid = (422, "business_search_invalid_cursor")
    assert code(cursor=cursor) == invalid
    assert code(kind="receipts", cursor=cursor) == invalid
    assert code(q="shell", kind="expenses", cursor=cursor) == invalid
    assert code(kind="expenses", cursor="bm90LWEtY3Vyc29y") == invalid
    assert code(kind="expenses", cursor=cursor)[0] == 200
    manual(alice, account, "2026-10-03")
    assert code(kind="expenses", cursor=cursor) == (
        409,
        "business_search_stale_cursor",
    )


def test_an_expense_matches_its_amount_by_value_only(alice: Owner) -> None:  # noqa: F811
    account = alice.account()
    expense = manual(alice, account, "2026-10-02", amount="3450.00")
    manual(alice, account, "2026-10-03", amount="345.00")

    def found(q: str) -> list[str]:
        return [e["id"] for e in alice.get("/search", q=q).json()["expenses"]]

    for q in ("3450", "3450.00", "3,450", "3,450.00", "$ 3450", "RD$ 3,450", "RD$3,450.00"):
        assert found(q) == [expense], q
    for q in ("345", "34", "3450.01", "US$3,450.00", "-3450", "taller 3450"):
        assert expense not in found(q), q
    # A comma before two digits is no thousands group: never 345.
    assert found("3,45") == []


def test_email_originals_are_left_out_before_the_page_is_cut(
    alice: Owner,  # noqa: F811
    runtime,  # noqa: ANN001
) -> None:
    """Two forwarded emails: each original is the email, not a receipt, so a
    page of two holds both attachments and has no next page."""

    from argus.domain.ingestion.email_intake.models import EmailDeliveryPart

    space_id = alice.scope().owner.space_id
    store = runtime.store
    route = store.create_route(
        recipient="recibos-00000002@recibos.example.test",
        space_id=space_id,
        principal_id=alice.scope().person_id,
        granted_by=alice.scope().person_id,
        grant_id=str(uuid4()),
    )
    attachments = []
    for n in (1, 2):
        store.enqueue(
            "resend",
            str(uuid4()),
            (route.recipient,),
            route_id=route.id,
            space_id=space_id,
            principal_id=route.principal_id,
        )
        claimed = store.claim()
        original = alice.upload(
            content=b"Subject: Factura %d\r\n\r\nForwarded receipt" % n,
            consent=False, name=f"factura-{n}.eml", media_type="message/rfc822",
        )
        attachment = alice.upload(
            content=UNREADABLE + bytes([n]), consent=False, name=f"factura-{n}.png"
        )
        assert (original.status_code, attachment.status_code) == (200, 200)
        store.update(claimed, original_document_id=original.json()["id"], subject="Factura")
        store.put_part(
            claimed,
            EmailDeliveryPart(
                "1.2", f"factura-{n}.png", "image/png", "captured",
                attachment.json()["id"], None,
            ),
        )
        store.finish(claimed, "captured")
        attachments.append(attachment.json()["id"])

    page = alice.get("/search", q="factura", limit="2").json()
    assert sorted(item["id"] for item in page["receipts"]) == sorted(attachments)
    assert page["next_cursors"]["receipts"] is None


def test_another_owner_finds_nothing(alice: Owner, bob: Owner) -> None:  # noqa: F811
    account = alice.account("DOP", "Caja")
    confirmed(alice, account, FERRETERIA)
    prepared(alice)
    bob.account("DOP", "Otra caja")

    assert bob.get("/search", q="ferreteria").json() == NOTHING
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
    assert service.search(scope, parse("Brisa"))["receipts"] == []
    [hit] = service.search(scope, parse("Brisa"), {receipt_id: view})["receipts"]
    assert (hit["id"], hit["status"], hit["merchant"]) == (
        receipt_id,
        "review_ready",
        "Hotel Brisa del Este SRL",
    )
    # The view's amount is matched too, and a view already saved as a listed
    # expense is left out: its expense opens it.
    assert [
        r["id"]
        for r in service.search(scope, parse("33254"), {receipt_id: view})["receipts"]
    ] == [receipt_id]


def test_email_deliveries_by_sender_and_subject_and_senders_by_address(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
    runtime,  # noqa: ANN001, F811
) -> None:
    space_id = alice.scope().owner.space_id
    store = runtime.store
    route = store.create_route(
        recipient="recibos-00000001@recibos.example.test",
        space_id=space_id,
        principal_id=alice.scope().person_id,
        granted_by=alice.scope().person_id,
        grant_id=str(uuid4()),
    )
    sent = {}
    for sender, subject in (
        ("facturas@colmado.example.test", "Factura 0041"),
        ("ventas@ferreteria.example.test", "Cotización de tubos"),
    ):
        store.enqueue(
            "resend",
            str(uuid4()),
            (route.recipient,),
            route_id=route.id,
            space_id=space_id,
            principal_id=route.principal_id,
        )
        claimed = store.claim()
        store.update(claimed, sender=sender, subject=subject)
        sent[sender] = claimed.id
    rule = store.upsert_sender(
        space_id, "address", "facturas@colmado.example.test", "authorized"
    )

    by_sender = alice.get("/search", q="colmado").json()
    [delivery] = by_sender["email_deliveries"]
    assert delivery == {
        "id": sent["facturas@colmado.example.test"],
        "sender": "facturas@colmado.example.test",
        "subject": "Factura 0041",
        "received_at": delivery["received_at"],
        "state": "processing",
        "inbox_group": None,
    }
    assert by_sender["email_senders"] == [
        {
            "id": rule.id,
            "kind": "address",
            "value": "facturas@colmado.example.test",
            "status": "authorized",
        }
    ]
    by_subject = alice.get("/search", q="cotizacion").json()
    assert [d["id"] for d in by_subject["email_deliveries"]] == [
        sent["ventas@ferreteria.example.test"]
    ]
    assert by_subject["email_senders"] == []
    assert bob.get("/search", q="colmado").json() == NOTHING


def test_no_email_kinds_while_receiving_is_off(alice: Owner) -> None:  # noqa: F811
    found = alice.get("/search", q="colmado", kind="email_deliveries")
    assert found.status_code == 200, found.text
    assert found.json() == NOTHING

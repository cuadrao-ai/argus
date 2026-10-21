"""Over HTTP on the real app, Auth and Postgres: Business search finds a record
by the RNC, NCF and amount its draft carries, by value only, before and after
approval; a saved Venta is listed under ``ventas``, never ``expenses``, and a
saved record's receipt is reached through the record, never listed twice."""

from __future__ import annotations

from tests.test_business_document_type_postgres import (  # noqa: F401
    API,
    CLIENT_RNC,
    PURCHASE_606,
    SALE_607,
    SUPPLIER_RNC,
    _account,
    _approve,
    _facts,
    _own_rnc,
    _review,
    _upload,
    pytestmark,
    web,
)


def _search(world, q: str) -> dict:  # noqa: ANN001
    found = world.client.get(
        f"{API}/business/search", params={"q": q}, headers=world.alice.headers
    )
    assert found.status_code == 200, found.text
    return found.json()


def _ids(world, q: str) -> dict[str, list[str]]:  # noqa: ANN001
    found = _search(world, q)
    return {
        kind: [item["id"] for item in found[kind]]
        for kind in ("expenses", "ventas", "receipts")
    }


def test_rnc_ncf_and_amount_find_receipts_expenses_and_ventas(web) -> None:  # noqa: ANN001, F811
    _own_rnc(web)
    account = _account(web)
    receipt = _upload(web, SUPPLIER_RNC)
    pending = {"expenses": [], "ventas": [], "receipts": [receipt["id"]]}
    for q in ("B0100000001", "b01-0000-0001", "199-99002-1", "199990021"):
        assert _ids(web, q) == pending, q

    bought = receipt["draft_id"]
    reviewed = _review(
        web,
        bought,
        {
            "facts": _facts("expense", "1180.00", "2026-09-03", account),
            "dgii": PURCHASE_606,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    _approve(web, bought, "record_expense")
    sale = _upload(web, CLIENT_RNC, "venta", occurred_on="2026-09-16", total="2360.00")
    sold = sale["draft_id"]
    reviewed = _review(
        web,
        sold,
        {"facts": _facts("income", "2360.00", "2026-09-16", account), "dgii": SALE_607},
    )
    assert reviewed.status_code == 200, reviewed.text
    _approve(web, sold, "record_income")

    [expense] = _search(web, "B0100000001")["expenses"]
    assert (expense["receipt_id"], expense["draft_id"], expense["amount"]) == (
        receipt["id"],
        bought,
        "1180.00",
    )
    saved = {"expenses": [expense["id"]], "ventas": [], "receipts": []}
    for q in ("B0100000001", "199-99002-1", "1180", "1,180.00", "RD$1,180.00"):
        assert _ids(web, q) == saved, q

    [venta] = _search(web, "B0100000002")["ventas"]
    assert (
        venta["merchant"],
        venta["amount"],
        venta["draft_id"],
        venta["receipt_id"],
    ) == (
        "PRÁCTICA cliente",
        "2360.00",
        sold,
        sale["id"],
    )
    sold_ids = {"expenses": [], "ventas": [venta["id"]], "receipts": []}
    for q in ("B0100000002", CLIENT_RNC, "2360", "2,360.00"):
        assert _ids(web, q) == sold_ids, q
    assert _ids(web, "práctica cliente") == {
        "expenses": [expense["id"]],
        "ventas": [venta["id"]],
        "receipts": [],
    }

    nothing = {"expenses": [], "ventas": [], "receipts": []}
    for q in ("B0100000003", "19999002", "1999900211", "1180.01", "US$1,180.00"):
        assert _ids(web, q) == nothing, q

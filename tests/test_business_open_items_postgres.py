"""Open items over HTTP, on the real app, Auth and Postgres.

What a Business is still owed, and still owes, stays listed from any month
until it is marked cobrado or pagado. Amounts stay in their own currency. The
owner and an accountant read the same list. Nobody else reads it.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_scope_switch_routes_postgres import (  # noqa: F401
    API,
    _as,
    _code,
    web,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
FIXTURES = Path(__file__).parent / "dgii/fixtures"
PRACTICE = {
    row["record_id"]: row["input"]
    for row in json.loads((FIXTURES / "practice-inputs.json").read_text())["records"]
}


def _send(world, method: str, path: str, body: dict, headers: dict):  # noqa: ANN001, ANN202
    answer = world.client.request(
        method,
        f"{API}{path}",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code in (200, 201), (path, answer.text)
    return answer.json()


def _account(world, currency: str) -> str:  # noqa: ANN001
    return _send(
        world,
        "POST",
        "/business/accounts",
        {"nickname": f"Caja {currency}", "type": "cash", "currency": currency},
        world.alice.headers,
    )["id"]


def _record(
    world,  # noqa: ANN001
    account: str,
    kind: str,
    amount: str,
    currency: str,
    day: str,
    counterparty: str,
    practice: str | None = None,
) -> str:
    """Capture, review, and approve one document as the owner; its activity id."""

    owner = world.alice.headers
    note = _send(world, "POST", "/business/captures", {"text": counterparty}, owner)
    facts = {
        name: {"state": "known", "value": value}
        for name, value in {
            "kind": kind,
            "amount": amount,
            "currency": currency,
            "occurred_on": day,
            "counterparty": counterparty,
            "funding": {"kind": "business_account", "account_id": account},
            "business_share": {"kind": "all"},
        }.items()
    }
    review = {"version": note["version"], "facts": facts}
    if practice:
        review["dgii"] = PRACTICE[practice]
    reviewed = _send(
        world, "PATCH", f"/business/drafts/{note['draft_id']}/review", review, owner
    )
    approved = _send(
        world,
        "POST",
        f"/business/drafts/{note['draft_id']}/approve",
        {"version": reviewed["version"], "action": f"record_{kind}"},
        owner,
    )
    return approved["approval_result"]["activity_id"]


def _settle(world, activity: str, status: str, headers: dict) -> None:  # noqa: ANN001
    body = {"status": status}
    if status != "pendiente":
        body |= {"settled_on": "2026-10-20", "payment_method": "transferencia"}
    _send(world, "PATCH", f"/business/month-close/documents/{activity}", body, headers)


def _open(world, headers: dict):  # noqa: ANN001, ANN202
    answer = world.client.get(f"{API}/business/open-items", headers=headers)
    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    return answer.json()


def _ids(listed: dict) -> list[str]:
    return [item["activity_id"] for item in listed["items"]]


def _totals(listed: dict) -> list[tuple[str, int, str]]:
    return [(t["currency"], t["total_minor"], t["total"]) for t in listed["totals"]]


def test_what_is_still_owed_stays_listed_across_months_until_it_is_marked_paid(
    web,  # noqa: ANN001, F811
) -> None:
    owner = web.alice.headers
    pesos, dollars = _account(web, "DOP"), _account(web, "USD")
    # Recorded newest first, so the list order cannot be the insertion order.
    october_sale = _record(
        web, dollars, "income", "150", "USD", "2026-10-02", "Cliente en dólares"
    )
    october_bill = _record(
        web, pesos, "expense", "500", "DOP", "2026-10-05", "Suplidor de octubre"
    )
    paid_sale = _record(
        web, pesos, "income", "590", "DOP", "2026-09-18", "PRÁCTICA S02", "S02"
    )
    september_sale = _record(
        web, pesos, "income", "2360", "DOP", "2026-09-16", "PRÁCTICA S01", "S01"
    )
    september_bill = _record(
        web, pesos, "expense", "1180", "DOP", "2026-09-03", "PRÁCTICA P01", "P01"
    )
    _settle(web, paid_sale, "cobrado", owner)

    october = web.client.get(
        f"{API}/business/month-close", params={"month": "2026-10"}, headers=owner
    ).json()
    assert [i["activity_id"] for i in october["cuentas_por_cobrar"]] == [october_sale]

    opened = _open(web, owner)
    cobrar, pagar = opened["cuentas_por_cobrar"], opened["cuentas_por_pagar"]
    assert _ids(cobrar) == [september_sale, october_sale]
    assert _ids(pagar) == [september_bill, october_bill]
    assert (cobrar["count"], pagar["count"]) == (2, 2)
    assert _totals(cobrar) == [("DOP", 236000, "2360.00"), ("USD", 15000, "150.00")]
    assert _totals(pagar) == [("DOP", 168000, "1680.00")]
    assert cobrar["items"][0] == {
        "activity_id": september_sale,
        "document_kind": "invoice",
        "currency": "DOP",
        "occurred_on": "2026-09-16",
        "total_minor": 236000,
        "total": "2360.00",
        "before_itbis_minor": 200000,
        "before_itbis": "2000.00",
        "itbis_minor": 36000,
        "itbis": "360.00",
        "counterparty": "PRÁCTICA S01",
        "rnc": "199990056",
        "ncf": "B0100000001",
        "ecf": None,
        "status": "pendiente",
        "sin_comprobante": False,
        "due_on": None,
    }
    dollar_line = cobrar["items"][1]
    assert (
        dollar_line["currency"],
        dollar_line["total_minor"],
        dollar_line["total"],
    ) == (
        "USD",
        15000,
        "150.00",
    )
    assert (dollar_line["itbis_minor"], dollar_line["itbis"]) == (None, None)

    _settle(web, september_sale, "cobrado", owner)
    _settle(web, september_bill, "pagado", owner)
    after = _open(web, owner)
    assert _ids(after["cuentas_por_cobrar"]) == [october_sale]
    assert _ids(after["cuentas_por_pagar"]) == [october_bill]
    assert _totals(after["cuentas_por_cobrar"]) == [("USD", 15000, "150.00")]

    _settle(web, september_bill, "pendiente", owner)
    assert _ids(_open(web, owner)["cuentas_por_pagar"]) == [september_bill, october_bill]


def test_the_owner_and_the_accountant_read_the_same_items_and_nobody_else(
    web,  # noqa: ANN001, F811
) -> None:
    pesos = _account(web, "DOP")
    sale = _record(web, pesos, "income", "800", "DOP", "2026-08-30", "Cliente de agosto")
    owner_view = _open(web, web.alice.headers)
    assert _ids(owner_view["cuentas_por_cobrar"]) == [sale]

    assert _open(web, _as(web.bob, web.grant_a)) == owner_view
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read'] where id=%s",
            (web.grant_a,),
        )
    assert _open(web, _as(web.bob, web.grant_a)) == owner_view
    extra = web.client.get(
        f"{API}/business/open-items",
        params={"month": "2026-10"},
        headers=web.alice.headers,
    )
    assert _code(extra) == (422, "validation_error")
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['prepare'] where id=%s",
            (web.grant_a,),
        )
    no_read = web.client.get(
        f"{API}/business/open-items", headers=_as(web.bob, web.grant_a)
    )
    # A grant without read is not a live grant for any Business route.
    assert _code(no_read) == (403, "business_grant_not_live")

    # Bob in his own Business, and Carol in hers, see none of Alice's documents.
    for stranger in (web.bob.headers, web.carol.headers):
        theirs = _open(web, stranger)
        assert theirs["cuentas_por_cobrar"] == {
            "count": 0,
            "totals": [],
            "overdue": {"count": 0, "totals": []},
            "items": [],
        }
    # Someone else's grant, and a revoked one, are refused before any read.
    borrowed = web.client.get(
        f"{API}/business/open-items", headers=_as(web.carol, web.grant_a)
    )
    assert _code(borrowed) == (403, "business_grant_not_live")
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (web.grant_a,),
        )
    revoked = web.client.get(
        f"{API}/business/open-items", headers=_as(web.bob, web.grant_a)
    )
    assert _code(revoked) == (403, "business_grant_not_live")

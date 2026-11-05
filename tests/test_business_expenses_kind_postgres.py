"""The period's ventas over HTTP, on the real app, Auth and Postgres.

`GET /business/expenses` reads one kind of saved record: expenses by default,
or ventas (saved income) with `kind=income`. Each item keeps its own currency.
"""

from __future__ import annotations

from tests.test_business_open_items_postgres import _account, _record
from tests.test_business_scope_switch_routes_postgres import (  # noqa: F401
    API,
    _as,
    web,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
OCTOBER = {"from": "2026-10-01", "to": "2026-10-31"}


def _listed(world, headers: dict, **params) -> list[dict]:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/expenses", params={**OCTOBER, **params}, headers=headers
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["items"]


def test_kind_income_lists_the_period_ventas_in_their_own_currency(web) -> None:  # noqa: ANN001, F811
    owner = web.alice.headers
    pesos = _account(web, "DOP")
    dollars = _account(web, "USD")
    purchase = _record(web, pesos, "expense", "3450", "DOP", "2026-10-16", "Ferreteria")
    sale = _record(web, pesos, "income", "5000", "DOP", "2026-10-10", "Cliente Uno")
    dollar_sale = _record(
        web, dollars, "income", "120", "USD", "2026-10-12", "Cliente Dos"
    )
    _record(web, pesos, "income", "900", "DOP", "2026-09-30", "Cliente de septiembre")

    assert [item["id"] for item in _listed(web, owner)] == [purchase]
    ventas = _listed(web, owner, kind="income")
    assert [(item["id"], item["currency"], item["amount"]) for item in ventas] == [
        (dollar_sale, "USD", "120.00"),
        (sale, "DOP", "5000.00"),
    ]
    assert [item["merchant"] for item in ventas] == ["Cliente Dos", "Cliente Uno"]
    assert _listed(web, _as(web.bob, web.grant_a), kind="income") == ventas
    assert _listed(web, web.bob.headers, kind="income") == []

    refused = web.client.get(
        f"{API}/business/expenses", params={**OCTOBER, "kind": "venta"}, headers=owner
    )
    assert refused.status_code == 422, refused.text

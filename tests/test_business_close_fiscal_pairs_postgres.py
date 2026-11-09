"""Over HTTP on the real app, Auth and Postgres: Para cerrar's fiscal-data row
counts the month's documents the 606 or 607 still holds, and its action opens
Registros on one family and one currency with "Faltan datos fiscales". The two
must list the same records: both read the export's one verdict."""

from __future__ import annotations

from collections import defaultdict

from tests import test_business_approve_unpaid_postgres as unpaid
from tests.test_business_month_close_fields_postgres import _month, _set_own_rnc
from tests.test_business_open_items_postgres import API, web  # noqa: F401
from tests.test_business_open_items_postgres import pytestmark as _local_supabase

pytestmark = _local_supabase
FAMILY = {"receipt": "purchase", "invoice": "sale"}


def _registros(world, family: str, currency: str, start: str, end: str) -> list[str]:  # noqa: ANN001
    """The rows the row's action opens: web/components/business-app/transacciones/records-focus.ts."""

    answer = world.client.post(
        f"{API}/business/reports/query",
        json={
            "schema_version": 1,
            "filters": {
                "period": {"kind": "custom", "from_date": start, "to_date": end},
                "record_families": [family],
                "currencies": [currency],
                "fiscal_data": "missing",
            },
            "page": 1,
            "page_size": 100,
        },
        headers=world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    return sorted(item["linked_activity_ids"][0] for item in answer.json()["items"])


def test_each_fiscal_row_opens_exactly_the_records_it_counts(web) -> None:  # noqa: ANN001, F811
    _set_own_rnc(web)
    held = [unpaid._recorded(web, "expense", f"B01000000{n}")[1]["approval_result"]["activity_id"] for n in (51, 52)]
    unpaid._recorded(web, "income", "B0100000054")

    month = _month(web, "2026-09")
    lines: dict[tuple[str, str], list[str]] = defaultdict(list)
    for document in month["missing_fiscal_data"]:
        lines[(FAMILY[document["document_kind"]], document["currency"])].append(document["activity_id"])
    assert set(held) <= set(lines[("purchase", "DOP")])
    rows = month["missing_fiscal_rows"]
    assert {(row["family"], row["currency"]) for row in rows} == set(lines)
    for row in rows:
        opened = _registros(web, row["family"], row["currency"], month["from"], month["to"])
        assert len(opened) == row["count"], row
        assert opened == sorted(lines[(row["family"], row["currency"])]), row

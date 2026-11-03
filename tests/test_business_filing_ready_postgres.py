"""Over HTTP on the real app, Auth and Postgres: ``filing_ready`` on the month
close is one fact. A month whose 606 and 607 stand by the export's verdict is
still not ready while a receipt of that month waits in the Bandeja, because the
export only sees approved records.
"""

from __future__ import annotations

from tests import test_business_approve_unpaid_postgres as unpaid
from tests.test_business_document_type_postgres import (  # noqa: F401
    API,
    SUPPLIER_RNC,
    _own_rnc,
    _upload,
    web,
)
from tests.test_business_document_type_postgres import pytestmark as _local_supabase

pytestmark = _local_supabase
MONTH = "2026-09"


def _month(world) -> dict:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/month-close",
        params={"month": MONTH},
        headers=world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_receipt_still_in_the_bandeja_holds_filing_ready_while_the_forms_stand(
    web,  # noqa: ANN001, F811
) -> None:
    _own_rnc(web)
    draft, recorded = unpaid._recorded(web, "expense", "B0100000041")
    activity = recorded["approval_result"]["activity_id"]
    unpaid._declare(web, draft, category="02", payment_method="01")
    unpaid._settle(web, activity, "pagado", "efectivo")

    month = _month(web)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert (month["missing_fiscal_data"], month["cuentas_por_pagar"]) == ([], [])
    assert month["filing_ready"] is True

    _upload(web, SUPPLIER_RNC, occurred_on=f"{MONTH}-10")
    month = _month(web)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert month["unreviewed_movements_count"] == 1
    assert month["filing_ready"] is False

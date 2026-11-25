"""An accepted document leaves the owner's reports until the owner restores it."""

from uuid import uuid4

import pytest

from tests import test_business_approve_unpaid_postgres as approvals
from tests.test_business_approve_unpaid_postgres import (
    SPAN,
    _declare,
    _export,
    _fiscal_profile,
    _get,
    _month,
    _recorded,
)
from tests.test_business_fiscal_routes_postgres import dgii_file, table_file
from tests.test_business_scope_switch_routes_postgres import API
from tests.test_business_scope_switch_routes_postgres import pytestmark as _local_supabase

world = approvals.world
pytestmark = _local_supabase


def _record(world, kind, ncf):
    if kind == "expense":
        draft, _ = _recorded(world, kind, ncf)
        _declare(world, draft, category="02", payment_method="01")
    else:
        draft, _ = _recorded(
            world,
            kind,
            ncf,
            id_type="1",
            income_type="1",
            billed_amount="1000.00",
            credit="1180.00",
        )
    return draft


#: The one Registros file each tab offers: the 606 for purchases, Lo que ves for sales.
FILE = {"purchase": dgii_file, "sale": table_file}


def _reads(world, family):
    report = world.client.post(
        f"{API}/business/reports/query", json={}, headers=world.alice.headers
    )
    assert report.status_code == 200, report.text
    registros = report.json()
    overview = _get(world, "/business/overview", **SPAN).json()
    return {
        "registros": sorted(row["row_id"] for row in registros["items"]),
        "matching_count": registros["matching_count"],
        "totals": registros["totals"],
        "inicio": overview["totals"],
        "period": _month(world)["currencies"],
        "export": sorted(_export(world)[1], key=lambda row: row["NCF"]),
        "file": sorted(FILE[family](world, family), key=str),
    }


@pytest.mark.parametrize(
    ("kind", "family"), [("expense", "purchase"), ("income", "sale")]
)
def test_accepted_delete_restore_updates_reports_and_action_counts(
    world, typed_notes_on, settlement_on, kind, family
):
    _fiscal_profile(world)
    _record(world, kind, "B0100000011")
    control = _reads(world, family)
    draft = _record(world, kind, "B0100000012")
    both = _reads(world, family)
    assert (control["matching_count"], both["matching_count"]) == (1, 2)
    assert (len(control["file"]), len(both["file"])) == (1, 2)
    if kind == "expense":
        assert both["inicio"] == [{"currency": "DOP", "amount": "2360.00", "count": 2}]
    delete_key = str(uuid4())
    purge_at = None
    for action, expected, eliminated in (("delete", control, 1), ("restore", both, 0)):
        headers = {
            **world.alice.headers,
            "Idempotency-Key": delete_key if action == "delete" else str(uuid4()),
        }
        url = f"{API}/business/drafts/{draft}/{action}"
        for _ in range(2):
            answer = world.client.post(url, headers=headers)
            assert answer.status_code == 200, answer.text
            assert answer.json()["registros_count"] == expected["matching_count"]
            if action == "delete":
                deadline = answer.json()["purge_at"]
                if purge_at is None:
                    purge_at = _get(world, f"/business/drafts/{draft}/dossier").json()["deleted"]["purge_at"]
                assert deadline == purge_at
            else:
                assert "purge_at" not in answer.json()
            counts = _get(world, "/business/receipt-activity").json()
            assert answer.json()["inbox_counts"] == counts
            assert counts["bandeja_eliminados_count"] == eliminated
        assert _reads(world, family) == expected
    old_delete = world.client.post(
        f"{API}/business/drafts/{draft}/delete",
        headers={**world.alice.headers, "Idempotency-Key": delete_key},
    )
    assert old_delete.status_code == 200
    assert old_delete.json()["registros_count"] == both["matching_count"]
    assert old_delete.json()["purge_at"] == purge_at
    assert old_delete.json()["inbox_counts"]["bandeja_eliminados_count"] == 0


def test_action_counts_still_work_above_the_report_projection_limit(
    world, typed_notes_on, settlement_on
):
    from psycopg import Connection

    from tests.test_financial_accounts_postgres import DSN

    draft, _ = _recorded(world, "expense", "B0100000013")
    with Connection.connect(DSN) as db:
        db.execute(
            "insert into public.financial_import_events "
            "(id,user_id,owner_space_id,state,evidence,possible_duplicates,resolution,"
            "created_at,updated_at,version) "
            "select gen_random_uuid(),user_id,owner_space_id,'dismissed',evidence,"
            "'{}',jsonb_build_object('business',resolution->'business'),now(),now(),1 "
            "from public.financial_import_events cross join generate_series(1,10000) "
            "where id=%s",
            (draft,),
        )
    report = world.client.post(
        f"{API}/business/reports/query", json={}, headers=world.alice.headers
    )
    assert report.json()["code"] == "business_report_too_large"
    for action, count in (("delete", 0), ("restore", 1)):
        result = world.client.post(
            f"{API}/business/drafts/{draft}/{action}",
            headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
        )
        assert result.status_code == 200, result.text
        assert result.json()["registros_count"] == count

from __future__ import annotations

from datetime import date
from uuid import uuid4

from argus.domain.business.contracts.facts import (
    BusinessFacts,
    BusinessResolution,
    Known,
)
from argus.domain.business.month_close import (
    month_period,
    open_items,
    project_documents,
    summarize,
)

from tests.business.test_month_close import DAY
from tests.business.test_open_items import pending


def test_open_items_list_the_soonest_due_date_first_and_undated_ones_after_oldest_first():
    documents = [
        pending("undated-old", "receipt", date(2026, 8, 1)),
        pending("due-late", "receipt", date(2026, 9, 1), due_on=date(2026, 11, 30)),
        pending("undated-new", "receipt", date(2026, 10, 1)),
        pending("due-soon", "receipt", date(2026, 10, 3), due_on=date(2026, 10, 20)),
        pending(
            "due-soon-older", "receipt", date(2026, 9, 15), due_on=date(2026, 10, 20)
        ),
        pending("sale-undated", "invoice", date(2026, 8, 2)),
        pending("sale-due", "invoice", date(2026, 9, 2), due_on=date(2026, 12, 1)),
    ]
    opened = open_items(documents, DAY)
    pagar = opened["cuentas_por_pagar"]["items"]
    assert [(item["activity_id"], item["due_on"]) for item in pagar] == [
        ("due-soon-older", "2026-10-20"),
        ("due-soon", "2026-10-20"),
        ("due-late", "2026-11-30"),
        ("undated-old", None),
        ("undated-new", None),
    ]
    cobrar = opened["cuentas_por_cobrar"]["items"]
    assert [item["activity_id"] for item in cobrar] == ["sale-due", "sale-undated"]


def test_the_cap_keeps_the_soonest_due_documents():
    documents = [
        pending("undated", "invoice", date(2026, 1, 1)),
        pending("due", "invoice", date(2026, 9, 1), due_on=date(2026, 10, 1)),
    ]
    cobrar = open_items(documents, DAY, cap=1)["cuentas_por_cobrar"]
    assert [item["activity_id"] for item in cobrar["items"]] == ["due"]
    assert cobrar["count"] == 2


def test_the_due_date_comes_from_the_draft_and_an_unset_one_stays_null():
    source = uuid4()
    facts = BusinessFacts(
        kind=Known(value="expense", origin="member_set", source_ids=(source,)),
        occurred_on=Known(value=DAY, origin="member_set", source_ids=(source,)),
    )
    bill = {
        "activity_id": "bill",
        "kind": "expense",
        "amount_minor": 5000,
        "currency": "DOP",
        "occurred_at": "2026-10-05T12:00:00-04:00",
        "time_zone": "America/Santo_Domingo",
    }
    undated = {**bill, "activity_id": "undated"}
    resolutions = [
        {
            "activity_id": "bill",
            "resolution": {
                "business": BusinessResolution(
                    facts=facts, due_on=date(2026, 11, 4)
                ).model_dump(mode="json")
            },
        },
        {
            "activity_id": "undated",
            "resolution": {
                "business": BusinessResolution(facts=facts).model_dump(mode="json")
            },
        },
    ]
    documents = project_documents([bill, undated], resolutions, {}, "space-a")
    assert {item.activity_id: item.due_on for item in documents} == {
        "bill": date(2026, 11, 4),
        "undated": None,
    }
    lines = open_items(documents, DAY)["cuentas_por_pagar"]["items"]
    assert [(item["activity_id"], item["due_on"]) for item in lines] == [
        ("bill", "2026-11-04"),
        ("undated", None),
    ]
    month = summarize(documents, *month_period("2026-10"))
    assert {
        item["activity_id"]: item["due_on"] for item in month["cuentas_por_pagar"]
    } == {
        "bill": "2026-11-04",
        "undated": None,
    }
    assert "due_on" not in BusinessResolution(facts=facts).model_dump(mode="json")

"""Open items across months: order, the cap, per-currency totals and the line shape."""

from __future__ import annotations

from datetime import date, timedelta

from argus.domain.business.month_close import month_period, open_items, summarize

from tests.business.test_month_close import DAY, document


def pending(activity_id, role, day, **overrides):
    return document(
        activity_id=activity_id,
        role=role,
        occurred_on=day,
        status="pendiente",
        settled_on=None,
        payment_method=None,
        **overrides,
    )


def test_open_items_are_every_month_close_list_from_every_month_oldest_first():
    documents = [
        pending("oct-sale", "invoice", date(2026, 10, 2), total_minor=500),
        pending("aug-sale", "invoice", date(2026, 8, 30), total_minor=700),
        pending("sep-sale-b", "invoice", date(2026, 9, 16), total_minor=300),
        pending("sep-sale-a", "invoice", date(2026, 9, 16), total_minor=200),
        document(activity_id="sep-collected", occurred_on=date(2026, 9, 1)),
        pending("sep-personal-sale", "invoice", date(2026, 9, 2), personal=True),
        pending("oct-bill", "receipt", date(2026, 10, 5), total_minor=900),
        pending("sep-bill", "receipt", date(2026, 9, 3), total_minor=100),
        pending(
            "sep-personal-kept",
            "receipt",
            date(2026, 9, 4),
            personal=True,
            include_606=True,
            total_minor=50,
        ),
        pending(
            "sep-personal-left",
            "receipt",
            date(2026, 9, 4),
            personal=True,
            include_606=False,
        ),
        document(
            activity_id="sep-paid",
            role="receipt",
            status="pagado",
            occurred_on=date(2026, 9, 9),
        ),
    ]
    opened = open_items(documents, DAY)
    cobrar, pagar = opened["cuentas_por_cobrar"], opened["cuentas_por_pagar"]
    assert [item["activity_id"] for item in cobrar["items"]] == [
        "aug-sale",
        "sep-sale-a",
        "sep-sale-b",
        "oct-sale",
    ]
    assert [item["activity_id"] for item in pagar["items"]] == [
        "sep-bill",
        "sep-personal-kept",
        "oct-bill",
    ]
    assert {item["status"] for item in cobrar["items"] + pagar["items"]} == {"pendiente"}
    assert (cobrar["count"], pagar["count"]) == (4, 3)

    def by_id(items):
        return sorted(items, key=lambda item: item["activity_id"])

    for key in ("cuentas_por_cobrar", "cuentas_por_pagar"):
        by_month = []
        for month in ("2026-08", "2026-09", "2026-10"):
            by_month += summarize(documents, *month_period(month))[key]
        assert by_id(opened[key]["items"]) == by_id(by_month)


def test_the_cap_keeps_the_count_and_each_currency_total_of_every_pending_item():
    documents = [
        pending("sale-1", "invoice", date(2026, 9, 1), total_minor=1000),
        pending("sale-2", "invoice", date(2026, 9, 2), total_minor=2000),
        pending("sale-3", "invoice", date(2026, 9, 3), total_minor=4000),
        pending("sale-usd", "invoice", date(2026, 9, 4), currency="USD", total_minor=150),
    ]
    cobrar = open_items(documents, DAY, cap=2)["cuentas_por_cobrar"]
    assert [item["activity_id"] for item in cobrar["items"]] == ["sale-1", "sale-2"]
    assert cobrar["count"] == 4
    assert cobrar["totals"] == [
        {"currency": "DOP", "total_minor": 7000, "total": "70.00"},
        {"currency": "USD", "total_minor": 150, "total": "1.50"},
    ]
    assert open_items([], DAY)["cuentas_por_pagar"] == {
        "count": 0,
        "totals": [],
        "overdue": {"count": 0, "totals": []},
        "items": [],
    }


def test_the_documented_cap_shows_the_oldest_hundred():
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(101)]
    documents = [
        pending(f"sale-{index:03}", "invoice", day, total_minor=1)
        for index, day in enumerate(reversed(days))
    ]
    cobrar = open_items(documents, DAY)["cuentas_por_cobrar"]
    assert len(cobrar["items"]) == 100
    assert cobrar["count"] == 101
    assert cobrar["totals"][0]["total_minor"] == 101
    assert [item["occurred_on"] for item in cobrar["items"]] == [
        day.isoformat() for day in days[:100]
    ]


def test_an_open_line_keeps_its_currency_parts_and_unknown_itbis_stays_null():
    line = open_items(
        [
            pending(
                "sale",
                "invoice",
                DAY,
                currency="USD",
                total_minor=11800,
                itbis_minor=None,
                counterparty="Cliente",
                ncf=None,
                ecf="E310000000001",
            )
        ],
        DAY,
    )["cuentas_por_cobrar"]["items"][0]
    assert line == {
        "activity_id": "sale",
        "document_kind": "invoice",
        "currency": "USD",
        "occurred_on": "2026-10-05",
        "total_minor": 11800,
        "total": "118.00",
        "before_itbis_minor": 11800,
        "before_itbis": "118.00",
        "itbis_minor": None,
        "itbis": None,
        "counterparty": "Cliente",
        "rnc": "131000001",
        "ncf": None,
        "ecf": "E310000000001",
        "status": "pendiente",
        "sin_comprobante": False,
        "due_on": None,
    }

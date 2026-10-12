"""The home overview says how many saved expenses the chosen period leaves
out, and when the latest of them happened, so a saved expense never looks
vanished because of a period chip."""

from __future__ import annotations

from uuid import uuid4

from tests.business.test_business_api import Owner, alice  # noqa: F401


def test_the_overview_counts_saved_expenses_outside_the_period(alice: Owner) -> None:  # noqa: F811
    account = alice.account("DOP")
    for occurred_on, amount in (("2026-08-26", "33254.91"), ("2026-07-03", "120.00")):
        saved = alice.post(
            "/expenses",
            {"account_id": account, "amount": amount, "occurred_on": occurred_on},
            key=str(uuid4()),
        )
        assert saved.status_code == 201, saved.text
    october = alice.get("/overview", **{"from": "2026-10-01", "to": "2026-10-12"}).json()
    assert october["totals"] == []
    assert (october["outside_period_count"], october["outside_period_latest_on"]) == (
        2,
        "2026-08-26",
    )
    august = alice.get("/overview", **{"from": "2026-08-01", "to": "2026-08-31"}).json()
    assert [t["count"] for t in august["totals"]] == [1]
    assert (august["outside_period_count"], august["outside_period_latest_on"]) == (
        1,
        "2026-07-03",
    )
    everything = alice.get(
        "/overview", **{"from": "2000-01-01", "to": "2026-12-31"}
    ).json()
    assert [t["count"] for t in everything["totals"]] == [2]
    assert (
        everything["outside_period_count"],
        everything["outside_period_latest_on"],
    ) == (
        0,
        None,
    )


def test_the_server_is_the_one_clock_and_a_reversed_range_is_refused(
    alice: Owner,  # noqa: F811
) -> None:
    from argus.domain.business import ledger

    today = ledger.today().isoformat()
    open_ended = alice.get("/overview", **{"from": "2026-10-01"}).json()
    assert (open_ended["to"], open_ended["today"]) == (today, today)
    assert alice.get("/expenses", **{"from": "2026-10-01"}).status_code == 200
    reversed_range = alice.get("/overview", **{"from": "2026-10-31", "to": "2026-10-01"})
    assert (reversed_range.status_code, reversed_range.json()["code"]) == (
        422,
        "period_reversed",
    )
    assert (
        alice.get("/expenses", **{"from": "2026-10-31", "to": "2026-10-01"}).status_code
        == 422
    )

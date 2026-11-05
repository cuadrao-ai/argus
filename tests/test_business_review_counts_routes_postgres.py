"""Over HTTP, on the real app, Auth and Postgres, one Business through the
owner's review journey: the Bandeja's count and the Resumen agree after a
note arrives, after review actions and after a reload; the Personal mark is
applied and taken back through its authorized action; "Sin comprobante
fiscal" is the owner's typed receipt decision and never makes a record valid
for the 606; a stale revision is refused and nothing posts money before
approval."""

from __future__ import annotations

from uuid import uuid4

from tests.test_business_fiscal_routes_postgres import _post, world  # noqa: F401
from tests.test_business_scope_switch_routes_postgres import (
    API,
    PERIOD,
    _as,
    _note,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase


def _get(web, path: str, headers: dict, **params):  # noqa: ANN001, ANN202
    answer = web.client.get(f"{API}{path}", params=params, headers=headers)
    assert answer.status_code == 200, (path, answer.text)
    return answer.json()


def _counts(web, headers: dict) -> tuple[int, int, int, int]:  # noqa: ANN001
    """The Bandeja's count, its notes, and the Resumen's two numbers."""

    activity = _get(web, "/business/receipts", headers, view="inbox")["activity"]
    assert _get(web, "/business/receipt-activity", headers) == activity
    notes = _get(web, "/business/captures", headers, view="inbox", limit=50)
    overview = _get(web, "/business/overview", headers, **PERIOD)
    assert (
        overview["awaiting_review"] + overview["needs_attention"]
        == activity["pending_review_count"]
    )
    return (
        activity["pending_review_count"],
        len({item["draft_id"] for item in notes["items"]}),
        overview["awaiting_review"],
        overview["needs_attention"],
    )


def _review(web, draft: str, facts: dict, headers: dict):  # noqa: ANN001, ANN202
    version = _get(web, f"/business/drafts/{draft}/dossier", headers)["version"]
    return web.client.patch(
        f"{API}/business/drafts/{draft}/review",
        json={
            "version": version,
            "facts": {
                name: {"state": "known", "value": value} for name, value in facts.items()
            },
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


EXPENSE = {
    "kind": "expense",
    "amount": "850",
    "currency": "DOP",
    "occurred_on": "2026-10-09",
    "counterparty": "Ferretería Prueba",
    "funding": {"kind": "owner_funds"},
    "business_share": {"kind": "all"},
}


def test_counts_marks_and_resumen_agree_through_the_review_journey(world) -> None:  # noqa: ANN001, F811
    alice, bob = world.alice, world.bob
    assert _counts(world, alice.headers) == (0, 0, 0, 0)

    first = _note(world, alice, "Pagué 850 en Ferretería Prueba")
    assert first.status_code == 200, first.text
    draft = first.json()["draft_id"]
    assert _counts(world, alice.headers) == (1, 1, 1, 0)
    # A second note on the same record is still one row awaiting review.
    again = world.client.post(
        f"{API}/business/captures",
        json={
            "text": "Con la tarjeta",
            "draft": {"draft_id": draft, "version": first.json()["version"]},
        },
        headers={**alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert again.status_code == 200, again.text
    assert _counts(world, alice.headers) == (1, 1, 1, 0)
    # The accountant working in Alice's Business reads the same numbers.
    assert _counts(world, _as(bob, world.grant)) == (1, 1, 1, 0)

    # "Sin comprobante fiscal": the owner's typed receipt decision, recorded as a revision.
    reviewed = _review(
        world, draft, {**EXPENSE, "receipt_state": "informal_receipt"}, alice.headers
    )
    assert reviewed.status_code == 200, reviewed.text
    record = reviewed.json()
    assert (
        record["facts"]["receipt_state"]["state"],
        record["facts"]["receipt_state"]["value"],
    ) == ("known", "informal_receipt")
    assert (record.get("fiscal_known"), record.get("fiscal_value")) == (True, None)
    # Reviewing records no money and leaves the record awaiting review.
    assert _get(world, "/business/overview", alice.headers, **PERIOD)["totals"] == []
    assert _counts(world, alice.headers) == (1, 1, 1, 0)
    # Missing evidence is never made valid for the 606: there is no question to answer.
    refused = _post(
        world,
        f"/business/drafts/{draft}/fiscal-inclusion",
        {"version": record["version"], "include": True},
        _as(bob, world.grant),
    )
    assert (refused.status_code, refused.json()["code"]) == (
        409,
        "business_606_not_applicable",
    )

    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        {"version": record["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    for _reload in range(2):
        assert _counts(world, alice.headers) == (0, 0, 0, 0)
        overview = _get(world, "/business/overview", alice.headers, **PERIOD)
        assert overview["totals"] == [{"currency": "DOP", "amount": "850.00", "count": 1}]
        assert overview["fiscal_totals"] == []
        assert overview["without_fiscal_totals"] == overview["totals"]

    # The Personal mark through its authorized action: a stale revision is refused,
    # the mark leaves Gastos reales, and taking it back restores it, after reload.
    current = _get(world, f"/business/drafts/{draft}/dossier", alice.headers)["version"]
    stale = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": current - 1, "personal": True},
        alice.headers,
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    marked = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": current, "personal": True},
        alice.headers,
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["personal"] is True
    assert _get(world, "/business/overview", alice.headers, **PERIOD)["totals"] == []
    [expense] = _get(world, "/business/expenses", alice.headers, **PERIOD)["items"]
    assert expense["personal"] is True
    back = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": marked.json()["version"], "personal": False},
        alice.headers,
    )
    assert back.status_code == 200, back.text
    for _reload in range(2):
        assert (
            _get(world, f"/business/drafts/{draft}/dossier", alice.headers)["personal"]
            is False
        )
        assert _get(world, "/business/overview", alice.headers, **PERIOD)["totals"] == [
            {"currency": "DOP", "amount": "850.00", "count": 1}
        ]
        assert _counts(world, alice.headers) == (0, 0, 0, 0)

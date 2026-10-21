"""A member's Business search memory over HTTP: recents per member and per
Business, and the records they opened ranked first in their next search."""

from __future__ import annotations

from uuid import uuid4

from tests.business.test_business_api import Owner, alice, bob  # noqa: F401
from tests.business.test_business_search import manual


def remember(owner: Owner, q: str) -> dict:
    saved = owner.post("/search/recents", {"q": q})
    assert saved.status_code == 201, saved.text
    assert set(saved.json()) == {"id", "q", "searched_at"}
    return saved.json()


def recents(owner: Owner) -> list[str]:
    listed = owner.get("/search/recents")
    assert listed.status_code == 200, listed.text
    return [item["q"] for item in listed.json()["items"]]


def test_recents_are_newest_first_one_per_query_and_capped(alice: Owner) -> None:  # noqa: F811
    first = remember(alice, "Ferretería")
    remember(alice, "B0100000001")
    again = remember(alice, "  ferreteria ")
    assert again["id"] == first["id"]
    assert recents(alice) == ["ferreteria", "B0100000001"]

    for n in range(11):
        remember(alice, f"gasto {n}")
    assert recents(alice) == [f"gasto {n}" for n in reversed(range(11))][:10]


def test_a_recent_is_removed_alone_or_with_all(alice: Owner, bob: Owner) -> None:  # noqa: F811
    kept = remember(alice, "colmado")
    gone = remember(alice, "taller")
    bobs = remember(bob, "taller")

    assert (
        alice.client.delete(
            f"/api/v1/business/search/recents/{gone['id']}", headers=alice.auth
        ).status_code
        == 204
    )
    assert recents(alice) == ["colmado"]
    for missing in (gone["id"], bobs["id"], str(uuid4())):
        refused = alice.client.delete(
            f"/api/v1/business/search/recents/{missing}", headers=alice.auth
        )
        assert (refused.status_code, refused.json()["code"]) == (
            404,
            "business_search_recent_not_found",
        )
    assert recents(bob) == ["taller"]

    assert (
        alice.client.delete(
            "/api/v1/business/search/recents", headers=alice.auth
        ).status_code
        == 204
    )
    assert recents(alice) == []
    assert recents(bob) == ["taller"]
    assert kept["q"] == "colmado"


def test_a_recent_query_is_bounded(alice: Owner) -> None:  # noqa: F811
    for q in ("", "   ", "x" * 513):
        assert alice.post("/search/recents", {"q": q}).status_code == 422
    assert recents(alice) == []


def ranked(owner: Owner, **params: str) -> list[str]:
    found = owner.get("/search", q="gasolina", **params)
    assert found.status_code == 200, found.text
    return [item["id"] for item in found.json()["expenses"]]


def opened(owner: Owner, kind: str, record_id: str) -> None:
    sent = owner.post("/search/opens", {"kind": kind, "id": record_id})
    assert sent.status_code == 204, sent.text


def test_opened_records_rank_first_for_the_member(alice: Owner, bob: Owner) -> None:  # noqa: F811
    account = alice.account()
    old, middle, new = (
        manual(alice, account, day) for day in ("2026-10-01", "2026-10-02", "2026-10-03")
    )
    assert ranked(alice) == [new, middle, old]
    # An open counts for its own list only.
    opened(alice, "receipts", old)
    assert ranked(alice) == [new, middle, old]

    opened(alice, "expenses", old)
    assert ranked(alice) == [old, new, middle]
    opened(alice, "expenses", middle)
    assert ranked(alice) == [middle, old, new]
    opened(alice, "expenses", old)
    assert ranked(alice) == [old, middle, new]
    opened(alice, "expenses", middle)
    assert ranked(alice) == [middle, old, new]
    opened(alice, "expenses", new)
    assert ranked(alice) == [middle, old, new]

    bob_account = bob.account()
    bobs = [manual(bob, bob_account, day) for day in ("2026-10-02", "2026-10-01")]
    opened(bob, "expenses", old)
    assert ranked(bob) == bobs


def test_an_open_since_the_first_page_makes_its_cursor_stale(alice: Owner) -> None:  # noqa: F811
    account = alice.account()
    old = manual(alice, account, "2026-10-01")
    manual(alice, account, "2026-10-02")
    cursor = alice.get("/search", q="gasolina", limit="1").json()["next_cursors"][
        "expenses"
    ]
    opened(alice, "expenses", old)
    stale = alice.get("/search", q="gasolina", limit="1", kind="expenses", cursor=cursor)
    assert (stale.status_code, stale.json()["code"]) == (
        409,
        "business_search_stale_cursor",
    )


def test_an_open_names_a_known_list_and_a_record_id(alice: Owner) -> None:  # noqa: F811
    for body in (
        {"kind": "expense", "id": str(uuid4())},
        {"kind": "expenses", "id": "not-an-id"},
        {"kind": "expenses"},
    ):
        assert alice.post("/search/opens", body).status_code == 422

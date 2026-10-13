"""An accountant works inside a client's Business through one of their own
grants, named per request; the server takes the Business from the grant,
never from the client. Owner-only routes stay the owner's; approve never
leaves the owner; a dead grant stops at once; the one-time access line is
remembered per grant, server side."""

from __future__ import annotations

from uuid import uuid4

from argus.api.business_spaces import business_access

from tests.business.test_business_api import (  # noqa: F401
    BASE,
    RECEIPT,
    Owner,
    alice,
    bob,
)

GRANT = "X-Business-Grant"
OTHER_RECEIPT = RECEIPT[:-8] + bytes(8)


def get_as(owner: Owner, path: str, grant: str | None, **params: str):  # noqa: ANN201
    headers = {**owner.auth, **({GRANT: grant} if grant else {})}
    return owner.client.get(BASE + path, params=params, headers=headers)


def _grant(alice: Owner, bob: Owner) -> str:  # noqa: F811
    """Bob holds read and prepare on Alice's Business; the grant id as listed."""

    store = business_access()
    assert store is not None
    store.confirm(bob.person, "bob@example.test")
    given = alice.post("/access", {"email": "bob@example.test"})
    assert given.status_code == 201, given.text
    [grant] = [g for g in given.json()["grants"] if not g["owner"]]
    return grant["id"]


def _listed(owner: Owner) -> list[dict]:
    answer = owner.get("/spaces")
    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    return answer.json()["spaces"]


def test_the_listing_names_every_business_the_caller_may_enter_own_first(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    own_only = _listed(bob)
    assert [(s["role"], s["access_seen"]) for s in own_only] == [("owner", True)]
    grant = _grant(alice, bob)
    spaces = _listed(bob)
    assert [(s["role"], s["capabilities"], s["access_seen"]) for s in spaces] == [
        ("owner", ["read", "prepare", "approve"], True),
        ("accountant", ["read", "prepare"], False),
    ]
    assert spaces[1]["grant_id"] == grant
    assert spaces[1]["space_id"] == alice.scope().owner.space_id
    assert spaces[1]["name"] == alice.get("/space").json()["name"]
    # Alice's own listing never shows Bob's grant.
    assert [s["role"] for s in _listed(alice)] == ["owner"]


def test_the_one_time_line_is_remembered_per_grant_and_never_for_the_own_business(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    grant = _grant(alice, bob)
    assert _listed(bob)[1]["access_seen"] is False
    assert bob.post(f"/spaces/{grant}/seen").status_code == 204
    assert _listed(bob)[1]["access_seen"] is True
    assert bob.post(f"/spaces/{grant}/seen").status_code == 204
    # A grant that is not Bob's, or nobody's, changes nothing and reveals nothing.
    own = _listed(alice)[0]["grant_id"]
    assert bob.post(f"/spaces/{own}/seen").status_code == 204
    assert bob.post(f"/spaces/{uuid4()}/seen").status_code == 204
    assert _listed(alice)[0]["access_seen"] is True
    # Revoked and granted again: a new grant, the line shows again.
    gone = alice.client.delete(
        f"/api/v1/business/access/grants/{grant}", headers=alice.auth
    )
    assert gone.status_code == 204
    again = _grant(alice, bob)
    assert again != grant
    assert _listed(bob)[1]["access_seen"] is False


def test_with_the_chosen_grant_the_accountant_reads_and_prepares_the_clients_business_only(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    grant = _grant(alice, bob)
    uploaded = alice.upload(consent=False)
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    bob_own = bob.upload(consent=False, content=OTHER_RECEIPT)
    assert bob_own.status_code == 200, bob_own.text
    headers = {GRANT: grant}
    # Alice's receipts, not Bob's own.
    listed = get_as(bob, "/receipts", grant, view="all")
    assert listed.status_code == 200, listed.text
    ids = [r["id"] for r in listed.json()["items"]]
    assert receipt_id in ids and bob_own.json()["id"] not in ids
    detail = get_as(bob, f"/receipts/{receipt_id}", grant)
    assert detail.status_code == 200, detail.text
    assert set(detail.json()["record_context"]["capabilities"]) == {"read", "prepare"}
    # Review by hand is preparing; confirming is approving, which never leaves the owner.
    version = detail.json()["version"]
    reviewed = bob.client.patch(
        f"/api/v1/business/receipts/{receipt_id}/review",
        json={"version": version, "fields": {"merchant": "Ferretería Luna"}},
        headers={**bob.auth, **headers},
    )
    assert reviewed.status_code == 200, reviewed.text
    refused = bob.post(
        f"/receipts/{receipt_id}/confirm",
        {"version": reviewed.json()["version"]},
        key=str(uuid4()),
        **headers,
    )
    assert (refused.status_code, refused.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    # Sending a document to the AI provider is the owner's choice alone.
    assert (
        bob.post(
            f"/receipts/{receipt_id}/prepare",
            key=str(uuid4()),
            **{**headers, "X-Extraction-Consent": "true"},
        ).status_code
        == 403
    )
    uploaded_with_consent = bob.client.post(
        "/api/v1/business/receipts",
        content=OTHER_RECEIPT,
        headers={
            **bob.auth,
            **headers,
            "Content-Type": "image/png",
            "Idempotency-Key": str(uuid4()),
            "X-Extraction-Consent": "true",
        },
    )
    assert (uploaded_with_consent.status_code, uploaded_with_consent.json()["code"]) == (
        403,
        "business_permission_denied",
    )


def test_owner_only_routes_refuse_a_grantee_and_a_dead_or_foreign_grant_stops_everything(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    grant = _grant(alice, bob)
    headers = {GRANT: grant}
    assert get_as(bob, "/access", grant).status_code == 403
    assert bob.post("/access", {"email": "x@example.test"}, **headers).status_code == 403
    assert (
        bob.post(
            "/accounts",
            {"nickname": "Caja", "type": "cash", "currency": "DOP"},
            key=str(uuid4()),
            **headers,
        ).status_code
        == 403
    )
    expense = {
        "account_id": str(uuid4()),
        "amount": "125.00",
        "occurred_on": "2026-10-06",
        "merchant": "Colmado",
        "category_id": None,
    }
    assert bob.post("/expenses", expense, key=str(uuid4()), **headers).status_code == 403
    # Reads through the grant work; the own Business is untouched by the header.
    period = {"from": "2026-10-01", "to": "2026-10-31"}
    assert get_as(bob, "/overview", grant, **period).status_code == 200
    assert get_as(bob, "/workspace", grant).status_code == 200
    # A grant that is Alice's own, a random id, or Bob's grant once revoked: 403, nothing revealed.
    own = _listed(alice)[0]["grant_id"]
    for bad in (own, str(uuid4()), "not-a-grant"):
        refused = get_as(bob, "/receipts", bad)
        assert (refused.status_code, refused.json()["code"]) == (
            403,
            "business_grant_not_live",
        ), bad
    gone = alice.client.delete(
        f"/api/v1/business/access/grants/{grant}", headers=alice.auth
    )
    assert gone.status_code == 204
    for path in ("/receipts", "/overview", "/workspace", "/expenses", "/updates"):
        refused = get_as(bob, path, grant, **period)
        assert (refused.status_code, refused.json()["code"]) == (
            403,
            "business_grant_not_live",
        ), path
    # Without the header Bob is back in his own Business.
    assert bob.get("/receipts").status_code == 200


def test_a_record_of_another_business_is_missing_not_forbidden(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    grant = _grant(alice, bob)
    own = bob.upload(consent=False, content=OTHER_RECEIPT)
    assert own.status_code == 200, own.text
    # Bob's own receipt, asked for through Alice's grant: not in that Business.
    answer = get_as(bob, f"/receipts/{own.json()['id']}", grant)
    assert answer.status_code == 404
    # Alice's receipt, asked for with no header (Bob's own Business): not there either.
    theirs = alice.upload(consent=False)
    assert bob.get(f"/receipts/{theirs.json()['id']}").status_code == 404

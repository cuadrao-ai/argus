"""An accountant works inside a client's Business through one of their own
grants, named per request; the server takes the Business from the grant,
never from the client. Owner-only routes stay the owner's; approve never
leaves the owner; a dead grant stops at once; the one-time access line is
remembered per grant, server side."""

from __future__ import annotations

from uuid import uuid4

from argus.api.business_spaces import business_access
from fastapi.testclient import TestClient

from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import (  # noqa: F401
    ALICE,
    BASE,
    BOB,
    RECEIPT,
    Owner,
    alice,
    bob,
)
from tests.business.test_business_email_api import runtime  # noqa: F401
from tests.business.test_business_whatsapp import wa_biz  # noqa: F401
from tests.test_conversation_surfaces import client as chat_client  # noqa: F401

GRANT = "X-Business-Grant"
OTHER_RECEIPT = RECEIPT[:-8] + bytes(8)
THIRD_RECEIPT = RECEIPT[:-8] + b"\x01" * 8


def get_as(owner: Owner, path: str, grant: str | None, **params: str):  # noqa: ANN201
    headers = {**owner.auth, **({GRANT: grant} if grant else {})}
    return owner.client.get(BASE + path, params=params, headers=headers)


def _grant(alice: Owner, bob: Owner) -> str:  # noqa: F811
    """Bob holds read and prepare on Alice's Business; the grant id as listed."""

    store = business_access()
    assert store is not None
    renamed = alice.client.patch(
        BASE + "/space", json={"name": "Ferretería Prueba"}, headers=alice.auth
    )
    assert renamed.status_code == 200, renamed.text
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
    stub: ReceiptStub,
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
    # A grantee's consent header is ignored: the owner's setting is off, so the
    # receipt is saved unread and the provider is never called.
    uploaded_with_consent = _grantee_upload(bob, grant, OTHER_RECEIPT)
    assert uploaded_with_consent.status_code == 200, uploaded_with_consent.text
    assert uploaded_with_consent.json()["status"] == "saved"
    assert stub.calls == []


def _grantee_upload(bob: Owner, grant: str, content: bytes):  # noqa: F811, ANN202
    return bob.client.post(
        "/api/v1/business/receipts",
        content=content,
        headers={
            **bob.auth,
            GRANT: grant,
            "Content-Type": "image/png",
            "Idempotency-Key": str(uuid4()),
            "X-Extraction-Consent": "true",
        },
    )


def test_a_grantees_upload_follows_the_owners_reading_setting(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
    stub: ReceiptStub,
) -> None:
    grant = _grant(alice, bob)
    assert alice.reading(True).status_code == 200
    uploaded = _grantee_upload(bob, grant, OTHER_RECEIPT)
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    assert uploaded.json()["status"] == "queued"
    assert stub.calls == [receipt_id]
    assert alice.detail(receipt_id)["status"] == "review_ready"
    assert alice.reading(False).status_code == 200
    unread = _grantee_upload(bob, grant, THIRD_RECEIPT)
    assert unread.status_code == 200, unread.text
    assert unread.json()["status"] == "saved"
    assert stub.calls == [receipt_id]


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


def test_the_own_business_routes_and_the_owner_channels_refuse_a_chosen_grant(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
    runtime,  # noqa: ANN001, F811
) -> None:
    """The own space's name and the receiving address are the owner's: under a
    client grant the space routes and the address writes refuse; the address
    itself is view-only."""

    grant = _grant(alice, bob)
    headers = {GRANT: grant}
    assert (
        get_as(bob, "/space", grant).status_code,
        get_as(bob, "/space", grant).json()["code"],
    ) == (
        403,
        "business_permission_denied",
    )
    renamed = bob.client.patch(
        BASE + "/space", json={"name": "Otro nombre"}, headers={**bob.auth, **headers}
    )
    assert (renamed.status_code, renamed.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    # Without the header Bob's own space is his to read and rename.
    assert bob.get("/space").status_code == 200
    # The email address: seen, never created or stopped, by a grantee.
    assert get_as(bob, "/email", grant).status_code == alice.get("/email").status_code
    created = bob.post("/email", key=str(uuid4()), **headers)
    assert (created.status_code, created.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    stopped = bob.client.delete(BASE + "/email", headers={**bob.auth, **headers})
    assert (stopped.status_code, stopped.json()["code"]) == (
        403,
        "business_permission_denied",
    )


def test_whatsapp_stays_the_owners_channel_under_a_chosen_grant(
    wa_biz,  # noqa: ANN001, F811
    identities,  # noqa: ANN001, F811
) -> None:
    client, _ = wa_biz
    owner = Owner(client, ALICE, identities[ALICE]["id"])
    accountant = Owner(client, BOB, identities[BOB]["id"])
    assert owner.start().status_code == 201 and accountant.start().status_code == 201
    grant = _grant(owner, accountant)
    headers = {GRANT: grant}
    # WhatsApp is the owner's channel: every link route refuses a grantee.
    for response in (
        client.post(
            "/api/v1/whatsapp/link-codes", headers={**accountant.auth, **headers}
        ),
        client.get("/api/v1/whatsapp/link", headers={**accountant.auth, **headers}),
    ):
        assert (response.status_code, response.json()["code"]) == (
            403,
            "business_permission_denied",
        )
    assert client.get("/api/v1/whatsapp/link", headers=accountant.auth).status_code == 200
    # Ending one's own sender link is never gated: it is the person's, not the Business's.
    assert (
        client.delete(
            "/api/v1/whatsapp/link", headers={**accountant.auth, **headers}
        ).status_code
        == 204
    )


def test_business_chat_stays_the_owners_under_a_chosen_grant(
    chat_client: TestClient,  # noqa: F811
) -> None:
    from argus.api.business_spaces import business_access, configure_business_access
    from argus.domain.business.access import InMemoryAccessStore

    from tests.test_conversation_surfaces import _as as as_person
    from tests.test_conversation_surfaces import _start_space

    client = chat_client
    space_a = _start_space(ALICE)
    space_b = _start_space(BOB)
    previous = business_access()
    store = InMemoryAccessStore()
    configure_business_access(store)
    try:
        _chat_under_grant(client, store, space_a, space_b, as_person)
    finally:
        configure_business_access(previous)


def _chat_under_grant(client, store, space_a, space_b, as_person) -> None:  # noqa: ANN001
    from argus.api import state as api_state

    store.ensure_owner_grant(space_a, ALICE)
    store.ensure_owner_grant(space_b, BOB)
    store.confirm(BOB, "bob@example.test")
    created, _ = store.give(space_a, ALICE, "bob@example.test")
    assert created is True
    [grant] = [s.grant_id for s in store.spaces_for(BOB) if s.role == "accountant"]
    # A stored conversation belongs to its space's owner, so Business chat under a
    # client grant is refused outright: never run in Bob's own Business by mistake.
    for response in (
        client.post(
            "/api/v1/conversations",
            json={"surface": "business"},
            headers={**as_person(BOB), GRANT: grant},
        ),
        client.get(
            "/api/v1/conversations",
            params={"surface": "business"},
            headers={**as_person(BOB), GRANT: grant},
        ),
    ):
        assert (response.status_code, response.json()["code"]) == (
            403,
            "business_permission_denied",
        ), response.text
    own = client.post(
        "/api/v1/conversations", json={"surface": "business"}, headers=as_person(BOB)
    )
    assert own.status_code == 200, own.text
    assert (
        api_state.store.conversation_spaces[own.json()["conversation"]["id"]] == space_b
    )
    dead = client.post(
        "/api/v1/conversations",
        json={"surface": "business"},
        headers={**as_person(BOB), GRANT: str(uuid4())},
    )
    assert (dead.status_code, dead.json()["code"]) == (403, "business_grant_not_live")


def test_a_grant_ends_when_its_issuer_loses_owner_access(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    from datetime import datetime, timezone

    grant = _grant(alice, bob)
    assert get_as(bob, "/receipts", grant).status_code == 200
    store = business_access()
    assert store is not None
    own = next(
        g
        for g in store._grants
        if g["grantee_id"] == alice.person and g["issuer_id"] == alice.person
    )
    own["revoked_at"] = datetime.now(timezone.utc)
    refused = get_as(bob, "/receipts", grant)
    assert (refused.status_code, refused.json()["code"]) == (
        403,
        "business_grant_not_live",
    )
    assert [s["role"] for s in _listed(bob)] == ["owner"]
    # Owner access restored: the grant Alice gave is live again, as given.
    assert store.ensure_owner_grant(alice.scope().owner.space_id, alice.person) is True
    assert get_as(bob, "/receipts", grant).status_code == 200
    assert [s["role"] for s in _listed(bob)] == ["owner", "accountant"]


def test_the_listing_never_reports_approve_for_a_grantee_and_nothing_is_in_scope_without_a_business(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    grant = _grant(alice, bob)
    store = business_access()
    assert store is not None
    # A row that carries approve for a grantee (hand-written) is reported without it.
    row = next(g for g in store._grants if g["id"] == grant)
    row["capabilities"] = ("read", "prepare", "approve")
    assert [s["capabilities"] for s in _listed(bob) if s["role"] == "accountant"] == [
        ["read", "prepare"]
    ]
    assert get_as(bob, f"/receipts/{uuid4()}", grant).status_code == 404
    # A person with no own Business and no chosen grant has nothing in scope, record ids included.
    uploaded = alice.upload(consent=False)
    receipt_id = uploaded.json()["id"]
    assert bob.get(f"/receipts/{receipt_id}").status_code == 404
    assert get_as(bob, f"/receipts/{receipt_id}", grant).status_code == 200


def test_the_chat_routes_and_the_email_retry_refuse_a_chosen_grant(
    chat_client: TestClient,  # noqa: F811
) -> None:
    from argus.api.business_spaces import business_access, configure_business_access
    from argus.domain.business.access import InMemoryAccessStore

    from tests.test_conversation_surfaces import _as as as_person
    from tests.test_conversation_surfaces import _create, _start_space

    client = chat_client
    space_a = _start_space(ALICE)
    _start_space(BOB)
    previous = business_access()
    store = InMemoryAccessStore()
    configure_business_access(store)
    try:
        store.confirm(BOB, "bob@example.test")
        store.give(space_a, ALICE, "bob@example.test")
        [grant] = [s.grant_id for s in store.spaces_for(BOB) if s.role == "accountant"]
        own = _create(client, BOB, "Mi chat", surface="business")
        personal = _create(client, BOB, "Mi chat personal")
        with_grant = {**as_person(BOB), GRANT: grant}
        # Bob's own Personal chat is his whatever Business is chosen: the header changes nothing there.
        assert (
            client.get(
                f"/api/v1/conversations/{personal}/messages", headers=with_grant
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/conversations/{personal}/activity", headers=with_grant
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/v1/conversations/{personal}",
                json={"title": "Personal"},
                headers=with_grant,
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/api/v1/conversations/{personal}", headers=with_grant
            ).status_code
            == 200
        )
        # Every chat route that takes a conversation id refuses the chosen grant,
        # so nothing is read or sent in Bob's own Business under Alice's name.
        calls = (
            client.get(f"/api/v1/conversations/{own}/messages", headers=with_grant),
            client.get(f"/api/v1/conversations/{own}/activity", headers=with_grant),
            client.get(f"/api/v1/conversations/{own}/run-dossiers", headers=with_grant),
            client.patch(
                f"/api/v1/conversations/{own}", json={"title": "x"}, headers=with_grant
            ),
            client.delete(f"/api/v1/conversations/{own}", headers=with_grant),
            client.post(
                "/api/v1/chat/stream",
                json={"conversation_id": own, "message": "hola"},
                headers=with_grant,
            ),
            client.post(
                "/api/v1/backtests/run",
                json={"conversation_id": own, "symbols": ["SPY"]},
                headers=with_grant,
            ),
            client.post(
                f"/api/v1/conversations/{own}/messages/{uuid4()}/continue",
                headers=with_grant,
            ),
            client.post(
                f"/api/v1/conversations/{own}/messages/{uuid4()}/computation/refresh",
                headers=with_grant,
            ),
            client.post(
                f"/api/v1/conversations/{own}/tool-results/{uuid4()}/recompute",
                json={
                    "message_id": str(uuid4()),
                    "input_revision": 0,
                    "arguments": {"a": 1},
                },
                headers=with_grant,
            ),
            client.post(
                f"/api/v1/conversations/{own}/confirmations/{uuid4()}/peer-assets",
                json={"symbols": ["SPY"]},
                headers=with_grant,
            ),
            client.post(
                f"/api/v1/conversations/{own}/confirmations/{uuid4()}/direct-edit",
                json={"capital": "100"},
                headers=with_grant,
            ),
        )
        assert [(r.status_code, r.json().get("code")) for r in calls] == [
            (403, "business_permission_denied")
        ] * len(calls)
        # Without the header Bob's own chat is his.
        assert (
            client.get(
                f"/api/v1/conversations/{own}/messages", headers=as_person(BOB)
            ).status_code
            == 200
        )
    finally:
        configure_business_access(previous)


def test_a_grantee_cannot_rerun_an_email_delivery(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
    runtime,  # noqa: ANN001, F811
) -> None:
    grant = _grant(alice, bob)
    refused = bob.post(
        f"/email/deliveries/{uuid4()}/retry", key=str(uuid4()), **{GRANT: grant}
    )
    assert (refused.status_code, refused.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    # The owner reaches the route itself (a delivery that does not exist is simply not found).
    assert alice.post(
        f"/email/deliveries/{uuid4()}/retry", key=str(uuid4())
    ).status_code in (404, 409)

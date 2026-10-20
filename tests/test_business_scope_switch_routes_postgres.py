"""Two client Businesses and an own one, over HTTP, on the real app, Auth and
Postgres: every Business route binds to the chosen grant, a record of any other
Business is missing, approval never leaves the owner whatever a grant row says,
a dead grant (revoked, expired, or whose issuer lost owner access) stops every
route at once, and each grantee write leaves a ledger row naming the grant."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.business.test_business_api import RECEIPT
from tests.local_supabase_support import local_supabase_gateway
from tests.test_financial_accounts_api_postgres import ORIGIN

pytestmark = pytest.mark.skipif(
    not (shared.DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)
GRANT = "X-Business-Grant"
API = "/api/v1"
OTHER_RECEIPT = RECEIPT[:-8] + bytes(8)
THIRD_RECEIPT = RECEIPT[:-8] + b"\x01" * 8
PERIOD = {"from": "2026-10-01", "to": "2026-10-31"}
ENV = {
    "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
    "NEXT_PUBLIC_MOCK_AUTH": "false",
    "ARGUS_MOCK_AUTH": "false",
    "ARGUS_DEV_MEMORY_FALLBACK": "false",
    "ARGUS_FINANCIAL_ACCOUNTS_ENABLED": "true",
    "ARGUS_INGESTION_ENABLED": "true",
    "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "true",
    "ARGUS_BUSINESS_PILOT_ENABLED": "true",
    "ARGUS_BUSINESS_CHAT_ENABLED": "true",
}


@dataclass
class Person:
    id: str
    email: str
    headers: dict[str, str]
    space_id: str = ""


def _person(client: TestClient, gateway, label: str, created: list[str]) -> Person:  # noqa: ANN001
    email = f"scope-{label}-{secrets.token_hex(4)}@example.test"
    password = f"Pw-{secrets.token_urlsafe(18)}"
    user = gateway.client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    assert user.user is not None
    created.append(str(user.user.id))
    response = client.post(
        f"{API}/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": "local-captcha-proof",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    token = response.json()["session"]["access_token"]
    return Person(
        str(user.user.id), email, {"Authorization": f"Bearer {token}", **ORIGIN}
    )


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Alice owns A, Bob owns B, Carol owns C; Bob holds read and prepare on A and C."""

    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    created: list[str] = []
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            people = {
                label: _person(client, gateway, label, created)
                for label in ("alice", "bob", "carol", "dave")
            }
            for person in (people["alice"], people["bob"], people["carol"]):
                started = client.post(
                    f"{API}/business/space",
                    json={"name": f"Negocio de {person.email}"},
                    headers=person.headers,
                )
                assert started.status_code == 201, started.text
                person.space_id = started.json()["id"]
            world = SimpleNamespace(client=client, **people)
            world.grant_a = _grant(world, world.alice, world.bob)
            world.grant_c = _grant(world, world.carol, world.bob)
            # Dave has no Business of his own, only a grant on A.
            world.grant_d = _grant(world, world.alice, world.dave)
            yield world
    finally:
        with Connection.connect(shared.DSN) as db:
            for user_id in created:
                db.execute(
                    "delete from public.business_client_grants where grantee_id=%s or issuer_id=%s",
                    (user_id, user_id),
                )
        for user_id in created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _grant(world, owner: Person, grantee: Person) -> str:  # noqa: ANN001
    given = world.client.post(
        f"{API}/business/access", json={"email": grantee.email}, headers=owner.headers
    )
    assert given.status_code == 201, given.text
    listed = world.client.get(f"{API}/business/spaces", headers=grantee.headers)
    assert listed.status_code == 200, listed.text
    [found] = [s for s in listed.json()["spaces"] if s["space_id"] == owner.space_id]
    assert found["role"] == "accountant" and set(found["capabilities"]) == {
        "read",
        "prepare",
    }
    return found["grant_id"]


def _as(person: Person, grant: str | None = None) -> dict[str, str]:
    return {**person.headers, **({GRANT: grant} if grant else {})}


def _upload(world, person: Person, content: bytes, grant: str | None = None):  # noqa: ANN001, ANN201
    return world.client.post(
        f"{API}/business/receipts",
        content=content,
        headers={
            **_as(person, grant),
            "Content-Type": "image/png",
            "Idempotency-Key": str(uuid4()),
            "X-Document-Filename": "recibo.png",
        },
    )


def _note(world, person: Person, text: str, grant: str | None = None):  # noqa: ANN001, ANN201
    return world.client.post(
        f"{API}/business/captures",
        json={"text": text},
        headers={**_as(person, grant), "Idempotency-Key": str(uuid4())},
    )


def _code(response) -> tuple[int, str | None]:  # noqa: ANN001
    body = (
        response.json()
        if response.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    return response.status_code, body.get("code")


def _ledger(space_id: str) -> list[tuple[str, str | None]]:
    with Connection.connect(shared.DSN) as db:
        return [
            (row[0], row[1])
            for row in db.execute(
                "select command->>'action', actor->>'grant_id' from public.business_action_receipts"
                " where space_id=%s and turn_key is null order by created_at",
                (space_id,),
            ).fetchall()
        ]


def _paths(
    world, grant_space: str | None, receipt: str, draft: str
) -> list[tuple[str, str, dict]]:  # noqa: ANN001
    """Every read route the Business shell calls, with the ids of that Business."""

    del grant_space
    return [
        ("GET", "/business/receipts", {"view": "all"}),
        ("GET", "/business/receipts", {"view": "inbox"}),
        ("GET", f"/business/receipts/{receipt}", {}),
        ("GET", f"/business/receipts/{receipt}/source", {}),
        ("GET", "/business/expenses", PERIOD),
        ("GET", "/business/overview", PERIOD),
        ("GET", "/business/updates", {}),
        ("GET", "/business/search", {"q": "nota"}),
        ("GET", "/business/captures", {}),
        ("GET", f"/business/drafts/{draft}/dossier", {}),
        ("GET", "/business/exports", {"start": PERIOD["from"], "end": PERIOD["to"]}),
        ("GET", "/business/workspace", {}),
        ("GET", "/business/email", {}),
        ("GET", "/business/email/deliveries", {}),
    ]


def test_every_route_binds_to_the_chosen_grant_and_a_record_of_another_business_is_missing(
    web,
) -> None:  # noqa: ANN001
    client, alice, bob, carol = web.client, web.alice, web.bob, web.carol
    receipt_a = _upload(web, alice, RECEIPT).json()["id"]
    receipt_b = _upload(web, bob, OTHER_RECEIPT).json()["id"]
    receipt_c = _upload(web, carol, THIRD_RECEIPT).json()["id"]
    draft_a = _note(web, alice, "nota de A: pintura").json()["draft_id"]
    draft_b = _note(web, bob, "nota de B: gasolina").json()["draft_id"]
    draft_c = _note(web, carol, "nota de C: tornillos").json()["draft_id"]
    conversation_a = client.post(
        f"{API}/conversations", json={"surface": "business"}, headers=alice.headers
    )
    assert conversation_a.status_code == 200, conversation_a.text

    # Bob under Alice's grant: every read route answers with A, and nothing of B or C.
    for method, path, params in _paths(web, alice.space_id, receipt_a, draft_a):
        answer = client.request(
            method, f"{API}{path}", params=params, headers=_as(bob, web.grant_a)
        )
        owner_answer = client.request(
            method, f"{API}{path}", params=params, headers=alice.headers
        )
        assert answer.status_code == owner_answer.status_code, (path, answer.text)
        assert answer.status_code != 403, (path, answer.text)
    listed = client.get(
        f"{API}/business/receipts", params={"view": "all"}, headers=_as(bob, web.grant_a)
    ).json()
    ids = {item["id"] for item in listed["items"]}
    assert receipt_a in ids and receipt_b not in ids and receipt_c not in ids
    notes = client.get(f"{API}/business/captures", headers=_as(bob, web.grant_a)).json()
    assert {item["draft_id"] for item in notes["items"]} == {draft_a}
    dossier = client.get(
        f"{API}/business/drafts/{draft_a}/dossier", headers=_as(bob, web.grant_a)
    ).json()
    assert dossier["space_id"] == alice.space_id
    assert set(dossier["capabilities"]) == {"read", "prepare"}
    # The records of B (Bob's own) and C (another client) are missing under A's grant, by id.
    for grant, foreign_receipt, foreign_draft in (
        (web.grant_a, receipt_b, draft_b),
        (web.grant_a, receipt_c, draft_c),
        (web.grant_c, receipt_a, draft_a),
        (web.grant_c, receipt_b, draft_b),
        (None, receipt_a, draft_a),
        (None, receipt_c, draft_c),
    ):
        for path in (
            f"/business/receipts/{foreign_receipt}",
            f"/business/receipts/{foreign_receipt}/source",
            f"/business/drafts/{foreign_draft}/dossier",
        ):
            assert _code(client.get(f"{API}{path}", headers=_as(bob, grant))) == (
                404,
                "business_record_not_found",
            ), (grant, path)
        export = client.get(
            f"{API}/business/exports",
            params={
                "start": PERIOD["from"],
                "end": PERIOD["to"],
                "draft_id": foreign_draft,
            },
            headers=_as(bob, grant),
        )
        assert export.status_code == 404, (grant, export.text)
    # Under C's grant, C's records answer; Bob's own answer with no header.
    assert (
        client.get(
            f"{API}/business/receipts/{receipt_c}", headers=_as(bob, web.grant_c)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{API}/business/drafts/{draft_c}/dossier", headers=_as(bob, web.grant_c)
        ).json()["space_id"]
        == carol.space_id
    )
    assert (
        client.get(
            f"{API}/business/receipts/{receipt_b}", headers=bob.headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{API}/business/drafts/{draft_b}/dossier", headers=bob.headers
        ).json()["space_id"]
        == bob.space_id
    )

    # Writes under the grant land in A and leave ledger rows naming the grant.
    note = _note(web, bob, "nota del contador en A", web.grant_a)
    assert note.status_code == 200, note.text
    assert note.json()["space_id"] == alice.space_id
    uploaded = _upload(web, bob, THIRD_RECEIPT[:-1] + b"\x02", web.grant_a)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["id"] in {
        item["id"]
        for item in client.get(
            f"{API}/business/receipts", params={"view": "all"}, headers=alice.headers
        ).json()["items"]
    }
    rows = _ledger(alice.space_id)
    # Alice's own upload left a row under her owner grant; Bob's names his grant.
    uploads = [r for r in rows if r[0] == "receipt_upload"]
    assert ("receipt_upload", web.grant_a) in uploads
    assert len(uploads) == 2 and all(grant for _, grant in uploads)
    assert ("capture_note", web.grant_a) in rows
    assert _ledger(bob.space_id) == [
        r for r in _ledger(bob.space_id) if r[1] != web.grant_a
    ]

    # Approval never leaves the owner: the database refuses approve on a grantee's
    # row, and the code refuses it even if such a row existed.
    with Connection.connect(shared.DSN) as db:
        with pytest.raises(
            psycopg.errors.CheckViolation, match="business_grant_approve_owner_only"
        ):
            db.execute(
                "update public.business_client_grants set capabilities=ARRAY['read','prepare','approve'] where id=%s",
                (web.grant_a,),
            )
    version = client.get(
        f"{API}/business/drafts/{draft_a}/dossier", headers=_as(bob, web.grant_a)
    ).json()["version"]
    for path, body in (
        (
            f"/business/drafts/{draft_a}/approve",
            {"version": version, "action": "record_expense"},
        ),
        (f"/business/drafts/{draft_a}/remainder/settle", {"version": version}),
        (f"/business/receipts/{receipt_a}/confirm", {"version": 1}),
    ):
        refused = client.post(
            f"{API}{path}",
            json=body,
            headers={**_as(bob, web.grant_a), "Idempotency-Key": str(uuid4())},
        )
        assert _code(refused) == (403, "business_permission_denied"), (path, refused.text)
    assert set(
        client.get(
            f"{API}/business/drafts/{draft_a}/dossier", headers=_as(bob, web.grant_a)
        ).json()["capabilities"]
    ) == {"read", "prepare"}

    # The own-Business routes and the owner's channels refuse a chosen grant.
    assert _code(client.get(f"{API}/business/space", headers=_as(bob, web.grant_a))) == (
        403,
        "business_permission_denied",
    )
    assert _code(
        client.patch(
            f"{API}/business/space", json={"name": "Otro"}, headers=_as(bob, web.grant_a)
        )
    ) == (403, "business_permission_denied")
    assert _code(
        client.post(
            f"{API}/business/email",
            headers={**_as(bob, web.grant_a), "Idempotency-Key": str(uuid4())},
        )
    ) == (403, "business_permission_denied")
    assert _code(
        client.delete(f"{API}/business/email", headers=_as(bob, web.grant_a))
    ) == (403, "business_permission_denied")
    assert client.get(f"{API}/business/space", headers=bob.headers).status_code == 200

    # With no header and no own Business nothing is in scope, record ids included.
    dave = web.dave
    for path in (
        "/business/receipts",
        f"/business/receipts/{receipt_a}",
        f"/business/drafts/{draft_a}/dossier",
        "/business/captures",
        "/business/workspace",
    ):
        assert _code(client.get(f"{API}{path}", headers=dave.headers)) == (
            404,
            "business_space_missing",
        ), path
    assert (
        client.get(
            f"{API}/business/receipts/{receipt_a}", headers=_as(dave, web.grant_d)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{API}/business/drafts/{draft_a}/dossier", headers=_as(dave, web.grant_d)
        ).json()["space_id"]
        == alice.space_id
    )
    # The listing reports effective capabilities and the retry is the owner's.
    listed = client.get(f"{API}/business/spaces", headers=_as(bob)).json()["spaces"]
    assert all(
        "approve" not in s["capabilities"] for s in listed if s["role"] == "accountant"
    )
    assert _code(
        client.post(
            f"{API}/business/email/deliveries/{uuid4()}/retry",
            headers={**_as(bob, web.grant_a), "Idempotency-Key": str(uuid4())},
        )
    ) == (403, "business_permission_denied")
    assert (
        client.get(f"{API}/business/workspace", headers=_as(bob, web.grant_a)).json()[
            "chat_available"
        ]
        is False
    )
    # Business chat is the owner's: a stored conversation belongs to its space's
    # creator, so under a chosen grant the chat routes refuse, never Bob's own Business.
    for response in (
        client.post(
            f"{API}/conversations",
            json={"surface": "business"},
            headers=_as(bob, web.grant_a),
        ),
        client.get(
            f"{API}/conversations",
            params={"surface": "business"},
            headers=_as(bob, web.grant_a),
        ),
    ):
        assert _code(response) == (403, "business_permission_denied"), response.text
    chats = lambda headers: {  # noqa: E731
        item["id"]
        for item in client.get(
            f"{API}/conversations", params={"surface": "business"}, headers=headers
        ).json()["items"]
    }
    assert conversation_a.json()["conversation"]["id"] in chats(alice.headers)
    assert conversation_a.json()["conversation"]["id"] not in chats(bob.headers)
    own_chat = client.post(
        f"{API}/conversations", json={"surface": "business"}, headers=bob.headers
    ).json()["conversation"]["id"]
    for method, path in (
        ("GET", f"/conversations/{own_chat}/messages"),
        ("PATCH", f"/conversations/{own_chat}"),
        ("DELETE", f"/conversations/{own_chat}"),
    ):
        answer = client.request(
            method,
            f"{API}{path}",
            json={"title": "x"} if method == "PATCH" else None,
            headers=_as(bob, web.grant_a),
        )
        assert _code(answer) == (403, "business_permission_denied"), (path, answer.text)
    assert (
        client.get(
            f"{API}/conversations/{own_chat}/messages", headers=bob.headers
        ).status_code
        == 200
    )
    # Bob's Personal chat is his whatever Business is chosen.
    personal = client.post(f"{API}/conversations", json={}, headers=bob.headers).json()[
        "conversation"
    ]["id"]
    for method, path in (
        ("GET", f"/conversations/{personal}/messages"),
        ("GET", f"/conversations/{personal}/activity"),
        ("PATCH", f"/conversations/{personal}"),
        ("DELETE", f"/conversations/{personal}"),
    ):
        answer = client.request(
            method,
            f"{API}{path}",
            json={"title": "x"} if method == "PATCH" else None,
            headers=_as(bob, web.grant_a),
        )
        assert answer.status_code == 200, (path, answer.text)


def test_a_revoked_expired_or_issuer_lost_grant_stops_every_route_at_once(web) -> None:  # noqa: ANN001
    client, alice, bob, carol = web.client, web.alice, web.bob, web.carol
    receipt_a = _upload(web, alice, RECEIPT).json()["id"]
    draft_a = _note(web, alice, "nota de A").json()["draft_id"]
    receipt_c = _upload(web, carol, THIRD_RECEIPT).json()["id"]
    draft_c = _note(web, carol, "nota de C").json()["draft_id"]

    def everything_refused(grant: str, receipt: str, draft: str) -> None:
        for method, path, params in _paths(web, None, receipt, draft):
            assert _code(
                client.request(
                    method, f"{API}{path}", params=params, headers=_as(bob, grant)
                )
            ) == (403, "business_grant_not_live"), path
        for method, path, body in (
            ("POST", "/business/captures", {"text": "nota"}),
            ("PATCH", f"/business/drafts/{draft}/review", {"version": 1, "facts": {}}),
            ("POST", "/conversations", {"surface": "business"}),
        ):
            answer = client.request(
                method,
                f"{API}{path}",
                json=body,
                headers={**_as(bob, grant), "Idempotency-Key": str(uuid4())},
            )
            assert _code(answer) == (403, "business_grant_not_live"), (path, answer.text)
        assert _code(
            client.patch(
                f"{API}/business/receipts/{receipt}/review",
                json={"version": 1, "fields": {}},
                headers=_as(bob, grant),
            )
        ) == (403, "business_grant_not_live")

    # Revoked by the owner.
    assert (
        client.delete(
            f"{API}/business/access/grants/{web.grant_a}", headers=alice.headers
        ).status_code
        == 204
    )
    everything_refused(web.grant_a, receipt_a, draft_a)
    assert {
        s["space_id"]
        for s in client.get(f"{API}/business/spaces", headers=bob.headers).json()[
            "spaces"
        ]
    } == {bob.space_id, carol.space_id}
    # Expired.
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set created_at=%s, expires_at=%s where id=%s",
            (
                datetime.now(timezone.utc) - timedelta(days=15),
                datetime.now(timezone.utc) - timedelta(seconds=1),
                web.grant_c,
            ),
        )
    everything_refused(web.grant_c, receipt_c, draft_c)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set expires_at=null where id=%s",
            (web.grant_c,),
        )
    assert (
        client.get(
            f"{API}/business/receipts/{receipt_c}", headers=_as(bob, web.grant_c)
        ).status_code
        == 200
    )
    # The issuer lost owner access: Carol's own owner grant revoked ends the grant she gave.
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where space_id=%s and grantee_id=%s and issuer_id=%s",
            (carol.space_id, carol.id, carol.id),
        )
    everything_refused(web.grant_c, receipt_c, draft_c)
    assert {
        s["space_id"]
        for s in client.get(f"{API}/business/spaces", headers=bob.headers).json()[
            "spaces"
        ]
    } == {bob.space_id}
    # Owner access restored (the workspace read heals the owner grant once): the grant Carol gave is live again.
    assert (
        client.get(f"{API}/business/workspace", headers=carol.headers).status_code == 200
    )
    assert (
        client.get(
            f"{API}/business/receipts/{receipt_c}", headers=_as(bob, web.grant_c)
        ).status_code
        == 200
    )
    assert {
        s["space_id"]
        for s in client.get(f"{API}/business/spaces", headers=bob.headers).json()[
            "spaces"
        ]
    } == {bob.space_id, carol.space_id}

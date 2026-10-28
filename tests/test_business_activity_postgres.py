from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argus.domain.business.activity.queries import (
    decode_cursor,
    encode_cursor,
    read_activity,
)
from argus.domain.business.authority import ActionError, BusinessAuthority
from argus.domain.business.contracts.authority import TrustedActor
from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import owned_space

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")

EMAIL = "invitee@example.test"
SECRET = "raw-input-that-never-leaves-the-ledger"
TIED = (23, 24, 25)
TIE_AGE = 123
NOW = datetime.now(timezone.utc) - timedelta(hours=1)


@pytest.fixture
def people():
    with Connection.connect(shared.DSN) as db:
        ids = shared._create_users(
            db,
            ("owner", False),
            ("admin", False),
            ("editor", False),
            ("viewer", False),
            ("stranger", False),
        )
        try:
            yield ids
        finally:
            shared._delete_users(db, ids)


@pytest.fixture
def authority():
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        yield BusinessAuthority(pool)


@pytest.fixture
def business(people):
    with Connection.connect(shared.DSN) as db:
        space_id = owned_space(db, people["owner"])
        for role in ("admin", "editor", "viewer"):
            db.execute(
                "insert into public.business_client_grants"
                " (space_id, grantee_id, issuer_id, business_role)"
                " values (%s, %s, %s, %s)",
                (space_id, people[role], people["owner"], role),
            )
        db.commit()
    return space_id


def _actor(person: str, display_name: str) -> dict:
    return {
        "actor_id": person,
        "actor_kind": "member",
        "display_name": display_name,
        "grant_id": str(uuid4()),
        "issuer_id": person,
        "issuer_display_name": "Synthetic issuer",
    }


def receipt(
    db: Connection,
    space_id: str,
    person: str,
    command: dict,
    *,
    seconds_ago: int = 0,
    outcome: str | None = "applied",
    draft_id: str | None = None,
    display_name: str = "Synthetic member",
    planned: bool = False,
) -> None:
    key = f"act-{uuid4().hex[:12]}"
    actor = _actor(person, display_name)
    if planned:
        db.execute(
            "insert into public.business_turns"
            " (turn_key, space_id, sender_hash, actor_id, model_state, plan, plan_actor)"
            " values (%s, %s, %s, %s, 'completed', %s, %s)",
            (
                key,
                space_id,
                hashlib.sha256(key.encode()).hexdigest(),
                person,
                Jsonb({"schema_version": 1, "actions": [command]}),
                Jsonb(actor),
            ),
        )
    result = None
    if outcome is not None:
        result = {"outcome": outcome}
        if draft_id is not None:
            result["draft_id"] = draft_id
    db.execute(
        "insert into public.business_action_receipts"
        " (space_id, actor_id, actor, idempotency_key, input_hash, command, outcome,"
        " created_at, turn_key, action_index)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            space_id,
            person,
            Jsonb(actor),
            key,
            hashlib.sha256(key.encode()).hexdigest(),
            Jsonb(command),
            None if result is None else Jsonb(result),
            NOW - timedelta(seconds=seconds_ago),
            key if planned else None,
            0 if planned else None,
        ),
    )


def reader(authority: BusinessAuthority, person: str, space_id: str):
    return authority.resolve_actor(
        TrustedActor(actor_id=UUID(person), actor_kind="member", space_id=UUID(space_id))
    )


def _seen(authority, person, space_id, **page):
    return read_activity(authority, reader(authority, person, space_id), limit=25, **page)


def _drafts(page) -> set[str]:
    return {
        str(i.object.id)
        for i in page.items
        if i.object is not None and i.object.kind == "draft"
    }


def test_lists_only_applied_changes_newest_first(people, business, authority):
    first, second = str(uuid4()), str(uuid4())
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": str(uuid4())},
            seconds_ago=60,
            draft_id=first,
            display_name="Ana Editora",
        )
        receipt(
            db,
            business,
            people["owner"],
            {"action": "approve_expense", "draft_id": first},
            seconds_ago=50,
            outcome="replayed",
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "approve_expense", "draft_id": first},
            seconds_ago=40,
            outcome="permission_denied",
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": first},
            seconds_ago=30,
            outcome=None,
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "access_seen", "grant_id": str(uuid4())},
            seconds_ago=20,
        )
        receipt(
            db,
            business,
            people["owner"],
            {"action": "settle_remainder", "draft_id": second},
            seconds_ago=10,
            display_name="Dueño",
        )
        db.commit()

    page = _seen(authority, people["editor"], business)

    assert [
        (i.action, i.actor.display_name, i.object.kind, str(i.object.id))
        for i in page.items
    ] == [
        ("settle_remainder", "Dueño", "draft", second),
        ("review_draft", "Ana Editora", "draft", first),
    ]
    assert page.next_cursor is None
    assert len({i.id for i in page.items}) == 2
    assert all(len(i.id) == 32 for i in page.items)


def test_access_changes_list_only_for_a_reader_who_may_manage(
    people, business, authority
):
    grant, invite, draft = str(uuid4()), str(uuid4()), str(uuid4())
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["owner"],
            {"action": "invite_access", "invite_id": invite, "email": EMAIL},
            seconds_ago=30,
        )
        receipt(
            db,
            business,
            people["owner"],
            {
                "action": "change_role",
                "grant_id": grant,
                "business_role": "admin",
                "membership_version": 2,
            },
            seconds_ago=20,
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": draft},
            seconds_ago=10,
            draft_id=draft,
        )
        db.commit()

    with Connection.connect(shared.DSN) as db:
        owner_grant = str(
            db.execute(
                "select id from public.business_client_grants"
                " where space_id=%s and grantee_id=%s",
                (business, people["owner"]),
            ).fetchone()[0]
        )
    for manager in ("owner", "admin"):
        managed = [
            (i.action, None if i.object is None else (i.object.kind, str(i.object.id)))
            for i in _seen(authority, people[manager], business).items
        ]
        assert managed == [
            ("owner_grant", ("grant", owner_grant)),
            ("review_draft", ("draft", draft)),
            ("change_role", ("grant", grant)),
            ("invite_access", ("invite", invite)),
        ], manager
    for role in ("editor", "viewer"):
        assert [i.action for i in _seen(authority, people[role], business).items] == [
            "review_draft"
        ]

    text = _seen(authority, people["owner"], business).model_dump_json()
    assert EMAIL not in text
    assert "membership_version" not in text
    assert people["owner"] not in text


def test_a_reader_sees_one_business_even_through_a_foreign_cursor(
    people, business, authority
):
    with Connection.connect(shared.DSN) as db:
        other = owned_space(db, people["stranger"])
        ours = [str(uuid4()) for _ in range(2)]
        theirs = [str(uuid4()) for _ in range(2)]
        for index, draft in enumerate(ours):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft},
                seconds_ago=index,
                draft_id=draft,
            )
        for index, draft in enumerate(theirs):
            receipt(
                db,
                other,
                people["stranger"],
                {"action": "review_draft", "draft_id": draft},
                seconds_ago=index,
                draft_id=draft,
            )
        db.commit()

    assert _drafts(_seen(authority, people["viewer"], business)) == set(ours)
    foreign = _seen(authority, people["stranger"], other)
    assert _drafts(foreign) == set(theirs)

    through = _seen(
        authority,
        people["viewer"],
        business,
        before=decode_cursor(encode_cursor(foreign.items[-1])),
    )
    assert _drafts(through) <= set(ours)
    assert not {str(i.object.id) for i in through.items} & set(theirs)

    with pytest.raises(ActionError) as refused:
        reader(authority, people["owner"], other)
    assert refused.value.code == "business_record_not_found"


def test_pages_stay_put_when_newer_rows_land(people, business, authority):
    drafts = [str(uuid4()) for _ in range(30)]
    with Connection.connect(shared.DSN) as db:
        for index, draft in enumerate(drafts):
            age = TIE_AGE if index in TIED else 100 + index
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft},
                seconds_ago=age,
                draft_id=draft,
            )
        db.commit()

    first = _seen(authority, people["editor"], business)
    assert len(first.items) == 25
    assert first.next_cursor is not None
    assert [str(i.object.id) for i in first.items[:23]] == drafts[:23]

    newer = [str(uuid4()) for _ in range(5)]
    with Connection.connect(shared.DSN) as db:
        for index, draft in enumerate(newer):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft},
                seconds_ago=index,
                draft_id=draft,
            )
        db.commit()

    second = _seen(
        authority, people["editor"], business, before=decode_cursor(first.next_cursor)
    )
    assert len(second.items) == 5
    assert second.next_cursor is None
    tied = {drafts[index] for index in TIED}
    assert len(tied & _drafts(first)) == 2
    assert len(tied & _drafts(second)) == 1
    seen = [str(i.object.id) for i in first.items + second.items]
    assert sorted(seen) == sorted(drafts)
    assert not set(seen) & set(newer)
    assert [
        str(i.object.id) for i in _seen(authority, people["editor"], business).items[:5]
    ] == newer


def test_the_stored_name_shows_not_the_profile(people, business, authority):
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.profiles set display_name='Ana Después' where id=%s",
            (people["editor"],),
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "mark_personal", "draft_id": str(uuid4())},
            seconds_ago=2,
            display_name="Ana Antes",
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "mark_personal", "draft_id": str(uuid4())},
            seconds_ago=1,
            display_name="Exmiembro",
        )
        db.commit()

    assert [
        i.actor.display_name for i in _seen(authority, people["viewer"], business).items
    ] == [
        "Exmiembro",
        "Ana Antes",
    ]


def test_an_action_the_feed_does_not_know_lists_as_other_for_managers_only(
    people, business, authority
):
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["owner"],
            {"action": "business_future_action", "note": SECRET},
            planned=True,
        )
        db.commit()

    for role in ("editor", "viewer"):
        assert _seen(authority, people[role], business).items == (), role
    for manager in ("owner", "admin"):
        page = _seen(authority, people[manager], business)
        listed = [(i.action, i.object) for i in page.items]
        assert ("other", None) in listed, manager
        assert {action for action, _ in listed} == {"owner_grant", "other"}, manager
        text = page.model_dump_json()
        assert SECRET not in text
        assert "business_future_action" not in text


def test_the_owners_email_ai_consent_answer_lists_for_no_one(people, business, authority):
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["owner"],
            {"action": "email_ai_consent_declined"},
            seconds_ago=1,
        )
        db.commit()

    for role in ("editor", "viewer"):
        assert _seen(authority, people[role], business).items == (), role
    for manager in ("owner", "admin"):
        page = _seen(authority, people[manager], business)
        assert [i.action for i in page.items] == ["owner_grant"], manager
        assert "email_ai_consent" not in page.model_dump_json()


def test_over_http_a_page_shows_only_what_the_feed_promises(people, business, authority):
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, stored_drafts
    from argus.api.routers.business_activity import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    draft = str(uuid4())
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["owner"],
            {"action": "invite_access", "invite_id": str(uuid4()), "email": EMAIL},
            seconds_ago=2,
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": draft},
            seconds_ago=1,
            draft_id=draft,
        )
        db.commit()

    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-activity"
        return await call_next(request)

    app.include_router(router)
    service = SimpleNamespace(authority=authority, resolve_actor=authority.resolve_actor)

    def acting_as(person: str) -> None:
        app.dependency_overrides[stored_drafts] = lambda: DraftContext(
            service, UUID(person), business, None
        )
        app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
            person, None
        )

    with TestClient(app) as client:
        acting_as(people["owner"])
        response = client.get("/business/activity", params={"limit": 25})
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        page = response.json()
        assert set(page) == {"items", "next_cursor"}
        assert [i["action"] for i in page["items"]] == [
            "owner_grant",
            "review_draft",
            "invite_access",
        ]
        for item in page["items"]:
            assert set(item) == {"id", "occurred_at", "actor", "action", "object"}
            assert set(item["actor"]) == {"display_name", "kind"}
        for leak in (
            EMAIL,
            people["owner"],
            people["editor"],
            "input_hash",
            "command",
            "idempotency",
            "act-",
        ):
            assert leak not in response.text, leak

        acting_as(people["viewer"])
        assert [
            i["action"] for i in client.get("/business/activity").json()["items"]
        ] == ["review_draft"]
        assert client.get("/business/activity", params={"limit": 30}).status_code == 422
        refused = client.get("/business/activity", params={"cursor": "not-a-cursor"})
        assert refused.status_code == 422
        assert refused.json()["detail"]["code"] == "invalid_cursor"

        with Connection.connect(shared.DSN) as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where space_id=%s and grantee_id=%s",
                (business, people["viewer"]),
            )
            db.commit()
        gone = client.get("/business/activity")
        assert gone.status_code == 404
        assert gone.json()["detail"]["code"] == "business_record_not_found"


def test_a_leak_check_sees_a_real_page(people, business, authority):
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["owner"],
            {"action": "set_business_rnc", "rnc": "131234567"},
            seconds_ago=1,
        )
        db.commit()
    page = _seen(authority, people["viewer"], business)
    assert [i.action for i in page.items] == ["set_business_rnc"]
    assert "131234567" not in json.dumps(page.model_dump(mode="json"))

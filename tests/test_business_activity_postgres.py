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
from argus.domain.business.contracts.activity import ActivityFilters
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
NONE = ActivityFilters()
#: 23:59 and 00:00:30 of March 10, 2026 in America/Santo_Domingo (UTC-4).
LATE_MARCH_9 = datetime(2026, 3, 10, 3, 59, tzinfo=timezone.utc)
EARLY_MARCH_10 = datetime(2026, 3, 10, 4, 0, 30, tzinfo=timezone.utc)


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


def _actor(person: str, display_name: str, kind: str) -> dict:
    return {
        "actor_id": person,
        "actor_kind": kind,
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
    at: datetime | None = None,
    outcome: str | None = "applied",
    draft_id: str | None = None,
    display_name: str = "Synthetic member",
    kind: str = "member",
    planned: bool = False,
) -> None:
    key = f"act-{uuid4().hex[:12]}"
    actor = _actor(person, display_name, kind)
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
            at or NOW - timedelta(seconds=seconds_ago),
            key if planned else None,
            0 if planned else None,
        ),
    )


def transfer(
    db: Connection,
    space_id: str,
    owner: str,
    target: str,
    *,
    status: str = "accepted",
    seconds_ago: int = 0,
) -> None:
    created = NOW - timedelta(seconds=seconds_ago + 60)
    db.execute(
        "insert into public.business_ownership_transfers"
        " (space_id, owner_id, target_id, target_grant_id, idempotency_key,"
        " confirmation, status, created_at, resolved_at)"
        " values (%s, %s, %s, %s, %s, 'Colmado', %s, %s, %s)",
        (
            space_id,
            owner,
            target,
            str(uuid4()),
            f"transfer-{uuid4().hex[:8]}",
            status,
            created,
            None if status == "pending" else NOW - timedelta(seconds=seconds_ago),
        ),
    )


def reading_consent(
    db: Connection, space_id: str, owner: str, *, seconds_ago: int, revoked: bool = False
) -> None:
    at = NOW - timedelta(seconds=seconds_ago)
    db.execute(
        "insert into public.business_receipt_reading_consents"
        " (space_id, owner_id, scope_version, route, idempotency_key, request_hash,"
        " disclosure, consented_at, revoked_at)"
        " values (%s, %s, 1, '{}', %s, %s, 'Synthetic disclosure', %s, %s)",
        (
            space_id,
            owner,
            f"consent-{uuid4().hex[:8]}",
            hashlib.sha256(at.isoformat().encode()).hexdigest(),
            at,
            at + timedelta(seconds=1) if revoked else None,
        ),
    )


def draft(db: Connection, space_id: str, owner: str, counterparty: dict) -> str:
    draft_id = str(uuid4())
    db.execute(
        "insert into public.financial_import_events"
        " (id, user_id, owner_space_id, state, evidence, resolution,"
        " created_at, updated_at, version)"
        " values (%s, %s, %s, 'open', 'unclassified', %s, %s, %s, 1)",
        (
            draft_id,
            owner,
            space_id,
            Jsonb(
                {
                    "business": {
                        "schema_version": 1,
                        "facts": {"counterparty": counterparty},
                    }
                }
            ),
            NOW,
            NOW,
        ),
    )
    return draft_id


def name(db: Connection, person: str, display_name: str) -> None:
    db.execute(
        "update public.profiles set display_name=%s where id=%s", (display_name, person)
    )


def reader(authority: BusinessAuthority, person: str, space_id: str):
    return authority.resolve_actor(
        TrustedActor(actor_id=UUID(person), actor_kind="member", space_id=UUID(space_id))
    )


def _seen(authority, person, space_id, filters=NONE, **page):
    return read_activity(
        authority, reader(authority, person, space_id), limit=25, filters=filters, **page
    )


def _actions(page) -> list[str]:
    return [i.action for i in page.items]


def _drafts(page) -> set[str]:
    return {
        str(i.object.id)
        for i in page.items
        if i.object is not None and i.object.kind == "draft"
    }


def _facet(page) -> list[tuple[str, str, str | None]]:
    assert page.actors is not None
    return sorted((a.display_name, a.kind, a.membership) for a in page.actors)


def _actor_id(page, display_name: str) -> str:
    return next(a.id for a in page.actors if a.display_name == display_name)


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
            {
                "action": "mark_personal",
                "draft_id": second,
                "request": {"version": 2, "personal": True},
            },
            seconds_ago=10,
            display_name="Dueño",
        )
        db.commit()

    page = _seen(authority, people["editor"], business)

    assert [
        (i.action, i.actor.display_name, i.object.kind, str(i.object.id), i.area)
        for i in page.items
    ] == [
        ("mark_personal", "Dueño", "draft", second, "records"),
        ("review_draft", "Ana Editora", "draft", first, "records"),
    ]
    assert [(i.restricted, i.personal, i.include, i.role) for i in page.items] == [
        (False, True, None, None),
        (False, None, None, None),
    ]
    assert page.next_cursor is None
    assert len({i.id for i in page.items}) == 2
    assert all(len(i.id) == 32 for i in page.items)
    assert all(i.actor.membership == "current" for i in page.items)
    assert {i.actor.id for i in page.items} == {
        _actor_id(page, "Dueño"),
        _actor_id(page, "Ana Editora"),
    }
    assert _seen(authority, people["viewer"], business).items == page.items

    owner = _seen(authority, people["owner"], business)
    assert _actions(owner) == ["owner_grant", "mark_personal", "review_draft"]
    assert owner.items[0].restricted is True


def test_access_changes_list_only_for_a_reader_who_may_manage(
    people, business, authority
):
    grant, invite, draft_id = str(uuid4()), str(uuid4()), str(uuid4())
    with Connection.connect(shared.DSN) as db:
        name(db, people["admin"], "Carlos Méndez")
        admin_grant = str(
            db.execute(
                "select id from public.business_client_grants"
                " where space_id=%s and grantee_id=%s",
                (business, people["admin"]),
            ).fetchone()[0]
        )
        receipt(
            db,
            business,
            people["owner"],
            {
                "action": "invite_access",
                "invite_id": invite,
                "email": EMAIL,
                "business_role": "viewer",
            },
            seconds_ago=30,
        )
        receipt(
            db,
            business,
            people["owner"],
            {
                "action": "change_role",
                "grant_id": admin_grant,
                "business_role": "admin",
                "membership_version": 2,
            },
            seconds_ago=20,
        )
        receipt(
            db,
            business,
            people["owner"],
            {"action": "revoke_grant", "grant_id": grant},
            seconds_ago=15,
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": draft_id},
            seconds_ago=10,
            draft_id=draft_id,
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
        page = _seen(authority, people[manager], business)
        managed = [
            (
                i.action,
                None if i.object is None else (i.object.kind, str(i.object.id)),
                None if i.object is None else i.object.label,
                None if i.role is None else i.role.value,
                i.restricted,
            )
            for i in page.items
        ]
        assert managed == [
            (
                "owner_grant",
                ("grant", owner_grant),
                "fin-owner-" + people["owner"][:8],
                None,
                True,
            ),
            ("review_draft", ("draft", draft_id), None, None, False),
            ("revoke_grant", ("grant", grant), None, None, True),
            ("change_role", ("grant", admin_grant), "Carlos Méndez", "admin", True),
            ("invite_access", ("invite", invite), None, "viewer", True),
        ], manager
    for role in ("editor", "viewer"):
        assert _actions(_seen(authority, people[role], business)) == ["review_draft"]

    text = _seen(authority, people["owner"], business).model_dump_json()
    assert EMAIL not in text
    assert "membership_version" not in text
    for person in people.values():
        assert person not in text


def test_a_reader_sees_one_business_even_through_a_foreign_cursor(
    people, business, authority
):
    with Connection.connect(shared.DSN) as db:
        other = owned_space(db, people["stranger"])
        ours = [str(uuid4()) for _ in range(2)]
        theirs = [str(uuid4()) for _ in range(2)]
        for index, draft_id in enumerate(ours):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft_id},
                seconds_ago=index,
                draft_id=draft_id,
            )
        for index, draft_id in enumerate(theirs):
            receipt(
                db,
                other,
                people["stranger"],
                {"action": "review_draft", "draft_id": draft_id},
                seconds_ago=index,
                draft_id=draft_id,
            )
        db.commit()

    assert _drafts(_seen(authority, people["viewer"], business)) == set(ours)
    foreign = _seen(authority, people["stranger"], other)
    assert _drafts(foreign) == set(theirs)

    through = _seen(
        authority,
        people["viewer"],
        business,
        before=decode_cursor(encode_cursor(foreign.items[-1], NONE), NONE),
    )
    assert _drafts(through) <= set(ours)
    assert not {str(i.object.id) for i in through.items} & set(theirs)
    assert through.actors is None

    with pytest.raises(ActionError) as refused:
        reader(authority, people["owner"], other)
    assert refused.value.code == "business_record_not_found"


def test_pages_stay_put_when_newer_rows_land(people, business, authority):
    drafts = [str(uuid4()) for _ in range(30)]
    with Connection.connect(shared.DSN) as db:
        for index, draft_id in enumerate(drafts):
            age = TIE_AGE if index in TIED else 100 + index
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft_id},
                seconds_ago=age,
                draft_id=draft_id,
            )
        db.commit()

    first = _seen(authority, people["editor"], business)
    assert len(first.items) == 25
    assert first.next_cursor is not None
    assert [str(i.object.id) for i in first.items[:23]] == drafts[:23]

    newer = [str(uuid4()) for _ in range(5)]
    with Connection.connect(shared.DSN) as db:
        for index, draft_id in enumerate(newer):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft_id},
                seconds_ago=index,
                draft_id=draft_id,
            )
        db.commit()

    second = _seen(
        authority,
        people["editor"],
        business,
        before=decode_cursor(first.next_cursor, NONE),
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
        name(db, people["editor"], "Ana Después")
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

    page = _seen(authority, people["viewer"], business)
    assert [i.actor.display_name for i in page.items] == ["Exmiembro", "Ana Antes"]
    assert len({i.actor.id for i in page.items}) == 1
    assert _facet(page) == [("Exmiembro", "member", "current")]


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
        listed = [(i.action, i.object, i.area, i.restricted) for i in page.items]
        assert ("other", None, None, True) in listed, manager
        assert {action for action, *_ in listed} == {"owner_grant", "other"}, manager
        text = page.model_dump_json()
        assert SECRET not in text
        assert "business_future_action" not in text
        for filters in (
            ActivityFilters(areas=("business",)),
            ActivityFilters(groups=("access",)),
        ):
            assert _actions(_seen(authority, people[manager], business, filters)) == [
                "owner_grant"
            ], (manager, filters)


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
        assert _actions(page) == ["owner_grant"], manager
        assert "email_ai_consent" not in page.model_dump_json()


def test_over_http_a_page_shows_only_what_the_feed_promises(people, business, authority):
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, stored_drafts
    from argus.api.routers.business_activity import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    draft_id = str(uuid4())
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
            {"action": "review_draft", "draft_id": draft_id},
            seconds_ago=1,
            draft_id=draft_id,
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
        assert set(page) == {"items", "next_cursor", "actors"}
        assert [i["action"] for i in page["items"]] == [
            "owner_grant",
            "review_draft",
            "invite_access",
        ]
        for item in page["items"]:
            assert set(item) == {
                "id",
                "occurred_at",
                "actor",
                "action",
                "object",
                "area",
                "restricted",
                "role",
                "personal",
                "include",
            }
            assert set(item["actor"]) == {"display_name", "kind", "id", "membership"}
            assert item["object"] is None or set(item["object"]) == {
                "kind",
                "id",
                "label",
            }
        assert {a["display_name"] for a in page["actors"]} == {
            "Synthetic member",
            "fin-owner-" + people["owner"][:8],
        }
        assert set(page["actors"][0]) == {"id", "display_name", "kind", "membership"}
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
        viewed = client.get("/business/activity").json()
        assert [i["action"] for i in viewed["items"]] == ["review_draft"]
        assert [a["display_name"] for a in viewed["actors"]] == ["Synthetic member"]
        narrowed = client.get(
            "/business/activity",
            params={"area": ["business", "documents"], "action_group": "access"},
        )
        assert (narrowed.status_code, narrowed.json()["items"]) == (200, [])
        by_actor = client.get(
            "/business/activity", params={"actor": viewed["actors"][0]["id"]}
        )
        assert [i["action"] for i in by_actor.json()["items"]] == ["review_draft"]
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
    assert _actions(page) == ["set_business_rnc"]
    assert "131234567" not in json.dumps(page.model_dump(mode="json"))


def test_the_read_lets_postgres_push_the_page_bound_into_the_visible_rows(business):
    """A volatile call inside the visible rows makes Postgres materialize every
    row of the Business before the actor filter and the keyset bound apply;
    the grant check reads the transaction's time instead."""

    from argus.domain.business.activity import queries

    scope = {
        "space_id": business,
        "only": None,
        "hidden": [],
        "since": None,
        "until": None,
    }
    page = {**scope, "actors": None, "before_at": None, "before_id": None, "limit": 26}
    with Connection.connect(shared.DSN) as db:
        for query, params in ((queries._PAGE, page), (queries._FACETS, scope)):
            plan = "\n".join(r[0] for r in db.execute("explain " + query, params))
            assert "CTE Scan" not in plan, plan

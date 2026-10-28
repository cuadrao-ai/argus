"""The activity feed on real PostgreSQL: server-side filters, the cursor bound
to its filter set, the actors facet and the HTTP surface."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argus.domain.business.activity.queries import decode_cursor
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.activity import ActivityFilters
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_activity_postgres import (
    EARLY_MARCH_10,
    EMAIL,
    LATE_MARCH_9,
    _actions,
    _actor_id,
    _drafts,
    _facet,
    _seen,
    authority,  # noqa: F401 - fixture
    business,  # noqa: F401 - fixture
    people,  # noqa: F401 - fixture
    reader,
    receipt,
)

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


def test_each_filter_narrows_the_page_the_reader_may_see(people, business, authority):  # noqa: F811
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": str(uuid4())},
            at=LATE_MARCH_9,
            display_name="Ana Editora",
        )
        receipt(
            db,
            business,
            people["owner"],
            {"action": "approve_expense", "draft_id": str(uuid4())},
            at=EARLY_MARCH_10,
            display_name="Dueño",
        )
        receipt(
            db,
            business,
            people["owner"],
            {"action": "receipt_upload", "subjects": []},
            seconds_ago=30,
            display_name="Dueño",
        )
        receipt(
            db,
            business,
            people["owner"],
            {
                "action": "change_role",
                "grant_id": str(uuid4()),
                "business_role": "editor",
            },
            seconds_ago=20,
            display_name="Dueño",
        )
        receipt(
            db,
            business,
            people["admin"],
            {"action": "set_business_rnc", "rnc": "131234567"},
            seconds_ago=10,
            display_name="Carlos",
        )
        db.commit()

    everyone = {"viewer": people["viewer"], "editor": people["editor"]}
    managers = {"owner": people["owner"], "admin": people["admin"]}
    cases = [
        (ActivityFilters(areas=("documents",)), ["receipt_upload"], ["receipt_upload"]),
        (
            ActivityFilters(groups=("reviews", "approvals")),
            ["approve_expense", "review_draft"],
            ["approve_expense", "review_draft"],
        ),
        (
            ActivityFilters(areas=("business",)),
            ["set_business_rnc"],
            ["owner_grant", "set_business_rnc", "change_role"],
        ),
        (
            ActivityFilters(areas=("business",), groups=("access",)),
            [],
            ["owner_grant", "change_role"],
        ),
        (
            ActivityFilters(
                areas=("business", "records"), groups=("settings", "approvals")
            ),
            ["set_business_rnc", "approve_expense"],
            ["set_business_rnc", "approve_expense"],
        ),
        (ActivityFilters(areas=("invoicing",)), [], []),
        (
            ActivityFilters(since=date(2026, 3, 10), until=date(2026, 3, 10)),
            ["approve_expense"],
            ["approve_expense"],
        ),
        (ActivityFilters(until=date(2026, 3, 9)), ["review_draft"], ["review_draft"]),
        (
            ActivityFilters(since=date(2026, 3, 9), until=date(2026, 3, 10)),
            ["approve_expense", "review_draft"],
            ["approve_expense", "review_draft"],
        ),
        (
            ActivityFilters(since=date(2026, 3, 10), groups=("reviews",)),
            [],
            [],
        ),
    ]
    for filters, members_see, managers_see in cases:
        for person in everyone.values():
            assert (
                _actions(_seen(authority, person, business, filters)) == members_see
            ), filters
        for person in managers.values():
            assert (
                _actions(_seen(authority, person, business, filters)) == managers_see
            ), filters

    first = _seen(authority, people["viewer"], business)
    ana, dueno = _actor_id(first, "Ana Editora"), _actor_id(first, "Dueño")
    by_ana = _seen(authority, people["viewer"], business, ActivityFilters(actors=(ana,)))
    assert _actions(by_ana) == ["review_draft"]
    both = ActivityFilters(actors=(ana, dueno), groups=("reviews", "approvals", "access"))
    assert _actions(_seen(authority, people["viewer"], business, both)) == [
        "approve_expense",
        "review_draft",
    ]
    assert _actions(_seen(authority, people["owner"], business, both)) == [
        "owner_grant",
        "change_role",
        "approve_expense",
        "review_draft",
    ]
    unknown = ActivityFilters(actors=("0" * 32,))
    assert _seen(authority, people["owner"], business, unknown).items == ()


def test_a_cursor_continues_the_same_filtered_page(people, business, authority):  # noqa: F811
    records = [str(uuid4()) for _ in range(30)]
    with Connection.connect(shared.DSN) as db:
        for index, draft_id in enumerate(records):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft_id},
                seconds_ago=100 + index,
                draft_id=draft_id,
            )
        for index in range(5):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "receipt_upload", "subjects": []},
                seconds_ago=110 + index * 7,
            )
        db.commit()

    filters = ActivityFilters(areas=("records",))
    first = _seen(authority, people["viewer"], business, filters)
    assert len(first.items) == 25 and first.next_cursor is not None
    assert first.actors is not None
    second = _seen(
        authority,
        people["viewer"],
        business,
        filters,
        before=decode_cursor(first.next_cursor, filters),
    )
    assert len(second.items) == 5 and second.next_cursor is None
    assert second.actors is None
    assert sorted(_drafts(first) | _drafts(second)) == sorted(records)
    assert {i.action for i in first.items + second.items} == {"review_draft"}
    assert len(_seen(authority, people["viewer"], business).items) == 25


def test_facets_name_only_actors_with_a_row_the_reader_may_see(
    people,  # noqa: F811
    business,  # noqa: F811
    authority,  # noqa: F811
):
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            people["admin"],
            {
                "action": "change_role",
                "grant_id": str(uuid4()),
                "business_role": "viewer",
            },
            seconds_ago=40,
            display_name="Carlos Admin",
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": str(uuid4())},
            seconds_ago=30,
            display_name="Ana Editora",
        )
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": str(uuid4())},
            seconds_ago=20,
            display_name="Ana Editora",
            kind="extractor",
        )
        receipt(
            db,
            business,
            people["owner"],
            {"action": "settle_remainder", "draft_id": str(uuid4())},
            seconds_ago=10,
            display_name="Dueño",
        )
        db.execute(
            "update public.business_client_grants set revoked_at=now()"
            " where space_id=%s and grantee_id=%s",
            (business, people["editor"]),
        )
        db.commit()

    viewer = _seen(authority, people["viewer"], business)
    assert _facet(viewer) == [
        ("Ana Editora", "extractor", None),
        ("Ana Editora", "member", "former"),
        ("Dueño", "member", "current"),
    ]
    keys = {a.id for a in viewer.actors}
    assert len(keys) == 3
    assert [(i.action, i.actor.kind, i.actor.membership) for i in viewer.items] == [
        ("settle_remainder", "member", "current"),
        ("review_draft", "extractor", None),
        ("review_draft", "member", "former"),
    ]
    assert viewer.items[2].actor.id in keys
    assert viewer.items[1].actor.id != viewer.items[2].actor.id
    by_cuadrao = ActivityFilters(actors=(viewer.items[1].actor.id,))
    assert [
        (i.action, i.actor.kind)
        for i in _seen(authority, people["viewer"], business, by_cuadrao).items
    ] == [("review_draft", "extractor")]
    by_ana = ActivityFilters(actors=(viewer.items[2].actor.id,))
    assert [
        (i.action, i.actor.kind)
        for i in _seen(authority, people["viewer"], business, by_ana).items
    ] == [("review_draft", "member")]

    # The owner's newest visible row is the owner_grant, stored under the
    # profile label, so a manager's facet names the owner by that row.
    owner = _seen(authority, people["owner"], business)
    owner_name = "fin-owner-" + people["owner"][:8]
    assert _facet(owner) == [
        ("Ana Editora", "extractor", None),
        ("Ana Editora", "member", "former"),
        ("Carlos Admin", "member", "current"),
        (owner_name, "member", "current"),
    ]
    assert _actor_id(owner, owner_name) == _actor_id(viewer, "Dueño")
    for person in ("admin", "owner"):
        records = _seen(
            authority, people[person], business, ActivityFilters(areas=("records",))
        )
        assert [name for name, *_ in _facet(records)] == [
            "Ana Editora",
            "Ana Editora",
            "Dueño",
        ]
    with pytest.raises(ActionError):
        reader(authority, people["editor"], business)


def test_over_http_a_page_shows_only_what_the_feed_promises(people, business, authority):  # noqa: F811
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
            people["owner"].replace("-", ""),
            people["editor"].replace("-", ""),
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
        for params in ({"to": "9999-12-31"}, {"from": "0001-01-01"}):
            refused = client.get("/business/activity", params=params)
            assert refused.status_code == 422, params
            assert refused.json()["detail"]["code"] == "invalid_date_range"

        with Connection.connect(shared.DSN) as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where space_id=%s and grantee_id=%s",
                (business, people["viewer"]),
            )
            db.commit()
        gone = client.get("/business/activity")
        assert gone.status_code == 404
        assert gone.json()["detail"]["code"] == "business_record_not_found"

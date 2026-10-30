from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from argus.domain.business.activity.queries import decode_cursor
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.activity import ActivityFilters
from psycopg import Connection

from tests import test_business_activity_postgres as activity
from tests import test_financial_accounts_postgres as shared
from tests.test_business_activity_postgres import (
    EARLY_MARCH_10,
    LATE_MARCH_9,
    _actions,
    _actor_id,
    _drafts,
    _facet,
    _seen,
    draft,
    name,
    reader,
    reading_consent,
    receipt,
    transfer,
)
from tests.test_business_spaces_migration_postgres import owned_space

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")

people = activity.people
business = activity.business
authority = activity.authority


def test_each_filter_narrows_the_page_the_reader_may_see(people, business, authority):
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


def test_a_cursor_continues_the_same_filtered_page(people, business, authority):
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
    people, business, authority
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


def test_a_label_comes_only_from_a_record_the_reader_may_read(
    people, business, authority
):
    with Connection.connect(shared.DSN) as db:
        known = draft(
            db,
            business,
            people["owner"],
            {"state": "known", "value": "  Ferretería Popular ", "origin": "stated"},
        )
        unknown = draft(db, business, people["owner"], {"state": "unknown"})
        blank = draft(
            db,
            business,
            people["owner"],
            {"state": "known", "value": "   ", "origin": "stated"},
        )
        elsewhere = owned_space(db, people["stranger"])
        foreign = draft(
            db,
            elsewhere,
            people["stranger"],
            {"state": "known", "value": "Colmado Ajeno", "origin": "stated"},
        )
        for draft_id in (known, unknown, blank, foreign, str(uuid4())):
            receipt(
                db,
                business,
                people["owner"],
                {"action": "review_draft", "draft_id": draft_id},
                seconds_ago=1,
                draft_id=draft_id,
            )
        db.commit()

    for role in ("viewer", "owner"):
        page = _seen(authority, people[role], business)
        labels = {
            str(i.object.id): i.object.label
            for i in page.items
            if i.object is not None and i.object.kind == "draft"
        }
        assert labels == {
            known: "Ferretería Popular",
            unknown: None,
            blank: None,
            foreign: None,
        } | {k: None for k in labels if k not in (known, unknown, blank, foreign)}
        assert "Colmado Ajeno" not in page.model_dump_json()


def test_a_derived_event_lists_for_managers_with_the_persons_name(
    people, business, authority
):
    erased, unknown = str(uuid4()), str(uuid4())
    with Connection.connect(shared.DSN) as db:
        name(db, people["admin"], "Carlos Méndez")
        db.execute(
            "insert into auth.users (id, email) values (%s, %s)",
            (erased, f"erased-{erased[:8]}@example.test"),
        )
        db.execute(
            "insert into public.profiles (id, email, username) values (%s, %s, %s)",
            (erased, f"erased-{erased[:8]}@example.test", "exmiembro-" + erased[:8]),
        )
        db.execute(
            "insert into argus_private.account_placeholders (id) values (%s)", (erased,)
        )
        transfer(db, business, people["owner"], people["admin"], seconds_ago=50)
        transfer(db, business, people["owner"], people["editor"], status="pending")
        transfer(
            db,
            business,
            people["owner"],
            people["viewer"],
            status="cancelled",
            seconds_ago=45,
        )
        transfer(db, business, people["owner"], erased, seconds_ago=40)
        transfer(db, business, people["owner"], unknown, seconds_ago=35)
        reading_consent(db, business, people["owner"], seconds_ago=30, revoked=True)
        reading_consent(db, business, people["owner"], seconds_ago=20)
        receipt(
            db,
            business,
            people["editor"],
            {"action": "review_draft", "draft_id": str(uuid4())},
            seconds_ago=10,
            display_name="Ana Editora",
        )
        db.commit()
        try:
            for role in ("editor", "viewer"):
                page = _seen(authority, people[role], business)
                assert _actions(page) == ["review_draft"], role
                assert _facet(page) == [("Ana Editora", "member", "current")]
            for manager in ("owner", "admin"):
                page = _seen(authority, people[manager], business)
                listed = [
                    (
                        i.action,
                        None
                        if i.actor is None
                        else (i.actor.display_name, i.actor.membership),
                        i.area,
                        i.restricted,
                        None if i.object is None else i.object.kind,
                    )
                    for i in page.items
                ]
                owner_name = "fin-owner-" + people["owner"][:8]
                enabled = (
                    "receipt_reading_enabled",
                    (owner_name, "current"),
                    "business",
                    True,
                    None,
                )
                assert listed == [
                    ("owner_grant", (owner_name, "current"), "business", True, "grant"),
                    (
                        "review_draft",
                        ("Ana Editora", "current"),
                        "records",
                        False,
                        "draft",
                    ),
                    enabled,
                    enabled,
                    ("ownership_transferred", None, "business", True, None),
                    (
                        "ownership_transferred",
                        ("Exmiembro", None),
                        "business",
                        True,
                        None,
                    ),
                    (
                        "ownership_transferred",
                        ("Carlos Méndez", "current"),
                        "business",
                        True,
                        None,
                    ),
                ], manager
                assert _facet(page) == sorted(
                    [
                        ("Ana Editora", "member", "current"),
                        (owner_name, "member", "current"),
                        ("Exmiembro", "member", None),
                        ("Carlos Méndez", "member", "current"),
                    ]
                )
                assert _actions(
                    _seen(
                        authority,
                        people[manager],
                        business,
                        ActivityFilters(groups=("settings",)),
                    )
                ) == ["receipt_reading_enabled", "receipt_reading_enabled"]
                text = page.model_dump_json()
                for leak in (
                    erased,
                    unknown,
                    "exmiembro-",
                    "cuadrao.invalid",
                    *people.values(),
                ):
                    assert leak not in text, leak
        finally:
            db.execute(
                "delete from public.business_ownership_transfers where space_id=%s",
                (business,),
            )
            db.execute(
                "delete from argus_private.account_placeholders where id=%s", (erased,)
            )
            db.execute("delete from public.profiles where id=%s", (erased,))
            db.execute("delete from auth.users where id=%s", (erased,))
            db.commit()

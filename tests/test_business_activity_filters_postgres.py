from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

import pytest
from argus.domain.business.activity.queries import decode_cursor
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.departures import PostgresBusinessDepartures
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


def departure_alias(db: Connection, space_id: str, alias: str) -> str:
    """The alias the departure flow leaves in a Business once the member's
    account is gone; returns the deletion run it belongs to."""

    run = str(uuid4())
    db.execute(
        "insert into argus_private.account_deletion_runs (id, status) values (%s, 'done')",
        (run,),
    )
    db.execute(
        "insert into argus_private.business_departure_aliases"
        " (space_id, actor_id, deletion_run_id, identity_cleaned_at)"
        " values (%s, %s, %s, clock_timestamp())",
        (space_id, alias, run),
    )
    return run


def claimed_departure(db: Connection, person: str) -> tuple[str, str]:
    run, claim = str(uuid4()), str(uuid4())
    db.execute(
        "insert into argus_private.account_deletion_runs"
        " (id, subject_hash, user_id, analytics_distinct_id, status, claim_id,"
        " claimed_until)"
        " values (%s, %s, %s, 'synthetic', 'started', %s, now() + interval '15 minutes')",
        (run, hashlib.sha256(run.encode()).hexdigest(), person, claim),
    )
    return run, claim


def test_a_derived_event_lists_for_managers_with_the_persons_name(
    people, business, authority
):
    erased, unknown = str(uuid4()), str(uuid4())
    with Connection.connect(shared.DSN) as db:
        name(db, people["admin"], "Carlos Méndez")
        run = departure_alias(db, business, erased)
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
                "delete from argus_private.business_departure_aliases where actor_id=%s",
                (erased,),
            )
            db.execute(
                "delete from argus_private.account_deletion_runs where id=%s", (run,)
            )
            db.commit()


def test_a_member_who_left_keeps_the_departure_name_on_every_row(
    people, business, authority
):
    """The departure flow rewrites the person's ledger rows and the derived
    columns to one alias; the feed names that alias Exmiembro everywhere and
    lists it once in `actors`."""

    admin = people["admin"]
    with Connection.connect(shared.DSN) as db:
        receipt(
            db,
            business,
            admin,
            {"action": "review_draft", "draft_id": str(uuid4())},
            seconds_ago=60,
            display_name="Carlos Admin",
        )
        transfer(db, business, people["owner"], admin, seconds_ago=50)
        db.execute(
            "update public.business_client_grants set business_role='owner'"
            " where space_id=%s and grantee_id=%s",
            (business, admin),
        )
        reading_consent(db, business, admin, seconds_ago=40)
        db.execute(
            "update public.business_client_grants set business_role='admin'"
            " where space_id=%s and grantee_id=%s",
            (business, admin),
        )
        transfer(db, business, admin, people["owner"], seconds_ago=30)
        run, claim = claimed_departure(db, admin)
        db.commit()
    try:
        PostgresBusinessDepartures(authority.pool).detach(
            user_id=admin, run_id=run, claim_id=claim
        )
        with Connection.connect(shared.DSN) as db:
            alias = db.execute(
                "select actor_id::text from argus_private.business_departure_aliases"
                " where space_id=%s and departing_user_id=%s",
                (business, admin),
            ).fetchone()[0]
        owner_name = "fin-owner-" + people["owner"][:8]
        page = _seen(authority, people["owner"], business)
        assert [
            (
                i.action,
                None if i.actor is None else (i.actor.display_name, i.actor.membership),
            )
            for i in page.items
        ] == [
            ("owner_grant", (owner_name, "current")),
            ("ownership_transferred", (owner_name, "current")),
            ("receipt_reading_enabled", ("Exmiembro", None)),
            ("ownership_transferred", ("Exmiembro", None)),
            ("review_draft", ("Exmiembro", None)),
        ]
        assert _facet(page) == [
            ("Exmiembro", "member", None),
            (owner_name, "member", "current"),
        ]
        assert len({i.actor.id for i in page.items[2:]}) == 1
        member = _seen(authority, people["viewer"], business)
        assert [(i.action, i.actor.display_name) for i in member.items] == [
            ("review_draft", "Exmiembro")
        ]
        assert _facet(member) == [("Exmiembro", "member", None)]
        for text in (page.model_dump_json(), member.model_dump_json()):
            for leak in (alias, alias.replace("-", ""), admin, "Carlos Admin"):
                assert leak not in text, leak
    finally:
        with Connection.connect(shared.DSN) as db:
            db.execute(
                "delete from argus_private.business_departure_aliases"
                " where deletion_run_id=%s",
                (run,),
            )
            db.execute(
                "delete from argus_private.account_deletion_runs where id=%s", (run,)
            )
            db.commit()


def test_a_deleted_creator_keeps_the_departure_name(people, business, authority):
    """Account deletion of a Business creator rewrites the derived columns to
    the custody reservation's deleted actor; the feed names it Exmiembro."""

    gone = str(uuid4())
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into argus_private.business_custody_reservations"
            " (space_id, custodian_id, deleted_actor_id) values (%s, %s, %s)",
            (business, str(uuid4()), gone),
        )
        transfer(db, business, people["owner"], gone, seconds_ago=10)
        db.commit()
    try:
        page = _seen(authority, people["admin"], business)
        assert [
            None if i.actor is None else i.actor.display_name
            for i in page.items
            if i.action == "ownership_transferred"
        ] == ["Exmiembro"]
        assert ("Exmiembro", "member", None) in _facet(page)
        assert gone not in page.model_dump_json()
    finally:
        with Connection.connect(shared.DSN) as db:
            db.execute(
                "delete from public.business_ownership_transfers where space_id=%s",
                (business,),
            )
            db.execute(
                "delete from argus_private.business_custody_reservations"
                " where space_id=%s",
                (business,),
            )
            db.commit()


def test_a_facet_names_the_actor_by_their_newest_stored_name(people, business, authority):
    """A derived row stores no name, so the facet keeps the name the newest
    ledger row stored instead of falling back to the profile."""

    with Connection.connect(shared.DSN) as db:
        name(db, people["admin"], "Carlos Méndez")
        receipt(
            db,
            business,
            people["admin"],
            {"action": "review_draft", "draft_id": str(uuid4())},
            seconds_ago=20,
            display_name="Carlos Admin",
        )
        transfer(db, business, people["owner"], people["admin"], seconds_ago=10)
        db.commit()
    page = _seen(authority, people["owner"], business)
    assert [(i.action, i.actor.display_name) for i in page.items[1:]] == [
        ("ownership_transferred", "Carlos Méndez"),
        ("review_draft", "Carlos Admin"),
    ]
    assert ("Carlos Admin", "member", "current") in _facet(page)
    assert "Carlos Méndez" not in [a.display_name for a in page.actors]


def test_a_grant_label_names_only_a_grant_of_this_business(people, business, authority):
    """A ledger row may carry any grant id; the label joins only grants of
    the Business being read, so a foreign grant's person never leaks."""

    with Connection.connect(shared.DSN) as db:
        name(db, people["editor"], "Ana Editora")
        name(db, people["stranger"], "Vecino Ajeno")
        elsewhere = owned_space(db, people["stranger"])
        mine, foreign = (
            db.execute(
                "select id::text from public.business_client_grants"
                " where space_id=%s and grantee_id=%s",
                (space, person),
            ).fetchone()[0]
            for space, person in (
                (business, people["editor"]),
                (elsewhere, people["stranger"]),
            )
        )
        for grant_id in (mine, foreign):
            receipt(
                db,
                business,
                people["owner"],
                {
                    "action": "change_role",
                    "grant_id": grant_id,
                    "business_role": "editor",
                },
                seconds_ago=1,
                display_name="Dueño",
            )
        db.commit()
    page = _seen(authority, people["admin"], business)
    labels = {
        str(i.object.id): i.object.label
        for i in page.items
        if i.object is not None and i.object.kind == "grant" and i.action == "change_role"
    }
    assert labels == {mine: "Ana Editora", foreign: None}
    assert "Vecino Ajeno" not in page.model_dump_json()

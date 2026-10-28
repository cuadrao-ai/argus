"""The activity feed on real PostgreSQL: object labels from records the reader
may read, and the derived events (ownership transfers, reading consent) named
from the profile or, after a departure, as the erased member."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.custody_graph import PostgresBusinessCustodyGraph
from argus.domain.business.custody_objects import PostgresBusinessCustodyCopies
from argus.domain.business.transfer import PostgresBusinessTransfer
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_activity_postgres import (
    _actions,
    _actor_id,
    _facet,
    _seen,
    authority,  # noqa: F401 - fixture
    business,  # noqa: F401 - fixture
    draft,
    name,
    people,  # noqa: F401 - fixture
    reading_consent,
    receipt,
    transfer,
)
from tests.test_business_custody_graph_postgres import FakeAuth, FakeObjects, claim
from tests.test_business_spaces_migration_postgres import owned_space

pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


def test_a_label_comes_only_from_a_record_the_reader_may_read(
    people,  # noqa: F811
    business,  # noqa: F811
    authority,  # noqa: F811
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
        # A grant of another Business, named by a row of ours, has no label.
        foreign_grant = str(
            db.execute(
                "select id from public.business_client_grants"
                " where space_id=%s and grantee_id=%s",
                (elsewhere, people["stranger"]),
            ).fetchone()[0]
        )
        receipt(
            db,
            business,
            people["owner"],
            {
                "action": "change_role",
                "grant_id": foreign_grant,
                "business_role": "editor",
            },
            seconds_ago=2,
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
        text = page.model_dump_json()
        assert "Colmado Ajeno" not in text
        assert "fin-stranger-" not in text
    owner = _seen(authority, people["owner"], business)
    assert [i.object.label for i in owner.items if str(i.object.id) == foreign_grant] == [
        None
    ]


def test_a_derived_event_lists_for_managers_with_the_persons_name(
    people,  # noqa: F811
    business,  # noqa: F811
    authority,  # noqa: F811
):
    unknown = str(uuid4())
    with Connection.connect(shared.DSN) as db:
        name(db, people["admin"], "Carlos Méndez")
        receipt(
            db,
            business,
            people["admin"],
            {"action": "set_business_rnc", "rnc": "131234567"},
            seconds_ago=60,
            display_name="Carlos Admin",
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
                assert _actions(page) == ["review_draft", "set_business_rnc"], role
                assert _facet(page) == [
                    ("Ana Editora", "member", "current"),
                    ("Carlos Admin", "member", "current"),
                ]
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
                        ("Carlos Méndez", "current"),
                        "business",
                        True,
                        None,
                    ),
                    (
                        "set_business_rnc",
                        ("Carlos Admin", "current"),
                        "business",
                        False,
                        None,
                    ),
                ], manager
                # The facet names a person by their newest row that stored a
                # name, so the older ledger row wins over the profile.
                assert _facet(page) == sorted(
                    [
                        ("Ana Editora", "member", "current"),
                        (owner_name, "member", "current"),
                        ("Carlos Admin", "member", "current"),
                    ]
                )
                assert _actions(
                    _seen(
                        authority,
                        people[manager],
                        business,
                        ActivityFilters(groups=("settings",)),
                    )
                ) == [
                    "receipt_reading_enabled",
                    "receipt_reading_enabled",
                    "set_business_rnc",
                ]
                text = page.model_dump_json()
                for leak in (unknown, "cuadrao.invalid", *people.values()):
                    assert leak not in text, leak
        finally:
            db.execute(
                "delete from public.business_ownership_transfers where space_id=%s",
                (business,),
            )
            db.commit()


def test_a_departed_owners_rows_name_the_erased_member(
    people,  # noqa: F811
    business,  # noqa: F811
    authority,  # noqa: F811
):
    """The owner turns reading on and hands the Business to the editor, then
    deletes their account. Every row of theirs, ledger and derived, names
    Exmiembro, shares one actor id, and stays in the facet."""

    pool = authority.pool
    owner, editor = people["owner"], people["editor"]
    with Connection.connect(shared.DSN) as db:
        name(db, editor, "Ana Editora")
        db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s", (editor,)
        )
        editor_grant = str(
            db.execute(
                "select id from public.business_client_grants"
                " where space_id=%s and grantee_id=%s",
                (business, editor),
            ).fetchone()[0]
        )
        receipt(
            db,
            business,
            owner,
            {"action": "set_business_rnc", "rnc": "131234567"},
            seconds_ago=40,
            display_name="Dueño",
        )
        reading_consent(db, business, owner, seconds_ago=30)
        db.commit()
    transfers = PostgresBusinessTransfer(pool)
    pending = transfers.request(
        owner_id=owner,
        space_id=business,
        target_grant_id=editor_grant,
        confirmation="Colmado",
        idempotency_key="transfer",
    )
    transfers.accept(actor_id=editor, transfer_id=pending.id)
    reservation = PostgresBusinessCustodyCopies(pool, FakeObjects(), FakeAuth()).prepare(
        space_id=business, departing_user_id=owner
    )
    run, token = claim({"pool": pool, "old": owner})
    try:
        assert (
            PostgresBusinessCustodyGraph(pool)
            .detach(
                space_id=business,
                departing_user_id=owner,
                reservation=reservation,
                deletion_run_id=run,
                claim_id=token,
            )
            .moved
        )

        page = _seen(authority, editor, business)
        listed = [
            (
                i.action,
                None if i.actor is None else (i.actor.display_name, i.actor.membership),
            )
            for i in page.items
        ]
        assert listed == [
            ("ownership_transferred", ("Ana Editora", "current")),
            ("owner_grant", ("Exmiembro", None)),
            ("receipt_reading_enabled", ("Exmiembro", None)),
            ("set_business_rnc", ("Exmiembro", None)),
        ]
        assert _facet(page) == [
            ("Ana Editora", "member", "current"),
            ("Exmiembro", "member", None),
        ]
        former = ActivityFilters(actors=(_actor_id(page, "Exmiembro"),))
        assert _actions(_seen(authority, editor, business, former)) == [
            "owner_grant",
            "receipt_reading_enabled",
            "set_business_rnc",
        ]
        text = page.model_dump_json()
        for leak in (
            owner,
            owner.replace("-", ""),
            reservation.custodian_id,
            reservation.deleted_actor_id,
            reservation.deleted_actor_id.replace("-", ""),
            "exmiembro-",
            "cuadrao.invalid",
            "131234567",
        ):
            assert leak not in text, leak
    finally:
        with Connection.connect(shared.DSN) as db:
            for statement in (
                "delete from argus_private.business_custody_changes where space_id=%s",
                "delete from argus_private.business_custody_moves where space_id=%s",
                "delete from argus_private.business_custody_objects where space_id=%s",
                "delete from argus_private.business_custody_reservations where space_id=%s",
                "delete from public.spaces where id=%s",
            ):
                db.execute(statement, (business,))
            db.execute(
                "delete from argus_private.account_deletion_runs where user_id=%s",
                (owner,),
            )
            db.execute("delete from auth.users where id=%s", (reservation.custodian_id,))
            db.execute(
                "delete from argus_private.account_placeholders where id=%s",
                (reservation.custodian_id,),
            )
            db.commit()

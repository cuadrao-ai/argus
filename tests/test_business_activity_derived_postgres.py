"""The activity feed on real PostgreSQL: object labels from records the reader
may read, and the derived events (ownership transfers, reading consent) named
from the profile or, after a departure, as the erased member."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.contracts.activity import ActivityFilters
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_activity_postgres import (
    _actions,
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
    people,  # noqa: F811
    business,  # noqa: F811
    authority,  # noqa: F811
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

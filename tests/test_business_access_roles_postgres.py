"""Over HTTP, on the real app, Auth and Postgres: what a role reads and corrects.

A person who manages the Business (Dueño, Administrador) reads every email
delivery and the senders list. An Editor or a Lector reads only the mail sent
from their own account address, in the inbox, the list, the detail and search,
and is refused the senders list. Marking an accepted record Personal takes it
out of the Business totals, so it is a correction and needs approve."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.api.email_intake import configure_email_intake
from psycopg import Connection

from tests import test_business_approve_unpaid_postgres as approvals
from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as shared
from tests.business.test_business_api import RECEIPT
from tests.test_business_receipt_uploader_routes_postgres import _emailed, _role
from tests.test_business_scope_switch_routes_postgres import API, _as, _code

pytestmark = [scope.pytestmark, pytest.mark.usefixtures("typed_notes_on", "settlement_on")]
web = scope.web
world = approvals.world

MANAGES = {"admin": True, "editor": False, "viewer": False}
DENIED = (403, "business_permission_denied")
SUPPLIER = "proveedor@example.test"


def _read(world, person: scope.Person, grant: str | None, path: str, **params):  # noqa: ANN001, ANN202
    return world.client.get(f"{API}{path}", params=params, headers=_as(person, grant))


@pytest.fixture
def mail(web, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN201
    """A supplier's delivery that saved a receipt, and two that saved none: one
    more from the supplier and one Dave sent from his account address."""

    try:
        _emailed(web, monkeypatch, RECEIPT + b"\x27")
        with Connection.connect(shared.DSN) as db:
            [supplier] = db.execute(
                "select id::text from public.business_email_deliveries where space_id=%s",
                (web.alice.space_id,),
            ).fetchone()
            own, bare = (
                db.execute(
                    "insert into public.business_email_deliveries(provider,external_id,"
                    "recipients,route_id,space_id,principal_id,sender,subject,state,"
                    "inbox_group,received_at)"
                    " select provider,gen_random_uuid()::text,recipients,route_id,"
                    "space_id,principal_id,%s,subject,state,inbox_group,"
                    "received_at+interval '1 second'"
                    " from public.business_email_deliveries where id=%s"
                    " returning id::text",
                    (sender, supplier),
                ).fetchone()[0]
                for sender in (web.dave.email, SUPPLIER)
            )
        yield {"supplier": supplier, "own": own, "bare": bare}
    finally:
        configure_email_intake(None)


def _pending(web, person: scope.Person, grant: str | None) -> int:  # noqa: ANN001
    """The Bandeja number: the receipts and the emails that are rows of their own."""

    activity = _read(web, person, grant, "/business/receipt-activity")
    assert activity.status_code == 200, activity.text
    return activity.json()["pending_review_count"]


def _seen(web, person: scope.Person, grant: str | None) -> dict[str, set[str]]:  # noqa: ANN001
    """The delivery ids each read gives this person."""

    listed = _read(web, person, grant, "/business/email/deliveries")
    inbox = _read(web, person, grant, "/business/email/inbox")
    found = _read(web, person, grant, "/business/search", q="example.test", limit=20)
    for answer in (listed, inbox, found):
        assert answer.status_code == 200, answer.text
    return {
        "deliveries": {item["id"] for item in listed.json()["items"]},
        "inbox": {
            item["id"] for group in inbox.json()["groups"] for item in group["items"]
        },
        "search": {item["id"] for item in found.json()["email_deliveries"]},
    }


def test_the_owner_reads_every_delivery(web, mail) -> None:  # noqa: ANN001
    everything = set(mail.values())
    assert _seen(web, web.alice, None) == dict.fromkeys(
        ("deliveries", "inbox", "search"), everything
    )


@pytest.mark.parametrize(("role", "manages"), MANAGES.items())
def test_a_member_reads_every_delivery_only_when_they_manage(
    web,  # noqa: ANN001
    mail,  # noqa: ANN001
    role: str,
    manages: bool,
) -> None:
    _role(web, web.dave, role)
    expected = set(mail.values()) if manages else {mail["own"]}
    assert _seen(web, web.dave, web.grant_d) == dict.fromkeys(
        ("deliveries", "inbox", "search"), expected
    )
    own = _read(web, web.dave, web.grant_d, f"/business/email/deliveries/{mail['own']}")
    assert own.status_code == 200, own.text
    assert own.json()["sender"] == web.dave.email
    other = _read(
        web, web.dave, web.grant_d, f"/business/email/deliveries/{mail['supplier']}"
    )
    assert _code(other) == (
        (200, None) if manages else (404, "email_delivery_not_found")
    )
    # The Bandeja number counts the rows this person can open: the supplier's
    # email with no receipt is one the Editor and the Lector never see.
    uncounted = _pending(web, web.alice, None) - _pending(web, web.dave, web.grant_d)
    assert uncounted == (0 if manages else 1)


@pytest.fixture
def long_history(web, mail) -> dict[str, list[str]]:  # noqa: ANN001
    """More mail than any read's limit, newest first: every delivery of the
    Business, and the ones Dave sent. His and the supplier's alternate."""

    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.business_email_deliveries(provider,external_id,"
            "recipients,route_id,space_id,principal_id,sender,subject,state,"
            "inbox_group,received_at)"
            " select provider,gen_random_uuid()::text,recipients,route_id,space_id,"
            "principal_id,case when n%%2=0 then %s else %s end,subject,state,"
            "inbox_group,received_at+make_interval(secs=>2+n)"
            " from public.business_email_deliveries, generate_series(0,409) n"
            " where id=%s",
            (web.dave.email, SUPPLIER, mail["supplier"]),
        )
        rows = db.execute(
            "select id::text,sender from public.business_email_deliveries"
            " where space_id=%s order by received_at desc,id",
            (web.alice.space_id,),
        ).fetchall()
    return {
        "all": [row[0] for row in rows],
        "own": [row[0] for row in rows if row[1] == web.dave.email],
    }


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The id of every delivery row the store reads out of the database."""

    from argus.domain.ingestion.email_intake import store

    rows: list[str] = []
    read = store._delivery

    def counted(row):  # noqa: ANN001, ANN202
        rows.append(str(row["id"]))
        return read(row)

    monkeypatch.setattr(store, "_delivery", counted)
    return rows


@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_a_long_history_costs_a_non_manager_only_their_own_mail(
    web,  # noqa: ANN001
    long_history: dict[str, list[str]],
    loaded: list[str],
    role: str,
) -> None:
    _role(web, web.dave, role)
    own = long_history["own"]
    assert len(own) > 200

    listed = _read(web, web.dave, web.grant_d, "/business/email/deliveries")
    assert [item["id"] for item in listed.json()["items"]] == own[:50]
    assert loaded == own[:50]

    loaded.clear()
    inbox = _read(web, web.dave, web.grant_d, "/business/email/inbox")
    shown = [item["id"] for group in inbox.json()["groups"] for item in group["items"]]
    assert shown == own[:200]
    assert loaded == own[:200]

    loaded.clear()
    found = _read(web, web.dave, web.grant_d, "/business/search", q="example.test", limit=20)
    assert found.status_code == 200, found.text
    assert {item["id"] for item in found.json()["email_deliveries"]} <= set(own[:200])
    assert loaded == own[:200]

    loaded.clear()
    other = next(item for item in long_history["all"] if item not in own)
    detail = _read(web, web.dave, web.grant_d, f"/business/email/deliveries/{other}")
    assert _code(detail) == (404, "email_delivery_not_found")
    assert loaded == []

    _pending(web, web.dave, web.grant_d)
    assert set(loaded) == set(own)


def test_a_long_history_gives_a_manager_the_newest_of_everyone(
    web,  # noqa: ANN001
    long_history: dict[str, list[str]],
    loaded: list[str],
) -> None:
    listed = _read(web, web.alice, None, "/business/email/deliveries")
    assert [item["id"] for item in listed.json()["items"]] == long_history["all"][:50]
    assert loaded == long_history["all"][:50]


@pytest.mark.parametrize(("role", "manages"), MANAGES.items())
def test_only_a_manager_reads_the_senders_list(
    web,  # noqa: ANN001
    mail,  # noqa: ANN001
    role: str,
    manages: bool,
) -> None:
    _role(web, web.dave, role)
    owner = _read(web, web.alice, None, "/business/email/senders")
    assert owner.status_code == 200, owner.text
    assert SUPPLIER in {item["value"] for item in owner.json()["items"]}
    listed = _read(web, web.dave, web.grant_d, "/business/email/senders")
    assert _code(listed) == ((200, None) if manages else DENIED)
    found = _read(web, web.dave, web.grant_d, "/business/search", q="proveedor", limit=20)
    assert found.status_code == 200, found.text
    senders = {item["value"] for item in found.json()["email_senders"]}
    assert senders == ({SUPPLIER} if manages else set())


def _mark(world, headers: dict[str, str], draft: str, version: int, personal: bool):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/business/drafts/{draft}/personal",
        json={"version": version, "personal": personal},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


@pytest.mark.parametrize(
    ("role", "corrects"), [("admin", True), ("editor", False), ("viewer", False)]
)
def test_marking_an_accepted_record_personal_needs_approve(
    world,  # noqa: ANN001
    role: str,
    corrects: bool,
) -> None:
    approvals._fiscal_profile(world)
    draft, accepted = approvals._recorded(
        world, "expense", "B0100000091", category="02", payment_method="01"
    )
    _role(world, world.bob, role)
    member = _as(world.bob, world.grant)
    marked = _mark(world, member, draft, accepted["version"], True)
    if not corrects:
        assert _code(marked) == DENIED
        dossier = world.client.get(
            f"{API}/business/drafts/{draft}/dossier", headers=member
        )
        assert dossier.status_code == 200, dossier.text
        assert dossier.json()["personal"] is not True
        marked = _mark(world, world.alice.headers, draft, accepted["version"], True)
    assert marked.status_code == 200, marked.text
    assert marked.json()["personal"] is True


def test_an_editor_still_marks_an_open_draft_personal(world) -> None:  # noqa: ANN001
    draft, reviewed = approvals._reviewed(world, "expense", "B0100000092")
    _role(world, world.bob, "editor")
    marked = _mark(
        world, _as(world.bob, world.grant), draft, reviewed["version"], True
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["personal"] is True

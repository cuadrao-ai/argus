"""Over HTTP, on the real app, Auth and Postgres (#2331): every Bandeja row
says who brought it in as one ``sent_by`` with a stable id. A web upload and a
typed note name the member, read live by the people rule (#2219): by name to
everyone, else by email only to a viewer who manages the Business and to
themself. An email arrival names the address of its earliest delivery however
old that is, and a WhatsApp arrival names the person who sent the file."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api import whatsapp as whatsapp_api
from argus.api.documents import documents_service
from argus.api.email_intake import configure_email_intake
from faker import Faker
from psycopg import Connection

from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as shared
from tests.business.test_business_api import RECEIPT
from tests.business.test_business_email_api import WEBHOOK, signed
from tests.business_reading_support import ROUTE
from tests.ingestion import whatsapp_support as wa
from tests.ingestion.test_whatsapp_api import LINK_BODY
from tests.ingestion.whatsapp_cases import image
from tests.test_business_reading_setting_postgres import _email, _email_runtime, _reading
from tests.test_business_scope_switch_routes_postgres import API, _as, _note, _upload

fake = Faker()
pytestmark = scope.pytestmark
web = scope.web

#: Whether a teammate in this role manages the Business, so reads an unnamed
#: uploader's email.
MANAGES = {"admin": True, "editor": False, "viewer": False}


def _name(person: scope.Person, display_name: str | None) -> None:
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.profiles set display_name=%s where id=%s",
            (display_name, person.id),
        )


def _role(world, person: scope.Person, role: str) -> None:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set business_role=%s"
            " where space_id=%s and grantee_id=%s and revoked_at is null",
            (role, world.alice.space_id, person.id),
        )


def _uploaded(world, person: scope.Person, grant: str | None) -> dict:  # noqa: ANN001
    answer = _upload(world, person, RECEIPT, grant)
    assert answer.status_code == 200, answer.text
    return answer.json()


def _listed(world, person: scope.Person, grant: str | None) -> tuple[dict, str]:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/receipts", params={"view": "all"}, headers=_as(person, grant)
    )
    assert answer.status_code == 200, answer.text
    return {item["id"]: item for item in answer.json()["items"]}, answer.text


def _who(person: dict | None) -> tuple | None:
    return person and (person["display_name"], person.get("email"), person["shown_as"])


def _member(person: scope.Person, shown: tuple) -> dict:
    return {"id": f"member:{person.id}", "kind": "member", "person": shown}


def _sent(item: dict) -> dict | None:
    """What an answer says of who sent the row, with nothing unset."""

    assert "uploaded_by" not in item
    sent = item["sent_by"]
    if sent is None:
        return None
    shown = {**sent, "person": _who(sent.get("person"))}
    return {key: value for key, value in shown.items() if value is not None}


def _viewers(world) -> list[tuple[scope.Person, str | None]]:  # noqa: ANN001
    return [(world.alice, None), (world.bob, world.grant_a), (world.dave, world.grant_d)]


def _notes(world, person: scope.Person, grant: str | None, view: str) -> tuple[dict, str]:  # noqa: ANN001
    answer = world.client.get(
        f"{API}/business/captures", params={"view": view}, headers=_as(person, grant)
    )
    assert answer.status_code == 200, answer.text
    return {item["draft_id"]: item for item in answer.json()["items"]}, answer.text


def _emailed(world, monkeypatch: pytest.MonkeyPatch, content: bytes) -> None:  # noqa: ANN001
    """One email from proveedor@example.test with ``content`` attached, read in."""

    with_documents = SimpleNamespace(alice=world.alice, documents=documents_service())
    runtime, route = _email_runtime(with_documents, monkeypatch, _email(content))
    body = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": str(uuid4()), "to": [route.recipient]},
        }
    ).encode()
    received = world.client.post(WEBHOOK, content=body, headers=signed(body))
    assert received.status_code == 202, received.text
    assert asyncio.run(runtime.next())


def test_a_named_uploader_reads_by_name_to_everyone(web) -> None:  # noqa: ANN001
    name = fake.name()
    _name(web.bob, name)
    uploaded = _uploaded(web, web.bob, web.grant_a)
    shown = _member(web.bob, (name, None, "name"))
    assert (uploaded["channel"], _sent(uploaded)) == ("web", shown)
    for person, grant in _viewers(web):
        items, _ = _listed(web, person, grant)
        assert _sent(items[uploaded["id"]]) == shown


@pytest.mark.parametrize("role", list(MANAGES))
def test_an_unnamed_uploader_reads_by_email_to_a_manager_or_themself(
    web,  # noqa: ANN001
    role: str,
) -> None:
    _name(web.bob, None)
    _role(web, web.dave, role)
    receipt = _uploaded(web, web.bob, web.grant_a)["id"]
    by_email = (None, web.bob.email, "email")
    expected = {
        web.alice.id: by_email,
        web.bob.id: by_email,
        web.dave.id: by_email if MANAGES[role] else (None, None, "member"),
    }
    for person, grant in _viewers(web):
        items, text = _listed(web, person, grant)
        shown = expected[person.id]
        assert _sent(items[receipt]) == _member(web.bob, shown), person
        if shown[1] is None:
            assert web.bob.email not in text


@pytest.mark.usefixtures("typed_notes_on")
@pytest.mark.parametrize("named", [True, False])
def test_a_typed_note_names_its_author_by_the_people_rule(web, named: bool) -> None:  # noqa: ANN001
    name = fake.name() if named else None
    _name(web.bob, name)
    _role(web, web.dave, "editor")
    saved = _note(web, web.bob, fake.sentence(), web.grant_a)
    assert saved.status_code == 200, saved.text
    draft = saved.json()["draft_id"]
    by_name = (name, None, "name")
    for view in ("inbox", "eliminados"):
        for person, grant in _viewers(web):
            sees_email = person is not web.dave
            shown = (
                by_name
                if named
                else (None, web.bob.email, "email")
                if sees_email
                else (None, None, "member")
            )
            items, text = _notes(web, person, grant, view)
            assert _sent(items[draft]) == _member(web.bob, shown), (view, person)
            if not named and not sees_email:
                assert web.bob.email not in text
        deleted = web.client.post(
            f"{API}/business/drafts/{draft}/delete",
            json={},
            headers={**_as(web.alice, None), "Idempotency-Key": str(uuid4())},
        )
        assert deleted.status_code == 200, deleted.text


def _post_phone_message(web, payload: dict) -> None:  # noqa: ANN001
    body = wa.encode(payload)
    answer = web.client.post(
        whatsapp_api.WEBHOOK_PATH,
        content=body,
        headers={"X-Hub-Signature-256": wa.sign(body)},
    )
    assert answer.status_code == 200, answer.text


@pytest.fixture
def phone(web, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN201
    """Send signed messages through the webhook using local media and test numbers."""
    for key, value in wa.ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CUADRAO_WHATSAPP_OUTBOUND_ENABLED", "false")
    monkeypatch.setenv("CUADRAO_WHATSAPP_SENDER_KEY", str(uuid4()))
    graph = wa.FakeGraph()
    client = graph.client()
    monkeypatch.setattr(
        whatsapp_api, "httpx", SimpleNamespace(AsyncClient=lambda: client)
    )
    monkeypatch.setattr(documents_service().business_receipt_consent, "route_resolver", lambda: ROUTE)
    monkeypatch.setattr("argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route", lambda: ROUTE)
    previous = whatsapp_api.whatsapp_runtime()
    whatsapp_api.start_whatsapp(scope.app)

    def send(number: str, content: bytes) -> None:
        _set_whatsapp_tax_id(web)
        assert _reading(web, True).status_code == 200
        issued = web.client.post(
            f"{API}/whatsapp/link-codes", json=LINK_BODY, headers=web.alice.headers
        )
        assert issued.status_code == 201, issued.text
        _post_phone_message(
            web, wa.fixture(
                "text_link_code.json",
                sender=number,
                id=str(uuid4()),
                text=issued.json()["message_text"],
            )
        )
        assert _reading(web, False).status_code == 200
        media_id = str(fake.random_number(digits=14, fix_len=True))
        graph.media[media_id] = wa.Media(content, "image/png")
        _post_phone_message(web, image(media_id, str(uuid4()), number))

    try:
        yield send
    finally:
        whatsapp_api.configure_whatsapp(previous)
        asyncio.run(client.aclose())


def _set_whatsapp_tax_id(world) -> None:
    path = f"{API}/business/fiscal-profile"
    profile = world.client.get(path, headers=world.alice.headers).json()
    if profile["tax_id"]:
        return
    saved = world.client.patch(
        path,
        json={"name": profile["name"], "previous_name": profile["name"],
              "tax_id": {"type": "rnc", "value": "131234567"}, "previous_tax_id": None},
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text


@pytest.mark.parametrize(
    "role,tax_id,reading,eligible",
    [("viewer", True, True, False), ("editor", True, True, True),
     ("editor", False, True, False), ("editor", True, False, False)],
    ids=["lector", "editor", "missing-rnc", "reading-off"],
)
def test_link_code_checks_persisted_membership_and_setup(
    web, phone, role, tax_id, reading, eligible,
) -> None:
    _role(web, web.dave, role)
    if tax_id:
        _set_whatsapp_tax_id(web)
    if reading:
        assert _reading(web, True).status_code == 200
    answer = web.client.post(f"{API}/whatsapp/link-codes", json=LINK_BODY, headers=web.dave.headers)
    if eligible:
        assert answer.status_code == 201, answer.text
        _post_phone_message(web, wa.fixture(
            "text_link_code.json", sender=wa.BOB_PHONE, id=str(uuid4()),
            text=answer.json()["message_text"],
        ))
        status = web.client.get(f"{API}/whatsapp/link", headers=web.dave.headers)
        assert status.json()["linked"] is True
        assert [item["space_id"] for item in status.json()["receiving_businesses"]] == [web.alice.space_id]
        with Connection.connect(shared.DSN) as db:
            receipt = db.execute(
                "select c.disclosure, c.grant_id::text, c.consenting_actor_id::text"
                " from public.business_whatsapp_ai_consents c"
                " join public.whatsapp_sender_links l on l.id=c.sender_link_id and l.wa_id_hash=c.sender_hash"
                " where l.destination_owner_id=%s and l.status='active' and c.revoked_at is null",
                (web.dave.id,),
            ).fetchall()
        assert receipt == [(LINK_BODY["disclosure"], web.grant_d, web.dave.id)]
    else:
        assert (answer.status_code, answer.json().get("code")) == (409, "whatsapp_setup_required")


def test_a_whatsapp_capture_names_the_web_uploader_for_every_member(web, phone) -> None:  # noqa: ANN001
    name = fake.name()
    _name(web.alice, name)
    _role(web, web.bob, "editor")
    _role(web, web.dave, "viewer")
    uploaded = _uploaded(web, web.alice, None)
    phone(wa.ALICE_PHONE, wa.RECEIPT_PNG + b"\x17")
    for person, grant in _viewers(web):
        items, _ = _listed(web, person, grant)
        [capture] = [row for row in items.values() if row["channel"] == "whatsapp"]
        assert wa.ALICE_PHONE not in json.dumps(capture)
        assert (
            _sent(capture)
            == _sent(items[uploaded["id"]])
            == _member(web.alice, (name, None, "name"))
        )
        detail = web.client.get(
            f"{API}/business/receipts/{capture['id']}", headers=_as(person, grant)
        )
        assert detail.status_code == 200, detail.text
        assert _sent(detail.json()) == _sent(capture)


def test_an_unnamed_whatsapp_sender_keeps_the_first_capturing_link(web, phone) -> None:  # noqa: ANN001
    _name(web.alice, None)
    phone(wa.ALICE_PHONE, wa.RECEIPT_PNG)
    phone(wa.BOB_PHONE, wa.RECEIPT_PNG)
    for person, grant in _viewers(web):
        items, _ = _listed(web, person, grant)
        [capture] = [row for row in items.values() if row["channel"] == "whatsapp"]
        assert _sent(capture) == {
            "id": f"member:{web.alice.id}",
            "kind": "whatsapp",
            "phone_last4": wa.ALICE_PHONE[-4:],
        }


def test_an_email_receipt_keeps_its_sender_past_the_latest_fifty_deliveries(
    web,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        _emailed(web, monkeypatch, RECEIPT + b"\x19")
        with Connection.connect(shared.DSN) as db:
            [first] = db.execute(
                "select id::text from public.business_email_deliveries where space_id=%s",
                (web.alice.space_id,),
            ).fetchone()
            db.execute(
                "insert into public.business_email_deliveries(provider,external_id,"
                "recipients,route_id,space_id,principal_id,sender,received_at)"
                " select provider,gen_random_uuid()::text,recipients,route_id,space_id,"
                "principal_id,%s,received_at+n*interval '1 second'"
                " from public.business_email_deliveries, generate_series(1,50) n"
                " where id=%s",
                (fake.email(domain="example.test"), first),
            )
        listed = web.client.get(
            f"{API}/business/email/deliveries", headers=_as(web.alice, None)
        )
        assert listed.status_code == 200, listed.text
        latest = listed.json()["items"]
        assert len(latest) == 50 and first not in {item["id"] for item in latest}
        assert {item["sent_by"]["id"] for item in latest} == {
            f"email:{latest[0]['sender']}"
        }

        items, _ = _listed(web, web.alice, None)
        emailed = [item for item in items.values() if item["channel"] == "email"]
        assert emailed
        for receipt in emailed:
            assert receipt["email_delivery_ids"] == [first]
            assert _sent(receipt)["id"] == "email:proveedor@example.test"
    finally:
        configure_email_intake(None)

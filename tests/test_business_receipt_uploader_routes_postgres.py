"""Over HTTP, on the real app, Auth and Postgres (#2331): every Bandeja row
says who brought it in as one ``sent_by`` with a stable id. A web upload and a
typed note name the member, read live by the people rule (#2219): by name to
everyone, else by email only to a viewer who manages the Business and to
themself. An email arrival names the address of its earliest delivery however
old that is, and a WhatsApp arrival names its linked number by its last four
digits."""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.documents import documents_service
from argus.api.email_intake import configure_email_intake
from faker import Faker
from psycopg import Connection

from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as shared
from tests.business.test_business_api import RECEIPT
from tests.business.test_business_email_api import WEBHOOK, signed
from tests.test_business_reading_setting_postgres import _email, _email_runtime
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

    with_documents = SimpleNamespace(**vars(world), documents=documents_service())
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


def test_a_whatsapp_or_email_arrival_names_its_sender(
    web,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    whatsapp = _uploaded(web, web.alice, None)["id"]
    captured = lambda person_id: frozenset({whatsapp})  # noqa: E731
    monkeypatch.setattr("argus.api.business._captured", captured)
    monkeypatch.setattr("argus.api.business_drafts._captured", captured)
    number = fake.msisdn()
    sender = sha256(number.encode()).digest()
    with Connection.connect(shared.DSN) as db:
        [link] = db.execute(
            "insert into public.whatsapp_sender_links(destination_owner_id,"
            "destination_space_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values(%s,%s,%s,%s,'es-419','active',clock_timestamp()) returning id::text",
            (web.alice.id, web.alice.space_id, sender, number[-4:]),
        ).fetchone()
        db.execute(
            "insert into public.whatsapp_inbound_messages(provider_message_key,"
            "sender_hash,destination_owner_id,status,connection_id,received_at,updated_at)"
            " values(%s,%s,%s,'captured',%s,clock_timestamp(),clock_timestamp())",
            (sha256(uuid4().bytes).digest(), sender, web.alice.id, whatsapp),
        )
    try:
        _emailed(web, monkeypatch, RECEIPT + b"\x17")
        for person, grant in _viewers(web):
            items, text = _listed(web, person, grant)
            arrivals = sorted(
                ((item["channel"], _sent(item)) for item in items.values()),
                key=lambda arrival: arrival[0],
            )
            by_email = {
                "id": "email:proveedor@example.test",
                "kind": "email",
                "address": "proveedor@example.test",
            }
            by_whatsapp = {
                "id": f"whatsapp:{link}",
                "kind": "whatsapp",
                "phone_last4": number[-4:],
            }
            assert arrivals == [
                ("email", by_email),
                ("email", by_email),
                ("whatsapp", by_whatsapp),
            ]
            assert number not in text
    finally:
        configure_email_intake(None)


def test_a_whatsapp_receipt_keeps_the_number_that_sent_it_first(
    web,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Number A links and is revoked, number B links and sends the receipt,
    then A links again and sends the same bytes: B sent it."""

    whatsapp = _uploaded(web, web.alice, None)["id"]
    monkeypatch.setattr("argus.api.business._captured", lambda person_id: frozenset({whatsapp}))
    first, second = fake.unique.msisdn(), fake.unique.msisdn()
    a, b = (sha256(number.encode()).digest() for number in (first, second))
    with Connection.connect(shared.DSN) as db:

        def link(sender: bytes, number: str, minutes_ago: int) -> str:
            [linked] = db.execute(
                "insert into public.whatsapp_sender_links(destination_owner_id,"
                "destination_space_id,wa_id_hash,last4,reply_language,status,linked_at)"
                " values(%s,%s,%s,%s,'es-419','active',now()-%s*interval '1 minute')"
                " returning id::text",
                (web.alice.id, web.alice.space_id, sender, number[-4:], minutes_ago),
            ).fetchone()
            return linked

        def revoke(linked: str) -> None:
            db.execute(
                "update public.whatsapp_sender_links set status='revoked',revoked_at=now()"
                " where id=%s",
                (linked,),
            )

        def sent(sender: bytes, minutes_ago: int) -> None:
            db.execute(
                "insert into public.whatsapp_inbound_messages(provider_message_key,"
                "sender_hash,destination_owner_id,status,connection_id,received_at,"
                "updated_at) values(%s,%s,%s,'captured',%s,now()-%s*interval '1 minute',now())",
                (sha256(uuid4().bytes).digest(), sender, web.alice.id, whatsapp, minutes_ago),
            )

        revoke(link(a, first, 50))
        by_b = link(b, second, 40)
        sent(b, 30)
        revoke(by_b)
        link(a, first, 20)
        sent(a, 10)

    items, _ = _listed(web, web.alice, None)
    assert _sent(items[whatsapp]) == {
        "id": f"whatsapp:{by_b}",
        "kind": "whatsapp",
        "phone_last4": second[-4:],
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

"""Over HTTP, on the real app, Auth and Postgres (#2264): a web upload names who
uploaded it, read live by the people rule (#2219). A named uploader reads by
name to everyone. An unnamed one reads by email to a viewer who manages the
Business and to themself, and as a member to anyone else, whose answer carries
no email for them. A WhatsApp or email arrival names no uploader."""

from __future__ import annotations

import asyncio
import json
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
from tests.test_business_scope_switch_routes_postgres import API, _as, _upload

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


def _viewers(world) -> list[tuple[scope.Person, str | None]]:  # noqa: ANN001
    return [(world.alice, None), (world.bob, world.grant_a), (world.dave, world.grant_d)]


def test_a_named_uploader_reads_by_name_to_everyone(web) -> None:  # noqa: ANN001
    name = fake.name()
    _name(web.bob, name)
    uploaded = _uploaded(web, web.bob, web.grant_a)
    shown = (name, None, "name")
    assert (uploaded["channel"], _who(uploaded["uploaded_by"])) == ("web", shown)
    for person, grant in _viewers(web):
        items, _ = _listed(web, person, grant)
        assert _who(items[uploaded["id"]]["uploaded_by"]) == shown


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
        assert _who(items[receipt]["uploaded_by"]) == expected[person.id], person
        if expected[person.id][1] is None:
            assert web.bob.email not in text


def test_a_whatsapp_or_email_arrival_names_no_uploader(
    web,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    whatsapp = _uploaded(web, web.alice, None)["id"]
    captured = lambda person_id: frozenset({whatsapp})  # noqa: E731
    monkeypatch.setattr("argus.api.business._captured", captured)
    monkeypatch.setattr("argus.api.business_drafts._captured", captured)
    world = SimpleNamespace(**vars(web), documents=documents_service())
    runtime, route = _email_runtime(world, monkeypatch, _email(RECEIPT + b"\x17"))
    try:
        body = json.dumps(
            {
                "type": "email.received",
                "data": {"email_id": str(uuid4()), "to": [route.recipient]},
            }
        ).encode()
        received = web.client.post(WEBHOOK, content=body, headers=signed(body))
        assert received.status_code == 202, received.text
        assert asyncio.run(runtime.next())

        items, _ = _listed(web, web.alice, None)
        arrivals = {(item["channel"], item["uploaded_by"]) for item in items.values()}
        assert arrivals == {("whatsapp", None), ("email", None)}
        assert len(items) == 3
    finally:
        configure_email_intake(None)

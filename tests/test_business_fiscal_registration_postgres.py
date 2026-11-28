"""The fiscal editor's PATCH against Auth and disposable Postgres."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from faker import Faker
from httpx import Response
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_scope_switch_routes_postgres import (
    API,
    Person,
    _as,
    pytestmark,
    web,
)

__all__ = ["pytestmark", "web"]

PROFILE = f"{API}/business/fiscal-profile"


def _save(world: SimpleNamespace, person: Person, kind: str, value: str) -> Response:
    profile = world.client.get(PROFILE, headers=person.headers).json()
    return world.client.patch(
        PROFILE,
        json={
            "previous_name": profile["name"],
            "name": "Nuevo nombre",
            "previous_tax_id": profile["tax_id"],
            "tax_id": {"type": kind, "value": value},
        },
        headers={**person.headers, "Idempotency-Key": str(uuid4())},
    )


@pytest.mark.parametrize("kind,length", [("rnc", 9), ("cedula", 11)])
@pytest.mark.parametrize("reachable", [False, True], ids=["private", "switch"])
def test_registered_number_only_returns_a_live_grant_of_the_person(
    web: SimpleNamespace, faker: Faker, kind: str, length: int, reachable: bool
) -> None:
    digits = str(faker.random_number(digits=length, fix_len=True))
    registered = _save(web, web.alice, kind, digits)
    assert registered.status_code == 200, registered.text
    formatted = f"{digits[:3]}-{digits[3:-1]}-{digits[-1]}"

    # Carol has no access. Bob holds his own grant on Alice's Business.
    person, grant = (web.bob, web.grant_a) if reachable else (web.carol, None)
    answer = _save(web, person, kind, formatted)
    assert answer.status_code == 409, answer.text
    body = answer.json()
    assert body["code"] == "business_rnc_registered"
    if grant:
        assert body["context"] == {"existing_grant_id": grant}
        switched = web.client.get(PROFILE, headers=_as(person, grant))
        assert switched.status_code == 200, switched.text
        assert switched.json()["tax_id"] == {"type": kind, "value": digits}
    else:
        assert "context" not in body
        assert web.grant_a not in answer.text
    for secret in (web.alice.id, web.alice.email, web.alice.space_id, "Nuevo nombre", digits):
        assert secret not in answer.text

    original = web.client.get(PROFILE, headers=person.headers)
    assert original.json()["tax_id"] is None
    assert original.json()["name"] == f"Negocio de {person.email}"


def test_sixth_registration_check_in_ten_minutes_is_limited(
    web: SimpleNamespace, faker: Faker, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1000.0
    monkeypatch.setattr("argus.api.rate_limits.monotonic", lambda: now)
    first = faker.random_int(min=100000000, max=999999990)
    for offset in range(5):
        saved = _save(web, web.carol, "rnc", str(first + offset))
        assert saved.status_code == 200, saved.text

    free = str(first + 5)
    blocked = _save(web, web.carol, "rnc", free)
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["code"] == "too_many_requests"
    assert "context" not in blocked.json()
    assert blocked.headers["retry-after"] == "600"
    assert _save(web, web.bob, "rnc", str(first + 6)).status_code == 200
    now += 599.5
    almost = _save(web, web.carol, "rnc", free)
    assert almost.status_code == 429
    assert almost.headers["retry-after"] == "1"
    now += 0.5
    assert _save(web, web.carol, "rnc", free).status_code == 200


def test_replaying_profile_save_does_not_check_registration_again(
    web: SimpleNamespace, faker: Faker
) -> None:
    number = str(faker.random_number(digits=9, fix_len=True))
    stored = _save(web, web.carol, "rnc", number)
    assert stored.status_code == 200
    for _ in range(6):
        replay = web.client.send(stored.request)
        assert replay.status_code == 200, replay.text
        assert replay.json() == stored.json()


@pytest.mark.parametrize("expired", [False, True], ids=["revoked", "expired"])
def test_dead_grant_never_leaves_the_refusal(
    web: SimpleNamespace, faker: Faker, expired: bool
) -> None:
    digits = str(faker.random_number(digits=9, fix_len=True))
    assert _save(web, web.alice, "rnc", digits).status_code == 200
    with Connection.connect(shared.DSN) as db:
        if expired:
            db.execute(
                "update public.business_client_grants set created_at=now()-interval '1 day',"
                " expires_at=now()-interval '1 second' where id=%s",
                (web.grant_a,),
            )
        else:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (web.grant_a,),
            )
    answer = _save(web, web.bob, "rnc", digits)
    assert answer.status_code == 409
    assert answer.json()["code"] == "business_rnc_registered"
    assert "context" not in answer.json()
    assert web.grant_a not in answer.text


def test_concurrent_registrations_have_one_winner(
    web: SimpleNamespace, faker: Faker
) -> None:
    digits = str(faker.random_number(digits=9, fix_len=True))
    together = Barrier(2)

    def save(person: Person) -> Response:
        together.wait(timeout=10)
        return _save(web, person, "rnc", digits)

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(save, (web.alice, web.carol)))
    success, refused = sorted(answers, key=lambda response: response.status_code)
    assert success.status_code == 200
    assert success.json()["tax_id"]["value"] == digits
    assert refused.status_code == 409
    assert refused.json()["code"] == "business_rnc_registered"
    assert "context" not in refused.json()


@pytest.mark.parametrize("kind,length", [("rnc", 9), ("cedula", 11)])
def test_reopen_refuses_reclaimed_number_and_preserves_closed_business(
    web: SimpleNamespace, faker: Faker, monkeypatch: pytest.MonkeyPatch, kind: str, length: int
) -> None:
    owner, holder = web.carol, web.alice
    number = str(faker.random_number(digits=length, fix_len=True))
    registered = _save(web, owner, kind, number)
    assert registered.status_code == 200, registered.text
    monkeypatch.delenv("CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD", raising=False)
    route = f"{API}/business/spaces/{owner.space_id}"
    closed = web.client.post(
        f"{route}/close",
        json={"confirmation": registered.json()["name"]},
        headers={**owner.headers, "Idempotency-Key": str(uuid4())},
    )
    assert closed.status_code == 200, closed.text
    reclaimed = _save(web, holder, kind, number)
    assert reclaimed.status_code == 200, reclaimed.text

    # Command failure is an HTTP response even if the server raises.
    monkeypatch.setattr(web.client._transport, "raise_server_exceptions", False)
    headers = {**owner.headers, "Idempotency-Key": str(uuid4())}
    refused = web.client.post(f"{route}/reopen", headers=headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "business_rnc_registered"
    assert "context" not in refused.json()
    for private in (holder.id, holder.email, holder.space_id, reclaimed.json()["name"], number):
        assert private not in refused.text
    waiting = web.client.get(f"{API}/business/closed-spaces", headers=owner.headers)
    assert waiting.json()["spaces"] == [closed.json()]

    # After the holder releases the number, even an owner with another open
    # Business can retry the same reopen command.
    additional = web.client.post(
        f"{API}/business/space", headers=owner.headers, json={"name": "Otro negocio"}
    )
    assert additional.status_code == 201, additional.text
    replacement = str((int(number[0]) % 9) + 1) + number[1:]
    assert _save(web, holder, kind, replacement).status_code == 200
    reopened = web.client.post(f"{route}/reopen", headers=headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["closed_at"] is None
    spaces = web.client.get(f"{API}/business/spaces", headers=owner.headers).json()["spaces"]
    assert {space["space_id"] for space in spaces} == {owner.space_id, additional.json()["id"]}

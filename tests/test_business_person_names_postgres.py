"""Who acted reads live through the dossier routes: the profile name, else the
email while the person still holds access to the Business, else nothing for
the screen to fill (#2219). The ledger keeps the id; no response carries a
stored label or the word "Member"."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.routers.business_drafts import router
from argus.domain.business.departures import PostgresBusinessDepartures
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_business_actions_postgres as shared
from tests import test_financial_accounts_postgres as accounts
from tests.test_business_activity_filters_postgres import claimed_departure

fake = Faker()
users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark


def _client(service, actor_id: str, space_id: UUID | None) -> TestClient:
    from argus.api.app_setup import add_core_middleware_and_handlers

    app = FastAPI()
    add_core_middleware_and_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, UUID(actor_id), None if space_id is None else str(space_id)
    )
    return TestClient(app)


def _name(person: str, display_name: str | None) -> None:
    with Connection.connect(accounts.DSN) as db:
        db.execute(
            "update public.profiles set display_name=%s where id=%s",
            (display_name, person),
        )


def _email(person: str) -> str:
    with Connection.connect(accounts.DSN) as db:
        return db.execute(
            "select email from auth.users where id=%s", (person,)
        ).fetchone()[0]


def _dossier(client: TestClient, draft) -> dict:
    response = client.get(f"/api/v1/business/drafts/{draft}/dossier")
    assert response.status_code == 200, response.text
    assert "Member" not in response.text
    return response.json()


def _approve(client: TestClient, draft) -> dict:
    version = _dossier(client, draft)["version"]
    response = client.post(
        f"/api/v1/business/drafts/{draft}/approve",
        json={"version": version, "action": "record_expense"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert "Member" not in response.text
    return response.json()


def _who(actor: dict) -> tuple:
    return (
        actor["display_name"],
        actor["email"],
        actor["issuer_display_name"],
        actor["issuer_email"],
    )


def _prepared_by(dossier: dict, person: str) -> list[dict]:
    found = [r["actor"] for r in dossier["history"] if r["actor"]["actor_id"] == person]
    assert found
    return found


@pytest.mark.parametrize("named", [True, False])
def test_an_approval_names_the_owner_by_name_else_by_email(actions, users, named):
    service, context, _ = actions
    owner = users["owner"]
    name = fake.name() if named else None
    _name(owner, name)
    draft = shared.ready(service, context)
    approved = _approve(_client(service, owner, context.actor.space_id), draft)
    email = None if named else _email(owner)
    actor = approved["approval_result"]["actor"]
    assert actor["actor_id"] == owner
    assert _who(actor) == (name, email, name, email)


def test_a_name_added_after_approval_shows_on_the_past_approval_and_history(
    actions, users
):
    service, context, _ = actions
    owner, accountant = users["owner"], users["other"]
    _name(owner, None)
    _name(accountant, None)
    draft = shared.ready(service, context)
    client = _client(service, owner, context.actor.space_id)
    _approve(client, draft)
    owner_name, accountant_name = fake.name(), fake.name()
    _name(owner, owner_name)
    _name(accountant, accountant_name)
    dossier = _dossier(client, draft)
    assert _who(dossier["approval_result"]["actor"]) == (
        owner_name,
        None,
        owner_name,
        None,
    )
    for actor in _prepared_by(dossier, accountant):
        assert _who(actor) == (accountant_name, None, owner_name, None)


def test_a_member_who_left_reads_without_their_email(actions, users):
    service, context, grant = actions
    owner, accountant = users["owner"], users["other"]
    _name(accountant, None)
    draft = shared.ready(service, context)
    client = _client(service, owner, context.actor.space_id)
    for actor in _prepared_by(_dossier(client, draft), accountant):
        assert (actor["display_name"], actor["email"]) == (None, _email(accountant))
    with Connection.connect(accounts.DSN) as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    response = client.get(f"/api/v1/business/drafts/{draft}/dossier")
    assert _email(accountant) not in response.text
    for actor in _prepared_by(response.json(), accountant):
        assert (actor["display_name"], actor["email"]) == (None, None)


def test_an_erased_account_reads_as_exmiembro(actions, users):
    service, context, _ = actions
    owner, accountant = users["owner"], users["other"]
    name = fake.name()
    _name(accountant, name)
    draft = shared.ready(service, context)
    with Connection.connect(accounts.DSN) as db:
        run, claim = claimed_departure(db, accountant)
        db.commit()
    try:
        PostgresBusinessDepartures(service.authority.pool).detach(
            user_id=accountant, run_id=run, claim_id=claim
        )
        response = _client(service, owner, context.actor.space_id).get(
            f"/api/v1/business/drafts/{draft}/dossier"
        )
        assert response.status_code == 200, response.text
        for leak in (name, accountant, _email(accountant)):
            assert leak not in response.text
        erased = [
            r["actor"]
            for r in response.json()["history"]
            if r["actor"]["actor_id"] != owner
        ]
        assert erased
        for actor in erased:
            assert (actor["display_name"], actor["email"]) == ("Exmiembro", None)
    finally:
        with Connection.connect(accounts.DSN) as db:
            db.execute(
                "delete from argus_private.business_departure_aliases"
                " where deletion_run_id=%s",
                (run,),
            )


def test_a_person_outside_the_business_never_reads_a_members_email(actions, users):
    service, context, _ = actions
    owner, accountant = users["owner"], users["other"]
    _name(owner, None)
    _name(accountant, None)
    draft = shared.ready(service, context)
    _approve(_client(service, owner, context.actor.space_id), draft)
    with Connection.connect(accounts.DSN) as db:
        stranger = accounts._create_users(db, ("stranger", False))
    try:
        for space in (context.actor.space_id, None):
            response = _client(service, stranger["stranger"], space).get(
                f"/api/v1/business/drafts/{draft}/dossier"
            )
            assert response.status_code == 404, response.text
            for leak in (_email(owner), _email(accountant)):
                assert leak not in response.text
    finally:
        with Connection.connect(accounts.DSN) as db:
            accounts._delete_users(db, stranger)

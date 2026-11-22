"""Who acted reads live through the real routes (#2219). A person with a name
reads by name to everyone. With no name, a viewer who manages the Business
(owner or admin) reads their email, and so does that person on their own
actions; any other viewer reads that they are a member, and the response
carries no email for them at all. Someone who left or was erased reads as a
former member. The server says which in ``shown_as``; the screen picks the
words, so no response carries "Member"."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argus.api.business import (
    BusinessPerson,
    require_business_person,
    require_business_surface,
)
from argus.api.business_drafts import DraftContext, require_drafts, stored_drafts
from argus.api.routers import business_activity, business_lifecycle, business_transfer
from argus.api.routers.business_drafts import router
from argus.domain.business.departures import PostgresBusinessDepartures
from argus.domain.business.lifecycle import PostgresBusinessLifecycle
from argus.domain.business.transfer import PostgresBusinessTransfer
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import Connection

from tests import test_business_actions_postgres as shared
from tests import test_business_activity_postgres as feed
from tests import test_business_lifecycle_postgres as lifecycle
from tests import test_business_transfer_mail_postgres as transfer_mail
from tests import test_financial_accounts_postgres as accounts
from tests.business.action_counts import count_no_rows
from tests.test_business_accountant_path_routes_postgres import _with_ncf
from tests.test_business_activity_filters_postgres import claimed_departure

fake = Faker()
users = shared.users
actions = shared.actions
people = feed.people
business = feed.business
authority = feed.authority
world = lifecycle.world
pytestmark = shared.pytestmark

#: Whether a viewer in this role manages the Business, so reads an unnamed
#: teammate's email.
MANAGES = {"owner": True, "admin": True, "editor": False, "viewer": False}
#: The viewers of an unnamed editor's work: each manager, a viewer, and the
#: editor themself, who reads their own email.
VIEWERS = ["owner", "admin", "viewer", "editor"]


def _sees_editor_email(viewer: str) -> bool:
    return MANAGES[viewer] or viewer == "editor"


def _client(service, actor_id: str, space_id: UUID | None) -> TestClient:
    from argus.api.app_setup import add_core_middleware_and_handlers

    app = FastAPI()
    add_core_middleware_and_handlers(app)
    app.include_router(router, prefix="/api/v1")
    count_no_rows(app)
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


def _shown(person: str, sees_email: bool) -> tuple:
    """An unnamed member as a viewer reads them: (name, email, shown_as)."""

    return (None, _email(person), "email") if sees_email else (None, None, "member")


def _dossier(client: TestClient, draft) -> dict:
    response = client.get(f"/api/v1/business/drafts/{draft}/dossier")
    assert response.status_code == 200, response.text
    assert "Member" not in response.text
    return response.json()


def _post(client: TestClient, path: str, body: dict) -> dict:
    response = client.post(
        f"/api/v1/business/drafts/{path}",
        json=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert "Member" not in response.text
    return response.json()


def _approve(client: TestClient, draft) -> dict:
    version = _dossier(client, draft)["version"]
    return _post(
        client, f"{draft}/approve", {"version": version, "action": "record_expense"}
    )


def _who(actor: dict) -> tuple:
    return tuple(
        actor[f"{prefix}{key}"]
        for prefix in ("", "issuer_")
        for key in ("display_name", "email", "shown_as")
    )


def _person(found: dict, prefix: str = "", name: str = "display_name") -> tuple:
    return tuple(found[f"{prefix}{key}"] for key in (name, "email", "shown_as"))


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
    shown = (name, None, "name") if named else (None, _email(owner), "email")
    actor = approved["approval_result"]["actor"]
    assert actor["actor_id"] == owner
    assert _who(actor) == shown + shown


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
    owner_shown = (owner_name, None, "name")
    assert _who(dossier["approval_result"]["actor"]) == owner_shown + owner_shown
    for actor in _prepared_by(dossier, accountant):
        assert _who(actor) == (accountant_name, None, "name") + owner_shown


def test_a_member_who_left_reads_as_a_former_member(actions, users):
    service, context, grant = actions
    owner, accountant = users["owner"], users["other"]
    _name(accountant, None)
    draft = shared.ready(service, context)
    client = _client(service, owner, context.actor.space_id)
    for actor in _prepared_by(_dossier(client, draft), accountant):
        assert _person(actor) == _shown(accountant, sees_email=True)
    with Connection.connect(accounts.DSN) as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    response = client.get(f"/api/v1/business/drafts/{draft}/dossier")
    assert _email(accountant) not in response.text
    for actor in _prepared_by(response.json(), accountant):
        assert _person(actor) == (None, None, "former")


def test_an_erased_account_reads_as_a_former_member(actions, users):
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
            assert _person(actor) == (None, None, "former")
    finally:
        with Connection.connect(accounts.DSN) as db:
            db.execute(
                "delete from argus_private.business_departure_aliases"
                " where deletion_run_id=%s",
                (run,),
            )
            db.execute(
                "delete from argus_private.account_deletion_runs where id=%s", (run,)
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


@pytest.fixture
def team(actions, users):
    """The actions Business with an admin and a viewer beside its owner and
    its editor ``other``; nobody has a name."""

    _, context, _ = actions
    with Connection.connect(accounts.DSN) as db:
        added = accounts._create_users(db, ("admin", False), ("viewer", False))
        for role, person in added.items():
            db.execute(
                "insert into public.business_client_grants"
                " (space_id, grantee_id, issuer_id, business_role)"
                " values (%s, %s, %s, %s)",
                (context.actor.space_id, person, users["owner"], role),
            )
        db.commit()
    everyone = {"owner": users["owner"], "editor": users["other"], **added}
    for person in everyone.values():
        _name(person, None)
    try:
        yield everyone
    finally:
        with Connection.connect(accounts.DSN) as db:
            accounts._delete_users(db, added)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_the_record_and_its_marks_show_an_unnamed_editors_email_to_a_manager_or_them(
    actions, team, viewer
):
    service, context, _ = actions
    editor = team["editor"]
    draft = shared.ready(service, context)
    _with_ncf(str(draft))
    acting = _client(service, editor, context.actor.space_id)
    marked = _post(
        acting,
        f"{draft}/personal",
        {"version": _dossier(acting, draft)["version"], "personal": True},
    )
    _post(
        acting,
        f"{draft}/fiscal-inclusion",
        {"version": marked["version"], "include": True},
    )

    response = _client(service, team[viewer], context.actor.space_id).get(
        f"/api/v1/business/drafts/{draft}/dossier"
    )
    assert response.status_code == 200, response.text
    record = response.json()
    shown = _shown(editor, _sees_editor_email(viewer))
    assert _person(record["personal_marked_by"]) == shown
    assert _person(record["include_606_by"]) == shown
    for actor in _prepared_by(record, editor):
        assert _person(actor) == shown
    if not MANAGES[viewer]:
        assert _email(team["owner"]) not in response.text
    if not _sees_editor_email(viewer):
        assert _email(editor) not in response.text


def _feed_client(authority, space_id: str, person: str) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-person-names"
        return await call_next(request)

    app.include_router(business_activity.router)
    service = SimpleNamespace(authority=authority, resolve_actor=authority.resolve_actor)
    app.dependency_overrides[stored_drafts] = lambda: DraftContext(
        service, UUID(person), space_id, None
    )
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        person, None
    )
    return TestClient(app)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_the_feed_shows_an_unnamed_editors_email_to_a_manager_or_them(
    people, business, authority, viewer
):
    editor = people["editor"]
    with Connection.connect(accounts.DSN) as db:
        feed.name(db, editor, None)
        for kind, seconds_ago in (("member", 2), ("extractor", 1)):
            feed.receipt(
                db,
                business,
                editor,
                {"action": "review_draft", "draft_id": str(uuid4())},
                seconds_ago=seconds_ago,
                kind=kind,
            )
        db.commit()

    response = _feed_client(authority, business, people[viewer]).get("/business/activity")
    assert response.status_code == 200, response.text
    page = response.json()
    actors = {
        item["actor"]["kind"]: item["actor"]
        for item in page["items"]
        if item["action"] == "review_draft"
    }
    shown = _shown(editor, _sees_editor_email(viewer))
    assert _person(actors["member"]) == shown
    facet = next(a for a in page["actors"] if a["id"] == actors["member"]["id"])
    assert _person(facet) == shown
    # The screen words automated work from the actor kind.
    assert _person(actors["extractor"]) == (None, None, None)
    assert "Cuadrao" not in response.text
    assert "Member" not in response.text
    if not _sees_editor_email(viewer):
        assert _email(editor) not in response.text


def _transfer_client(pool, person: str) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-person-names"
        return await call_next(request)

    for module in (business_transfer, business_lifecycle):
        app.include_router(module.router, prefix="/api/v1")
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        person, None
    )
    app.dependency_overrides[business_transfer.require_transfer] = (
        lambda: PostgresBusinessTransfer(pool)
    )
    app.dependency_overrides[business_lifecycle.require_lifecycle] = (
        lambda: PostgresBusinessLifecycle(pool)
    )
    return TestClient(app)


@pytest.mark.parametrize("viewer", ["owner", "other"])
def test_a_transfer_shows_an_unnamed_persons_email_to_a_manager_or_them(world, viewer):
    pool, _, team, _, _ = world
    owner, target = team["owner"], team["other"]
    for person in (owner, target):
        _name(person, None)
    transfer_mail.request(world)
    manages = viewer == "owner"

    client = _transfer_client(pool, team[viewer])
    response = client.get("/api/v1/business/ownership-transfers")
    assert response.status_code == 200, response.text
    assert "Member" not in response.text
    (found,) = response.json()["transfers"]
    assert _person(found, "owner_", "name") == _shown(owner, manages)
    # The target, an editor, reads their own email; the owner manages.
    assert _person(found, "target_", "name") == _shown(target, True)
    if not manages:
        assert _email(owner) not in response.text
        return
    owned = client.get("/api/v1/business/owned-spaces")
    assert owned.status_code == 200, owned.text
    (space,) = owned.json()["spaces"]
    (member,) = space["members"]
    assert (member["name"], member["email"], member["shown_as"]) == _shown(target, True)

"""What blocks an account deletion, asked before the person presses delete.

Synthetic people and Businesses on a disposable PostgreSQL. The pre-check, the
delete command and the HTTP routes must agree for every case.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg
import pytest
from argus.api.account_deletion_runtime import household_repository
from argus.api.main import app
from argus.api.routers import account as account_route
from argus.api.schemas import User
from argus.domain.account_deletion.service import (
    AccountDeletionRejected,
    AccountDeletionService,
    subject_hash,
)
from argus.domain.business.lifecycle import REOPEN_WINDOW
from argus.observability.analytics_deletion import RecordingAnalyticsDeletion
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.business_cleanup import delete_spaces

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")

client = TestClient(app)
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


CUSTODY_TABLES = (
    "business_custody_changes",
    "business_custody_objects",
    "business_custody_moves",
    "business_departure_aliases",
    "business_custody_reservations",
)


class Objects:
    """Stored originals: none are held, so only the calls matter."""

    bucket = "financial-document-sources"

    def get(self, path):  # noqa: ANN001, ANN201
        return None

    def put(self, path, content, media):  # noqa: ANN001, ANN201
        pass

    def delete(self, prefix):  # noqa: ANN001, ANN201
        pass


class SqlAuth:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_placeholder(self, *, user_id: str, email: str) -> None:
        with psycopg.connect(DSN) as db:
            db.execute(
                "insert into auth.users(id,email,is_anonymous,email_confirmed_at,"
                "banned_until,raw_app_meta_data) values(%s,%s,false,now(),"
                "now()+interval '100 years','{\"placeholder\":true}')",
                (user_id, email),
            )

    def lock_user(self, user_id: str) -> None:
        self.calls.append("lock_user")

    def user_exists(self, user_id: str) -> bool:
        with psycopg.connect(DSN) as db:
            return bool(
                db.execute("select 1 from auth.users where id=%s", (user_id,)).fetchone()
            )

    def delete_user(self, user_id: str) -> None:
        self.calls.append("delete_user")
        with psycopg.connect(DSN) as db:
            db.execute("delete from auth.users where id=%s", (user_id,))


class World:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool
        self.people: list[str] = []
        self.auth = SqlAuth()
        self.service = AccountDeletionService(
            households=household_repository(pool),
            auth_admin=self.auth,
            revoker=None,
            analytics=RecordingAnalyticsDeletion(),
            allow_fake_analytics=True,
            source_objects=Objects(),
        )
        self.spaces: list[str] = []

    def person(self, *, placeholder: bool = False) -> str:
        user_id = str(uuid4())
        meta = '{"placeholder": true}' if placeholder else "{}"
        with self.pool.connection() as db:
            db.execute(
                "insert into auth.users(id,email,is_anonymous,raw_app_meta_data)"
                " values(%s,%s,false,%s::jsonb)",
                (user_id, f"eligibility-{user_id}@example.test", meta),
            )
        self.people.append(user_id)
        return user_id

    def business(
        self, owner: str, name: str, *, closed: bool = False, owner_id: str | None = None
    ) -> str:
        space_id = str(uuid4())
        with self.pool.connection() as db:
            db.execute(
                "insert into public.spaces(id,kind,name,created_by,current_owner_id,"
                "closed_at,business_legacy_default) values(%s,'business',%s,%s,%s,"
                "case when %s then clock_timestamp() - interval '60 days' end,false)",
                (
                    space_id,
                    name,
                    owner,
                    owner_id if owner_id is not None else owner,
                    closed,
                ),
            )
        self.spaces.append(space_id)
        return space_id

    def owner_grant(self, space_id: str, grantee: str, issuer: str, *, revoked=False):
        with self.pool.connection() as db:
            db.execute(
                "insert into public.business_client_grants"
                "(space_id,grantee_id,issuer_id,business_role,capabilities,revoked_at)"
                " values(%s,%s,%s,'owner',array['read','prepare','approve'],"
                "case when %s then clock_timestamp() end)",
                (space_id, grantee, issuer, revoked),
            )

    def start_run(self, user_id: str) -> None:
        with self.pool.connection() as db:
            db.execute(
                "insert into argus_private.account_deletion_runs"
                " (subject_hash,user_id,analytics_distinct_id,status,steps)"
                " values(%s,%s,'synthetic','started','{}')",
                (subject_hash(user_id), user_id),
            )

    def snapshot(self) -> tuple:
        with self.pool.connection() as db:
            return (
                db.execute(
                    "select count(*) from argus_private.account_deletion_runs"
                ).fetchone()[0],
                db.execute("select count(*) from public.spaces").fetchone()[0],
                db.execute("select count(*) from auth.users").fetchone()[0],
            )

    def clean(self) -> None:
        with self.pool.connection() as db:
            custodians = [
                row[0]
                for row in db.execute(
                    "select distinct created_by::text from public.spaces"
                    " where id=any(%s::uuid[]) and not created_by=any(%s::uuid[])",
                    (self.spaces, self.people),
                )
            ]
            for table in CUSTODY_TABLES:
                db.execute(
                    f"delete from argus_private.{table} where space_id=any(%s::uuid[])",
                    (self.spaces,),
                )
            db.execute(
                "delete from argus_private.business_purge_runs"
                " where space_id=any(%s::uuid[])",
                (self.spaces,),
            )
            delete_spaces(db, "id=any(%s::uuid[])", (self.spaces,))
            db.execute(
                "delete from argus_private.account_deletion_runs"
                " where user_id=any(%s::uuid[])",
                (self.people,),
            )
            db.execute(
                "delete from auth.users where id=any(%s::uuid[])",
                (self.people + custodians,),
            )


@pytest.fixture
def world():
    with ConnectionPool(DSN, min_size=1, max_size=4) as pool:
        w = World(pool)
        try:
            yield w
        finally:
            w.clean()


def owner_of(space_id: str, name: str) -> dict:
    return {"kind": "business_owner", "business_id": space_id, "business_name": name}


def shape(blockers) -> list[dict]:
    return [{k: v for k, v in vars(b).items() if v is not None} for b in blockers]


def closed_notice(w: World, owner: str, name: str, *, days_ago: float) -> str:
    space = w.business(owner, name, closed=True)
    with w.pool.connection() as db:
        db.execute(
            "update public.spaces set closed_at = clock_timestamp() - %s * interval '1 day'"
            " where id=%s",
            (days_ago, space),
        )
    return space


def purge_at(w: World, space: str) -> datetime:
    with w.pool.connection() as db:
        closed_at = db.execute(
            "select closed_at from public.spaces where id=%s", (space,)
        ).fetchone()[0]
    return closed_at + REOPEN_WINDOW


def build_case(w: World, case: str) -> tuple[str, list[dict]]:
    """The person under test and what the pre-check must say about them."""
    person = w.person(placeholder=case in {"placeholder", "placeholder_owner"})
    other = w.person()
    if case in {"none", "placeholder"}:
        return person, [{"kind": "not_allowed"}] if case == "placeholder" else []
    if case == "one_open":
        return person, [owner_of(w.business(person, "Colmado Uno"), "Colmado Uno")]
    if case == "two_open":
        zeta = w.business(person, "Zeta")
        alfa = w.business(person, "Alfa")
        return person, [owner_of(alfa, "Alfa"), owner_of(zeta, "Zeta")]
    if case == "closed":
        w.business(person, "Cerrado", closed=True)
        return person, []
    if case == "owner_grant":
        space = w.business(other, "Ajeno")
        w.owner_grant(space, person, other)
        return person, [owner_of(space, "Ajeno")]
    if case == "revoked_owner_grant":
        space = w.business(other, "Ajeno")
        w.owner_grant(space, other, other)
        w.owner_grant(space, person, other, revoked=True)
        return person, []
    if case == "owner_grant_on_closed":
        space = w.business(other, "Ajeno cerrado", closed=True)
        w.owner_grant(space, person, other)
        return person, []
    if case == "placeholder_owner":
        space = w.business(person, "Fantasma")
        return person, [owner_of(space, "Fantasma")]
    raise AssertionError(case)


ALLOWED = ["none", "closed", "revoked_owner_grant", "owner_grant_on_closed"]
REFUSED = [
    "one_open",
    "two_open",
    "owner_grant",
    "placeholder",
    "placeholder_owner",
]


@pytest.mark.parametrize("case", ALLOWED + REFUSED)
def test_blockers_name_every_open_business_the_person_owns(world, case):
    person, expected = build_case(world, case)
    before = world.snapshot()
    result = world.service.deletion_eligibility(person)
    assert shape(result.blockers) == expected
    assert result.allowed is not expected
    assert world.snapshot() == before
    assert world.auth.calls == []


def test_a_closed_business_inside_its_window_is_a_notice_not_a_blocker(world):
    person = world.person()
    space = closed_notice(world, person, "Colmado Cerrado", days_ago=3)
    result = world.service.deletion_eligibility(person)
    assert result.blockers == [] and result.allowed
    assert [
        (n.kind, n.business_id, n.business_name, n.purge_at) for n in result.notices
    ] == [("closed_business", space, "Colmado Cerrado", purge_at(world, space))]
    assert world.service.delete_account(user_id=person).status == "done"


def test_a_closed_business_past_its_window_gives_nothing(world):
    person = world.person()
    closed_notice(world, person, "Colmado Viejo", days_ago=31)
    result = world.service.deletion_eligibility(person)
    assert (result.blockers, result.notices, result.allowed) == ([], [], True)


def test_notices_are_ordered_by_name_and_follow_live_owner_grants(world):
    person, other = world.person(), world.person()
    zeta = closed_notice(world, person, "Zeta", days_ago=1)
    alfa = closed_notice(world, other, "Alfa", days_ago=2)
    world.owner_grant(alfa, person, other)
    revoked = closed_notice(world, other, "Revocado", days_ago=2)
    world.owner_grant(revoked, person, other, revoked=True)
    open_space = world.business(person, "Abierto")
    result = world.service.deletion_eligibility(person)
    assert [n.business_name for n in result.notices] == ["Alfa", "Zeta"]
    assert [n.purge_at for n in result.notices] == [
        purge_at(world, alfa),
        purge_at(world, zeta),
    ]
    assert shape(result.blockers) == [owner_of(open_space, "Abierto")]
    assert not result.allowed


def test_a_run_in_flight_is_resumed_not_blocked(world):
    person = world.person()
    world.business(person, "Colmado Uno")
    world.start_run(person)
    assert world.service.deletion_eligibility(person).blockers == []


def test_a_person_the_database_no_longer_knows_blocks_nothing(world):
    result = world.service.deletion_eligibility(str(uuid4()))
    assert (result.blockers, result.notices, result.allowed) == ([], [], True)


@pytest.mark.parametrize("case", ALLOWED + REFUSED)
def test_the_command_agrees_with_the_pre_check(world, case):
    person, expected = build_case(world, case)
    if expected:
        reason = (
            "placeholder"
            if expected[0]["kind"] == "not_allowed"
            else "business_owner_must_exit"
        )
        with pytest.raises(AccountDeletionRejected, match=reason):
            world.service.delete_account(user_id=person)
        assert world.service.deletion_eligibility(person).blockers
    else:
        assert world.service.delete_account(user_id=person).status == "done"


def requester(person: str):
    def inner(request):  # noqa: ANN001, ANN202
        return User(id=person, email="p@example.test", created_at=NOW, updated_at=NOW)

    return inner


@pytest.fixture
def routes(monkeypatch, world):
    monkeypatch.setenv(account_route.FLAG, "true")
    account_route._per_account.reset()
    account_route._per_account_check.reset()
    yield
    account_route._per_account.reset()
    account_route._per_account_check.reset()


@pytest.mark.parametrize("case", ALLOWED + REFUSED)
def test_get_and_post_agree_over_http(world, routes, case):
    person, expected = build_case(world, case)
    with (
        patch.object(account_route, "deletion_requester", requester(person)),
        patch.object(
            account_route, "account_deletion_service", return_value=world.service
        ),
    ):
        before = world.snapshot()
        checked = client.get("/api/v1/account/deletion")
        assert world.snapshot() == before
        assert checked.status_code == 200
        assert checked.json() == {
            "allowed": not expected,
            "blockers": expected,
            "notices": [],
        }
        posted = client.post("/api/v1/account/delete", json={"confirm": True})
    if expected:
        assert posted.status_code == 403
        assert posted.json()["code"] == "account_deletion_not_allowed"
    else:
        assert posted.status_code == 200
        assert posted.json() == {"status": "done", "pending": []}


def test_the_database_failing_is_unavailable_not_allowed(routes):
    service = MagicMock()
    service.deletion_eligibility.side_effect = RuntimeError("database down")
    with (
        patch.object(account_route, "deletion_requester", requester(str(uuid4()))),
        patch.object(account_route, "account_deletion_service", return_value=service),
    ):
        response = client.get("/api/v1/account/deletion")
    assert response.status_code == 503
    assert response.json()["code"] == "account_deletion_unavailable"

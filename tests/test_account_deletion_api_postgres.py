"""Marcus #801 S1 / Priya 1 on real PostgreSQL: a person whose deletion run is
in flight is locked out of every route but POST /account/delete, and a retry
there resumes and finishes their own run. Nobody else gets in through that
door: a placeholder, a token naming someone else's session, a token with no
subject or no expiry (Marcus #801 re-check S1 and N1)."""

from __future__ import annotations

import hashlib
import time
import uuid
from unittest.mock import MagicMock, patch

import jwt
import psycopg
import pytest
from argus.api import dependencies
from argus.api import state as api_state
from argus.api.auth_sessions import auth_session_is_active
from argus.api.main import app
from argus.api.routers import account as account_route
from argus.api.schemas import User
from fastapi.testclient import TestClient

from tests.document_sources_support import LOCAL_STORAGE, source_objects, stored_paths
from tests.household.financial_fixtures import DSN, NOW
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
)
from tests.test_account_deletion_postgres import (  # noqa: F401 - fixtures
    BANNED,
    SqlAuthAdmin,
    _locked,
    _service,
    world,
)
from tests.test_account_deletion_third_parties_postgres import _StorageDown

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")

SECRET = "test-only-jwt-secret-0123456789abcdef"
URL = "/api/v1/account/delete"


def _token(sub: str | None, session: str | None, *, exp: bool = True) -> str:
    claims: dict = {"aud": "authenticated", "role": "authenticated"}
    if sub is not None:
        claims["sub"] = sub
    if session is not None:
        claims["session_id"] = session
    if exp:
        claims["exp"] = int(time.time()) + 600
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _session(user_id: str) -> str:
    session = str(uuid.uuid4())
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "insert into auth.sessions(id, user_id) values (%s, %s)", (session, user_id)
        )
    return session


@pytest.fixture
def route(world, monkeypatch):  # noqa: ANN001, ANN201, F811
    """The API wired to the disposable database, with GoTrue's /user stood in
    by a mock that refuses what GoTrue refuses: a banned account (the run and
    every placeholder are banned) or a token with no subject."""
    placeholders: set[str] = set()

    def gotrue_user(raw):  # noqa: ANN001, ANN202
        sub = jwt.decode(raw, options={"verify_signature": False}).get("sub")
        if not sub or sub in BANNED or sub in placeholders:
            raise RuntimeError("User is banned or token invalid")
        return {"id": sub, "email": f"{sub}@example.test"}

    gateway = MagicMock()
    gateway.get_auth_user_from_token.side_effect = gotrue_user
    gateway.get_or_create_profile_for_auth_user.side_effect = lambda user, **_: User(
        id=user["id"], email=user["email"], created_at=NOW, updated_at=NOW
    )
    monkeypatch.setenv(account_route.FLAG, "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.delenv("ARGUS_MOCK_AUTH", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    monkeypatch.setattr(api_state, "DATABASE_URL", DSN)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(dependencies, "permanent_account_access_allowed", lambda *_: True)
    account_route._per_account.reset()
    sessions: list[str] = []
    try:
        yield {
            "client": TestClient(app),
            "gateway": gateway,
            "placeholders": placeholders,
            "sessions": sessions,
        }
    finally:
        account_route._per_account.reset()
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("delete from auth.sessions where id = any(%s::uuid[])", (sessions,))


def _lock(lane, world, route):  # noqa: ANN001, ANN202, F811
    """A's first pass: the run opens, the account locks, the data moves, and
    the Admin API delete fails. Returns A's live session."""
    a = world["a"]
    session = _session(a)
    route["sessions"].append(session)
    admin = SqlAuthAdmin(crash_on_delete=1)
    try:
        with patch.object(
            account_route, "account_deletion_service", return_value=_service(lane, admin)
        ):
            first = route["client"].post(
                URL, json={"confirm": True}, headers=_bearer(_token(a, session))
            )
    finally:
        world["placeholders"] += admin.created
    assert first.status_code == 503, first.text
    assert first.json()["code"] == "account_deletion_incomplete"
    return session


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_locked_person_retries_and_the_run_finishes(lane, world, route):  # noqa: ANN001, F811
    a = world["a"]
    session = _lock(lane, world, route)
    token = _token(a, session)
    # Locked: every other route refuses this session now.
    assert not auth_session_is_active(database_url=DSN, token=token, user_id=a)
    admin = SqlAuthAdmin()
    try:
        with patch.object(
            account_route, "account_deletion_service", return_value=_service(lane, admin)
        ):
            second = route["client"].post(
                URL, json={"confirm": True}, headers=_bearer(token)
            )
    finally:
        world["placeholders"] += admin.created
    assert second.status_code == 200, second.text
    assert second.json() == {"status": "done", "pending": []}
    # The retry was verified locally, never through GoTrue's /user.
    assert route["gateway"].get_auth_user_from_token.call_count == 1
    with psycopg.connect(DSN) as c:
        assert not c.execute("select 1 from auth.users where id=%s", (a,)).fetchone()
        assert not c.execute(
            "select 1 from auth.sessions where id=%s", (session,)
        ).fetchone()


def _refused(route, token: str) -> None:  # noqa: ANN001
    with patch.object(
        account_route,
        "account_deletion_service",
        side_effect=AssertionError("the service must not be reached"),
    ):
        response = route["client"].post(
            URL, json={"confirm": True}, headers=_bearer(token)
        )
    assert response.status_code == 401, response.text


def _still_locked_then_finish(lane, world) -> None:  # noqa: ANN001, F811
    """Nothing moved for the refused token; the run then finishes as usual."""
    with psycopg.connect(DSN) as c:
        assert c.execute(
            "select status from argus_private.account_deletion_runs where user_id=%s",
            (world["a"],),
        ).fetchone() == ("data_deleted",)
        assert c.execute("select 1 from auth.users where id=%s", (world["a"],)).fetchone()
    admin = SqlAuthAdmin()
    try:
        assert _service(lane, admin).delete_account(user_id=world["a"]).status == "done"
    finally:
        world["placeholders"] += admin.created


def test_a_placeholder_never_gets_in(lane, world, route):  # noqa: ANN001, F811
    """A placeholder with a live session, and even a run row in its name,
    is refused: the lock door is closed to placeholders."""
    placeholder = str(uuid.uuid4())
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "insert into argus_private.account_placeholders(id) values (%s)",
            (placeholder,),
        )
        c.execute(
            "insert into auth.users(id, email) values (%s, %s)",
            (placeholder, f"exmiembro+{uuid.uuid4()}@cuadrao.invalid"),
        )
        c.execute(
            "insert into argus_private.account_deletion_runs"
            " (subject_hash, user_id, analytics_distinct_id, status)"
            " values (%s, %s, %s, 'started')",
            (hashlib.sha256(placeholder.encode()).hexdigest(), placeholder, "test"),
        )
    route["placeholders"].add(placeholder)
    session = _session(placeholder)
    route["sessions"].append(session)
    try:
        _refused(route, _token(placeholder, session))
    finally:
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("delete from auth.sessions where id=%s", (session,))
            c.execute(
                "delete from argus_private.account_deletion_runs where user_id=%s",
                (placeholder,),
            )
            c.execute("delete from auth.users where id=%s", (placeholder,))
            c.execute(
                "delete from argus_private.account_placeholders where id=%s",
                (placeholder,),
            )


def test_someone_elses_session_never_unlocks_a_locked_person(lane, world, route):  # noqa: ANN001, F811
    """A's run is in flight; a token for A that names B's live session is
    refused, so the lock door needs the person's own session."""
    _lock(lane, world, route)
    other = _session(world["b"])
    route["sessions"].append(other)
    _refused(route, _token(world["a"], other))
    _still_locked_then_finish(lane, world)


@pytest.mark.parametrize("shape", ["no_sub", "no_exp"])
def test_a_token_missing_its_subject_or_expiry_is_refused(lane, world, route, shape):  # noqa: ANN001, F811
    """No subject: nothing names the person. No expiry: the token would never
    lapse. Both are refused, with A's own live session in the token."""
    session = _lock(lane, world, route)
    if shape == "no_sub":
        token = _token(None, session)
    else:
        token = _token(world["a"], session, exp=False)
    _refused(route, token)
    _still_locked_then_finish(lane, world)


def test_a_session_past_its_not_after_never_unlocks(lane, world, route):  # noqa: ANN001, F811
    """Note 6: GoTrue's time-boxed session ends at not_after. The lock door
    is verified locally, so it must refuse an ended session itself."""
    from argus.api.auth_sessions import deletion_in_flight

    session = _lock(lane, world, route)
    token = _token(world["a"], session)
    assert deletion_in_flight(database_url=DSN, token=token, user_id=world["a"])
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "update auth.sessions set not_after = now() + interval '1 hour' where id=%s",
            (session,),
        )
    assert deletion_in_flight(database_url=DSN, token=token, user_id=world["a"])
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "update auth.sessions set not_after = now() - interval '1 second' where id=%s",
            (session,),
        )
    assert not deletion_in_flight(database_url=DSN, token=token, user_id=world["a"])
    _refused(route, token)
    _still_locked_then_finish(lane, world)


@pytest.mark.skipif(not LOCAL_STORAGE, reason="Local Supabase Storage required")
def test_storage_failure_answers_202_until_a_retry_erases_the_sources(
    lane,  # noqa: ANN001, F811
    world,  # noqa: ANN001, F811
    route,  # noqa: ANN001
) -> None:
    """#778 at the route: Storage down is a pending third party (202, locked);
    the retry answers 200 with the person's folder gone and B's file kept."""
    a, b = world["a"], world["b"]
    objects = source_objects()
    mine, theirs = f"{a}/{uuid.uuid4()}/{'a' * 64}", f"{b}/{uuid.uuid4()}/{'b' * 64}"
    for path in (mine, theirs):
        objects.put(path, b"%PDF-fixture", "application/pdf")
    session = _session(a)
    route["sessions"].append(session)
    token = _token(a, session)
    try:
        admin = SqlAuthAdmin()
        try:
            with patch.object(
                account_route,
                "account_deletion_service",
                return_value=_service(lane, admin, source_objects=_StorageDown()),
            ):
                first = route["client"].post(
                    URL, json={"confirm": True}, headers=_bearer(token)
                )
        finally:
            world["placeholders"] += admin.created
        assert first.status_code == 202, first.text
        assert first.json() == {"status": "in_progress", "pending": ["storage"]}
        assert _locked(a) == (True, True)
        assert not auth_session_is_active(database_url=DSN, token=token, user_id=a)

        admin = SqlAuthAdmin()
        try:
            with patch.object(
                account_route,
                "account_deletion_service",
                return_value=_service(lane, admin, source_objects=objects),
            ):
                second = route["client"].post(
                    URL, json={"confirm": True}, headers=_bearer(token)
                )
        finally:
            world["placeholders"] += admin.created
        assert second.status_code == 200, second.text
        assert second.json() == {"status": "done", "pending": []}
        with psycopg.connect(DSN) as c:
            assert stored_paths(c, f"{a}/") == []
            assert stored_paths(c, f"{b}/") == [theirs]
    finally:
        objects.delete(f"{a}/")
        objects.delete(f"{b}/")


def _deployed(monkeypatch, *, posthog_token: str | None) -> None:  # noqa: ANN001
    """A hosted deployment: not a local or test environment, no PostHog
    deletion adapter, and the server's event token set or not."""
    for name in ("ARGUS_ENV", "ARGUS_APP_ENV", "ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("ARGUS_ANALYTICS_DELETION_ENABLED", raising=False)
    if posthog_token is None:
        monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", posthog_token)


def _delete_as_deployed(lane, world, route) -> tuple:  # noqa: ANN001, F811
    """One POST through the route with the analytics step chosen from the
    environment the way the runtime chooses it; returns the response and the
    steps of the run it opened."""
    from argus.observability.analytics_deletion import (
        analytics_deletion_from_env,
        fake_analytics_allowed,
    )

    a = world["a"]
    session = _session(a)
    route["sessions"].append(session)
    with psycopg.connect(DSN) as c:
        before = {
            row[0]
            for row in c.execute("select id from argus_private.account_deletion_runs")
        }
    admin = SqlAuthAdmin()
    service = _service(
        lane,
        admin,
        analytics=analytics_deletion_from_env(),
        allow_fake=fake_analytics_allowed(),
    )
    try:
        with patch.object(
            account_route, "account_deletion_service", return_value=service
        ):
            response = route["client"].post(
                URL, json={"confirm": True}, headers=_bearer(_token(a, session))
            )
    finally:
        world["placeholders"] += admin.created
    with psycopg.connect(DSN) as c:
        (steps,) = [
            steps
            for run_id, steps in c.execute(
                "select id, steps from argus_private.account_deletion_runs"
            )
            if run_id not in before
        ]
    return response, steps


def test_without_posthog_events_the_analytics_step_is_not_applicable(
    lane,  # noqa: ANN001, F811
    world,  # noqa: ANN001, F811
    route,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
) -> None:
    """Decision 1B: a deployment that sends no PostHog events has nothing at
    PostHog to delete. The step records not_applicable with its reason, never
    deleted, and the run finishes."""
    _deployed(monkeypatch, posthog_token=None)
    response, steps = _delete_as_deployed(lane, world, route)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "done", "pending": []}
    assert steps["analytics"] == "not_applicable"
    assert steps["analytics_evidence"] == {"reason": "posthog_not_configured"}
    with psycopg.connect(DSN) as c:
        assert not c.execute(
            "select 1 from auth.users where id=%s", (world["a"],)
        ).fetchone()


def test_with_posthog_events_and_no_adapter_the_analytics_step_stays_pending(
    lane,  # noqa: ANN001, F811
    world,  # noqa: ANN001, F811
    route,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
) -> None:
    """Unchanged where the server sends events: nothing was deleted at
    PostHog, so the step stays pending and the account stays locked."""
    _deployed(monkeypatch, posthog_token="ph_project_token")
    response, steps = _delete_as_deployed(lane, world, route)
    assert response.status_code == 202, response.text
    assert response.json() == {"status": "in_progress", "pending": ["analytics"]}
    assert steps["analytics"] == "pending"
    assert steps["last_error"] == {"analytics": "analytics_adapter_unconfigured"}
    assert "analytics_evidence" not in steps
    assert _locked(world["a"]) == (True, True)
    _still_locked_then_finish(lane, world)

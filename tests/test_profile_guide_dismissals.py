"""`GET /me` carries the person's dismissed guide cards; the per-card read is gone."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from argus.api import state as api_state
from argus.api.business_guide import dismiss_guide_card
from argus.api.guest_access import registered_account_context
from argus.api.main import app
from argus.api.routers import profile
from psycopg import OperationalError
from starlette.requests import Request


class Dismissals:
    """A pool over `business_guide_dismissals` rows: (user_id, card_id)."""

    def __init__(self, rows: list[tuple[str, str]], failure: Exception | None = None) -> None:
        self.rows = rows
        self.failure = failure
        self.statements: list[tuple[str, tuple[str, ...]]] = []

    def connection(self) -> Dismissals:
        if self.failure:
            raise self.failure
        return self

    def __enter__(self) -> Dismissals:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, params: tuple[str, ...]) -> SimpleNamespace:
        self.statements.append((query, params))
        if query.startswith("insert"):
            self.rows.append(params)
            return SimpleNamespace()
        assert "where user_id = %s" in query
        return SimpleNamespace(
            fetchall=lambda: [(card,) for user, card in self.rows if user == params[0]]
        )


def _request(pool: Dismissals | None) -> Request:
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(financial_accounts_pool=pool))}
    )
    request.state.request_id = "synthetic-guide-read"
    return request


@pytest.fixture
def me(monkeypatch):
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(profile, "_apple_identity", lambda *_: None)
    monkeypatch.setattr(
        profile, "account_context", lambda request: registered_account_context("unused")
    )

    def read(pool: Dismissals | None, user_id: str) -> list[str] | None:
        user = api_state.store.get_or_create_dev_user().model_copy(update={"id": user_id})
        return profile.get_me(_request(pool), user).model_dump()["dismissed_guide_cards"]

    return read


def test_me_returns_only_this_persons_dismissed_guides(me, faker):
    ana, beto, carla = (faker.uuid4() for _ in range(3))
    pool = Dismissals(
        [
            (ana, "registros-intro"),
            (beto, "bandeja-intro"),
            (ana, "actividad-intro"),
            (ana, f"retired-{faker.word()}"),
        ]
    )
    assert me(pool, ana) == ["actividad-intro", "registros-intro"]
    assert me(pool, beto) == ["bandeja-intro"]
    assert me(pool, carla) == []
    assert [params for _, params in pool.statements] == [(ana,), (beto,), (carla,)]


def test_unreadable_dismissals_are_unknown_and_me_still_answers(me, faker):
    assert me(None, faker.uuid4()) is None
    assert me(Dismissals([], OperationalError("synthetic outage")), faker.uuid4()) is None


def test_the_per_card_guide_read_is_gone_and_dismiss_stays():
    routes = {
        (method, route.path)
        for route in app.routes
        if "guide-cards" in getattr(route, "path", "")
        for method in route.methods
    }
    assert routes == {("POST", "/api/v1/business/guide-cards/{card_id}/dismiss")}
    paths = [path for path in app.openapi()["paths"] if "guide-cards" in path]
    assert paths == ["/api/v1/business/guide-cards/{card_id}/dismiss"]


def test_dismiss_saves_for_the_signed_in_person_and_me_reads_it(me, faker):
    ana = faker.uuid4()
    pool = Dismissals([])
    person = SimpleNamespace(person_id=ana)
    state = dismiss_guide_card(_request(pool), person, "registros-intro")
    assert state.dismissed is True
    assert pool.rows == [(ana, "registros-intro")]
    assert me(pool, ana) == ["registros-intro"]

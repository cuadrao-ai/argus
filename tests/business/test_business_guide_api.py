"""Each guide card, Actividad's included, reads and dismisses for the signed-in person."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import get_args

import pytest
from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_guide import CardId, router
from argus.domain.business.spaces import InMemorySpaceStore
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient


class DismissalTable:
    """Stands in for `business_guide_dismissals`: one row per person and card."""

    def __init__(self) -> None:
        self.rows: set[tuple[str, str]] = set()

    @contextmanager
    def connection(self):
        yield self

    def execute(self, statement: str, key: tuple[str, str]) -> SimpleNamespace:
        if statement.startswith("insert"):
            self.rows.add(key)
        return SimpleNamespace(fetchone=lambda: (1,) if key in self.rows else None)


@pytest.fixture
def guide():
    person = Faker().uuid4()
    app = FastAPI()
    app.include_router(router, prefix="/business")
    app.state.financial_accounts_pool = DismissalTable()
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        person, InMemorySpaceStore()
    )
    with TestClient(app) as client:
        yield client


def test_actividad_intro_reads_and_dismisses_on_its_own(guide):
    assert "actividad-intro" in get_args(CardId)
    states = lambda: {  # noqa: E731
        card: guide.get(f"/business/guide-cards/{card}").json()["dismissed"]
        for card in get_args(CardId)
    }
    assert set(states().values()) == {False}

    response = guide.post("/business/guide-cards/actividad-intro/dismiss")
    assert response.status_code == 200, response.text
    assert response.json() == {"dismissed": True}
    assert response.headers["cache-control"] == "no-store"

    assert states() == {card: card == "actividad-intro" for card in get_args(CardId)}


def test_an_unknown_card_is_refused(guide):
    for response in (
        guide.get("/business/guide-cards/unknown"),
        guide.post("/business/guide-cards/unknown/dismiss"),
    ):
        assert response.status_code == 422

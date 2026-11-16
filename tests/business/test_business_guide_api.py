"""Each guide card, Actividad's included, dismisses on its own for the signed-in person."""

from __future__ import annotations

from types import SimpleNamespace
from typing import get_args

import pytest
from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_guide import router
from argus.api.schemas import GuideCardId
from argus.domain.business.spaces import InMemorySpaceStore
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient


class DismissalTable:
    """Stands in for `business_guide_dismissals`: one row per person and card."""

    def __init__(self) -> None:
        self.rows: set[tuple[str, str]] = set()

    def connection(self) -> DismissalTable:
        return self

    def __enter__(self) -> DismissalTable:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: str, key: tuple[str, str]) -> SimpleNamespace:
        assert statement.startswith("insert")
        self.rows.add(key)
        return SimpleNamespace()


@pytest.fixture
def guide():
    person = Faker().uuid4()
    table = DismissalTable()
    app = FastAPI()
    app.include_router(router, prefix="/business")
    app.state.financial_accounts_pool = table
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        person, InMemorySpaceStore()
    )
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, person=person, table=table)


def test_actividad_intro_is_a_guide_card():
    assert "actividad-intro" in get_args(GuideCardId)


@pytest.mark.parametrize("card", get_args(GuideCardId))
def test_each_card_dismisses_on_its_own_for_the_person(guide, card):
    response = guide.client.post(f"/business/guide-cards/{card}/dismiss")
    assert response.status_code == 200, response.text
    assert response.json() == {"dismissed": True}
    assert response.headers["cache-control"] == "no-store"
    assert guide.table.rows == {(guide.person, card)}


def test_an_unknown_card_is_refused(guide):
    response = guide.client.post("/business/guide-cards/unknown/dismiss")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert guide.table.rows == set()

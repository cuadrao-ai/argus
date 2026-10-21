"""A Business's country and currency, set once when the Business starts."""

from __future__ import annotations

from typing import get_args
from uuid import uuid4

from argus.domain.business.country import COUNTRIES, CountryCode, business_country
from argus.domain.business.spaces import InMemorySpaceStore
from fastapi.testclient import TestClient

from tests.business.test_business_api import ALICE, BOB, Owner

PERIOD = {"from": "2026-10-01", "to": "2026-10-21"}


def test_a_space_takes_the_currency_of_its_country() -> None:
    space, _ = InMemorySpaceStore().create("p", "Mi negocio", "CA")
    assert (space.country, space.currency) == ("CA", "CAD")


def test_a_space_without_a_country_is_dominican_in_pesos() -> None:
    space, _ = InMemorySpaceStore().create("p", "Mi negocio")
    assert (space.country, space.currency) == ("DO", "DOP")


def test_the_wire_literal_admits_exactly_the_registry_countries() -> None:
    assert set(get_args(CountryCode)) == set(COUNTRIES)


def test_the_registry_names_each_country_currency() -> None:
    assert business_country("US").currency == "USD"


def _identity(response) -> tuple[str, str]:  # noqa: ANN001
    assert response.status_code == 200, response.text
    body = response.json()
    return body["country"], body["currency"]


def _business_reads(owner: Owner) -> list[tuple[str, str]]:
    return [
        _identity(owner.get("/space")),
        _identity(owner.get("/space/name")),
        _identity(owner.get("/workspace")),
        _identity(owner.get("/overview", **PERIOD)),
    ]


def test_a_business_started_without_a_country_is_dominican(
    biz: TestClient, identities
) -> None:  # noqa: ANN001
    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    started = alice.start({})
    assert started.status_code == 201, started.text
    assert (started.json()["country"], started.json()["currency"]) == ("DO", "DOP")
    assert _business_reads(alice) == [("DO", "DOP")] * 4


def test_a_business_keeps_the_country_it_started_with(
    biz: TestClient, identities
) -> None:  # noqa: ANN001
    bob = Owner(biz, BOB, identities[BOB]["id"])
    started = bob.start({"country": "US"})
    assert started.status_code == 201, started.text
    assert (started.json()["country"], started.json()["currency"]) == ("US", "USD")
    assert _business_reads(bob) == [("US", "USD")] * 4

    again = bob.start({"country": "CA"})
    assert again.status_code == 200, again.text
    assert again.json()["id"] == started.json()["id"]
    assert (again.json()["country"], again.json()["currency"]) == ("US", "USD")
    assert _business_reads(bob) == [("US", "USD")] * 4


def test_an_unknown_country_is_refused(biz: TestClient, identities) -> None:  # noqa: ANN001
    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    assert alice.start({"country": "XX"}).status_code == 422
    assert alice.get("/space").status_code == 404


def test_the_business_currency_never_forces_a_document_currency(
    biz: TestClient, identities
) -> None:  # noqa: ANN001
    alice = Owner(biz, ALICE, identities[ALICE]["id"])
    assert alice.start({}).json()["currency"] == "DOP"
    account = alice.account("USD", "Card")
    saved = alice.post(
        "/expenses",
        {"account_id": account, "amount": "24.00", "occurred_on": "2026-10-05"},
        key=str(uuid4()),
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["currency"] == "USD"
    overview = alice.get("/overview", **PERIOD).json()
    assert overview["currency"] == "DOP"
    assert [(t["currency"], t["amount"]) for t in overview["totals"]] == [
        ("USD", "24.00")
    ]

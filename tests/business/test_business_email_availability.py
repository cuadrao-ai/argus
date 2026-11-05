"""The workspace and intake routes share one receiving answer."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from argus.api import email_intake as runtime_module
from faker import Faker

from tests.business.test_business_api import BASE, Owner, alice  # noqa: F401
from tests.business.test_business_email_api import runtime  # noqa: F401


@pytest.mark.parametrize("missing", ["receiving", "domain", "provider", "runtime"])
def test_workspace_and_email_intake_routes_share_availability(
    alice: Owner, runtime, monkeypatch, missing  # noqa: F811
) -> None:
    fake = Faker()
    item_id = fake.uuid4()
    assert alice.get("/workspace").json()["receiving_channels"]["email"] == {
        "available": True
    }
    assert alice.get("/email").json()["receiving_address"] is None
    if missing == "receiving":
        monkeypatch.setattr(runtime_module, "webhook_enabled", lambda: False)
    elif missing == "domain":
        monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_DOMAIN", " ")
    elif missing == "provider":
        runtime.provider = None
    else:
        runtime_module.configure_email_intake(None)
    assert alice.get("/workspace").json()["receiving_channels"]["email"] == {
        "available": False
    }
    routes = [
        ("GET", "", None), ("POST", "", {"alias": fake.user_name()}),
        ("DELETE", "", None), ("GET", "/availability?alias=fixture", None),
        ("GET", "/suggestion?name=Fixture", None),
        ("POST", "/address", {"alias": fake.user_name()}),
        ("GET", "/senders", None), ("POST", "/senders", {"email": fake.email()}),
        ("DELETE", f"/senders/{item_id}", None),
        ("POST", f"/deliveries/{item_id}/retry", None),
    ]
    for method, path, body in routes:
        response = alice.client.request(
            method, BASE + "/email" + path, json=body,
            headers={**alice.auth, "Idempotency-Key": fake.uuid4()},
        )
        assert response.status_code == 404, (method, path, response.text)
        assert response.headers["cache-control"] == "no-store"


def test_new_address_records_the_acting_person_after_transfer(
    alice: Owner, runtime, monkeypatch  # noqa: F811
):
    from argus.api.business import BusinessContext
    from argus.api.routers import email_intake as routes
    from fastapi import Response
    from starlette.requests import Request

    fake = Faker()
    scope = replace(alice.scope(), person_id=fake.uuid4(), actor_id=alice.person)
    actors = []

    def resolve(actor):
        actors.append(str(actor.actor_id))
        return SimpleNamespace(owner_id=scope.person_id, grant_id=fake.uuid4())

    monkeypatch.setattr(routes, "BusinessActions", lambda *args: SimpleNamespace(resolve_actor=resolve))
    monkeypatch.setattr(routes, "_configured_domain", lambda request: "recibos.example.test")
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(financial_accounts_pool=object()))})
    response = Response(status_code=201)
    routes.create_receiving_address(request, response, BusinessContext(scope, None), routes.AliasBody(alias="tienda-prueba"))
    assert actors == [alice.person]
    assert response.status_code == 201
    assert runtime.store.route_for_space(scope.owner.space_id).granted_by == alice.person

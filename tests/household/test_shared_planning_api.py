"""Real thin API/Pydantic transport over disposable canonical PostgreSQL services."""

from dataclasses import replace

import pytest
from argus.api.dependencies import current_user
from argus.api.guest_access import registered_account_context, store_account_context
from argus.api.households import require_households_surface
from argus.api.routers import household_financial, household_planning
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from tests.household.financial_fixtures import DSN, NOW, key
from tests.household.shared_plan_fixtures import create, request, scene, scope

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


@pytest.fixture
def api(lane):
    s = scene(lane)
    app = FastAPI()

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = key()
        return await call_next(request)

    app.include_router(household_planning.router)
    app.include_router(household_financial.router)

    def authenticated(request: Request):
        actor = request.headers.get("x-fixture-identity")
        if actor not in [s["a"], s["b"], s["c"]]:
            raise HTTPException(401)
        account = registered_account_context(actor)
        if request.headers.get("x-fixture-guest"):
            account = replace(account, kind="guest")
        store_account_context(request, account)
        return None

    app.dependency_overrides[current_user] = authenticated
    app.dependency_overrides[require_households_surface] = lambda: s["households"]
    with TestClient(app) as client:
        yield s, client, app


def send(client, s, actor, method, path, body=None, k=None):
    return client.request(
        method,
        "/api/v1/households/" + s["hid"] + path,
        headers={"X-Fixture-Identity": actor, "Idempotency-Key": k or key()},
        json=body,
    )


@pytest.mark.parametrize("kind", ["budget", "bill", "goal", "debt"])
def test_public_route_detail_home_search_and_actions_validate_exact_wire(api, kind):
    s, client, _ = api
    p = create(s, kind)
    path = "/plan/" + kind + "/" + str(p["ref"]["id"])
    for suffix in ["", "/history", "/contributions/candidates"]:
        response = send(client, s, s["b"], "GET", path + suffix)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
    snapshot = send(client, s, s["b"], "GET", "/snapshot")
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["plans"][0]["ref"] == p["ref"]
    options = send(client, s, s["b"], "GET", "/plan/options")
    assert options.status_code == 200, options.text
    assert options.json()["money"]["eligibility"]["expense"] == [
        "cash",
        "checking",
        "savings",
        "credit_card",
    ]
    assert send(client, s, s["c"], "GET", path).status_code == 404
    denied = send(
        client,
        s,
        s["b"],
        "PATCH",
        path,
        scope(s, s["b"], p["version"]) | {"definition": {"name": "Unauthorized"}},
    )
    assert denied.status_code == 404
    changed = send(
        client,
        s,
        s["a"],
        "PATCH",
        path,
        scope(s, s["a"], p["version"]) | {"definition": {"name": "API shared"}},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["plan"]["last_edited_by"]["membership_id"] == s["amid"]
    private = scope(s, s["a"], changed.json()["plan"]["version"]) | {
        "definition": {"source_account_id": s["ba"]}
    }
    assert send(client, s, s["a"], "PATCH", path, private).status_code == 422


def test_api_create_money_preview_confirm_retry_cas_private_receipt_and_revoke(api):
    s, client, _ = api
    body = scope(s, s["a"]) | dict(
        definition=dict(
            kind="budget",
            name="API budget",
            limit="100",
            currency="DOP",
            month=NOW.strftime("%Y-%m"),
            account_ids=[s["aa"]],
            category_ids=[],
            include_uncategorized=True,
        ),
        participants=[dict(membership_id=s["bmid"])],
    )
    created = send(client, s, s["a"], "POST", "/plan/budget", body)
    assert created.status_code == 201, created.text
    p = created.json()["plan"]
    path = "/plan/budget/" + p["ref"]["id"]
    body = scope(s, s["b"], p["version"]) | dict(
        activity=request("expense", s["ba"], "10", note="PRIVATE API note").model_dump(
            mode="json"
        ),
        purpose="spending",
    )
    preview = send(client, s, s["b"], "POST", path + "/contributions/preview", body)
    assert preview.status_code == 200, preview.text
    body["activity"] = preview.json()["money"]["reviewed_request"] | {
        "preview_token": preview.json()["money"]["preview_token"]
    }
    k = key()
    written = send(client, s, s["b"], "POST", path + "/contributions", body, k)
    assert written.status_code == 201, written.text
    assert "PRIVATE API note" not in written.text
    assert written.json()["plan"]["progress"]["spent_minor"] == "1000"
    retry = send(client, s, s["b"], "POST", path + "/contributions", body, k)
    assert retry.status_code == 201 and retry.json()["replayed"]
    assert (
        send(client, s, s["b"], "POST", path + "/contributions", body).status_code == 409
    )
    changed_body = body | {"purpose": "funding"}
    assert (
        send(
            client, s, s["b"], "POST", path + "/contributions", changed_body, k
        ).status_code
        == 409
    )
    current = written.json()["plan"]
    revoked = send(
        client,
        s,
        s["a"],
        "PUT",
        path + "/participants",
        scope(s, s["a"], current["version"]) | {"participants": []},
    )
    assert revoked.status_code == 200, revoked.text
    assert send(client, s, s["b"], "GET", path).status_code == 404
    assert (
        send(client, s, s["b"], "POST", path + "/contributions", body, k).status_code
        == 404
    )


def test_api_guest_and_default_off_gate(api, monkeypatch):
    s, client, app = api
    response = client.get(
        "/api/v1/households/" + s["hid"] + "/plan",
        headers={"X-Fixture-Identity": s["b"], "X-Fixture-Guest": "true"},
    )
    assert response.status_code == 403
    del app.dependency_overrides[require_households_surface]
    monkeypatch.setenv("CUADRAO_HOUSEHOLDS_ENABLED", "false")
    assert send(client, s, s["b"], "GET", "/plan").status_code == 404

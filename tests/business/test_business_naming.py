from concurrent.futures import ThreadPoolExecutor

import pytest
from argus.domain.business.spaces import InMemorySpaceStore


def test_prompt_is_claimed_once_for_each_business():
    store = InMemorySpaceStore()
    first, _ = store.create("owner", "Mi negocio")
    with ThreadPoolExecutor(max_workers=4) as workers:
        claims = list(
            workers.map(lambda _: store.claim_naming_visit("owner", first.id), range(8))
        )
    assert sum(claims) == 1
    assert store.open_space("owner").name == "Mi negocio"
    assert store.open_space("owner").name_prompt_seen is True


def test_prompt_uses_current_owned_business():
    store = InMemorySpaceStore()
    own, _ = store.create("owner", "Mi negocio")
    other, _ = store.create("other", "Mi negocio")
    assert not store.claim_naming_visit("owner", other.id)
    assert not store.open_space("owner").name_prompt_seen
    assert store.claim_naming_visit("owner", own.id)


def test_custom_name_does_not_trigger_prompt_and_rename_preserves_seen():
    store = InMemorySpaceStore()
    space, _ = store.create("owner", "Colmado La Esquina")
    assert not store.claim_naming_visit("owner", space.id)
    assert not space.name_required
    default, _ = store.create("new-owner", "My business")
    assert default.name_required
    assert store.claim_naming_visit("new-owner", default.id)
    renamed = store.rename("new-owner", "Colmado La Esquina")
    assert renamed.name_prompt_seen
    assert not renamed.name_required


def test_owner_prompt_persists_and_invite_requires_custom_name(biz, identities):
    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    started = biz.post(base + "/space", headers=headers, json={}).json()
    claim = biz.post(
        base + "/space/name-prompt", headers=headers, json={"space_id": started["id"]}
    )
    assert claim.status_code == 200
    assert claim.json()["show_prompt"] is True
    assert (
        biz.post(
            base + "/space/name-prompt", headers=headers, json={"space_id": started["id"]}
        ).json()["show_prompt"]
        is False
    )
    blocked = biz.post(
        base + "/access", headers=headers, json={"email": "accountant@example.test"}
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "business_name_required"
    renamed = biz.patch(
        base + "/space/name",
        headers=headers,
        json={"space_id": started["id"], "name": " Colmado La Esquina "},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Colmado La Esquina"
    assert renamed.json()["name_prompt_seen"] is True
    assert renamed.json()["name_required"] is False
    assert (
        biz.post(
            base + "/access", headers=headers, json={"email": "accountant@example.test"}
        ).status_code
        == 201
    )


@pytest.mark.parametrize("name", ["Mi negocio", "My business"])
def test_default_name_remains_required_after_skip(name):
    store = InMemorySpaceStore()
    space, _ = store.create("owner", name)
    store.claim_naming_visit("owner", space.id)
    assert store.open_space("owner").name_required


@pytest.mark.parametrize("name", ["", " " * 4, "x" * 81])
def test_invalid_name_does_not_replace_current_name(biz, name):
    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    space = biz.post(base + "/space", headers=headers, json={}).json()
    response = biz.patch(
        base + "/space/name",
        headers=headers,
        json={"space_id": space["id"], "name": name},
    )
    assert response.status_code == 422
    assert biz.get(base + "/space/name", headers=headers).json()["name"] == space["name"]


def test_accountant_never_claims_or_renames_another_business(biz, identities):
    from argus.api.business_spaces import business_access

    from tests.business.conftest import ALICE, BOB

    base = "/api/v1/business"
    owner = {"Authorization": f"Bearer {ALICE}"}
    space = biz.post(base + "/space", headers=owner, json={}).json()
    access = business_access()
    access.confirm(identities[BOB]["id"], "accountant@example.test")
    access.give(space["id"], identities[ALICE]["id"], "accountant@example.test")
    grant = access.spaces_for(identities[BOB]["id"])[0]
    accountant = {"Authorization": f"Bearer {BOB}", "X-Business-Grant": grant.grant_id}
    for response in [
        biz.get(base + "/space/name", headers=accountant),
        biz.post(
            base + "/space/name-prompt",
            headers=accountant,
            json={"space_id": space["id"]},
        ),
        biz.patch(
            base + "/space/name",
            headers=accountant,
            json={"space_id": space["id"], "name": "Changed"},
        ),
    ]:
        assert response.status_code == 403
    assert not biz.get(base + "/space/name", headers=owner).json()["name_prompt_seen"]


def test_wrong_business_id_cannot_consume_or_rename_current_business(biz):
    from uuid import uuid4

    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    biz.post(base + "/space", headers=headers, json={})
    for method, path, body in [
        (biz.post, "/space/name-prompt", {"space_id": str(uuid4())}),
        (biz.patch, "/space/name", {"space_id": str(uuid4()), "name": "Changed"}),
    ]:
        assert method(base + path, headers=headers, json=body).status_code == 404
    state = biz.get(base + "/space/name", headers=headers).json()
    assert state["name"] == "Mi negocio"
    assert not state["name_prompt_seen"]


@pytest.mark.parametrize(
    "is_owner,name,expected",
    [
        (True, "Mi negocio", 409),
        (True, "Colmado La Esquina", 200),
        (False, "Mi negocio", 200),
    ],
)
def test_export_requires_name_only_for_owner(monkeypatch, is_owner, name, expected):
    from types import SimpleNamespace
    from uuid import uuid4

    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import require_drafts
    from argus.api.documents import require_saved_documents
    from argus.api.routers import business_export
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    owner = str(uuid4())
    spaces = InMemorySpaceStore()
    space, _ = spaces.create(owner, name)
    context = SimpleNamespace(
        actor=SimpleNamespace(
            actor_id=owner if is_owner else str(uuid4()), space_id=space.id
        ),
        owner_id=owner,
    )
    app = FastAPI()
    app.include_router(business_export.router)

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "naming-export-test"
        return await call_next(request)

    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        owner, spaces
    )
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        for_space=lambda *_: context, service=SimpleNamespace(authority=None)
    )
    app.dependency_overrides[require_saved_documents] = lambda: SimpleNamespace(
        store=SimpleNamespace(objects=object())
    )
    called = []
    monkeypatch.setattr(
        business_export, "export_package", lambda *_: called.append(True) or b"PKfixture"
    )
    with TestClient(app) as client:
        result = client.get("/business/exports?start=2026-10-01&end=2026-10-31")
    assert result.status_code == expected
    assert bool(called) == (expected == 200)


def test_invite_rechecks_name_after_client_read(biz, identities):
    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    biz.post(base + "/space", headers=headers, json={})
    biz.patch(base + "/space", headers=headers, json={"name": "Colmado La Esquina"})
    assert not biz.get(base + "/space/name", headers=headers).json()["name_required"]
    biz.patch(base + "/space", headers=headers, json={"name": "Mi negocio"})
    response = biz.post(
        base + "/access", headers=headers, json={"email": "accountant@example.test"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "business_name_required"
    assert biz.get(base + "/access", headers=headers).json()["invites"] == []

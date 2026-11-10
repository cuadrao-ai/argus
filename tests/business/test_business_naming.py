import pytest
from argus.domain.business.spaces import InMemorySpaceStore


def test_default_name_is_required_until_renamed():
    store = InMemorySpaceStore()
    default, _ = store.create("new-owner", "My business")
    assert default.name_required
    renamed = store.rename("new-owner", "Colmado La Esquina")
    assert not renamed.name_required
    custom, _ = store.create("owner", "Colmado La Esquina")
    assert not custom.name_required


@pytest.fixture
def invitations_configured(monkeypatch):
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.setattr(
        "argus.domain.business.invite_email.send_resend_email",
        lambda **message: "fake-receipt",
    )


def test_invite_requires_custom_name_and_no_first_visit_prompt_exists(
    biz, identities, invitations_configured
):
    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    started = biz.post(base + "/space", headers=headers, json={}).json()
    # A new Business's first steps live in Inicio's setup guide; nothing claims a first-visit prompt.
    assert (
        biz.post(
            base + "/space/name-prompt", headers=headers, json={"space_id": started["id"]}
        ).status_code
        == 404
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
    assert renamed.json()["name_required"] is False
    assert (
        biz.post(
            base + "/access", headers=headers, json={"email": "accountant@example.test"}
        ).status_code
        == 201
    )


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


def test_accountant_never_renames_another_business(biz, identities):
    from argus.api.business_spaces import business_access

    from tests.business.conftest import ALICE, BOB

    base = "/api/v1/business"
    owner = {"Authorization": f"Bearer {ALICE}"}
    space = biz.post(base + "/space", headers=owner, json={}).json()
    access = business_access()
    access.confirm(identities[BOB]["id"], "accountant@example.test")
    _, listing = access.give(
        space["id"], identities[ALICE]["id"], "accountant@example.test"
    )
    access.accept_invite(identities[BOB]["id"], space["id"], listing.invites[0].id)
    grant = access.spaces_for(identities[BOB]["id"])[0]
    accountant = {"Authorization": f"Bearer {BOB}", "X-Business-Grant": grant.grant_id}
    assert biz.get(base + "/space/name", headers=accountant).status_code == 200
    renamed = biz.patch(
        base + "/space/name",
        headers=accountant,
        json={"space_id": space["id"], "name": "Changed"},
    )
    assert renamed.status_code == 403
    assert biz.get(base + "/space/name", headers=owner).json()["name"] == space["name"]


def test_wrong_business_id_cannot_rename_current_business(biz):
    from uuid import uuid4

    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    biz.post(base + "/space", headers=headers, json={})
    response = biz.patch(
        base + "/space/name",
        headers=headers,
        json={"space_id": str(uuid4()), "name": "Changed"},
    )
    assert response.status_code == 404
    assert biz.get(base + "/space/name", headers=headers).json()["name"] is None


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


@pytest.mark.parametrize("language", ["en", "es-419"])
def test_an_unnamed_business_has_no_name_on_the_wire(biz, language):
    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    started = biz.post(base + "/space", headers=headers, json={"language": language})
    naming = biz.get(base + "/space/name", headers=headers).json()
    listed = biz.get(base + "/spaces", headers=headers).json()["spaces"]
    assert started.json()["name"] is None
    assert biz.get(base + "/space", headers=headers).json()["name"] is None
    assert (naming["name"], naming["name_required"]) == (None, True)
    assert [space["name"] for space in listed] == [None]


@pytest.mark.parametrize("name", ["My business supplies", "Colmado Mi negocio"])
def test_a_real_name_is_untouched_on_the_wire(biz, name):
    from tests.business.conftest import ALICE

    headers = {"Authorization": f"Bearer {ALICE}"}
    base = "/api/v1/business"
    biz.post(base + "/space", headers=headers, json={"language": "en"})
    biz.patch(base + "/space", headers=headers, json={"name": name})
    listed = biz.get(base + "/spaces", headers=headers).json()["spaces"]
    assert biz.get(base + "/space", headers=headers).json()["name"] == name
    assert [space["name"] for space in listed] == [name]


@pytest.mark.parametrize(
    "stored,typed,confirmed",
    [
        ("My business", "Mi negocio", "My business"),
        ("Mi negocio", "My business", "Mi negocio"),
        ("Mi negocio", "Mi negocio", "Mi negocio"),
        ("My business", "Colmado", "Colmado"),
        ("Colmado", "Mi negocio", "Mi negocio"),
        ("Colmado", "Colmado", "Colmado"),
    ],
)
def test_an_unnamed_business_confirms_with_the_name_its_reader_shows(
    stored, typed, confirmed
):
    from argus.domain.business.space_name import typed_name

    assert typed_name(stored, typed) == confirmed


@pytest.mark.parametrize(
    "stored,spoken",
    [("My business", "Mi negocio"), ("Mi negocio", "Mi negocio"), ("Colmado", "Colmado")],
)
def test_a_spanish_message_names_an_unnamed_business_mi_negocio(stored, spoken):
    from argus.domain.business.space_name import spanish_name

    assert spanish_name(stored) == spoken

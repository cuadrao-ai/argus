from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business import BusinessPerson, require_business_person
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.routers.business_manual import router
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Applied, OutcomeUnknown, Refused
from argus.domain.business.contracts.dossier import BusinessDossier
from argus.domain.business.contracts.facts import BusinessFacts
from argus.domain.business.spaces import InMemorySpaceStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


class CaptureService:
    def __init__(self, actor, space):
        self.actor, self.space = actor, space
        self.calls = []
        self.view = BusinessDossier(
            draft_id=uuid4(),
            version=3,
            space_id=space,
            space_name="Shop",
            accounts=(),
            capabilities={"read", "prepare"},
            review_state="open",
            facts=BusinessFacts(),
            sources=(),
            questions=(),
            history=(),
            blockers=(),
            approval_available=False,
        )
        self.outcome = Applied(outcome="applied", draft_id=self.view.draft_id, version=1)

    def resolve_actor(self, actor, **_pin):
        self.calls.append(("owner", actor))
        return actor

    def context_for_draft(self, actor, draft, **_pin):
        self.calls.append(("draft", actor, draft))
        return self.actor

    def capture(self, actor, request, key):
        self.calls.append(("capture", request, key))
        return self.outcome

    def dossier(self, actor, draft):
        self.calls.append(("dossier", draft))
        return self.view

    def captures(self, actor, *, query, limit):
        self.calls.append(("list", query, limit))
        return [
            {
                "draft_id": self.view.draft_id,
                "version": self.view.version,
                "revision": 1,
                "source_id": uuid4(),
                "text": "  Original note\n",
                "received_at": datetime.now(timezone.utc),
                "review_state": "open",
            }
        ]


@pytest.fixture
def capture_api():
    actor = uuid4()
    spaces = InMemorySpaceStore()
    space = spaces.create(str(actor), "Shop")[0]
    service = CaptureService(actor, space.id)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(service, actor)
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(actor), spaces
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "capture-api"
        return await call_next(request)

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, service=service, actor=actor)


def test_capture_preserves_original_text_and_returns_current_dossier(capture_api):
    api = capture_api
    response = api.client.post(
        "/business/captures",
        json={"text": "  Una nota\n"},
        headers={"Idempotency-Key": "capture-key"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft_id"] == str(api.service.view.draft_id)
    assert response.json()["version"] == 3
    assert response.headers["cache-control"] == "no-store"
    owner, command, read = api.service.calls
    assert owner[1].actor_id == api.actor
    assert owner[1].space_id == api.service.view.space_id
    assert owner[1].actor_kind == "member"
    assert command[1].text == "  Una nota\n"
    assert command[2] == "capture-key"
    assert read == ("dossier", api.service.view.draft_id)


def test_append_uses_existing_draft_authority_without_owner_workspace(capture_api):
    api = capture_api
    api.app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(api.actor), InMemorySpaceStore()
    )
    draft = uuid4()
    response = api.client.post(
        "/business/captures",
        json={"text": "Extra note", "draft": {"draft_id": str(draft), "version": 7}},
        headers={"Idempotency-Key": "append"},
    )
    assert response.status_code == 200
    assert api.service.calls[0] == ("draft", api.actor, draft)
    assert api.service.calls[1][1].draft.version == 7


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": " \n\t"},
        {"text": "x" * 20001},
        {"text": "original\x00note"},
        {"text": "note", "actor_id": str(uuid4())},
        {"text": "note", "space_id": str(uuid4())},
        {"text": "note", "grant_id": str(uuid4())},
        {"text": "note", "source_ids": [str(uuid4())]},
        {"text": "note", "facts": {"amount": {"state": "known", "value": "10"}}},
        {"text": "note", "draft": {"draft_id": str(uuid4()), "version": 0}},
        *[
            {"text": "note", "draft": {"draft_id": str(uuid4()), "version": value}}
            for value in (True, False, "1", 1.0, 1.5)
        ],
    ],
)
def test_capture_rejects_invalid_text_and_caller_authority(capture_api, body):
    response = capture_api.client.post(
        "/business/captures", json=body, headers={"Idempotency-Key": "invalid"}
    )
    assert response.status_code == 422
    assert capture_api.service.calls == []


def test_capture_requires_key_and_existing_owner_workspace(capture_api):
    api = capture_api
    assert api.client.post("/business/captures", json={"text": "note"}).status_code == 400
    api.app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(api.actor), InMemorySpaceStore()
    )
    response = api.client.post(
        "/business/captures", json={"text": "note"}, headers={"Idempotency-Key": "key"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "business_space_missing"
    assert api.service.calls == []


@pytest.mark.parametrize(
    "outcome,code",
    [
        (Refused(outcome="stale_version", code="stale_version"), "stale_version"),
        (OutcomeUnknown(code="business_action_unsettled"), "business_action_unsettled"),
    ],
)
def test_unsettled_and_refused_capture_never_returns_a_dossier(
    capture_api, outcome, code
):
    api = capture_api
    api.service.outcome = outcome
    response = api.client.post(
        "/business/captures", json={"text": "note"}, headers={"Idempotency-Key": "key"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == code
    assert not any(call[0] == "dossier" for call in api.service.calls)


def test_search_preserves_source_identity_and_bounds(capture_api):
    api = capture_api
    response = api.client.get("/business/captures", params={"q": "100%_", "limit": 5})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    item = response.json()["items"][0]
    assert item["draft_id"] == str(api.service.view.draft_id)
    assert item["text"] == "  Original note\n"
    assert item["source_id"]
    assert (item["version"], item["revision"]) == (api.service.view.version, 1)
    assert api.service.calls[-1] == ("list", "100%_", 5)
    assert api.client.get("/business/captures?limit=51").status_code == 422
    assert (
        api.client.get("/business/captures", params={"q": "x" * 201}).status_code == 422
    )
    assert api.client.get("/business/captures", params={"q": "\x00"}).status_code == 422


def test_revoked_capture_context_keeps_not_found_envelope(capture_api, monkeypatch):
    def denied(actor, **_pin):
        raise ActionError("not_found", "business_record_not_found")

    monkeypatch.setattr(capture_api.service, "resolve_actor", denied)
    for response in (
        capture_api.client.get("/business/captures"),
        capture_api.client.post(
            "/business/captures",
            json={"text": "note"},
            headers={"Idempotency-Key": "key"},
        ),
    ):
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "business_record_not_found"

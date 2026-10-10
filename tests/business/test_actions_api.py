from __future__ import annotations

from uuid import uuid4

from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.routers.business_drafts import router
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Refused
from fastapi import FastAPI
from fastapi.testclient import TestClient


class MissingDraft:
    def context_for_draft(self, actor_id, draft_id):
        return object()

    def dossier(self, context, draft_id):
        raise ActionError("invalid_input", "draft_not_prepared")


def test_untyped_dossier_reports_explicit_preparation_conflict():
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "test-actions"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        MissingDraft(), uuid4()
    )
    with TestClient(app) as client:
        response = client.get(f"/business/drafts/{uuid4()}/dossier")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "draft_not_prepared"
    assert response.headers["cache-control"] == "no-store"


def test_human_review_rejects_authority_and_source_parameters():
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "test-actions"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        MissingDraft(), uuid4()
    )
    with TestClient(app) as client:
        response = client.patch(
            f"/business/drafts/{uuid4()}/review",
            json={
                "version": 1,
                "facts": {"amount": {"state": "unknown"}},
                "space_id": str(uuid4()),
                "source_ids": [str(uuid4())],
            },
            headers={"Idempotency-Key": "test"},
        )
    assert response.status_code == 422


def test_refusal_problem_uses_existing_envelope():
    from argus.api.business_drafts import action_problem
    from starlette.requests import Request

    error = action_problem(
        Request(
            {
                "type": "http",
                "path": "/",
                "headers": [],
                "state": {"request_id": "test-actions"},
            }
        ),
        Refused(outcome="not_found", code="business_record_not_found"),
    )
    assert error.status_code == 404
    assert error.detail["code"] == "business_record_not_found"

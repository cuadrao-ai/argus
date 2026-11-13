from __future__ import annotations

from uuid import uuid4

import pytest
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.routers.business_drafts import router
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.actions import OutcomeUnknown, Refused
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import BusinessDossier
from argus.domain.business.contracts.facts import BusinessFacts
from fastapi import FastAPI
from fastapi.testclient import TestClient


class MissingDraft:
    def context_for_draft(self, actor_id, draft_id, **_pin):
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


def test_approve_route_dispatches_strict_income_and_expense_commands():
    class RefusingDraft(MissingDraft):
        def __init__(self):
            self.calls = []

        def approve(self, context, draft_id, request, key):
            self.calls.append(("expense", draft_id, request.action, request.version, key))
            return Refused(outcome="invalid_input", code="expense_blocked")

        def approve_income(self, context, draft_id, request, key):
            self.calls.append(("income", draft_id, request.action, request.version, key))
            return Refused(outcome="invalid_input", code="income_blocked")

    service = RefusingDraft()
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "test-actions"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(service, uuid4())
    draft_id = uuid4()
    url = f"/business/drafts/{draft_id}/approve"
    headers = {"Idempotency-Key": "same-key"}
    with TestClient(app) as client:
        income = client.post(
            url, json={"action": "record_income", "version": 2}, headers=headers
        )
        expense = client.post(
            url, json={"action": "record_expense", "version": 3}, headers=headers
        )
        unknown = client.post(
            url, json={"action": "record_transfer", "version": 3}, headers=headers
        )
        untyped = client.post(url, json={"version": 3}, headers=headers)
        loose_version = client.post(
            url, json={"action": "record_income", "version": "2"}, headers=headers
        )
    assert income.status_code == 422
    assert income.json()["detail"]["code"] == "income_blocked"
    assert expense.status_code == 422
    assert expense.json()["detail"]["code"] == "expense_blocked"
    assert [unknown.status_code, untyped.status_code, loose_version.status_code] == [
        422,
        422,
        422,
    ]
    assert service.calls == [
        ("income", draft_id, "record_income", 2, "same-key"),
        ("expense", draft_id, "record_expense", 3, "same-key"),
    ]


def test_duplicate_resolution_is_a_strict_business_command():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(MissingDraft(), uuid4())
    with TestClient(app) as client:
        response = client.post(
            f"/business/drafts/{uuid4()}/duplicate-resolution",
            json={
                "version": 1,
                "other_draft_id": str(uuid4()),
                "other_version": 1,
                "decision": "different_purchase",
                "space_id": str(uuid4()),
            },
            headers={"Idempotency-Key": "duplicate-decision"},
        )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "body", "service_method"),
    [
        ("POST", "approve", {"action": "record_expense"}, "approve"),
        ("POST", "approve", {"action": "record_income"}, "approve_income"),
        ("POST", "approve", {"action": "record_refund"}, "approve_refund"),
        ("POST", "reopen", {}, "reopen"),
        ("PATCH", "review", {"facts": {"amount": {"state": "unknown"}}}, "review"),
        (
            "POST",
            "duplicate-resolution",
            {
                "other_draft_id": str(uuid4()),
                "other_version": 1,
                "decision": "different_purchase",
            },
            "resolve_duplicate",
        ),
        ("POST", "personal", {"personal": True}, "mark_personal"),
        ("POST", "fiscal-inclusion", {"include": True}, "decide_606"),
        ("POST", "remainder/settle", {}, "settle_remainder"),
    ],
    ids=[
        "expense",
        "income",
        "refund",
        "reopen",
        "review",
        "duplicate",
        "personal",
        "fiscal-inclusion",
        "remainder",
    ],
)
@pytest.mark.parametrize(
    "code", ["business_recording_unsettled", "business_approval_reconciliation_required"]
)
def test_unsettled_action_returns_conflict_without_reading_dossier(
    method, path, body, service_method, code
):
    actor, space, draft = uuid4(), uuid4(), uuid4()
    calls = []

    class UnsettledDraft(MissingDraft):
        def context_for_draft(self, actor_id, draft_id, **_pin):
            return ActionContext(
                actor=TrustedActor(
                    actor_id=actor_id, actor_kind="member", space_id=space
                ),
                grant_id=uuid4(),
                owner_id=str(actor_id),
                space_name="Shop",
                current_owner_id=str(actor_id),
            )

        def unsettled(self, context, draft_id, command, key):
            calls.append((draft_id, command.version, key))
            return OutcomeUnknown(code=code)

        def dossier(self, context, draft_id):
            calls.append("dossier")
            return BusinessDossier(
                draft_id=draft_id,
                version=2,
                space_id=space,
                space_name="Shop",
                accounts=(),
                capabilities={"read", "prepare", "approve"},
                review_state="accepting",
                facts=BusinessFacts(),
                sources=(),
                questions=(),
                history=(),
                blockers=(),
                approval_available=False,
            )

    setattr(UnsettledDraft, service_method, UnsettledDraft.unsettled)
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "test-actions"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        UnsettledDraft(), actor
    )
    with TestClient(app) as client:
        response = client.request(
            method,
            f"/business/drafts/{draft}/{path}",
            json={"version": 1, **body},
            headers={"Idempotency-Key": "unsettled"},
        )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert calls == [(draft, 1, "unsettled")]

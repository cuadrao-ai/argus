from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from argus.api import business_annotations
from argus.api.business import require_business_surface
from argus.api.business_drafts import DraftContext, require_drafts
from argus.domain.business.annotations import NoteResult
from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import AttachmentSource, BusinessDossier
from argus.domain.business.contracts.facts import BusinessFacts
from argus.domain.business.supporting_files import (
    SupportingLinkCommand,
    SupportingLinkResult,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


class NoteService:
    authority = object()

    def __init__(self, owner: UUID, space: UUID, dossier: BusinessDossier):
        self.owner, self.space, self.view = owner, space, dossier

    def context_for_draft(self, actor, draft, **_pin):
        return ActionContext(
            actor=TrustedActor(actor_id=actor, actor_kind="member", space_id=self.space),
            grant_id=uuid4(),
            owner_id=str(self.owner),
            space_name="Shop",
            current_owner_id=str(self.owner),
        )

    def dossier(self, actor, draft):
        return self.view


def _view(space: UUID, *sources: AttachmentSource) -> BusinessDossier:
    return BusinessDossier(
        draft_id=uuid4(),
        version=4,
        space_id=space,
        space_name="Shop",
        accounts=(),
        capabilities={"read"},
        review_state="open",
        facts=BusinessFacts(),
        sources=sources,
        questions=(),
        history=(),
        blockers=(),
        approval_available=False,
    )


def _app(owner: UUID, space: UUID, view: BusinessDossier) -> FastAPI:
    app = FastAPI()
    app.include_router(business_annotations.router)
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        NoteService(owner, space, view), owner
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "annotations-api"
        return await call_next(request)

    return app


def test_current_note_answers_the_dossier_with_its_channels(monkeypatch) -> None:
    """The note's answer reads the captured set keyed on the Business owner, as
    every other dossier answer does, so a WhatsApp original stays WhatsApp."""

    owner, space = uuid4(), uuid4()
    original = AttachmentSource(
        id=uuid4(),
        channel="web",
        received_at=datetime.now(timezone.utc),
        connection_id=uuid4(),
        filename="recibo.jpg",
        media_type="image/jpeg",
    )
    view = _view(space, original)
    asked = []

    def captured(owner_id):
        asked.append(owner_id)
        return frozenset({str(original.connection_id)})

    monkeypatch.setattr("argus.api.business_drafts._captured", captured)
    monkeypatch.setattr("argus.api.email_intake.email_receipt_flags", lambda space_id: {})
    monkeypatch.setattr(
        business_annotations,
        "edit_note",
        lambda authority, actor, draft_id, body, key: NoteResult(
            draft_id=draft_id, version=body.expected_version + 1, note=body.note
        ),
    )
    with TestClient(_app(owner, space, view)) as client:
        response = client.put(
            f"/drafts/{view.draft_id}/current-note",
            json={"expected_version": 4, "note": "Pagado en efectivo"},
            headers={"Idempotency-Key": "note"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["note"] == "Pagado en efectivo"
    assert [s["channel"] for s in body["dossier"]["sources"]] == ["whatsapp"]
    assert asked == [str(owner)]


@pytest.mark.parametrize(
    ("method", "suffix", "action", "outcome"),
    [
        ("DELETE", "", "unlink_supporting_file", "unlinked"),
        ("POST", "/restore", "restore_supporting_file", "restored"),
    ],
)
def test_supporting_file_link_routes_send_one_command_and_answer_the_dossier(
    monkeypatch, method, suffix, action, outcome
) -> None:
    owner, space, source_id = uuid4(), uuid4(), uuid4()
    view = _view(space)
    sent = []

    def change(authority, actor, command, key):
        sent.append((command, key))
        return SupportingLinkResult(
            draft_id=command.draft_id,
            version=command.expected_version + 1,
            outcome=outcome,
            source_id=command.source_id,
        )

    monkeypatch.setattr("argus.api.business_drafts._captured", lambda owner_id: frozenset())
    monkeypatch.setattr("argus.api.email_intake.email_receipt_flags", lambda space_id: {})
    monkeypatch.setattr(business_annotations, "change_file_link", change)
    path = f"/drafts/{view.draft_id}/supporting-files/{source_id}{suffix}"
    with TestClient(_app(owner, space, view)) as client:
        response = client.request(
            method, path, headers={"Idempotency-Key": "k", "X-Draft-Version": "4"}
        )
        unversioned = client.request(method, path, headers={"Idempotency-Key": "k"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["result"] == {
        "draft_id": str(view.draft_id),
        "version": 5,
        "outcome": outcome,
        "source_id": str(source_id),
        "purge_at": None,
    }
    assert response.json()["dossier"]["draft_id"] == str(view.draft_id)
    assert sent == [
        (
            SupportingLinkCommand(
                action=action,
                draft_id=view.draft_id,
                expected_version=4,
                source_id=source_id,
            ),
            "k",
        )
    ]
    assert unversioned.status_code == 422


@pytest.mark.parametrize(
    ("outcome", "code", "status"),
    [
        ("invalid_input", "supporting_file_limit_reached", 422),
        ("invalid_input", "supporting_file_restore_expired", 422),
        ("not_found", "supporting_file_not_found", 404),
        ("stale_version", "stale_version", 409),
    ],
)
def test_a_refused_supporting_file_change_answers_its_code(
    monkeypatch, outcome, code, status
) -> None:
    owner, space = uuid4(), uuid4()
    view = _view(space)

    def refuse(authority, actor, command, key):
        raise ActionError(outcome, code)

    monkeypatch.setattr(business_annotations, "change_file_link", refuse)
    with TestClient(_app(owner, space, view)) as client:
        response = client.post(
            f"/drafts/{view.draft_id}/supporting-files/{uuid4()}/restore",
            headers={"Idempotency-Key": "k", "X-Draft-Version": "4"},
        )
    assert (response.status_code, response.json()["detail"]["code"]) == (status, code)

from datetime import datetime, timezone
from uuid import UUID, uuid4

from argus.api import business_annotations
from argus.api.business import require_business_surface
from argus.api.business_drafts import DraftContext, require_drafts
from argus.domain.business.annotations import NoteResult
from argus.domain.business.authority import ActionContext
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import AttachmentSource, BusinessDossier
from argus.domain.business.contracts.facts import BusinessFacts
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
    view = BusinessDossier(
        draft_id=uuid4(),
        version=4,
        space_id=space,
        space_name="Shop",
        accounts=(),
        capabilities={"read"},
        review_state="open",
        facts=BusinessFacts(),
        sources=(original,),
        questions=(),
        history=(),
        blockers=(),
        approval_available=False,
    )
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

    with TestClient(app) as client:
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

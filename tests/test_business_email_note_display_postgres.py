"""With email receiving off, the note-edit and capture responses still carry
the sender note, read from Postgres (the display paths beside approve)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api import email_intake as intake_api
from argus.api.business import require_business_person, require_business_surface
from argus.api.business_annotations import router as annotations_router
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.documents import require_saved_documents
from argus.api.routers.business_manual import router as manual_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_email_intake_postgres as shared
from tests.test_business_email_intake_postgres import FORGED, NOTE, deliver, prepare

actions = shared.actions
users = shared.users
rig = shared.rig
receipts = shared.receipts
pytestmark = shared.pytestmark


def _http(receipts):  # noqa: ANN001, ANN202
    service, context = receipts["service"], receipts["context"]
    app = FastAPI()
    app.include_router(annotations_router, prefix="/business")
    app.include_router(manual_router)

    @app.middleware("http")
    async def identify(request, call_next):  # noqa: ANN001, ANN202
        request.state.request_id = str(uuid4())
        return await call_next(request)

    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, receipts["space"]
    )
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        spaces=None
    )
    app.dependency_overrides[require_saved_documents] = lambda: receipts["documents"]
    return TestClient(app)


def _send_note(http, draft_id, version):  # noqa: ANN001, ANN202
    return http.put(
        f"/business/drafts/{draft_id}/current-note",
        json={"expected_version": version, "note": "revisar"},
        headers={"Idempotency-Key": str(uuid4())},
    )


def _send_capture(http, draft_id, version):  # noqa: ANN001, ANN202
    return http.post(
        "/business/captures",
        json={"text": "otra nota", "draft": {"draft_id": draft_id, "version": version}},
        headers={"Idempotency-Key": str(uuid4())},
    )


@pytest.mark.owner_acts
@pytest.mark.parametrize(
    ("send", "key"), [(_send_note, "dossier"), (_send_capture, None)]
)
def test_with_email_receiving_off_display_responses_carry_the_note(
    receipts, monkeypatch, send, key
):
    receipts["store"].upsert_sender(
        receipts["space"], "address", receipts["provider"].sender, "authorized"
    )
    attachment = deliver(receipts, FORGED)
    draft_id, _ = prepare(receipts, attachment)
    version = receipts["service"].dossier(receipts["context"], draft_id).version
    monkeypatch.setattr(intake_api, "_runtime", None)
    assert intake_api.email_intake() is None
    with _http(receipts) as http:
        response = send(http, str(draft_id), version)
    assert response.status_code == 200, response.text
    body = response.json()
    dossier = body[key] if key else body
    assert dossier["review_note"] == NOTE

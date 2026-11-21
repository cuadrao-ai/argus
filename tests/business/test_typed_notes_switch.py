"""New typed notes behind one server switch, off by default.

Off, `POST /business/captures` refuses a note that starts a draft, the
workspace says so, and a note added to an existing draft still saves. On, a
typed note starts a draft as before."""

from __future__ import annotations

import pytest

from tests.business.test_actions_capture_api import capture_api  # noqa: F401
from tests.business.test_business_api import Owner, alice  # noqa: F401

SWITCH = "CUADRAO_BUSINESS_TYPED_NOTES_ENABLED"
KEY = {"Idempotency-Key": "typed-note"}


@pytest.fixture
def typed_notes_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set, not deleted: an absent name would be refilled from a worktree .env.
    monkeypatch.setenv(SWITCH, "false")


def test_off_a_new_note_is_refused_and_never_reaches_the_service(
    capture_api,  # noqa: F811, ANN001
    typed_notes_off: None,
) -> None:
    response = capture_api.client.post(
        "/business/captures", json={"text": "Una nota"}, headers=KEY
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "business_typed_notes_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert capture_api.service.calls == []


def test_off_a_note_on_an_existing_draft_still_saves(
    capture_api,  # noqa: F811, ANN001
    typed_notes_off: None,
) -> None:
    draft = capture_api.service.view
    response = capture_api.client.post(
        "/business/captures",
        json={
            "text": "Otra nota",
            "draft": {"draft_id": str(draft.draft_id), "version": draft.version},
        },
        headers=KEY,
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft_id"] == str(draft.draft_id)


def test_on_a_new_note_starts_a_draft(capture_api, typed_notes_on) -> None:  # noqa: F811, ANN001
    response = capture_api.client.post(
        "/business/captures", json={"text": "Una nota"}, headers=KEY
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft_id"] == str(capture_api.service.view.draft_id)


def test_the_workspace_reports_the_switch(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SWITCH, "false")
    assert alice.get("/workspace").json()["typed_notes_available"] is False
    monkeypatch.setenv(SWITCH, "true")
    assert alice.get("/workspace").json()["typed_notes_available"] is True

"""A saved Personal document stays readable and removable while intake is off.

Turning document extraction or ingestion off stops new intake only: the owner
can still list, open, download and disconnect what they already saved.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.document_jobs import document_jobs, sweep_forever
from argus.api.documents import documents_service
from argus.api.ingestion import ingestion_hub
from argus.api.main import app
from argus.domain.ingestion.documents.objects import owner_prefix
from argus.domain.owner_scope import PERSONAL
from fastapi.testclient import TestClient

from tests.ingestion.conftest import ALICE, bearer
from tests.ingestion.test_documents_api import (  # noqa: F401
    DOCUMENTS,
    extraction,
    upload,
)

CONNECTIONS = "/api/v1/financial-connections"
RECEIPT = (
    Path(__file__).parents[1] / "document_extraction_fixtures/receipt-dop.png"
).read_bytes()


def _stored(user_id: str) -> int:
    objects = documents_service().store.objects
    return sum(path.startswith((owner_prefix(user_id), f"sealed/{user_id}/", f"rebuilt/{user_id}/")) for path in objects.objects)


def _saved(client) -> str:
    saved = upload(client, **{"X-Extraction-Consent": "false"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "saved"
    return saved.json()["connection_id"]


def _code(response) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


def test_extraction_off_keeps_reading_and_removal_and_refuses_intake(
    client,
    extraction,  # noqa: F811
    identities,
    monkeypatch,
):
    alice = identities[ALICE]["id"]
    document = _saved(client)
    assert _stored(alice) == 1
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "false")

    listed = client.get(DOCUMENTS, headers=bearer(ALICE))
    assert listed.status_code == 200, listed.text
    assert [item["connection_id"] for item in listed.json()["items"]] == [document]
    opened = client.get(f"{DOCUMENTS}/{document}", headers=bearer(ALICE))
    assert (opened.status_code, opened.json()["status"]) == (200, "saved")
    source = client.get(f"{DOCUMENTS}/{document}/source", headers=bearer(ALICE))
    assert source.json()["code"] == "document_source_unavailable"

    unavailable = (404, "financial_connections_unavailable")
    assert _code(upload(client)) == unavailable
    for action in ("prepare", "resume"):
        assert (
            _code(client.post(f"{DOCUMENTS}/{document}/{action}", headers=bearer(ALICE)))
            == unavailable
        )
    edit = client.patch(
        f"{DOCUMENTS}/{document}/proposal",
        json={"version": 1, "proposal": {}},
        headers=bearer(ALICE),
    )
    assert _code(edit) == unavailable

    removed = client.post(f"{CONNECTIONS}/{document}/disconnect", headers=bearer(ALICE))
    assert removed.status_code == 200, removed.text
    assert _stored(alice) == 0
    assert client.get(DOCUMENTS, headers=bearer(ALICE)).json()["items"] == []
    assert extraction.await_count == 0


def test_ingestion_off_still_reads_and_removes_only_a_document(
    client,
    extraction,  # noqa: F811
    identities,
    monkeypatch,
):
    alice = identities[ALICE]["id"]
    document = _saved(client)
    mailbox = documents_service().hub.connections.create(
        user_id=alice,
        source="gmail",
        external_ref="alice@example.test",
        label=None,
        now=datetime.now(timezone.utc),
        scope=PERSONAL,
    )
    monkeypatch.setenv("ARGUS_INGESTION_ENABLED", "false")

    source = client.get(f"{DOCUMENTS}/{document}/source", headers=bearer(ALICE))
    assert source.json()["code"] == "document_source_unavailable"
    assert _code(client.get(CONNECTIONS, headers=bearer(ALICE))) == (
        404,
        "financial_connections_unavailable",
    )
    refused = client.post(f"{CONNECTIONS}/{mailbox.id}/disconnect", headers=bearer(ALICE))
    assert _code(refused) == (404, "financial_connections_unavailable")
    assert (
        documents_service()
        .hub.connections.get(user_id=alice, connection_id=mailbox.id, scope=PERSONAL)
        .status
        != "disconnected"
    )

    for _attempt in range(2):
        removed = client.post(
            f"{CONNECTIONS}/{document}/disconnect", headers=bearer(ALICE)
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["connection"]["status"] == "disconnected"
    assert _stored(alice) == 0
    assert extraction.await_count == 0


def test_ingestion_off_at_start_serves_reading_and_removal_only(
    surface_env, gateway, monkeypatch
):
    monkeypatch.setenv("ARGUS_INGESTION_ENABLED", "false")
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("ARGUS_DOCUMENT_JOBS_ENABLED", "true")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        assert ingestion_hub() is None
        assert document_jobs() is None
        assert documents_service() is not None
        listed = client.get(DOCUMENTS, headers=bearer(ALICE))
        assert (listed.status_code, listed.json()["items"]) == (200, [])
        assert _code(upload(client)) == (404, "financial_connections_unavailable")
        missing = client.post(
            f"{CONNECTIONS}/00000000-0000-4000-8000-000000000000/disconnect",
            headers=bearer(ALICE),
        )
        assert _code(missing) == (404, "financial_connection_not_found")
        assert client.get(DOCUMENTS).status_code == 401


@pytest.mark.asyncio
async def test_the_preparation_sweep_waits_while_extraction_is_off(monkeypatch):
    """A queued draft is neither dispatched nor failed while extraction is off."""

    sweeps: list[str] = []

    class Jobs:
        def sweep(self) -> None:
            sweeps.append(os.environ["ARGUS_DOCUMENT_EXTRACTION_ENABLED"])

    for flag in ("false", "true"):
        monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", flag)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sweep_forever(Jobs(), 0.01), 0.1)
    assert set(sweeps) == {"true"}

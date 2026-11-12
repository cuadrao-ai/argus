from __future__ import annotations

import json
from typing import Any

from argus.api.main import app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _stream_payloads(stream: str, event_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for part in stream.split("\n\n"):
        data_line = next(
            (line for line in part.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line is None:
            continue
        raw = data_line.removeprefix("data: ").strip()
        if raw == "[DONE]":
            continue
        event = json.loads(raw)
        if event.get("type") == event_type:
            payloads.append(event.get("payload", event))
    return payloads


def _conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/conversations", json={"language": "en"})
    assert response.status_code == 200
    return response.json()["conversation"]


def _user_id(client: TestClient) -> str:
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    return str(response.json()["user"]["id"])


def test_artifact_metadata_fields_are_backward_compatible() -> None:
    from argus.agent_runtime.state.models import ArtifactReference, TaskSnapshot

    reference = ArtifactReference(
        artifact_kind="confirmation",
        artifact_id="confirm-1",
        artifact_status="active",
        metadata={"confirmation_id": "confirm-1"},
    )
    snapshot = TaskSnapshot(
        active_confirmation_reference=reference,
        artifact_references=[reference],
    )

    assert snapshot.active_confirmation_reference.artifact_id == "confirm-1"
    assert snapshot.artifact_references[0].artifact_status == "active"




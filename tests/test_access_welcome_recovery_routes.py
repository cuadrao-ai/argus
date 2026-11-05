"""Route-level recovery proofs for the access-approval welcome path."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from argus.api import state as api_state
from argus.domain.access_approval_email import AccessWelcomeSendResult
from test_access_approval_email import (  # noqa: E402
    _StatefulApprovalGateway,
    client,
)


def test_internal_approval_stale_delivery_falls_through_to_a_fresh_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # State this route did not create: a delivery row from an earlier grant
    # next to a fresh requested row. The approval must send a new welcome
    # instead of silently promoting or hard-409ing.
    from argus.api.routers import ops

    gateway = _StatefulApprovalGateway(language="es-419")
    gateway.deliveries["person@example.com"] = {
        "recipient_email": "person@example.com",
        "language": "en",
        "content_version": "private-alpha-access-welcome/v1",
        "subject": "Welcome to Argus",
        "provider_receipt": "stale-receipt",
        "sent_at": "2026-08-01T00:00:00Z",
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    send_count = 0

    def _send(**kwargs: object) -> AccessWelcomeSendResult:
        nonlocal send_count
        send_count += 1
        gateway.events.append("send")
        return AccessWelcomeSendResult(
            subject="Bienvenido a Argus",
            content_version="private-alpha-access-welcome/v1",
            provider_receipt="fresh-receipt",
        )

    monkeypatch.setattr(ops, "send_access_welcome_email", _send)

    response = client.post(
        "/internal/access-requests/approve",
        json={"email": "person@example.com"},
        headers={"Authorization": "Bearer ops-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"approved": True}
    assert send_count == 1
    assert gateway.role == "user"
    delivery = gateway.deliveries["person@example.com"]
    assert delivery["language"] == "es-419"
    assert delivery["provider_receipt"] == "fresh-receipt"


def test_internal_approval_failures_log_the_stage_and_nothing_identifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import ops
    from loguru import logger

    gateway = _StatefulApprovalGateway()
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setenv("CUADRAO_OPS_TOKEN", "ops-token")
    monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://app.example")
    monkeypatch.setattr(
        ops,
        "send_access_welcome_email",
        MagicMock(side_effect=RuntimeError("smtp unavailable")),
    )
    records: list[object] = []
    handler_id = logger.add(lambda message: records.append(message.record))
    try:
        response = client.post(
            "/internal/access-requests/approve",
            json={"email": "person@example.com"},
            headers={"Authorization": "Bearer ops-token"},
        )
    finally:
        logger.remove(handler_id)

    assert response.status_code == 503
    stages = [
        record["extra"].get("stage")
        for record in records
        if record["message"] == "access approval failed"
    ]
    assert stages == ["smtp"]
    for record in records:
        rendered = f"{record['message']} {record['extra']}"
        assert "person@example.com" not in rendered
        assert "fresh-receipt" not in rendered
        assert "11111111-1111-4111-8111-111111111111" not in rendered

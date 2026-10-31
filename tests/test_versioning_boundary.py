"""§3.6: a confirmed run mints exactly one IdeaVersion; edits mint nothing.

Material change is defined once, in DATA_MODEL.md's idea_versions boundary,
and consumed by comparison. Pending-card edits, however many, must leave the
version history untouched or the user's record fills with phantom versions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.chat.confirmation import runtime_confirmation_card
from argus.api.main import app
from argus.api.message_store import create_message
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _in_place_surface_enabled(monkeypatch):
    """These tests exercise the in-place surface, which ships default-off
    behind ARGUS_IN_PLACE_CARD_EDITS_ENABLED until the consumption guard
    lane closes."""
    monkeypatch.setenv("ARGUS_IN_PLACE_CARD_EDITS_ENABLED", "true")


CONFIRMATION_ID = "44444444-4444-4444-8444-444444444444"


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _confirmation_payload() -> dict[str, Any]:
    return {
        "confirmation_id": CONFIRMATION_ID,
        "artifact_id": CONFIRMATION_ID,
        "strategy": {
            "strategy_type": "buy_and_hold",
            "asset_universe": ["NFLX"],
            "asset_class": "equity",
            "timeframe": "1D",
            "date_range": {"start": "2023-01-02", "end": "2023-06-30"},
            "sizing_mode": "capital_amount",
            "capital_amount": 10000,
        },
        "optional_parameters": {},
        "launch_payload": {
            "strategy_type": "buy_and_hold",
            "symbol": "NFLX",
            "symbols": ["NFLX"],
            "asset_class": "equity",
            "timeframe": "1D",
            "date_range": {"start": "2023-01-02", "end": "2023-06-30"},
            "sizing_mode": "capital_amount",
            "capital_amount": 10000,
            "parameters": {},
            "risk_rules": [],
            "benchmark_symbol": "SPY",
            "language": "en",
        },
        "validation": {"status": "ready_to_run", "executable": True},
    }


def test_direct_edits_mint_no_idea_versions() -> None:
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    user_id = client.get("/api/v1/me").json()["user"]["id"]
    payload = _confirmation_payload()
    card = runtime_confirmation_card(
        {"stage_outcome": "await_approval", "confirmation_payload": payload},
        confirmation_id=CONFIRMATION_ID,
        conversation_id=conversation["id"],
        language="en",
    )
    assert card is not None
    create_message(
        user_id=user_id,
        conversation_id=conversation["id"],
        role="assistant",
        content=str(card.get("summary") or ""),
        metadata={
            "conversation_mode": "confirm",
            "confirmation_card": card,
            "confirmation_payload": payload,
        },
        settle_usage=None,
    )
    assert api_state.store.idea_versions == {}

    active_id = CONFIRMATION_ID
    for edit in (
        {"capital": 25000},
        {"date_window": {"start": "2023-02-01", "end": "2023-05-31"}},
        {"capital": 5000, "date_window": {"start": "2023-03-01", "end": "2023-06-30"}},
    ):
        response = client.post(
            f"/api/v1/conversations/{conversation['id']}/confirmations/"
            f"{active_id}/direct-edit",
            json=edit,
        )
        assert response.status_code == 200, response.text
        active_id = response.json()["message"]["metadata"]["confirmation_card"][
            "confirmation_id"
        ]

    assert (
        api_state.store.idea_versions == {}
    ), "edits to a pending card mint nothing, however many there are"
    assert api_state.store.ideas == {}


def test_only_the_run_finalization_boundary_mints_versions() -> None:
    """Source-level guard: the IdeaVersion writer has exactly the two
    run-completion callers. An edit path importing it is the defect this
    catches before it ships."""
    root = Path(__file__).resolve().parents[1] / "src"
    callers: set[str] = set()
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if (
            "finalize_completed_backtest" in text
            or "finalize_completed_direct_backtest" in text
        ):
            callers.add(str(path.relative_to(root)))
    assert callers == {
        "argus/api/chat/evidence.py",
        "argus/api/chat/persistence.py",
    }, f"unexpected IdeaVersion finalization callers: {sorted(callers)}"

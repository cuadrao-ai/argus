"""A tool answer survives delivery and reload without minting a backtest."""

from __future__ import annotations

from typing import Any

import pytest
from argus.domain.tool_contracts import ToolResultCard
from faker import Faker

fake = Faker()


def card_document(*, call_id: str | None = None) -> dict[str, Any]:
    """Test-only identity output; deliberately no financial computation."""
    return ToolResultCard.model_validate(
        {
            "kind": "tool_result",
            "schema_version": 1,
            "tool_name": "identity_value",
            "call_id": call_id or fake.uuid4(),
            "artifact_id": fake.uuid4(),
            "input_revision": 0,
            "card_type": "identity_value",
            "card_version": 1,
            "arguments": {"known": 0, "unknown": None},
            "outcome": {"status": "succeeded", "result": {"value": 0}, "failure": None},
            "presentation": {
                "title": {
                    "locale_key": "chat.tools.identity.title",
                    "interpolation_args": {},
                },
                "answer": {
                    "name": "value",
                    "label": {
                        "locale_key": "chat.tools.identity.value",
                        "interpolation_args": {},
                    },
                    "value": 0,
                    "unit": None,
                },
                "rows": [],
                "inputs": [],
                "notes": [],
            },
            "artifact_state": "active",
        }
    ).model_dump(mode="json")


def test_publication_refuses_ambiguous_duplicate_card_identity() -> None:
    from argus.api.chat.tool_results import runtime_tool_result_cards

    card = card_document()
    with pytest.raises(ValueError):
        runtime_tool_result_cards(
            {"final_response_payload": {"tool_result_cards": [card, card]}}
        )


@pytest.mark.parametrize("mismatch", ["duplicate_call", "wrong_artifact"])
def test_invalid_private_effect_batch_dispatches_nothing(monkeypatch, mismatch) -> None:
    from argus.api.chat import research_jobs
    from argus.api.chat.tool_results import apply_runtime_tool_effects

    card = card_document()
    effects = [
        {
            "call_id": card["call_id"],
            "tool_name": card["tool_name"],
            "artifact_id": card["artifact_id"],
            "stage_patch": {"research_job_request": {}},
        }
    ]
    if mismatch == "duplicate_call":
        effects.append(effects[0])
    else:
        effects[0]["artifact_id"] = fake.uuid4()
    calls = []
    monkeypatch.setattr(
        research_jobs,
        "apply_research_job_request",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    with pytest.raises(ValueError):
        apply_runtime_tool_effects(
            {"tool_result_cards": [card]},
            effects,
            user_id=fake.uuid4(),
            conversation_id=fake.uuid4(),
            request_message_id=fake.uuid4(),
            request_id=fake.uuid4(),
        )
    assert calls == []


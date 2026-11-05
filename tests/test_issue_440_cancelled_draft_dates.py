"""Issue #440: after a drawer edit, every later turn publishes its own card.

The runtime checkpoint's workflow-level ``confirmation_payload`` channel is
the launch hand-off between interpret and execute, and it is turn-scoped like
every other stage output. The pending card's runtime owners are the task
snapshot and the run state. The drawer edit once parked the edited card in that
channel, which outlived its turn and was published over every later card in the
conversation: a stated six-month window after a cancelled drawer-edited draft
vanished with no disclosure, and so would any typed unapplied-change record
(confirmation edit contract, section 3.2).
"""

from __future__ import annotations

from typing import Any

import pytest
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.graph.workflow import _apply_stage_result, build_workflow
from argus.agent_runtime.stages.interpret import (
    InterpretationRequest,
    StageResult,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import RunState, StrategySummary, UserState
from argus.api import state as api_state
from argus.api.main import app

from tests.test_chat_stream_contract import _final_payload
from tests.test_confirmation_direct_edit import _conversation, _direct_edit

IDEA_WINDOW = {"start": "2023-01-02", "end": "2023-12-29"}
DRAWER_WINDOW = {"start": "2022-08-11", "end": "2023-12-29"}
SIX_MONTH_WINDOW = {"start": "2023-07-03", "end": "2023-12-29"}
UNAPPLIED_DATE_WINDOW = {
    "op": "set",
    "target": "date_window",
    "reason": "unsupported_operation",
}


@pytest.fixture(autouse=True)
def _in_place_surface_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drawer ships default-off behind ARGUS_IN_PLACE_CARD_EDITS_ENABLED."""
    monkeypatch.setenv("ARGUS_IN_PLACE_CARD_EDITS_ENABLED", "true")


class _ScriptedInterpreter:
    """Plays back one typed interpretation per turn, in order."""

    def __init__(self, interpretations: list[StructuredInterpretation]) -> None:
        self._queue = list(interpretations)

    async def ainvoke(self, request: InterpretationRequest) -> StructuredInterpretation:
        del request
        return self._queue.pop(0)


def _idea_interpretation() -> StructuredInterpretation:
    return StructuredInterpretation(
        intent="backtest_execution",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="Buy and hold Apple for a year.",
        candidate_strategy_draft=StrategySummary(
            raw_user_phrasing="Buy and hold Apple for the last year with $10,000",
            strategy_type="buy_and_hold",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range=dict(IDEA_WINDOW),
            capital_amount=10000,
            extra_parameters={
                "date_range_intent": {"kind": "explicit_range", **IDEA_WINDOW},
                "field_provenance": {"date_range": "explicit_user"},
            },
        ),
        semantic_turn_act="new_idea",
    )


def _stated_duration_applied() -> StructuredInterpretation:
    """The interpreter read the six-month window; the turn must apply it."""
    return StructuredInterpretation(
        intent="strategy_drafting",
        task_relation="refine",
        requires_clarification=False,
        user_goal_summary="Run the Apple idea again for the last six months.",
        candidate_strategy_draft=StrategySummary(
            raw_user_phrasing="Run that Apple idea again for the last six months",
            strategy_type="buy_and_hold",
            asset_universe=["AAPL"],
            asset_class="equity",
            date_range=dict(SIX_MONTH_WINDOW),
            capital_amount=10000,
            extra_parameters={
                "date_range_intent": {"kind": "explicit_range", **SIX_MONTH_WINDOW},
                "field_provenance": {"date_range": "explicit_user"},
            },
        ),
        semantic_turn_act="refine_current_idea",
    )


def _stated_duration_refused() -> StructuredInterpretation:
    """The edit planner could not apply the window; the typed record must ride."""
    return StructuredInterpretation(
        intent="backtest_execution",
        task_relation="continue",
        requires_clarification=False,
        user_goal_summary="User changed a visible confirmation assumption.",
        candidate_strategy_draft=StrategySummary(
            raw_user_phrasing="Run that Apple idea again for the last six months",
            strategy_type="buy_and_hold",
            extra_parameters={
                "edit_disclosure": {"unapplied": [dict(UNAPPLIED_DATE_WINDOW)]},
            },
        ),
        reason_codes=["artifact_assumption_edit_planned"],
        semantic_turn_act="answer_pending_need",
    )


def _install_scripted_runtime(
    monkeypatch: pytest.MonkeyPatch,
    interpretations: list[StructuredInterpretation],
) -> None:
    checkpointer = api_state.build_agent_runtime_checkpointer()
    workflow = build_workflow(
        contract=build_default_capability_contract(),
        structured_interpreter=_ScriptedInterpreter(interpretations),
        checkpointer=checkpointer,
    )
    monkeypatch.setattr(
        app.state, "agent_runtime_checkpointer", checkpointer, raising=False
    )
    monkeypatch.setattr(app.state, "agent_runtime_workflow", workflow, raising=False)


def _turn(client: Any, conversation_id: str, message: str, **extra: Any) -> dict:
    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": conversation_id, "message": message, **extra},
    )
    assert response.status_code == 200, response.text
    return _final_payload(response.text)


def _cancel_action(confirmation_id: str, conversation_id: str) -> dict[str, Any]:
    return {
        "type": "cancel_confirmation",
        "label": "Cancel",
        "presentation": "confirmation",
        "payload": {
            "confirmation_id": confirmation_id,
            "artifact_id": confirmation_id,
            "conversation_id": conversation_id,
        },
    }


def _cancelled_drawer_edited_draft(
    client: Any,
    monkeypatch: pytest.MonkeyPatch,
    follow_up: StructuredInterpretation,
) -> tuple[dict[str, Any], str]:
    """The issue's interleaving: idea, drawer date edit, cancel, follow-up."""
    _install_scripted_runtime(monkeypatch, [_idea_interpretation(), follow_up])
    conversation = _conversation(client)
    idea = _turn(
        client,
        conversation["id"],
        "Buy and hold Apple for the last year with $10,000",
    )
    assert idea["stage_outcome"] == "await_approval"
    card = idea["confirmation"]
    confirmation_id = str(card.get("confirmation_id") or card.get("confirmationId"))

    edited = _direct_edit(
        client, conversation["id"], confirmation_id, {"date_window": DRAWER_WINDOW}
    )
    assert edited.status_code == 200, edited.text
    edited_strategy = edited.json()["message"]["metadata"]["confirmation_payload"][
        "strategy"
    ]
    assert edited_strategy["date_range"] == DRAWER_WINDOW

    cancelled = _turn(
        client,
        conversation["id"],
        "Cancel",
        action=_cancel_action(confirmation_id, conversation["id"]),
    )
    assert cancelled["confirmation_cancelled"] == {"confirmation_id": confirmation_id}

    final = _turn(
        client,
        conversation["id"],
        "Run that Apple idea again for the last six months",
    )
    return final, confirmation_id


def _persisted_card_payload(client: Any, conversation_id: str) -> dict[str, Any]:
    messages = client.get(f"/api/v1/conversations/{conversation_id}/messages").json()[
        "items"
    ]
    return messages[-1]["metadata"]["confirmation_payload"]


def _conversation_of(client: Any) -> str:
    conversations = client.get("/api/v1/conversations").json()["items"]
    assert len(conversations) == 1
    return conversations[0]["id"]


def test_launch_hand_off_channel_is_turn_scoped() -> None:
    """A stale card in the channel dies with the first stage of the next turn,
    while the launch hand-off a stage writes survives to the execute node."""
    stale_card = {"strategy": {"strategy_type": "buy_and_hold"}, "launch_payload": {}}
    state = {
        "run_state": RunState.new(current_user_message="x", recent_thread_history=[]),
        "user": UserState(user_id="user-440"),
        "confirmation_payload": stale_card,
    }

    cleared = _apply_stage_result(
        state, StageResult(outcome="ready_for_confirmation", stage_patch={})
    )
    assert cleared["confirmation_payload"] is None

    launch_request = {
        "strategy_type": "buy_and_hold",
        "symbol": "AAPL",
        "timeframe": "1D",
        "date_range": dict(IDEA_WINDOW),
        "sizing_mode": "capital_amount",
        "benchmark_symbol": "SPY",
    }
    handed_off = _apply_stage_result(
        state,
        StageResult(
            outcome="approved_for_execution",
            stage_patch={"confirmation_payload": launch_request},
        ),
    )
    assert handed_off["confirmation_payload"] == launch_request

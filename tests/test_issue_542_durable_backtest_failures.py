from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from argus.agent_runtime.stages.execute import execute_stage
from argus.agent_runtime.state.models import RunState
from argus.api.chat.artifacts import ensure_unspent_confirmation_identity
from argus.api.chat.backtest_jobs import (
    BacktestJobShadowContext,
    ShadowBacktestJobTool,
    backtest_job_shadow_context,
)
from argus.api.main import app
from argus.domain.market_data.new_york_clock import new_york_today
from argus.domain.research.admission import (
    ResearchAttemptAdmission,
    claim_current_research_attempt,
)
from fastapi import Request
from fastapi.testclient import TestClient

CONVERSATION_ID = "91931579-0cc8-4fa0-bedd-726abb0afa9c"
SPENT_CONFIRMATION_ID = "confirmation-17470c6c-83e9-4305-bf6d-645ec3a40be9"
SYMBOLS = ["NVDA", "MSFT", "PLTR", "GOOGL", "AMZN"]


def _today_launch_payload() -> dict[str, Any]:
    today = new_york_today()
    return {
        "strategy_type": "buy_and_hold",
        "symbol": SYMBOLS[0],
        "symbols": SYMBOLS,
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": {
            "start": (today - timedelta(days=3 * 365)).isoformat(),
            "end": today.isoformat(),
        },
        "capital_amount": 100_000,
        "sizing_mode": "capital_amount",
        "benchmark_symbol": "SPY",
        "language": "en",
    }


def _confirmation_result() -> dict[str, Any]:
    launch_payload = _today_launch_payload()
    confirmation_payload = {
        "confirmation_id": SPENT_CONFIRMATION_ID,
        "artifact_id": SPENT_CONFIRMATION_ID,
        "strategy": {
            "strategy_type": "buy_and_hold",
            "asset_universe": SYMBOLS,
            "asset_class": "equity",
            "date_range": launch_payload["date_range"],
            "capital_amount": 100_000,
            "comparison_baseline": "SPY",
        },
        "optional_parameters": {},
        "launch_payload": launch_payload,
        "validation": {"status": "ready_to_run", "executable": True},
    }
    return {
        "stage_outcome": "await_approval",
        "confirmation_payload": confirmation_payload,
        "artifact_references": [
            {
                "artifact_kind": "confirmation",
                "artifact_id": SPENT_CONFIRMATION_ID,
                "metadata": {
                    "confirmation_id": SPENT_CONFIRMATION_ID,
                    "confirmation_payload": confirmation_payload,
                },
            }
        ],
    }


class _SpentReservationGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_backtest_job_reservation(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "id": "cc6b042e-earlier-three-symbol-job",
            "idempotency_key": SPENT_CONFIRMATION_ID,
            "status": "succeeded",
            "result_run_id": "269ef-earlier-three-symbol-run",
            "launch_payload": {
                "request": {
                    "symbols": ["NVDA", "MSFT", "PLTR"],
                    "capital_amount": 1_000,
                }
            },
        }


class _UnspentReservationGateway:
    def get_backtest_job_reservation(self, **kwargs: Any) -> None:
        del kwargs
        return None


def test_unspent_confirmation_identity_is_preserved() -> None:
    runtime_result = _confirmation_result()

    def fail_new_id() -> str:
        raise AssertionError("an unused identity must not be replaced")

    confirmation_id = ensure_unspent_confirmation_identity(
        runtime_result,
        gateway=_UnspentReservationGateway(),
        user_id="user-542",
        new_id=fail_new_id,
    )

    assert confirmation_id == SPENT_CONFIRMATION_ID
    assert runtime_result["confirmation_payload"]["confirmation_id"] == (
        SPENT_CONFIRMATION_ID
    )


def test_spent_confirmation_identity_rotates_before_today_card_is_published() -> None:
    gateway = _SpentReservationGateway()
    runtime_result = _confirmation_result()

    confirmation_id = ensure_unspent_confirmation_identity(
        runtime_result,
        gateway=gateway,
        user_id="user-542",
        new_id=lambda: "confirmation-fresh-five-symbol-run",
    )

    assert confirmation_id == "confirmation-fresh-five-symbol-run"
    payload = runtime_result["confirmation_payload"]
    assert payload["confirmation_id"] == confirmation_id
    assert payload["artifact_id"] == confirmation_id
    assert payload["launch_payload"]["symbols"] == SYMBOLS
    assert payload["launch_payload"]["capital_amount"] == 100_000
    assert payload["launch_payload"]["date_range"]["end"] == new_york_today().isoformat()
    reference = runtime_result["artifact_references"][0]
    assert reference["artifact_id"] == confirmation_id
    assert reference["metadata"]["confirmation_id"] == confirmation_id
    assert reference["metadata"]["confirmation_payload"] is payload
    assert gateway.calls == [
        {
            "user_id": "user-542",
            "operation_scope": "chat.run_backtest",
            "idempotency_key": SPENT_CONFIRMATION_ID,
        }
    ]


class _ConflictReceiptGateway:
    def __init__(self) -> None:
        self.earlier_job = {
            "id": "cc6b042e-earlier-three-symbol-job",
            "status": "succeeded",
            "result_run_id": "269ef-earlier-three-symbol-run",
            "failure_code": None,
            "failure_detail": None,
        }
        self.failure_receipts: list[dict[str, Any]] = []
        self.admission_calls: list[dict[str, Any]] = []

    def get_backtest_job_reservation(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return self.earlier_job

    def admit_backtest_job(self, **kwargs: Any) -> dict[str, str]:
        self.admission_calls.append(kwargs)
        return {"decision": "conflict"}

    def record_backtest_job_rejection(self, **kwargs: Any) -> dict[str, Any]:
        rejected_key = kwargs.pop("rejected_idempotency_key")
        execution_metadata = {
            **kwargs.pop("execution_metadata"),
            "rejected_idempotency_key": rejected_key,
        }
        receipt = {
            "id": "job-542-failed-before-start",
            "status": "failed",
            "idempotency_key": "rejection:issue-542",
            "execution_metadata": execution_metadata,
            **kwargs,
        }
        self.failure_receipts.append(receipt)
        return receipt


def test_conflicting_today_launch_records_reason_and_drives_user_copy(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    gateway = _ConflictReceiptGateway()
    launch_payload = _today_launch_payload()
    context = BacktestJobShadowContext(
        user_id="user-542",
        conversation_id=CONVERSATION_ID,
        account_kind="registered",
        request_message_id="message-542-run-request",
        confirmation_message_id="message-542-confirmation",
        idempotency_key=SPENT_CONFIRMATION_ID,
        request_id="request-542",
        chat_action={
            "type": "run_backtest",
            "payload": {"confirmation_id": SPENT_CONFIRMATION_ID},
        },
    )
    tool = ShadowBacktestJobTool(
        delegate=None,
        gateway_getter=lambda: gateway,
        dev_memory_fallback_getter=lambda: False,
    )
    state = RunState.new(current_user_message="run it", recent_thread_history=[])
    state.confirmation_payload = launch_payload

    with backtest_job_shadow_context(context):
        result = execute_stage(state=state, tool=tool, max_retries=1)

    assert gateway.earlier_job == {
        "id": "cc6b042e-earlier-three-symbol-job",
        "status": "succeeded",
        "result_run_id": "269ef-earlier-three-symbol-run",
        "failure_code": None,
        "failure_detail": None,
    }
    assert len(gateway.failure_receipts) == 1
    receipt = gateway.failure_receipts[0]
    assert receipt["idempotency_key"].startswith("rejection:")
    assert receipt["idempotency_key"] != SPENT_CONFIRMATION_ID
    assert receipt["execution_metadata"]["rejected_idempotency_key"] == (
        SPENT_CONFIRMATION_ID
    )
    assert receipt["failure_code"] == "idempotency_conflict"
    assert receipt["failure_detail"] == "confirmation_identity_already_spent"
    assert receipt["launch_payload"]["request"]["symbols"] == SYMBOLS
    assert receipt["launch_payload"]["request"]["capital_amount"] == 100_000
    assert receipt["launch_payload"]["request"]["date_range"]["end"] == (
        new_york_today().isoformat()
    )

    assert result.outcome == "execution_failed_terminally"
    assert result.patch["backtest_job"]["id"] == "job-542-failed-before-start"
    assert result.patch["backtest_job"]["failure_code"] == "idempotency_conflict"
    prompt = result.patch["assistant_prompt"]
    assert "already been used for a different setup" in prompt
    assert "fresh confirmation" in prompt
    assert "could not complete" not in prompt
    assert result.patch["backtest_job"]["retryable"] is False
    failed_action = result.patch["latest_failed_action_reference"]
    assert failed_action["metadata"]["retryable"] is True
    assert failed_action["metadata"]["recovery_mode"] == "reopen_confirmation"


def _final_stream_payload(stream: str) -> dict[str, Any]:
    for line in stream.splitlines():
        if not line.startswith("data: {"):
            continue
        event = json.loads(line.removeprefix("data: "))
        if event.get("type") == "final":
            return dict(event["payload"])
    raise AssertionError("chat stream did not emit a final event")


def test_one_request_can_claim_research_then_record_one_admission_refusal(
    monkeypatch,
) -> None:
    """The #544 allowance claim and #542 refusal share one router scope."""
    from argus.api import state as api_state
    from argus.api.dependencies import current_user
    from argus.api.guest_access import (
        guest_account_context,
        store_account_context,
        visitor_key_for_request,
    )
    from argus.api.routers import agent as agent_router
    from argus.domain.guest_workspaces import GuestWorkspace
    from argus.domain.store import utcnow

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_RUNTIME_STREAM_WORKER", "true")

    gateway = _ConflictReceiptGateway()
    claim_guest_keys: list[str | None] = []
    guest_key_inputs: list[dict[str, Any]] = []
    runtime_turn = 0
    derive_guest_key = agent_router.guest_research_visitor_key

    def claim_research(*, guest_visitor_key: str | None) -> ResearchAttemptAdmission:
        claim_guest_keys.append(guest_visitor_key)
        return ResearchAttemptAdmission(available=True)

    def capture_guest_key(**kwargs: Any) -> str | None:
        guest_key_inputs.append(dict(kwargs))
        return derive_guest_key(**kwargs)

    async def runtime_events(**kwargs: Any):
        nonlocal runtime_turn
        del kwargs
        runtime_turn += 1
        if runtime_turn == 1:
            yield {"type": "final", "payload": _confirmation_result()}
            return

        first_claim = claim_current_research_attempt()
        second_claim = claim_current_research_attempt()
        assert first_claim is second_claim

        state = RunState.new(current_user_message="run it", recent_thread_history=[])
        state.confirmation_payload = _today_launch_payload()
        result = execute_stage(
            state=state,
            tool=ShadowBacktestJobTool(
                delegate=None,
                gateway_getter=lambda: gateway,
                dev_memory_fallback_getter=lambda: False,
            ),
            max_retries=1,
        )
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": result.outcome,
                "assistant_response": result.patch["assistant_prompt"],
                "backtest_job": result.patch["backtest_job"],
                "latest_failed_action_reference": result.patch[
                    "latest_failed_action_reference"
                ],
            },
        }

    monkeypatch.setattr(agent_router, "claim_research_provider_attempt", claim_research)
    monkeypatch.setattr(agent_router, "guest_research_visitor_key", capture_guest_key)
    monkeypatch.setattr(agent_router, "stream_agent_turn_events", runtime_events)

    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]
    guest_user = api_state.store.get_or_create_dev_user()
    now = utcnow()
    guest_workspace = GuestWorkspace(
        user_id=guest_user.id,
        conversation_id=conversation["id"],
        status="active",
        created_at=now,
        expires_at=now + timedelta(days=7),
        claimed_by=None,
        claimed_at=None,
        updated_at=now,
    )

    def verified_guest(request: Request):
        store_account_context(
            request,
            guest_account_context(
                guest_workspace,
                visitor_key=visitor_key_for_request(request),
            ),
        )
        return guest_user

    monkeypatch.setitem(app.dependency_overrides, current_user, verified_guest)
    confirmation_response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Test five symbols with $100,000 through today.",
            "language": "en",
        },
    )
    confirmation = _final_stream_payload(confirmation_response.text)["confirmation"]
    run_action = next(
        action for action in confirmation["actions"] if action["type"] == "run_backtest"
    )

    response = client.post(
        "/api/v1/chat/stream",
        headers={"Idempotency-Key": run_action["payload"]["confirmation_id"]},
        json={
            "conversation_id": conversation["id"],
            "action": run_action,
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert [item["is_guest"] for item in guest_key_inputs] == [True, True]
    assert len(claim_guest_keys) == 1
    assert claim_guest_keys[0] is not None
    assert gateway.admission_calls[0]["execution_metadata"][
        "openrouter_traffic_class"
    ] == "guest"
    assert len(gateway.failure_receipts) == 1
    [receipt] = gateway.failure_receipts
    assert receipt["failure_code"] == "idempotency_conflict"
    assert receipt["failure_detail"] == "confirmation_identity_already_spent"
    assert receipt["execution_metadata"]["refused_before_dispatch"] is True
    failed_job = _final_stream_payload(response.text)["backtest_job"]
    assert failed_job["id"] == receipt["id"]
    assert failed_job["failure_code"] == receipt["failure_code"]
    assert failed_job["failure_detail"] == receipt["failure_detail"]

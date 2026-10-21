from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from pydantic import BaseModel


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _Schema(BaseModel):
    accepted: bool


PROVEN_PRODUCTION_BUILDER_CORRIDOR = (
    "asset_preflight.structured_primary",
    "asset_preflight.structured_fallback",
    "interpretation.structured_primary",
    "interpretation.structured_fallback",
    "readiness.focused_strategy_repair",
    "clarification.chat_primary",
    "clarification.chat_fallback",
)


def _typed_state() -> dict[str, Any]:
    return {
        "response_intent": {
            "kind": "clarification",
            "requested_fields": ["date_range"],
            "semantic_needs": ["period"],
        },
        "pending_strategy": {
            "strategy": {
                "strategy_type": "buy_and_hold",
                "asset_universe": ["AAPL"],
                "asset_class": "equity",
            },
            "requested_field": "date_range",
        },
    }


def test_primary_and_fallback_share_one_call_allowance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.turn_execution import (
        reserve_provider_call,
        turn_budget_block_reason,
        turn_execution_scope,
    )

    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "1")

    with turn_execution_scope(entry_state=_typed_state()) as execution:
        primary = reserve_provider_call(
            "interpretation",
            task_timeout_seconds=20,
        )
        fallback = reserve_provider_call(
            "interpretation",
            task_timeout_seconds=20,
        )

        assert primary is not None
        assert primary.timeout_seconds == 20
        assert fallback is None
        assert execution.calls_reserved == 1
        assert execution.blocked_tasks == ["interpretation"]
        assert turn_budget_block_reason() == "turn_call_allowance_exhausted"


@pytest.mark.asyncio
async def test_exhausted_reservation_records_skipped_receipt_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.turn_execution import (
        reserve_provider_call,
        turn_execution_scope,
    )
    from argus.llm import openrouter

    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ARGUS_STRUCTURED_MODEL", "primary/model")
    monkeypatch.setenv("ARGUS_STRUCTURED_FALLBACK_MODEL", "fallback/model")
    clients_created = 0

    class _ForbiddenAsyncClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            nonlocal clients_created
            clients_created += 1
            raise AssertionError("provider client must not be created")

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", _ForbiddenAsyncClient)

    with turn_execution_scope(entry_state=_typed_state()):
        assert (
            reserve_provider_call(
                "interpretation",
                task_timeout_seconds=20,
            )
            is not None
        )
        receipt_token = openrouter.begin_openrouter_route_receipt_capture()
        try:
            result = await openrouter.invoke_openrouter_json_schema(
                task="interpretation",
                messages=[{"role": "user", "content": "test"}],
                schema_model=_Schema,
                schema_name="_Schema",
            )
        finally:
            receipts = openrouter.end_openrouter_route_receipt_capture(receipt_token)

    assert result is None
    assert clients_created == 0
    assert len(receipts) == 1
    assert receipts[0].outcome == "skipped"
    assert receipts[0].failure_mode == "turn_call_allowance_exhausted"
    assert receipts[0].model == "primary/model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing_key", "missing_model", "expected_reason"),
    [
        (True, False, "missing_api_key"),
        (False, True, "missing_model"),
    ],
)
async def test_missing_provider_configuration_does_not_reserve_call(
    monkeypatch: pytest.MonkeyPatch,
    missing_key: bool,
    missing_model: bool,
    expected_reason: str,
) -> None:
    from argus.agent_runtime.turn_execution import turn_execution_scope
    from argus.llm import openrouter

    if missing_key:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    if missing_model:
        monkeypatch.delenv("ARGUS_STRUCTURED_MODEL", raising=False)
        monkeypatch.delenv("ARGUS_STRUCTURED_FALLBACK_MODEL", raising=False)
    else:
        monkeypatch.setenv("ARGUS_STRUCTURED_MODEL", "primary/model")

    with turn_execution_scope(entry_state=_typed_state()) as execution:
        receipt_token = openrouter.begin_openrouter_route_receipt_capture()
        try:
            result = await openrouter.invoke_openrouter_json_schema(
                task="interpretation",
                messages=[{"role": "user", "content": "test"}],
                schema_model=_Schema,
                schema_name="_Schema",
            )
        finally:
            receipts = openrouter.end_openrouter_route_receipt_capture(receipt_token)

        assert execution.calls_reserved == 0

    assert result is None
    assert len(receipts) == 1
    assert receipts[0].failure_mode == expected_reason


def test_first_terminal_claim_wins() -> None:
    from argus.agent_runtime.turn_execution import (
        claim_turn_terminal,
        turn_execution_scope,
    )

    with turn_execution_scope(entry_state=_typed_state()) as execution:
        assert claim_turn_terminal("advanced", "normal_final") is True
        assert claim_turn_terminal("recoverable_failed", "late_failure") is False
        assert execution.terminal == "advanced"
        assert execution.terminal_reason == "normal_final"


def test_same_typed_state_becomes_no_progress() -> None:
    from argus.agent_runtime.turn_execution import (
        record_exit_progress,
        turn_execution_scope,
        turn_execution_summary,
    )

    state = _typed_state()
    with turn_execution_scope(entry_state=state) as execution:
        assessment = record_exit_progress(state, terminal=None)
        summary = turn_execution_summary(())

        assert assessment.outcome == "no_progress"
        assert assessment.changed_fields == ()
        assert execution.progress_outcome == "no_progress"
        assert execution.terminal == "no_progress"
        assert summary["input_fingerprint"] == summary["output_fingerprint"]
        assert summary["progress_outcome"] == "no_progress"
        assert "entry_state" not in summary
        assert "exit_state" not in summary


def test_exact_final_preserves_claimed_no_progress_across_private_evidence() -> None:
    from argus.agent_runtime.turn_execution import (
        claim_turn_terminal,
        record_exit_progress,
        turn_execution_scope,
        turn_execution_summary,
    )

    entry_state = _typed_state()
    final_state = _typed_state()
    final_state["pending_strategy"]["strategy"]["asset_universe"] = ["MSFT"]
    final_state["response_intent"]["facts"] = {"progress_outcome": "no_progress"}

    with turn_execution_scope(entry_state=entry_state) as execution:
        assert claim_turn_terminal("no_progress", "unchanged_typed_state") is True
        assessment = record_exit_progress(final_state, terminal=None)
        summary = turn_execution_summary(())

        assert final_state["response_intent"]["facts"]["progress_outcome"] == (
            "no_progress"
        )
        assert assessment.outcome == "no_progress"
        assert assessment.changed_fields == ("strategy",)
        assert execution.progress_outcome == "no_progress"
        assert execution.terminal == "no_progress"
        assert summary["progress_outcome"] == "no_progress"
        assert summary["terminal"] == "no_progress"
        assert summary["input_fingerprint"] != summary["output_fingerprint"]


def test_exact_final_preserves_other_claimed_explicit_terminal() -> None:
    from argus.agent_runtime.turn_execution import (
        claim_turn_terminal,
        record_exit_progress,
        turn_execution_scope,
        turn_execution_summary,
    )

    entry_state = _typed_state()
    final_state = _typed_state()
    final_state["pending_strategy"]["strategy"]["asset_universe"] = ["MSFT"]

    with turn_execution_scope(entry_state=entry_state) as execution:
        assert claim_turn_terminal("redirected", "explicit_redirect") is True
        assessment = record_exit_progress(final_state, terminal=None)
        summary = turn_execution_summary(())

        assert assessment.outcome == "redirected"
        assert assessment.changed_fields == ("strategy",)
        assert execution.progress_outcome == "redirected"
        assert execution.terminal == "redirected"
        assert summary["progress_outcome"] == "redirected"
        assert summary["terminal"] == "redirected"


def test_exact_final_without_claim_keeps_changed_state_assessment() -> None:
    from argus.agent_runtime.turn_execution import (
        record_exit_progress,
        turn_execution_scope,
        turn_execution_summary,
    )

    entry_state = _typed_state()
    final_state = _typed_state()
    final_state["pending_strategy"]["strategy"]["asset_universe"] = ["MSFT"]

    with turn_execution_scope(entry_state=entry_state) as execution:
        assessment = record_exit_progress(final_state, terminal=None)
        summary = turn_execution_summary(())

        assert assessment.outcome == "advanced"
        assert assessment.changed_fields == ("strategy",)
        assert execution.progress_outcome == "advanced"
        assert execution.terminal == "advanced"
        assert summary["progress_outcome"] == "advanced"
        assert summary["terminal"] == "advanced"
        assert summary["input_fingerprint"] != summary["output_fingerprint"]


@pytest.mark.asyncio
async def test_background_title_work_has_no_parent_turn_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime.turn_execution import (
        active_turn_execution,
        turn_execution_scope,
    )
    from argus.api.chat import title_finalization

    observed_contexts: list[object | None] = []
    completed = asyncio.Event()

    async def _fake_to_thread(_function: Any, **_kwargs: Any) -> None:
        observed_contexts.append(active_turn_execution())
        completed.set()

    monkeypatch.setattr(
        title_finalization,
        "_artifact_naming_disabled_for_pytest",
        lambda: False,
    )
    monkeypatch.setattr(title_finalization.asyncio, "to_thread", _fake_to_thread)

    with turn_execution_scope(entry_state=_typed_state()):
        title_finalization.schedule_artifact_naming_after_stream(
            user_id="user-1",
            conversation_id="conversation-1",
            language="en",
        )
        await asyncio.wait_for(completed.wait(), timeout=1)

    assert observed_contexts == [None]


def test_provider_permit_uses_remaining_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution

    clock = _Clock()
    monkeypatch.setattr(turn_execution, "_monotonic", clock)
    monkeypatch.setenv("ARGUS_TURN_DEADLINE_SECONDS", "0.25")

    with turn_execution.turn_execution_scope(entry_state=_typed_state()):
        clock.advance(0.1)
        permit = turn_execution.reserve_provider_call(
            "interpretation",
            task_timeout_seconds=20,
        )

    assert permit is not None
    assert permit.timeout_seconds == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_async_reasoning_compatibility_retry_needs_its_own_permit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from argus.agent_runtime.turn_execution import turn_execution_scope
    from argus.llm import openrouter

    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    posts: list[dict[str, object]] = []

    class _AsyncClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> _AsyncClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, _url: str, **kwargs: Any) -> httpx.Response:
            posts.append(dict(kwargs["json"]))
            return httpx.Response(
                400,
                json={"error": {"message": "reasoning unsupported"}},
                request=httpx.Request("POST", _url),
            )

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", _AsyncClient)
    receipt_token = openrouter.begin_openrouter_route_receipt_capture()
    try:
        with turn_execution_scope(entry_state=_typed_state()) as execution:
            result = await openrouter.invoke_openrouter_json_schema(
                task="interpretation",
                messages=[{"role": "user", "content": "test"}],
                schema_model=_Schema,
                schema_name="_Schema",
                model_name="structured/model",
            )
    finally:
        receipts = openrouter.end_openrouter_route_receipt_capture(receipt_token)

    assert result is None
    assert execution.calls_reserved == 1
    assert len(posts) == 1
    assert "reasoning" in posts[0]
    assert [(receipt.outcome, receipt.failure_mode) for receipt in receipts] == [
        ("skipped", "turn_call_allowance_exhausted")
    ]


def test_sync_reasoning_compatibility_retry_needs_its_own_permit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from argus.agent_runtime.turn_execution import turn_execution_scope
    from argus.llm import openrouter

    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    posts: list[dict[str, object]] = []

    class _Client:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, _url: str, **kwargs: Any) -> httpx.Response:
            posts.append(dict(kwargs["json"]))
            return httpx.Response(
                400,
                json={"error": {"message": "reasoning unsupported"}},
                request=httpx.Request("POST", _url),
            )

    monkeypatch.setattr(openrouter.httpx, "Client", _Client)
    receipt_token = openrouter.begin_openrouter_route_receipt_capture()
    try:
        with turn_execution_scope(entry_state=_typed_state()) as execution:
            result = openrouter.invoke_openrouter_json_schema_sync(
                task="interpretation",
                messages=[{"role": "user", "content": "test"}],
                schema_model=_Schema,
                schema_name="_Schema",
                model_name="structured/model",
            )
    finally:
        receipts = openrouter.end_openrouter_route_receipt_capture(receipt_token)

    assert result is None
    assert execution.calls_reserved == 1
    assert len(posts) == 1
    assert [(receipt.outcome, receipt.failure_mode) for receipt in receipts] == [
        ("skipped", "turn_call_allowance_exhausted")
    ]


@pytest.mark.asyncio
async def test_chat_completion_first_post_is_accounted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from argus.agent_runtime.turn_execution import turn_execution_scope
    from argus.llm import openrouter

    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    posts = 0

    class _AsyncClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> _AsyncClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, _url: str, **_: Any) -> httpx.Response:
            nonlocal posts
            posts += 1
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "hello"}}]},
                request=httpx.Request("POST", _url),
            )

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", _AsyncClient)
    with turn_execution_scope(entry_state=_typed_state()) as execution:
        result = await openrouter.invoke_openrouter_chat_completion(
            task="chat_composer",
            messages=[{"role": "user", "content": "test"}],
            model_name="chat/model",
        )

    assert result == "hello"
    assert posts == 1
    assert execution.calls_reserved == 1


@pytest.mark.asyncio
async def test_calibrated_production_corridor_reaches_n_and_blocks_n_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from argus.agent_runtime import turn_execution
    from argus.agent_runtime.graph import workflow as workflow_module
    from argus.agent_runtime.llm_clarifier import ClarificationRequest
    from argus.agent_runtime.stages.interpret_types import InterpretationRequest
    from argus.agent_runtime.state.models import UserState
    from argus.api import state as api_state
    from argus.llm import openrouter

    captured_builder: dict[str, Any] = {}

    def _capture_builder(**kwargs: Any) -> dict[str, Any]:
        captured_builder.update(kwargs)
        return kwargs

    monkeypatch.setattr(workflow_module, "build_workflow", _capture_builder)
    monkeypatch.setattr(api_state, "build_backtest_tool", object)
    api_state.build_agent_runtime_workflow(checkpointer=object())
    interpreter = captured_builder["structured_interpreter"]
    clarifier = captured_builder["clarification_generator"]
    assert interpreter.model_name is None
    assert clarifier.model_name is None

    monkeypatch.delenv("ARGUS_TURN_CALL_ALLOWANCE", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ARGUS_STRUCTURED_MODEL", "structured/primary")
    monkeypatch.setenv("ARGUS_STRUCTURED_FALLBACK_MODEL", "structured/fallback")
    monkeypatch.setenv("ARGUS_CHAT_MODEL", "chat/primary")
    monkeypatch.setenv("ARGUS_CHAT_FALLBACK_MODEL", "chat/fallback")
    posts: list[tuple[str, str]] = []

    class _AsyncClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> _AsyncClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, _url: str, **kwargs: Any) -> httpx.Response:
            payload = kwargs["json"]
            schema_name = payload["response_format"]["json_schema"]["name"]
            model = payload["model"]
            posts.append((schema_name, model))
            content = "{}"
            if (
                schema_name == "LLMAssetMentionExtraction"
                and model == "structured/fallback"
            ):
                content = json.dumps(
                    {
                        "asset_mentions": [],
                        "all_traded_asset_mentions_included": True,
                    }
                )
            elif (
                schema_name == "LLMInterpretationResponse"
                and model == "structured/fallback"
            ):
                content = json.dumps(
                    {
                        "intent": "strategy_drafting",
                        "task_relation": "new_task",
                        "requires_clarification": True,
                        "user_goal_summary": "Test a buy-and-hold idea.",
                        "semantic_turn_act": "new_idea",
                        "candidate_strategy_draft": {
                            "raw_user_phrasing": "Test a buy-and-hold idea.",
                            "strategy_thesis": "Test a buy-and-hold idea.",
                        },
                    }
                )
            elif schema_name == "FocusedStrategyExtraction":
                content = json.dumps(
                    {
                        "is_testable_strategy": True,
                        "requires_clarification": True,
                        "user_goal_summary": "Test a buy-and-hold idea.",
                        "strategy_type": "buy_and_hold",
                        "strategy_thesis": "Test a buy-and-hold idea.",
                        "missing_required_fields": ["asset_universe", "date_range"],
                        "confidence": 0.92,
                    }
                )
            elif schema_name == "ClarificationResponse" and model == "chat/fallback":
                content = json.dumps(
                    {
                        "question": "Which asset and date range should I test?",
                        "direct_question": "",
                        "question_targets": [],
                        "directly_asks_user": True,
                        "detail_targets": [],
                    }
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
                request=httpx.Request("POST", _url),
            )

    async def unusable_typed_read(**_: Any) -> None:
        # Exercise the last-resort budget after a typed test read fails runtime
        # preparation. A schema/transport failure alone cannot authorize repair.
        raise RuntimeError("scripted runtime preparation failure")

    monkeypatch.setattr(
        "argus.agent_runtime.llm_interpreter._response_ready_for_runtime",
        unusable_typed_read,
    )
    monkeypatch.setattr(openrouter.httpx, "AsyncClient", _AsyncClient)
    receipt_token = openrouter.begin_openrouter_route_receipt_capture()
    try:
        with turn_execution.turn_execution_scope(entry_state=_typed_state()) as execution:
            interpretation = await interpreter.ainvoke(
                InterpretationRequest(
                    current_user_message="Test a buy-and-hold idea.",
                    recent_thread_history=[],
                    latest_task_snapshot=None,
                    user=UserState(user_id="user-1"),
                )
            )
            assert interpretation is not None
            assert interpretation.requires_clarification is True
            clarification = await clarifier.ainvoke(
                ClarificationRequest(
                    current_user_message="Test a buy-and-hold idea.",
                    candidate_strategy_draft=interpretation.candidate_strategy_draft,
                    missing_required_fields=interpretation.missing_required_fields,
                )
            )
            assert clarification == "Which asset and date range should I test?"
            blocked = await openrouter.invoke_openrouter_json_schema(
                task="clarification",
                messages=[{"role": "user", "content": "N+1"}],
                schema_model=_Schema,
                schema_name="_Schema",
                model_name="model/blocked",
            )
            assessment = turn_execution.record_exit_progress(
                _typed_state(),
                terminal=None,
            )
    finally:
        receipts = openrouter.end_openrouter_route_receipt_capture(receipt_token)

    assert execution.call_allowance == len(PROVEN_PRODUCTION_BUILDER_CORRIDOR)
    assert posts == [
        ("LLMAssetMentionExtraction", "structured/primary"),
        ("LLMAssetMentionExtraction", "structured/fallback"),
        ("LLMInterpretationResponse", "structured/primary"),
        ("LLMInterpretationResponse", "structured/fallback"),
        ("FocusedStrategyExtraction", "structured/primary"),
        ("ClarificationResponse", "chat/primary"),
        ("ClarificationResponse", "chat/fallback"),
    ]
    assert [
        (receipt.schema_name, receipt.model, receipt.outcome) for receipt in receipts[:-1]
    ] == [
        ("LLMAssetMentionExtraction", "structured/primary", "failed"),
        ("LLMAssetMentionExtraction", "structured/fallback", "succeeded"),
        ("LLMInterpretationResponse", "structured/primary", "failed"),
        ("LLMInterpretationResponse", "structured/fallback", "succeeded"),
        ("FocusedStrategyExtraction", "structured/primary", "succeeded"),
        ("ClarificationResponse", "chat/primary", "failed"),
        ("ClarificationResponse", "chat/fallback", "succeeded"),
    ]
    assert blocked is None
    assert assessment.outcome == "no_progress"
    assert execution.terminal == "no_progress"
    assert receipts[-1].outcome == "skipped"
    assert receipts[-1].failure_mode == "turn_call_allowance_exhausted"


def test_call_allowance_override_can_lower_but_not_raise_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution

    policy = len(PROVEN_PRODUCTION_BUILDER_CORRIDOR)
    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", str(policy + 10))
    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        assert execution.call_allowance == policy

    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", "3")
    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        assert execution.call_allowance == 3


@pytest.mark.parametrize("allowance", [1, 7])
def test_research_recovery_reserves_one_scoped_call_without_extending_deadline(
    monkeypatch: pytest.MonkeyPatch, allowance: int
) -> None:
    from argus.agent_runtime import turn_execution

    clock = _Clock()
    monkeypatch.setattr(turn_execution, "_monotonic", clock)
    monkeypatch.setenv("ARGUS_TURN_CALL_ALLOWANCE", str(allowance))
    monkeypatch.setenv("ARGUS_TURN_DEADLINE_SECONDS", "20")
    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        for _ in range(allowance):
            assert turn_execution.reserve_provider_call("interpretation") is not None
        deadline = execution.deadline_monotonic
        assert turn_execution.reserve_provider_call("knowledge_voicing") is None
        clock.advance(15)
        with turn_execution.research_recovery_scope():
            assert turn_execution.reserve_provider_call("interpretation") is None
            permit = turn_execution.reserve_provider_call("knowledge_voicing", 18)
            assert permit is not None and permit.timeout_seconds == pytest.approx(5)
            assert turn_execution.reserve_provider_call("knowledge_voicing") is None
        with turn_execution.research_recovery_scope():
            assert turn_execution.reserve_provider_call("knowledge_voicing") is None
        assert execution.calls_reserved == allowance
        assert execution.deadline_monotonic == deadline
        assert turn_execution.turn_execution_summary(())["research_recovery_reserved"]
        assert turn_execution.reserve_provider_call("knowledge_voicing") is None


def test_research_recovery_cannot_reserve_after_the_turn_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution

    clock = _Clock()
    monkeypatch.setattr(turn_execution, "_monotonic", clock)
    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        clock.advance(execution.deadline_seconds)
        with turn_execution.research_recovery_scope():
            assert turn_execution.reserve_provider_call("knowledge_voicing") is None
        assert execution.deadline_exhausted
        assert not execution.research_recovery_reserved


def test_a_turn_without_a_focused_repair_keeps_exactly_seven_ordinary_permits() -> None:
    from argus.agent_runtime import turn_execution

    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        granted = [
            turn_execution.reserve_provider_call(task)
            for task in (
                "asset_mention_preflight",
                "interpretation",
                "interpretation",
                "interpretation",
                "interpretation_repair",
                "interpretation_repair",
                "field_fidelity",
            )
        ]
        assert turn_execution.reserve_provider_call("field_fidelity") is None
        assert turn_execution.reserve_provider_call("interpretation_repair") is None
        assert turn_execution.reserve_provider_call("clarification") is None
        summary = turn_execution.turn_execution_summary(())

    assert all(permit is not None for permit in granted)
    assert execution.blocked_tasks == [
        "field_fidelity",
        "interpretation_repair",
        "clarification",
    ]
    assert summary["calls_reserved"] == 7
    assert summary["repair_approval_grant_used"] == 0
    assert summary["call_allowance_exhausted"] is True


@pytest.mark.asyncio
async def test_a_focused_repair_on_the_last_ordinary_permit_funds_its_approval() -> None:
    from argus.agent_runtime import turn_execution

    @turn_execution.focused_repair
    async def repair_then_approve() -> list[str]:
        return [
            task
            for task in ("interpretation_repair", "field_fidelity", "clarification")
            if turn_execution.reserve_provider_call(task) is not None
        ]

    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        for _ in range(execution.call_allowance - 1):
            assert turn_execution.reserve_provider_call("interpretation") is not None
        granted = await repair_then_approve()
        # Outside the repair the corridor is still spent.
        assert turn_execution.reserve_provider_call("field_fidelity") is None
        summary = turn_execution.turn_execution_summary(())

    assert granted == ["interpretation_repair", "field_fidelity"]
    assert summary["calls_reserved"] == 8
    assert summary["repair_approval_grant_used"] == 1
    assert execution.blocked_tasks == ["clarification", "field_fidelity"]


@pytest.mark.asyncio
async def test_an_exhausted_allowance_does_not_start_a_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution
    from argus.llm import openrouter

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ARGUS_STRUCTURED_MODEL", "primary/model")
    monkeypatch.setenv("ARGUS_STRUCTURED_FALLBACK_MODEL", "fallback/model")
    posts: list[str] = []

    async def post(*, retry_attempt: Any, **_: Any) -> Any:
        posts.append(retry_attempt[4])
        raise AssertionError("an unfundable repair must not reach the provider")

    monkeypatch.setattr(openrouter, "_post_openrouter_json_schema", post)

    @turn_execution.focused_repair
    async def approve_then_retry_repair() -> Any:
        assert turn_execution.reserve_provider_call("field_fidelity") is not None
        with turn_execution.last_resort_repair_scope():
            return await openrouter.invoke_openrouter_json_schema(
                task="interpretation_repair",
                messages=[{"role": "user", "content": "200 al mes"}],
                schema_model=_Schema,
                schema_name="FocusedStrategyExtraction",
            )

    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        for _ in range(execution.call_allowance):
            assert turn_execution.reserve_provider_call("interpretation") is not None
        receipt_token = openrouter.begin_openrouter_route_receipt_capture()
        try:
            result = await approve_then_retry_repair()
        finally:
            receipts = openrouter.end_openrouter_route_receipt_capture(receipt_token)
        summary = turn_execution.turn_execution_summary(receipts)

    # One pool call is left, but a repair needs a second one for its approval.
    assert result is None
    assert posts == []
    assert [
        (receipt.task, receipt.schema_name, receipt.outcome, receipt.failure_mode)
        for receipt in receipts
    ] == [
        (
            "interpretation_repair",
            "FocusedStrategyExtraction",
            "skipped",
            "turn_call_allowance_exhausted",
        )
    ]
    assert execution.blocked_tasks == ["interpretation_repair"]
    assert summary["last_resort_repair_calls_granted"] == 2
    assert summary["last_resort_repair_grant_used"] == 1
    assert summary["repair_approval_grant_used"] == 1
    assert summary["calls_reserved"] == 8


@pytest.mark.asyncio
async def test_a_last_resort_repair_and_its_approval_share_the_pool() -> None:
    from argus.agent_runtime import turn_execution

    @turn_execution.focused_repair
    async def last_resort_repair_then_approve() -> list[str]:
        with turn_execution.last_resort_repair_scope():
            return [
                task
                for task in (
                    "interpretation_repair",
                    "interpretation_repair",
                    "field_fidelity",
                    "field_fidelity",
                )
                if turn_execution.reserve_provider_call(task) is not None
            ]

    with turn_execution.turn_execution_scope(entry_state={}) as execution:
        for _ in range(execution.call_allowance):
            assert turn_execution.reserve_provider_call("interpretation") is not None
        granted = await last_resort_repair_then_approve()
        summary = turn_execution.turn_execution_summary(())

    assert granted == ["interpretation_repair", "field_fidelity"]
    assert execution.blocked_tasks == ["interpretation_repair", "field_fidelity"]
    assert summary["calls_reserved"] == 9
    assert summary["last_resort_repair_grant_used"] == 2
    assert summary["repair_approval_grant_used"] == 1


@pytest.mark.asyncio
async def test_every_reservation_source_together_stays_within_the_stated_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.agent_runtime import turn_execution

    monkeypatch.setenv("ARGUS_RESEARCH_RAIL_ENABLED", "true")
    attempts = 4 * turn_execution.TURN_PROVIDER_POST_CEILING

    def grants(task: str) -> int:
        return sum(
            turn_execution.reserve_provider_call(task) is not None
            for _ in range(attempts)
        )

    @turn_execution.focused_repair
    async def focused_repair_calls() -> int:
        with turn_execution.last_resort_repair_scope():
            return grants("interpretation_repair") + grants("field_fidelity")

    with turn_execution.turn_execution_scope(entry_state={}):
        granted = grants("interpretation") + grants("knowledge_route")
        with turn_execution.research_recovery_scope():
            granted += grants("knowledge_voicing")
        granted += await focused_repair_calls()
        granted += await focused_repair_calls()
        with turn_execution.last_resort_repair_scope():
            granted += grants("interpretation_repair")

    assert turn_execution.TURN_PROVIDER_POST_CEILING == 11
    assert granted == 11

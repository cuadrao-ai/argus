"""Issue #498 acceptance bar: the live-eval compound-edit cases apply fully.

Each case drives the REAL structured interpreter and interpret stage with
canned LLM outputs shaped like the live scorecard failures: the primary read
carries the whole typed request while the planner's plan drops half of it.
The union completion must apply every operation; a half-applied confirmation
is the defect under test.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.evals import measurement_eval_harness as harness
from tests.evals.measurement_eval_harness import load_eval_cases


def _issue_498_resolve_stub(symbol: str, **kwargs: Any):
    from argus.domain.market_data import ResolvedAsset

    del kwargs
    canonical = symbol.strip().upper()
    if canonical not in {"LOW", "HD", "QQQ", "SPY", "AAPL", "MSFT", "NVDA", "TSLA"}:
        raise ValueError("invalid_symbol")
    return ResolvedAsset(
        canonical_symbol=canonical,
        asset_class="equity",
        name=canonical,
        raw_symbol=canonical,
        provider="issue-498-test",
    )


def _issue_498_wiring(
    monkeypatch: Any,
    *,
    primary: Any,
    plan: Any,
    effective_range: dict[str, str] | None,
    adjustment_reason: str | None,
) -> None:
    """Wire the REAL structured interpreter with canned LLM outputs.

    Unlike interpreter-level mocks, this exercises the whole deterministic
    spine: readiness audits, edit planning, completion, coverage guards, and
    the stage merge — only the two LLM reads are canned."""
    from argus.agent_runtime import artifact_edit_planner
    from argus.agent_runtime import llm_interpreter as interpreter_module
    from argus.agent_runtime.stages import interpret as interpret_module
    from argus.domain.backtesting import coverage as coverage_module
    from argus.domain.backtesting.coverage import (
        CoverageDateRange,
        PreparedMarketData,
    )

    async def dispatcher(*, schema_model: Any = None, **kwargs: Any):
        name = getattr(schema_model, "__name__", "")
        if name == "LLMInterpretationResponse":
            return primary()
        if name == "ArtifactAssumptionEditPlan":
            return plan()
        raise RuntimeError(f"no canned response for schema {name}")

    def prepared_coverage(config: dict[str, Any]) -> PreparedMarketData:
        requested = CoverageDateRange(
            start=str(config["start_date"]), end=str(config["end_date"])
        )
        window = (
            CoverageDateRange(**effective_range) if effective_range else requested
        )
        return PreparedMarketData(
            requested_date_range=requested,
            effective_date_range=window,
            outcome="full_coverage",
            adjustment_reason=adjustment_reason,
            dataset_id="issue-498-coverage",
            bars_by_symbol={},
            observations_by_symbol={
                str(symbol): 84
                for symbol in [
                    *config.get("symbols", []),
                    config.get("benchmark_symbol"),
                ]
                if symbol
            },
        )

    for module in (interpreter_module, artifact_edit_planner):
        monkeypatch.setattr(
            module, "openrouter_structured_model_candidates", lambda *a, **k: ["m1"]
        )
        monkeypatch.setattr(module, "invoke_openrouter_json_schema", dispatcher)
    monkeypatch.setattr(interpreter_module, "resolve_asset", _issue_498_resolve_stub)
    monkeypatch.setattr(interpret_module, "resolve_asset", _issue_498_resolve_stub)
    monkeypatch.setattr(coverage_module, "prepare_market_data", prepared_coverage)


def _issue_498_primary(**draft_fields: Any):
    from argus.agent_runtime.llm_interpreter_types import (
        LLMInterpretationResponse,
        LLMStrategyDraft,
    )

    def build() -> LLMInterpretationResponse:
        return LLMInterpretationResponse(
            intent="backtest_execution",
            task_relation="continue",
            requires_clarification=False,
            user_goal_summary="Apply the requested confirmation edits.",
            candidate_strategy_draft=LLMStrategyDraft(**draft_fields),
            semantic_turn_act="answer_pending_need",
            confidence=0.9,
        )

    return build


def _issue_498_plan(**plan_fields: Any):
    from argus.agent_runtime.artifact_edit_planner import ArtifactAssumptionEditPlan

    def build() -> ArtifactAssumptionEditPlan:
        return ArtifactAssumptionEditPlan(
            outcome="ready_to_confirm", confidence=0.9, **plan_fields
        )

    return build


def _issue_498_case_configs() -> list[Any]:
    from argus.agent_runtime.artifact_edit_planner import EditOperation
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent

    return [
        pytest.param(
            "compound_benchmark_start_date_preserves_confirmation_issue_339",
            _issue_498_primary(
                comparison_baseline="QQQ",
                date_range_intent=LLMDateRangeIntent(
                    kind="endpoint_patch",
                    endpoint="start",
                    start="2026-04-01",
                    evidence="April 1, 2026",
                ),
                field_provenance={
                    "comparison_baseline": "explicit_user",
                    "date_range": "explicit_user",
                },
            ),
            # The live drop shape: the benchmark op survives, the date is gone.
            _issue_498_plan(
                operations=[EditOperation(op="set", target="benchmark", value="QQQ")]
            ),
            None,
            None,
            id="339-planner-drops-the-date",
        ),
        pytest.param(
            "action_chip_change_asset_no_active_ref_asset_and_date_issue_188",
            _issue_498_primary(
                asset_universe=["MSFT", "NVDA"],
                asset_universe_operation="replace",
                asset_exclusions=["AAPL"],
                date_range_intent=LLMDateRangeIntent(
                    kind="calendar_year", year=2023, evidence="2023"
                ),
                field_provenance={
                    "asset_universe": "explicit_user",
                    "date_range": "explicit_user",
                },
            ),
            # The live drop shape: the date lands, the removal vanishes.
            _issue_498_plan(
                operations=[
                    EditOperation(
                        op="set",
                        target="date_window",
                        date_window=LLMDateRangeIntent(
                            kind="calendar_year", year=2023
                        ),
                    )
                ]
            ),
            {"start": "2023-01-03", "end": "2023-12-29"},
            "calendar_alignment",
            id="188-planner-drops-the-removal",
        ),
        pytest.param(
            "action_chip_change_asset_bare_ticker_append_issue_190",
            _issue_498_primary(
                asset_universe=["TSLA"],
                asset_universe_operation="append",
                asset_inclusions=["TSLA"],
                field_provenance={"asset_universe": "explicit_user"},
            ),
            # The live drop shape: the plan echoes the current basket and
            # carries no operation at all for the appended ticker.
            _issue_498_plan(operations=[], asset_universe=["AAPL", "MSFT", "NVDA"]),
            {"start": "2024-01-02", "end": "2024-12-31"},
            "calendar_alignment",
            id="190-planner-drops-the-append",
        ),
    ]


@pytest.mark.parametrize(
    ("case_id", "primary", "plan", "effective_range", "adjustment_reason"),
    _issue_498_case_configs(),
)
def test_issue_498_compound_edits_apply_every_operation(
    monkeypatch: Any,
    case_id: str,
    primary: Any,
    plan: Any,
    effective_range: dict[str, str] | None,
    adjustment_reason: str | None,
) -> None:
    """Issue #498: a plan that drops half of a typed compound request is
    completed from the primary read and applied in full; the eval cases from
    the live scorecard are the acceptance bar."""
    case = {case.id: case for case in load_eval_cases()}[case_id]
    _issue_498_wiring(
        monkeypatch,
        primary=primary,
        plan=plan,
        effective_range=effective_range,
        adjustment_reason=adjustment_reason,
    )

    result = harness.run_eval_case(case, run_prose_judge=False)

    assert result["failed_checks"] == []
    assert result["status"] == "passed"


@pytest.mark.parametrize("fallback", [False, True], ids=["primary-plan", "fallback-plan"])
def test_compound_date_from_planner_survives_primary_omission(monkeypatch, fallback):
    """Replay the missing-primary-date and repeated-planner shape on efaf4b53.

    The saved trace records no primary date fields and a later benchmark-only
    confirmation. Canned plans reproduce that shape, not unsaved model bytes.
    """
    from argus.agent_runtime import artifact_edit_planner
    from argus.agent_runtime.artifact_edit_planner import EditOperation
    from argus.agent_runtime.llm_interpreter_types import LLMDateRangeIntent
    from loguru import logger

    case_id = "compound_benchmark_start_date_preserves_confirmation_issue_339"
    primary = _issue_498_primary(
        comparison_baseline="QQQ",
        field_provenance={"comparison_baseline": "explicit_user"},
    )
    complete_plan = _issue_498_plan(
        operations=[
            EditOperation(op="set", target="benchmark", value="QQQ"),
            EditOperation(
                op="set",
                target="date_window",
                date_window=LLMDateRangeIntent(
                    kind="endpoint_patch",
                    endpoint="start",
                    start="2026-04-01",
                    evidence="April 1, 2026",
                ),
            ),
        ]
    )
    benchmark_only = _issue_498_plan(
        operations=[EditOperation(op="set", target="benchmark", value="QQQ")]
    )
    plans = iter(([lambda: None] if fallback else []) + [complete_plan, benchmark_only])
    calls = []

    def next_plan():
        calls.append(True)
        return next(plans, benchmark_only)()

    _issue_498_wiring(
        monkeypatch,
        primary=primary,
        plan=next_plan,
        effective_range=None,
        adjustment_reason=None,
    )
    monkeypatch.setattr(
        artifact_edit_planner,
        "openrouter_structured_model_candidates",
        lambda: ["m1", "m2"] if fallback else ["m1"],
    )
    case = {case.id: case for case in load_eval_cases()}[case_id]
    reasons = []
    sink = logger.add(
        lambda message: reasons.append(message.record["extra"].get("reason_code"))
    )
    try:
        result = harness.run_eval_case(case, run_prose_judge=False)
    finally:
        logger.remove(sink)

    assert result["failed_checks"] == []
    assert result["status"] == "passed"
    assert len(calls) == (2 if fallback else 1)
    assert "artifact_edit_date_completed_from_plan" in reasons

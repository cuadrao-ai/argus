"""Compute kernels are registered as data; the dispatcher never branches on a name."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from argus.api.decision_contract import DecisionComputation
from argus.domain import computations
from argus.domain.computations import (
    BACKTEST_COMPUTATION_KIND,
    ComputationKernel,
    InvalidComputationInputs,
    RerunContext,
    kernel_for,
    register_kernel,
    registered_kinds,
    rerun_calculation,
    rerun_computation,
    unregister_kernel,
)
from computation_harness import (
    SAVINGS_PROJECTION_KIND as HARNESS_KIND,
)
from computation_harness import (
    registered_savings_projection,
)
from faker import Faker

fake = Faker()


@pytest.fixture
def harness_kernel() -> Iterator[ComputationKernel]:
    with registered_savings_projection() as kernel:
        yield kernel


def _context(run: dict[str, Any] | None = None) -> RerunContext:
    return RerunContext(
        load_run=lambda run_id: run if run and run.get("id") == run_id else None,
        today=date(2026, 9, 8),
    )


def test_backtest_is_registered_at_import_and_names_are_unique(
    harness_kernel: ComputationKernel,
) -> None:
    assert BACKTEST_COMPUTATION_KIND in registered_kinds()
    assert kernel_for(HARNESS_KIND) is harness_kernel
    with pytest.raises(ValueError):
        register_kernel(harness_kernel)
    register_kernel(harness_kernel, replace=True)
    assert kernel_for(HARNESS_KIND) is harness_kernel


def test_registered_kind_computes_and_overrides_merge_over_stored_inputs(
    harness_kernel: ComputationKernel,
) -> None:
    computation = DecisionComputation(
        kind=HARNESS_KIND,
        inputs={"monthly_amount": 5000, "months": 9, "target_amount": 60_000},
    )

    (stored,) = rerun_computation(computation, overrides=None, context=_context())
    (changed,) = rerun_computation(
        computation, overrides={"months": 3}, context=_context()
    )

    assert stored.status == "computed"
    assert stored.result == {"saved_total": 45_000.0, "shortfall": 15_000.0}
    assert changed.status == "computed"
    assert changed.inputs["months"] == 3
    assert changed.result == {"saved_total": 15_000.0, "shortfall": 45_000.0}
    # The stored computation is a value; a re-run never mutates it.
    assert computation.calculations[0].inputs["months"] == 9


def test_invalid_merged_inputs_raise_with_the_kernel_errors(
    harness_kernel: ComputationKernel,
) -> None:
    computation = DecisionComputation(kind=HARNESS_KIND, inputs={"monthly_amount": 5000})

    with pytest.raises(InvalidComputationInputs) as excinfo:
        rerun_computation(computation, overrides={"months": 0}, context=_context())

    assert excinfo.value.kind == HARNESS_KIND
    assert any(error["loc"] == ("months",) for error in excinfo.value.errors)


def test_unknown_kind_is_a_typed_unavailable_state_never_a_crash() -> None:
    computation = DecisionComputation(kind="not_registered", inputs={"x": 1})

    (rerun,) = rerun_computation(computation, overrides={"x": 2}, context=_context())

    assert rerun.status == "unavailable"
    assert rerun.reason_code == "kernel_unavailable"
    assert rerun.inputs == {"x": 1}
    assert rerun.result is None and rerun.retest is None






def test_backtest_kernel_requires_a_source_run_id() -> None:
    computation = DecisionComputation(kind=BACKTEST_COMPUTATION_KIND, inputs={})

    with pytest.raises(InvalidComputationInputs):
        rerun_calculation(computation.calculations[0], overrides=None, context=_context())


def test_unregister_is_idempotent() -> None:
    unregister_kernel("never_registered")
    assert "never_registered" not in computations.registered_kinds()


def _completed_run(run_id: str) -> dict[str, Any]:
    return {
        "id": run_id,
        "conversation_id": fake.uuid4(),
        "status": "completed",
        "asset_class": "equity",
        "symbols": ["TSLA"],
        "benchmark_symbol": "SPY",
        "config_snapshot": {
            "template": "buy_and_hold",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "timeframe": "1D",
            "starting_capital": 10_000,
            "resolved_strategy": {
                "strategy_type": "buy_and_hold",
                "asset_class": "equity",
            },
            "resolved_parameters": {
                "timeframe": "1D",
                "benchmark_symbol": "SPY",
                "sizing_mode": "capital_amount",
                "capital_amount": 10_000,
            },
        },
        "conversation_result_card": {
            "title": "TSLA buy and hold",
            "evidence_artifact_id": fake.uuid4(),
            "idea_id": fake.uuid4(),
            "idea_version_id": fake.uuid4(),
        },
    }


def test_an_index_past_the_calculations_is_the_clients_error_even_with_no_edits(
    harness_kernel: ComputationKernel,
) -> None:
    computation = DecisionComputation(kind=HARNESS_KIND, inputs={"monthly_amount": 5000})
    for overrides in ({}, None):
        with pytest.raises(InvalidComputationInputs):
            rerun_computation(
                computation, overrides=overrides, context=_context(), index=3
            )

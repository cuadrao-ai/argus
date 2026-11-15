"""Every calculation kind re-runs through its declaration's one compute function."""

from __future__ import annotations

from datetime import date

import pytest
from argus.api.decision_contract import DecisionComputation
from argus.domain.calculations import get_calculation_declarations
from argus.domain.computations import (
    InvalidComputationInputs,
    RerunContext,
    kernel_for,
    registered_kinds,
    rerun_calculation,
    rerun_computation,
)
from argus.domain.tool_contracts import ToolResultCard

from tests.domain.calculations.support import run_calculation

_CONTEXT = RerunContext(load_run=lambda _run_id: None, today=date(2026, 9, 11))


def test_every_declared_calculation_is_a_registered_kind() -> None:
    names = {declaration.name for declaration in get_calculation_declarations()}
    assert names <= set(registered_kinds())
    for name in names:
        kernel = kernel_for(name)
        assert kernel is not None and kernel.inputs_editable and kernel.merge is not None


@pytest.mark.parametrize(
    "declaration", get_calculation_declarations(), ids=lambda d: d.name
)
def test_a_kernel_re_run_is_the_same_card_the_chat_turn_produced(declaration) -> None:
    from tests.domain.calculations import worked_arguments

    arguments = worked_arguments(declaration.name)
    card = run_calculation(declaration.name, arguments)
    (rerun,) = rerun_computation(
        DecisionComputation(kind=declaration.name, inputs=card.arguments),
        overrides=None,
        context=_CONTEXT,
    )
    assert rerun.status == "computed"
    reran = ToolResultCard.model_validate(rerun.result)
    assert reran.outcome == card.outcome
    assert reran.presentation == card.presentation
    assert reran.arguments == card.arguments


def test_an_override_re_runs_through_the_declaration_and_keeps_the_unknown() -> None:
    card = run_calculation(
        "time_value",
        {
            "direction": "borrow",
            "currency": "USD",
            "present_value": 200_000,
            "payment": None,
            "future_value": 0,
            "annual_rate_pct": 6,
            "periods": 360,
        },
    )
    computation = DecisionComputation(kind="time_value", inputs=card.arguments)
    (changed,) = rerun_computation(
        computation, overrides={"annual_rate_pct": 5}, context=_CONTEXT
    )
    assert changed.status == "computed"
    assert changed.inputs["annual_rate_pct"] == 5
    assert changed.inputs["sources"]["annual_rate_pct"] == {"kind": "user"}
    assert changed.result["presentation"]["answer"]["value"] == pytest.approx(1_073.64)
    with pytest.raises(InvalidComputationInputs):
        rerun_computation(computation, overrides={"payment": 1_000}, context=_CONTEXT)
    with pytest.raises(InvalidComputationInputs):
        rerun_computation(computation, overrides={"periods": 0}, context=_CONTEXT)


def test_a_no_solution_re_run_is_computed_with_the_typed_outcome_on_the_card() -> None:
    card = run_calculation(
        "time_value",
        {
            "direction": "borrow",
            "currency": "DOP",
            "present_value": 180_000,
            "payment": 5_000,
            "future_value": 0,
            "annual_rate_pct": 14,
            "periods": None,
        },
    )
    (rerun,) = rerun_computation(
        DecisionComputation(kind="time_value", inputs=card.arguments),
        overrides={"payment": 2_000},
        context=_CONTEXT,
    )
    assert rerun.status == "computed"
    assert rerun.result["outcome"]["status"] == "invalid"
    assert rerun.result["outcome"]["failure"]["code"] == "payment_below_interest"
    assert rerun.result["outcome"]["failure"]["repair"]["changes"]["payment"] > 2_100


def test_stored_inputs_that_no_longer_fit_the_kind_are_invalid_inputs() -> None:
    computation = DecisionComputation(kind="time_value", inputs={"nonsense": 1})
    with pytest.raises(InvalidComputationInputs):
        rerun_calculation(computation.calculations[0], overrides=None, context=_CONTEXT)
    (rerun,) = rerun_computation(computation, overrides=None, context=_CONTEXT)
    assert rerun.status == "unavailable"
    assert rerun.reason_code == "invalid_inputs"

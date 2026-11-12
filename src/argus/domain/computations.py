"""Compute kernels a decision can re-run, keyed by computation kind.

The backtest is the first kind, not an exception. Its re-run is the typed
retest projection, which never executes anything: a backtest earns its
confirmation by cost (operating rule 2). Cheap kinds compute in-process when
the decision is opened. Kinds are registered as data, and the dispatcher
never branches on a name.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from argus.api.decision_contract import (
    DecisionCalculation,
    DecisionComputation,
    DecisionRerun,
    DecisionRerunReasonCode,
)
from argus.domain.decision_attachment import (
    BACKTEST_COMPUTATION_KIND as BACKTEST_COMPUTATION_KIND,
)


@dataclass(frozen=True)
class RerunContext:
    """Owner-scoped readers a kernel may need; the API layer binds them."""

    load_run: Callable[[str], Mapping[str, Any] | None]
    today: date


@dataclass(frozen=True)
class ComputationKernel:
    """A registered kind: typed inputs and the function that re-runs them."""

    kind: str
    inputs_model: type[BaseModel]
    compute: Callable[[BaseModel, RerunContext], DecisionRerun]
    # A backtest's inputs are its immutable run; editing them is a new run.
    inputs_editable: bool = True
    # How overrides merge over stored inputs; a calculation keeps its unknown
    # and marks the edited input as stated, through its declaration.
    merge: Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]] | None = None


class InvalidComputationInputs(ValueError):
    """The merged inputs do not satisfy the kernel's typed input model."""

    def __init__(self, kind: str, errors: list[dict[str, Any]]) -> None:
        super().__init__(f"Inputs for computation kind {kind!r} are invalid.")
        self.kind = kind
        self.errors = errors


_KERNELS: dict[str, ComputationKernel] = {}


def register_kernel(kernel: ComputationKernel, *, replace: bool = False) -> None:
    if kernel.kind in _KERNELS and not replace:
        raise ValueError(f"Computation kind {kernel.kind!r} is already registered.")
    _KERNELS[kernel.kind] = kernel


def unregister_kernel(kind: str) -> None:
    _KERNELS.pop(kind, None)


def kernel_for(kind: str) -> ComputationKernel | None:
    registered = _KERNELS.get(kind)
    if registered is not None:
        return registered
    return _calculation_kernels().get(kind)


def registered_kinds() -> tuple[str, ...]:
    return tuple(sorted({*_KERNELS, *_calculation_kernels()}))


def _calculation_kernels() -> dict[str, ComputationKernel]:
    """One kernel per free calculation, each calling the declaration's one function.

    Built on first use so this module stays importable from the API schemas
    without loading the catalog.
    """
    from argus.domain.calculations import get_calculation_declarations

    kernels: dict[str, ComputationKernel] = {}
    for declaration in get_calculation_declarations():
        kernels[declaration.name] = calculation_kernel(declaration)
    return kernels


CALCULATION_RERUN_CALL_ID = "decision_rerun"
CALCULATION_RERUN_ARTIFACT_ID = "decision_rerun"


def calculation_kernel(declaration: Any) -> ComputationKernel:
    """The kernel for a declared calculation: the same compute function, as a card."""
    from argus.domain.tool_contracts import ToolCall

    def compute(inputs: BaseModel, _context: RerunContext) -> DecisionRerun:
        arguments = inputs.model_dump(mode="json")
        outcome = declaration.invoke_sync(arguments)
        card = declaration.result_card(
            call=ToolCall(
                tool_name=declaration.name,
                call_id=CALCULATION_RERUN_CALL_ID,
                arguments=arguments,
            ),
            outcome=outcome,
            artifact_id=CALCULATION_RERUN_ARTIFACT_ID,
        )
        return DecisionRerun(
            kind=declaration.name,
            inputs=dict(card.arguments),
            status="computed",
            result=card.model_dump(mode="json"),
        )

    def merge(stored: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
        return declaration.recompute_arguments(stored, overrides).model_dump(mode="json")

    return ComputationKernel(
        kind=declaration.name,
        inputs_model=declaration.call_arguments_type,
        compute=compute,
        merge=merge,
    )


def unavailable_rerun(
    calculation: DecisionCalculation,
    *,
    inputs: Mapping[str, Any] | None = None,
    reason_code: DecisionRerunReasonCode,
) -> DecisionRerun:
    return DecisionRerun(
        kind=calculation.kind,
        inputs=dict(inputs if inputs is not None else calculation.inputs),
        status="unavailable",
        reason_code=reason_code,
    )


def rerun_computation(
    computation: DecisionComputation,
    *,
    overrides: Mapping[str, Any] | None,
    context: RerunContext,
    index: int = 0,
) -> list[DecisionRerun]:
    """Re-run every calculation of ``computation``, in order, with ``overrides``
    merged over the stored inputs of the one at ``index``.

    Raises :class:`InvalidComputationInputs` when no calculation sits at
    ``index``, whatever the overrides, or when overrides were supplied and the
    edited calculation's merged inputs fail its kernel's typed model: that is the
    client's error. A calculation
    whose stored inputs drifted re-runs as a typed unavailable state, because
    the row, not the request, is what drifted.
    """
    if not 0 <= index < len(computation.calculations):
        raise InvalidComputationInputs(
            computation.kinds[0],
            [{"type": "value_error", "msg": "No calculation at that index.", "loc": []}],
        )
    reruns: list[DecisionRerun] = []
    for position, calculation in enumerate(computation.calculations):
        edited = overrides if position == index else None
        try:
            reruns.append(
                rerun_calculation(calculation, overrides=edited, context=context)
            )
        except InvalidComputationInputs:
            if edited:
                raise
            reruns.append(unavailable_rerun(calculation, reason_code="invalid_inputs"))
    return reruns


def rerun_calculation(
    calculation: DecisionCalculation,
    *,
    overrides: Mapping[str, Any] | None,
    context: RerunContext,
) -> DecisionRerun:
    """Re-run one calculation with ``overrides`` merged over its stored inputs.

    Raises :class:`InvalidComputationInputs` when the merged inputs fail the
    kernel's typed model.
    """
    kernel = kernel_for(calculation.kind)
    if kernel is None:
        return unavailable_rerun(calculation, reason_code="kernel_unavailable")
    merged: dict[str, Any] = {**calculation.inputs, **dict(overrides or {})}
    if overrides and not kernel.inputs_editable:
        return unavailable_rerun(
            calculation, inputs=merged, reason_code="inputs_not_editable"
        )
    try:
        if overrides and kernel.merge is not None:
            merged = kernel.merge(calculation.inputs, overrides)
        typed_inputs = kernel.inputs_model.model_validate(merged)
    except ValidationError as exc:
        raise InvalidComputationInputs(calculation.kind, exc.errors()) from exc
    except (ValueError, TypeError) as exc:
        raise InvalidComputationInputs(
            calculation.kind, [{"type": "value_error", "msg": str(exc), "loc": []}]
        ) from exc
    return kernel.compute(typed_inputs, context)


class BacktestRerunInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_run_id: str = Field(min_length=1)


def _rerun_backtest(inputs: BaseModel, context: RerunContext) -> DecisionRerun:
    # Imported lazily: run_dossiers reaches into agent_runtime for the
    # retest materializer, and this module must stay importable from schemas.
    from argus.domain.run_dossiers import project_retest_action

    typed = BacktestRerunInputs.model_validate(inputs.model_dump())
    calculation = DecisionCalculation(
        kind=BACKTEST_COMPUTATION_KIND,
        inputs={"source_run_id": typed.source_run_id},
    )
    run = context.load_run(typed.source_run_id)
    if run is None:
        return unavailable_rerun(calculation, reason_code="run_unavailable")
    action = project_retest_action(run=run, today=context.today)
    if action is None:
        return unavailable_rerun(calculation, reason_code="retest_unavailable")
    return DecisionRerun(
        kind=calculation.kind,
        inputs=dict(calculation.inputs),
        status="confirmation_required",
        retest=action,
    )


register_kernel(
    ComputationKernel(
        kind=BACKTEST_COMPUTATION_KIND,
        inputs_model=BacktestRerunInputs,
        compute=_rerun_backtest,
        inputs_editable=False,
    )
)

"""Issue #159: typed guards for the unsupported-intent vs executable-draft contradiction.

Invariant: an interpretation still carrying ``intent=unsupported_or_out_of_scope``
never admits to confirmation. Promotion to a supported intent stays LLM-owned via
the capability-conflict audit; every non-promoted outcome fails closed into typed
unsupported recovery."""

from __future__ import annotations

import json
from typing import Any

from argus.agent_runtime.interpreter.draft_shape import strategy_draft_future_horizon
from argus.agent_runtime.interpreter.provider_context_assets import (
    resolved_asset_records_from_strategy_context,
)
from argus.agent_runtime.interpreter.shared import (
    _llm_strategy_draft_has_concrete_execution_target,
)
from argus.agent_runtime.llm_interpreter_types import LLMInterpretationResponse
from argus.agent_runtime.stages.interpret_internal.asset_resolution import (
    _educational_turn_has_strategy_baggage,
    _optional_parameter_stage_patch,
)
from argus.agent_runtime.stages.interpret_types import (
    InterpretationRequest,
    InterpretDecision,
    StageResult,
)
from argus.agent_runtime.state.models import UnsupportedConstraint
from argus.agent_runtime.strategy_contract import canonical_strategy_type
from argus.domain.capability_registry import REGISTERED_STRATEGY_TEMPLATES
from argus.domain.strategy_capabilities import STRATEGY_CAPABILITIES

UNSUPPORTED_INTENT_ADMISSION_BLOCKED = "unsupported_intent_confirmation_blocked"
RECOGNIZED_NON_EXECUTABLE_ADMISSION_BLOCKED = (
    "recognized_non_executable_strategy_admission_blocked"
)
CAPABILITY_CONFLICT_INVERSE_REASON = "supported_strategy_capability_conflict_inverse"

# Issue #241: a typed forward-looking horizon can never admit as an executable
# historical window; it survives only as original-intent evidence.
FUTURE_PERFORMANCE_CATEGORY = "future_performance"
FUTURE_PERFORMANCE_ADMISSION_BLOCKED = "future_performance_admission_blocked"
FUTURE_HORIZON_EVIDENCE_KEY = "future_horizon_intent"

_FUTURE_PERFORMANCE_EXPLANATION = (
    "There is no market data for a period that has not happened yet, so Argus "
    "cannot run a test over it. It can test how the same idea performed over a "
    "historical period the user chooses, or research what analysts expect for "
    "the asset."
)


def requested_strategy_template_capability_clause() -> str:
    """Interpreter prompt generated from the canonical capability registry."""

    capability_rows = ", ".join(
        f"{template}={STRATEGY_CAPABILITIES[template].status}"
        for template in sorted(REGISTERED_STRATEGY_TEMPLATES)
    )
    return (
        "Named strategy capability identity is separate from execution routing. "
        "When the user names or clearly requests a registered strategy template, "
        "set candidate_strategy_draft.requested_strategy_template to its canonical "
        f"registry key. Registered template statuses are: {capability_rows}. "
        "Preserve a draft template's identity even though it is not runnable: do "
        "not relabel it as buy_and_hold, do not create a rule_spec, and do not ask "
        "the user to define custom logic as though Argus could then run it. For a "
        "draft template, classify the turn as unsupported_or_out_of_scope with "
        "semantic_turn_act=unsupported_request, preserve the user's asset, amount, "
        "and dates, explain that Argus cannot run that named strategy yet, and offer "
        "only genuinely executable alternatives. For an executable template, set "
        "requested_strategy_template too and use its normal execution family.\n\n"
    )


def future_test_window_capability_clause() -> str:
    """Interpreter-prompt contract for the one future boundary that remains.

    A question about the future is research (decision 10); only a test over a
    future window is impossible, because that market data does not exist."""

    return (
        "Forward-looking and valuation questions are research questions, in any "
        "language and for any asset: what something will be worth, return or "
        "become over a future period ('in ten years', 'dentro de diez años'), "
        "what price a company needs to grow into, what it is worth today, "
        "analyst targets, forecasts, fair value, multiples. Classify them as a "
        "question turn (conversation_followup or beginner_guidance with an "
        "educational_question act), fill research_query with the fitting "
        "question_kind and subjects, and set research_query.scenario_question="
        "true when the answer is a value, target or fair value to compute; "
        "never classify them as "
        "unsupported_or_out_of_scope, never add an unsupported constraint for "
        "them, and leave candidate_strategy_draft without execution fields: a "
        "named strategy, an amount or a horizon inside a question does not make "
        "it a test request. A money question a computed figure answers on the "
        "user's own stated numbers (what a monthly saving grows to, a loan's "
        "payment, how long a sum takes to double) is arithmetic, not a "
        "prediction: set research_query.question_kind=none and scenario_question="
        "true with no symbols, and write assistant_response as one short lead "
        "with no figures; Argus computes it. When that figure also needs one a "
        "page publishes and the user did not state (a product's price, a bank's "
        "or lender's rate or fees, local inflation), it is a "
        "research question: set question_kind=current_external, or company_lookup "
        "for a named company, with scenario_question=true. That holds for whether "
        "a raise keeps pace with rising rents, which of two plans leaves more "
        "money, and choosing among products. Argus never converts between "
        "currencies: when the user asks to convert an amount into another "
        "currency or asks what it is worth in another currency, set "
        "research_query.question_kind=none and research_query."
        "currency_conversion=true, never route it to research and never "
        "look up a rate. An annuity, insurance policy, "
        "pension plan, store gift card or other product that is not a "
        "traded ticker is never an asset_universe entry, a strategy or an "
        "unsupported symbol. "
        "The one thing that cannot run is a backtest over a future period, "
        "because that market data does not exist: only when the user asks to "
        "test, backtest or run a strategy over a period that points forward "
        "from today, keep the strategy route, set date_range_intent.kind="
        "future_window with the exact phrase as evidence, never convert the "
        "horizon into rolling_window, calendar dates or any historical "
        "date_range, and keep the compatible facts (asset_universe, "
        "capital_amount, strategy_type, cadence) with evidence_spans so a "
        "historical test can reuse them.\n\n"
    )


# Byte-identical to the constraint-present audit framing previously inlined in
# run_field_audits._supported_strategy_capability_conflict_messages.
CAPABILITY_CONFLICT_KEEP_DIRECTION_PROMPT = (
    "You are Argus's capability-conflict audit. The primary interpreter "
    "returned both a supported canonical strategy and an "
    "unsupported_strategy_logic constraint, or returned a raw natural-"
    "language strategy phrase as unsupported while preserving executable "
    "field evidence. Decide whether the current user message semantically "
    "selects a supported Alpha strategy or asks for real unsupported "
    "custom logic. Use semantic meaning, not keyword or phrase matching. "
    "Supported Alpha strategy families include buy_and_hold and "
    "dca_accumulation for holding or recurring fixed-dollar buys, plus "
    "registry-backed signal_strategy requests when their typed executable "
    "signal rules are complete. A plain "
    "performance, "
    "return, or benchmark comparison between one primary asset and a "
    "reference asset over a stated window is a supported buy_and_hold "
    "comparison with comparison_baseline; it is not unsupported custom "
    "strategy logic unless the user adds a separate unsupported rule. "
    "Likewise, comparison_baseline on a complete supported signal strategy is "
    "only its benchmark; it does not request a second buy-and-hold strategy. "
    "Keep the unsupported "
    "constraint when the current message adds an extra unsupported entry "
    "condition, exit condition, fundamental rule, sentiment/news/event "
    "rule, custom script, brokerage action, shorting, or other logic "
    "beyond the supported strategy family. Drop it only when the message "
    "semantically asks for the supported strategy itself and no extra "
    "unsupported rule. Set selected_strategy_type to the canonical "
    "supported family when dropping the constraint. Reason from the "
    "current message and structured draft meaning. Return only JSON "
    "matching the schema."
)

_CAPABILITY_CONFLICT_INVERSE_PROMPT = (
    "You are Argus's capability-conflict audit. The primary interpreter "
    "reported this turn as unsupported or out of scope, yet it also "
    "produced an executable supported strategy draft without any "
    "unsupported_strategy_logic constraint. Decide which half is true of "
    "the current user message. Use semantic meaning, not keyword or "
    "phrase matching. Set drop_unsupported_strategy_logic=true only when "
    "the message itself semantically asks for the supported canonical "
    "strategy in the draft (for example plain holding or recurring "
    "fixed-dollar buys over a period) and the unsupported classification "
    "is the contradiction; then set selected_strategy_type to that "
    "supported family. Set keep_unsupported_strategy_logic=true when the "
    "message asks for a capability the backtest engine does not execute, "
    "such as custom entry/exit conditions, fundamental or sentiment/news/"
    "event rules, custom scripting, brokerage actions, shorting, or "
    "instruments beyond plain spot holdings; treat the supported draft as "
    "a substitution the user did not ask for. Never treat the mere "
    "presence of the draft as consent. Return only JSON matching the "
    "schema."
)

_ADMISSION_CONSTRAINT_EXPLANATION = (
    "That idea needs a rule or data source the current backtest engine "
    "cannot execute directly yet."
)


def response_has_only_unsupported_strategy_logic_constraints(
    response: LLMInterpretationResponse,
) -> bool:
    constraints = response.unsupported_constraints
    return bool(constraints) and all(
        item.category == "unsupported_strategy_logic" for item in constraints
    )


def response_needs_inverse_capability_conflict_audit(
    response: LLMInterpretationResponse,
) -> bool:
    if any(
        item.category == "unsupported_strategy_logic"
        for item in response.unsupported_constraints
    ):
        return False
    if (
        response.intent != "unsupported_or_out_of_scope"
        and response.semantic_turn_act != "unsupported_request"
    ):
        return False
    draft = response.candidate_strategy_draft
    if canonical_strategy_type(draft.strategy_type) not in {
        "buy_and_hold",
        "dca_accumulation",
    }:
        return False
    return _llm_strategy_draft_has_concrete_execution_target(draft)


def inverse_capability_conflict_messages(
    *,
    response: LLMInterpretationResponse,
    request: InterpretationRequest,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _CAPABILITY_CONFLICT_INVERSE_PROMPT},
        {
            "role": "system",
            "content": (
                "Structured draft JSON: "
                f"{response.candidate_strategy_draft.model_dump(mode='json')}"
            ),
        },
        {
            "role": "system",
            "content": (
                "Primary interpretation verdict JSON: "
                + json.dumps(
                    {
                        "intent": response.intent,
                        "semantic_turn_act": response.semantic_turn_act,
                    },
                    ensure_ascii=False,
                )
            ),
        },
        {"role": "user", "content": request.current_user_message},
    ]


def inverse_promotion_reason_codes(
    response: LLMInterpretationResponse,
) -> list[str]:
    if any(
        item.category == "unsupported_strategy_logic"
        for item in response.unsupported_constraints
    ):
        return []
    return [CAPABILITY_CONFLICT_INVERSE_REASON]


def _admission_constraint_raw_value(decision: InterpretDecision) -> str:
    draft = decision.candidate_strategy_draft
    for candidate in (
        decision.user_goal_summary,
        draft.strategy_thesis,
        draft.raw_user_phrasing,
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return "the requested strategy"


def _recognized_non_executable_template(decision: InterpretDecision) -> str | None:
    template = decision.candidate_strategy_draft.requested_strategy_template
    if template is None:
        return None
    capability = STRATEGY_CAPABILITIES[template]
    return template if capability.status != "executable" else None


def recognized_non_executable_strategy_admission_result(
    *,
    decision: InterpretDecision,
    contract: Any,
    optional_parameter_values: dict[str, Any],
) -> StageResult | None:
    """Fail closed when typed recognition and execution routing contradict."""

    template = _recognized_non_executable_template(decision)
    if template is None:
        return None
    capability = STRATEGY_CAPABILITIES[template]
    draft = decision.candidate_strategy_draft.model_copy(
        update={
            "strategy_type": template,
            "entry_rule": None,
            "exit_rule": None,
            "rule_spec": None,
        }
    )
    constraint = UnsupportedConstraint(
        category="unsupported_strategy_logic",
        raw_value=capability.display_name,
        explanation=(
            f"Argus recognizes {capability.display_name}, but cannot run that "
            "named strategy yet."
        ),
        simplification_options=contract.get_simplification_options(
            "unsupported_strategy_logic"
        ),
    )
    blocked_decision = decision.model_copy(
        update={
            "candidate_strategy_draft": _draft_with_conserved_resolved_assets(draft),
            "requires_clarification": True,
            "missing_required_fields": [
                field
                for field in decision.missing_required_fields
                if field not in {"entry_logic", "exit_logic", "rule_spec"}
            ],
            "unsupported_constraints": [constraint],
            "reason_codes": list(
                dict.fromkeys(
                    [
                        *decision.reason_codes,
                        RECOGNIZED_NON_EXECUTABLE_ADMISSION_BLOCKED,
                    ]
                )
            ),
        }
    )
    blocked_patch = dict(
        _optional_parameter_stage_patch(
            decision=blocked_decision,
            values=optional_parameter_values,
        )
    )
    # The dedicated clarification model voices typed unsupported recovery. A
    # contradictory interpreter response cannot leak into the user-visible turn.
    blocked_patch["assistant_response"] = None
    return StageResult(
        outcome="needs_clarification",
        decision=blocked_decision,
        stage_patch=blocked_patch,
    )


def admitted_or_blocked_confirmation_result(
    *,
    decision: InterpretDecision,
    stage_patch: dict[str, Any],
    contract: Any,
    optional_parameter_values: dict[str, Any],
    assistant_response: str | None,
) -> StageResult:
    """Admission invariant: an unsupported verdict cannot become an executable card.

    The verdict lives on either typed field (intent or semantic_turn_act). Only a
    typed promotion path (audit, requested-asset answer, pending-option selection,
    artifact patch) normalizes them before this boundary; anything still carrying
    the unsupported verdict here fails closed into typed unsupported recovery."""

    if (
        decision.intent != "unsupported_or_out_of_scope"
        and decision.semantic_turn_act != "unsupported_request"
    ):
        return StageResult(
            outcome="ready_for_confirmation",
            decision=decision,
            stage_patch=stage_patch,
        )
    constraint = UnsupportedConstraint(
        category="unsupported_strategy_logic",
        raw_value=_admission_constraint_raw_value(decision),
        explanation=_ADMISSION_CONSTRAINT_EXPLANATION,
        simplification_options=contract.get_simplification_options(
            "unsupported_strategy_logic"
        ),
    )
    blocked_decision = decision.model_copy(
        update={
            "candidate_strategy_draft": _draft_with_conserved_resolved_assets(
                decision.candidate_strategy_draft
            ),
            "requires_clarification": True,
            "unsupported_constraints": [*decision.unsupported_constraints, constraint],
            "reason_codes": list(
                dict.fromkeys(
                    [*decision.reason_codes, UNSUPPORTED_INTENT_ADMISSION_BLOCKED]
                )
            ),
        }
    )
    blocked_patch = dict(
        _optional_parameter_stage_patch(
            decision=blocked_decision,
            values=optional_parameter_values,
        )
    )
    # Clarification owns the refusal copy. The interpreter's acknowledgement
    # has not passed deterministic admission and cannot reach the user.
    blocked_patch["assistant_response"] = None
    return StageResult(
        outcome="needs_clarification",
        decision=blocked_decision,
        stage_patch=blocked_patch,
    )


def _draft_with_conserved_resolved_assets(draft: Any) -> Any:
    """Typed provider-validated assets survive the unsupported-recovery route.

    Restores an empty asset_universe from the draft's own provider-resolved
    records. Unresolved asset text is never promoted, the comparison baseline
    never enters the traded universe, and only a single-class set is
    structurally valid — mixed-class records keep the universe empty so
    recovery keeps asking."""

    if any(str(symbol or "").strip() for symbol in draft.asset_universe):
        return draft
    extra_parameters = draft.extra_parameters or {}
    field_provenance = extra_parameters.get("field_provenance")
    baseline_is_user_stated = (
        isinstance(field_provenance, dict)
        and field_provenance.get("comparison_baseline") == "explicit_user"
    )
    # Only a user-stated comparison target is excluded from the traded set: a
    # runtime-applied default benchmark can legitimately equal the traded
    # asset (crypto -> BTC, currency pairs -> the pair itself).
    baseline = (
        str(draft.comparison_baseline or "").strip().upper()
        if baseline_is_user_stated
        else ""
    )
    draft_class = str(draft.asset_class or "").strip().lower()
    symbols: list[str] = []
    classes: set[str] = set()
    for record in resolved_asset_records_from_strategy_context(draft):
        symbol = str(record.get("symbol") or "").strip().upper()
        record_class = str(record.get("asset_class") or "").strip().lower()
        if not symbol or (baseline and symbol == baseline):
            continue
        if draft_class and record_class and record_class != draft_class:
            continue
        if symbol not in symbols:
            symbols.append(symbol)
            if record_class:
                classes.add(record_class)
    if not symbols:
        return draft
    if not draft_class and len(classes) != 1:
        return draft
    update: dict[str, Any] = {"asset_universe": symbols[:5]}
    if not draft_class and classes:
        update["asset_class"] = next(iter(classes))
    return draft.model_copy(update=update)


def strategy_route_flags_with_future_precedence(
    *,
    interpretation: Any,
    expects_strategy_route: bool,
) -> tuple[bool, bool]:
    """A typed future horizon research did not answer keeps its recovery.

    Research claims a question read before this stage runs (decision 10), so a
    future horizon still here belongs to a turn with no grounded answer. Forcing
    the strategy route and disabling educational suppression sends it to the
    future test-window recovery, which offers the historical test and analyst
    research, instead of returning the model's own forecast as prose."""

    if strategy_draft_future_horizon(interpretation.candidate_strategy_draft):
        return True, False
    return expects_strategy_route, _educational_turn_has_strategy_baggage(
        interpretation=interpretation,
        expects_strategy_route=expects_strategy_route,
    )


def _typed_future_horizon(decision: InterpretDecision) -> dict[str, Any] | None:
    return strategy_draft_future_horizon(decision.candidate_strategy_draft)


def future_performance_admission_result(
    *,
    decision: InterpretDecision,
    contract: Any,
    optional_parameter_values: dict[str, Any],
) -> StageResult | None:
    """Fail closed when a strategy-route turn asks to test a future window.

    Only a test over a period that has not happened yet is impossible; a
    question about the future is research and never reaches this route. The
    horizon moves to original-intent evidence, compatible facts stay on the
    draft, and the historical period is re-requested after an explicit
    supported-alternative selection. The clarify stage owns the voice."""

    horizon = _typed_future_horizon(decision)
    if horizon is None:
        return None
    draft = decision.candidate_strategy_draft
    extra_parameters = dict(draft.extra_parameters or {})
    extra_parameters.pop("date_range_intent", None)
    extra_parameters.pop("requested_date_range", None)
    extra_parameters.pop("effective_date_range", None)
    # Stale date evidence must not outlive the horizon move: the DCA contract
    # rebuilds a window from these spans, which would skip the period question
    # after a historical-period selection. Non-date evidence stays.
    extra_parameters.pop("date_range_raw_text", None)
    evidence_spans = extra_parameters.get("evidence_spans")
    if isinstance(evidence_spans, dict) and "date_range" in evidence_spans:
        remaining_spans = {
            key: value for key, value in evidence_spans.items() if key != "date_range"
        }
        if remaining_spans:
            extra_parameters["evidence_spans"] = remaining_spans
        else:
            extra_parameters.pop("evidence_spans", None)
    extra_parameters[FUTURE_HORIZON_EVIDENCE_KEY] = horizon
    stripped_draft = _draft_with_conserved_resolved_assets(
        draft.model_copy(
            update={"date_range": None, "extra_parameters": extra_parameters}
        )
    )
    constraint = UnsupportedConstraint(
        category=FUTURE_PERFORMANCE_CATEGORY,
        raw_value=str(
            horizon.get("evidence") or decision.user_goal_summary or "future performance"
        ),
        explanation=_FUTURE_PERFORMANCE_EXPLANATION,
        simplification_options=contract.get_simplification_options(
            FUTURE_PERFORMANCE_CATEGORY
        ),
    )
    blocked_decision = decision.model_copy(
        update={
            "candidate_strategy_draft": stripped_draft,
            "requires_clarification": True,
            # The typed future boundary owns this turn's reason code, ahead of
            # any model-authored constraint label.
            "unsupported_constraints": [constraint, *decision.unsupported_constraints],
            "missing_required_fields": list(
                dict.fromkeys([*decision.missing_required_fields, "date_range"])
            ),
            "reason_codes": list(
                dict.fromkeys(
                    [*decision.reason_codes, FUTURE_PERFORMANCE_ADMISSION_BLOCKED]
                )
            ),
        }
    )
    blocked_patch = dict(
        _optional_parameter_stage_patch(
            decision=blocked_decision,
            values=optional_parameter_values,
        )
    )
    blocked_patch["assistant_response"] = None
    return StageResult(
        outcome="needs_clarification",
        decision=blocked_decision,
        stage_patch=blocked_patch,
    )


def strategy_route_admission_result(
    *,
    expects_strategy_route: bool,
    decision: InterpretDecision,
    stage_patch: dict[str, Any],
    contract: Any,
    optional_parameter_values: dict[str, Any],
    assistant_response: str | None,
) -> StageResult | None:
    """Apply unsupported admission before ordinary missing-field clarification."""

    if not expects_strategy_route:
        return None
    recognized_non_executable_result = (
        recognized_non_executable_strategy_admission_result(
            decision=decision,
            contract=contract,
            optional_parameter_values=optional_parameter_values,
        )
    )
    if recognized_non_executable_result is not None:
        return recognized_non_executable_result
    future_result = future_performance_admission_result(
        decision=decision,
        contract=contract,
        optional_parameter_values=optional_parameter_values,
    )
    if future_result is not None:
        return future_result
    has_unsupported_verdict = (
        decision.intent == "unsupported_or_out_of_scope"
        or decision.semantic_turn_act == "unsupported_request"
    )
    if decision.requires_clarification and not has_unsupported_verdict:
        return None
    confirmation_patch = dict(stage_patch)
    if assistant_response and "artifact_assumption_edit_planned" in decision.reason_codes:
        confirmation_patch["assistant_response"] = assistant_response
    return admitted_or_blocked_confirmation_result(
        decision=decision,
        stage_patch=confirmation_patch,
        contract=contract,
        optional_parameter_values=optional_parameter_values,
        assistant_response=assistant_response,
    )

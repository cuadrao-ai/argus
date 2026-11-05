"""Typed ownership checks shared by preparation and both research entries."""

from __future__ import annotations

from typing import Any

from loguru import logger

from argus.agent_runtime.interpreter.draft_shape import (
    strategy_draft_future_horizon,
    strategy_has_execution_evidence,
)
from argus.agent_runtime.interpreter.strategy_routing import route_owner
from argus.agent_runtime.research_query import ResearchQueryExtraction

# Recorded when a concept question is answered by grounded research rather
# than by the interpreter's own prose.
CONCEPT_QUESTION_REASON_CODE = "research_answers_concept_question"
# Recorded when an out-of-scope verdict that typed nothing to run is answered
# by research: a money question is never refused as out of scope.
UNSUPPORTED_VERDICT_REASON_CODE = "research_answers_unsupported_verdict"
# Recorded on the interpretation when a strategy claim was set aside because
# its horizon points forward: the question was answered by research, not
# refused as a test that cannot run (decision 10).
FUTURE_HORIZON_QUESTION_REASON_CODE = "research_answers_future_horizon_question"


def _strategy_route_claims_the_turn(interpretation: Any) -> bool:
    return bool(
        route_owner(
            intent=interpretation.intent,
            semantic_turn_act=interpretation.semantic_turn_act,
        )
        or strategy_has_execution_evidence(
            interpretation.candidate_strategy_draft, include_defaults=False
        )
    )


def strategy_claim_waived_by_future_horizon(interpretation: Any) -> bool:
    """A strategy claim over a future horizon is not a runnable test.

    There is no market data for a period that has not happened yet, so the
    claim cannot own the turn: the question it arrived with is what research
    answers, and the horizon survives typed for the answer's next steps."""
    return _strategy_route_claims_the_turn(interpretation) and bool(
        strategy_draft_future_horizon(interpretation.candidate_strategy_draft)
    )


def research_turn_has_conflicting_owner(interpretation: Any) -> bool:
    """A question payload cannot take execution, refusal or artifact ownership."""
    return bool(
        (
            _strategy_route_claims_the_turn(interpretation)
            and not strategy_claim_waived_by_future_horizon(interpretation)
        )
        or interpretation.unsupported_constraints
        or interpretation.semantic_turn_act in {"result_followup", "retry_failed_action"}
        or interpretation.artifact_target not in (None, "none")
        # An explicit discovery act owns the turn even when the interpreter
        # also supplies a generic result-composition hint. Artifact targets,
        # result acts and factual result keys still protect their own route.
        or (
            interpretation.result_followup_focus
            and interpretation.semantic_turn_act != "asset_discovery"
        )
        or interpretation.result_followup_fact_key
        or interpretation.capability_question_focus
        or getattr(interpretation, "uses_latest_result_context", False)
    )


def scenario_is_typed(query: Any, interpretation: Any) -> bool:
    """Whether either typed fact says this read is a computed scenario: the
    research query's ``scenario_question`` bit, or a ``future_window`` horizon
    the interpreter typed on the draft. Pure; the research layer records the
    horizon-only case when it applies the contract."""
    return bool(getattr(query, "scenario_question", False)) or (
        strategy_draft_future_horizon(interpretation.candidate_strategy_draft) is not None
    )


def primary_read_asks_a_fact_question(interpretation: Any) -> bool:
    """The primary read typed the message as a finance fact question.

    A read that says the answer is a computed scenario about named subjects is
    a fact question whatever kind it left (decision 10): the scenario owner
    must see it. A scenario bit with no subject is research only when a page
    must supply a figure; on the user's own numbers it is arithmetic for the
    no-search answer, and a typed horizon alone never admits, so a test asked
    over a future window keeps its recovery."""
    query = getattr(interpretation, "research_query", None)
    if query is None:
        return False
    if scenario_is_typed(query, interpretation) and not query.symbols:
        # A scenario with no subject is research only when its bit names a
        # published figure to look up (a product's price, a bank's rate, local
        # inflation); on the user's own numbers it is arithmetic, and a typed
        # horizon alone keeps a future test on its recovery.
        return bool(getattr(query, "scenario_question", False)) and (
            query.question_kind not in ("concept", "none")
        )
    if query.question_kind not in ("concept", "none"):
        return True
    # A kind-none read is admitted only by the scenario bit with subjects; a
    # horizon alone keeps a test asked over a future window on its recovery.
    return bool(getattr(query, "scenario_question", False))


def primary_read_is_arithmetic(interpretation: Any) -> bool:
    """The primary read typed a computed answer on the user's own numbers: the
    scenario bit, no subject, kind none, and no other owner. A concept question
    is research's to answer."""
    query = getattr(interpretation, "research_query", None)
    return bool(
        query is not None
        and getattr(query, "scenario_question", False)
        and not query.symbols
        and query.question_kind == "none"
        and not research_turn_has_conflicting_owner(interpretation)
    )


def primary_research_query(interpretation: Any) -> ResearchQueryExtraction | None:
    if not primary_read_asks_a_fact_question(interpretation):
        return None
    if research_turn_has_conflicting_owner(interpretation):
        return None
    if strategy_claim_waived_by_future_horizon(interpretation):
        _note_future_horizon_question(interpretation)
    return interpretation.research_query


def concept_research_query(interpretation: Any) -> ResearchQueryExtraction | None:
    """A concept question the fact gate declined takes the grounded balanced
    path: research leads, and the no-search answer keeps kind none."""
    query = getattr(interpretation, "research_query", None)
    if (
        query is None
        or query.question_kind != "concept"
        or research_turn_has_conflicting_owner(interpretation)
    ):
        return None
    _note_research_route(interpretation, CONCEPT_QUESTION_REASON_CODE)
    return query


def unsupported_verdict_research_query(
    interpretation: Any,
) -> ResearchQueryExtraction | None:
    """An out-of-scope verdict that typed no question, no refusal payload, no
    pending need and nothing to run is answered by research as a current
    external question; a typed refusal keeps its recovery route."""
    draft = interpretation.candidate_strategy_draft
    if (
        (
            interpretation.intent != "unsupported_or_out_of_scope"
            and interpretation.semantic_turn_act != "unsupported_request"
        )
        or getattr(interpretation, "research_query", None) is not None
        or interpretation.requires_clarification
        or getattr(interpretation, "asset_discovery", None) is not None
        or research_turn_has_conflicting_owner(interpretation)
        or strategy_has_execution_evidence(draft, include_defaults=False)
        or strategy_draft_future_horizon(draft)
    ):
        return None
    _note_research_route(interpretation, UNSUPPORTED_VERDICT_REASON_CODE)
    return ResearchQueryExtraction(question_kind="current_external")


def educational_question_has_no_query(interpretation: Any) -> bool:
    """Absence of a typed question does not authorize external research."""
    return (
        interpretation.semantic_turn_act == "educational_question"
        and getattr(interpretation, "research_query", None) is None
    )


def _note_research_route(interpretation: Any, code: str) -> None:
    if code not in interpretation.reason_codes:
        interpretation.reason_codes.append(code)
    logger.info(
        "Research answers a read the fact gate declined intent={} act={} code={}",
        interpretation.intent,
        interpretation.semantic_turn_act,
        code,
    )


def _note_future_horizon_question(interpretation: Any) -> None:
    """Record that a strategy claim was set aside for a future horizon."""
    if FUTURE_HORIZON_QUESTION_REASON_CODE in interpretation.reason_codes:
        return
    interpretation.reason_codes.append(FUTURE_HORIZON_QUESTION_REASON_CODE)
    draft = interpretation.candidate_strategy_draft
    logger.info(
        "Research answers a future-horizon question over a strategy claim "
        "intent={} act={} asset_count={} reason={}",
        interpretation.intent,
        interpretation.semantic_turn_act,
        len(getattr(draft, "asset_universe", None) or []),
        FUTURE_HORIZON_QUESTION_REASON_CODE,
        failure_classification=FUTURE_HORIZON_QUESTION_REASON_CODE,
    )

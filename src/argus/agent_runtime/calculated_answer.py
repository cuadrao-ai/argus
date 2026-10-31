"""The no-search answer that owns its math.

When the user's own figures are enough, or a lookup failed, the answer comes
from one voicing call that returns prose and its typed calculations, one per
option. Their inputs may be the user's words, Argus market data for a current
price, or assumptions the answer states; a page only when it was retrieved for
this conversation. The answer step computes each card and fills the prose's
figures from them. Figures only the user knows become one plain question.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pydantic import ConfigDict, Field, ValidationError, field_validator

from argus.agent_runtime.answer_calculation import (
    ANSWER_ASSUMPTIONS_KEY,
    ANSWER_TEMPLATE_KEY,
    MarketClose,
    PublishedCalculation,
    calculation_names,
    latest_market_close,
    publish_calculations,
)
from argus.agent_runtime.history import select_thread_history
from argus.agent_runtime.knowledge_answer import VoicedAnswer
from argus.agent_runtime.stages.interpret_types import (
    InterpretDecision,
    StageResult,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import RunState, UserState
from argus.domain.calculations._shared import field_label
from argus.domain.calculations.answer_request import (
    ANSWER_CALCULATION_INSTRUCTIONS,
    MAX_ANSWER_CALCULATIONS,
    AnswerCalculation,
    AnswerCalculationInput,
    all_properties_required,
    calculation_kinds_clause,
)
from argus.domain.research.contracts import ResearchSource, RetrievedRow
from argus.llm.openrouter import (
    invoke_openrouter_json_schema_sync,
    openrouter_structured_model_candidates,
    resolve_openrouter_api_key,
)

PENDING_PAYLOAD_KEY = "calculations"
# The one calculation a pending question stored before answers carried several.
LEGACY_PENDING_PAYLOAD_KEY = "calculation"
CALCULATED_ANSWER_REASON_CODE = "calculated_answer"
PENDING_REPLY_REASON_CODE = "calculation_pending_reply"
# Recorded when a reply's voiced calculation changed a figure its pending
# question already held: the stored calculation stands, and only the blanks it
# owed take the reply's figures.
PENDING_KEPT_REASON_CODE = "calculation_pending_reply_kept_stored"
# A pending payload's map of each calculation's reference name to the fields that
# calculation asked for; a reply fills a blank only on its own calculation.
REQUESTED_BY_CALCULATION_KEY = "requested_by_calculation"
INPUT_MISSING_REASON_CODE = "calculation_input_missing"
# Recorded when a voiced answer only restated the user's question; it is never
# published, and the caller's honest note stands in.
ANSWER_RESTATED_QUESTION_REASON_CODE = "answer_restated_question"
# A research answer's calculation that needs figures only the reader knows is
# offered under the answer, and taken through a typed action.
CALCULATION_OFFER_KEY = "calculation_offer"
CALCULATION_OFFER_ACTION = "calculation_offer"
CALCULATION_OFFERED_REASON_CODE = "calculation_offered"
CALCULATION_OFFER_TAKEN_REASON_CODE = "calculation_offer_taken"
_HISTORY_TURNS = 4

# Model-facing contract for the one no-search answer that computes.
NO_SEARCH_ANSWER_GUIDANCE = (
    "Answer the user's money question in their language. Nothing was looked "
    "up for this answer: use the user's own figures, the Argus market data "
    "listed below and assumptions you state plainly. When a figure computed "
    "from inputs answers or decides the question, always return calculations; "
    "never answer such a question with prose alone. A figure a page would "
    "publish that is not listed here, such as a product's price or a bank's "
    "rate, becomes an assumption: choose a typical value, mark it assumption "
    "and say plainly in the answer that you assumed it and that the user can "
    "change it. A figure only the user knows, such as their balance, payment, "
    "term, income or horizon, is never assumed: list each one with source user "
    "and a null value, still return calculations, and write the answer as one "
    "plain question asking for all of them and nothing else: never for a figure "
    "the calculation produces, such as an effective annual rate. Name a currency only when "
    "the user stated one. "
    "No advice, no forecast stated as fact, no em dashes, no headings, no "
    "tables. Compose lead (required), one short sentence that answers the "
    "question or asks the one question; bullets (optional, up to 4), short "
    "plain phrases; note (optional), one closing sentence, which mentions a "
    "lookup only when this message lists one that failed. "
)


def _calculation_first(schema: dict[str, Any]) -> None:
    """Every field is written, the calculations before the prose that references them."""
    all_properties_required(schema)
    properties = schema.get("properties") or {}
    if "calculations" in properties:
        schema["properties"] = {
            "calculations": properties["calculations"],
            **{
                name: value
                for name, value in properties.items()
                if name != "calculations"
            },
        }
        schema["required"] = list(schema["properties"])


class CalculatedVoicedAnswer(VoicedAnswer):
    """A voiced answer with the calculations Argus computes for it."""

    model_config = ConfigDict(json_schema_extra=_calculation_first)

    calculations: list[AnswerCalculation] = Field(default_factory=list)

    @field_validator("calculations")
    @classmethod
    def _bounded(cls, value: list[AnswerCalculation]) -> list[AnswerCalculation]:
        return value[:MAX_ANSWER_CALCULATIONS]


@dataclass(frozen=True)
class CalculatedAnswer:
    """An answer whose figures came from its cards, or one plain question."""

    answer_text: str
    patch: dict[str, Any]
    template: dict[str, Any] | None
    question_field: str | None
    pending: dict[str, Any] | None
    missing_inputs: tuple[str, ...] = ()
    assumptions: tuple[dict[str, str], ...] = ()


def calculated_answer(
    *,
    message: str,
    language: str,
    user: UserState,
    notes: list[str],
    history: Sequence[Any] = (),
    market_facts: dict[str, str] | None = None,
    not_looked_up: Sequence[str] = (),
    pending: dict[str, Any] | None = None,
    subject_symbol: str | None = None,
    retrieved: Sequence[ResearchSource] = (),
    market_close: MarketClose = latest_market_close,
    lookup_failed: bool = False,
    offered: bool = False,
    evidence: Sequence[RetrievedRow] = (),
) -> CalculatedAnswer | None:
    """One voicing call and its computed calculation, or None when voicing failed."""
    if not resolve_openrouter_api_key():
        return None
    voiced = _voice(
        _messages(
            message=message,
            language=language,
            history=history,
            market_facts=market_facts or {},
            not_looked_up=not_looked_up,
            pending=pending,
            lookup_failed=lookup_failed,
            offered=offered,
        )
    )
    if voiced is None:
        return None
    if _restates(message, voiced.lead):
        if ANSWER_RESTATED_QUESTION_REASON_CODE not in notes:
            notes.append(ANSWER_RESTATED_QUESTION_REASON_CODE)
        logger.info(
            "Voiced answer only restated the question",
            failure_classification=ANSWER_RESTATED_QUESTION_REASON_CODE,
        )
        return None
    prose = voiced.as_markdown()
    if not voiced.calculations:
        return None if "{{" in prose else CalculatedAnswer(prose, {}, None, None, None)
    from argus.domain.capability_registry import get_tool_catalog

    calculations = (
        completed_pending(pending, voiced.calculations, notes)
        if pending
        else list(voiced.calculations)
    )
    published = publish_calculations(
        calculations,
        template=prose,
        language=language,
        catalog=get_tool_catalog(),
        retrieved=retrieved,
        currency=user.currency,
        subject_symbol=subject_symbol,
        market_close=market_close,
        notes=notes,
        evidence=evidence,
    )
    return answer_from_published(
        calculations,
        published,
        prose=prose,
        language=language,
        retrieved=retrieved,
        evidence=evidence,
    )


def answer_from_published(
    requests: Sequence[AnswerCalculation],
    published: PublishedCalculation | None,
    *,
    prose: str,
    language: str,
    retrieved: Sequence[ResearchSource],
    evidence: Sequence[RetrievedRow] = (),
) -> CalculatedAnswer | None:
    """The answer published calculations make: their cards and prose, or the one
    question for the figures only the user knows; None when inputs were not found."""
    if published is None or published.not_looked_up:
        return None
    if published.question_field is not None:
        field = published.question_field
        owed = published.owed or (field,)
        return CalculatedAnswer(
            answer_text=missing_inputs_lead(language),
            patch={},
            template=None,
            question_field=field,
            missing_inputs=tuple(owed),
            pending={
                PENDING_PAYLOAD_KEY: [
                    request.model_dump(mode="json") for request in requests
                ],
                "requested_field": field,
                "requested_fields": list(owed),
                REQUESTED_BY_CALCULATION_KEY: {
                    name: list(fields) for name, fields in published.owed_by_calculation
                },
                "evidence": [row.model_dump(mode="json") for row in evidence],
                "retrieved": [source.model_dump(mode="json") for source in retrieved],
            },
        )
    return CalculatedAnswer(
        answer_text=published.answer_text or "",
        patch=published.patch,
        template=published.template,
        question_field=None,
        pending=None,
        assumptions=published.assumptions,
    )


async def calculated_answer_stage_result(
    *,
    interpretation: StructuredInterpretation,
    state: RunState,
    user: UserState,
    pending: dict[str, Any] | None = None,
    offered: bool = False,
) -> StageResult | None:
    """The no-search answer as a turn: its computed card under the prose, or one
    plain question for the figure only the user knows."""
    retrieved = [
        ResearchSource.model_validate(page)
        for page in ((pending or {}).get("retrieved") or [])
        if isinstance(page, dict) and page.get("url")
    ]
    answered = await asyncio.to_thread(
        calculated_answer,
        message=state.current_user_message,
        language=user.language_preference,
        user=user,
        notes=interpretation.reason_codes,
        history=state.recent_thread_history,
        pending=pending,
        retrieved=retrieved,
        offered=offered,
        evidence=[
            RetrievedRow.model_validate(row)
            for row in ((pending or {}).get("evidence") or [])
            if isinstance(row, dict)
        ],
    )
    if answered is None:
        return None
    from argus.agent_runtime.research_grounded import research_decision

    code = PENDING_REPLY_REASON_CODE if pending else CALCULATED_ANSWER_REASON_CODE
    if answered.question_field is not None:
        return question_stage_result(
            answered,
            decision=research_decision(interpretation, user, INPUT_MISSING_REASON_CODE),
        )
    patch: dict[str, Any] = {**answered.patch, "assistant_response": answered.answer_text}
    from argus.agent_runtime.answer_calculation import cards_in, record_unsourced_figures

    record_unsourced_figures(
        answered.answer_text,
        cited=[],
        cards=cards_in(answered.patch),
        notes=interpretation.reason_codes,
        message=state.current_user_message,
    )
    if answered.template is not None:
        patch[ANSWER_TEMPLATE_KEY] = answered.template
    if answered.assumptions:
        patch[ANSWER_ASSUMPTIONS_KEY] = list(answered.assumptions)
    return StageResult(
        outcome="ready_to_respond",
        decision=research_decision(interpretation, user, code),
        stage_patch=patch,
    )


async def calculation_offer_stage_result(
    *,
    state: RunState,
    user: UserState,
    selected_thread_metadata: dict[str, Any],
) -> StageResult | None:
    """The reader took a research answer's offered calculation: one plain
    question for the figures only they know, with the cited ones kept, which the
    reply completes like any pending calculation."""
    action = state.structured_action
    if action is None or action.type != CALCULATION_OFFER_ACTION:
        return None
    from argus.agent_runtime.recovery_messages import recovery_message
    from argus.agent_runtime.research_grounded import research_decision
    from argus.agent_runtime.state.models import StrategySummary

    interpretation = StructuredInterpretation(
        intent="conversation_followup",
        task_relation="new_task",
        user_goal_summary=state.current_user_message,
        semantic_turn_act="educational_question",
        candidate_strategy_draft=StrategySummary(),
        reason_codes=[CALCULATION_OFFER_TAKEN_REASON_CODE],
    )
    offer = selected_thread_metadata.get(CALCULATION_OFFER_KEY)
    if not isinstance(offer, dict) or not pending_requests(offer):
        return StageResult(
            outcome="ready_to_respond",
            decision=research_decision(
                interpretation, user, CALCULATION_OFFER_TAKEN_REASON_CODE
            ),
            stage_patch={
                "assistant_response": recovery_message(
                    "artifact_action_invalid_state", language=user.language_preference
                )
            },
        )
    asked = await calculated_answer_stage_result(
        interpretation=interpretation,
        state=state,
        user=user,
        pending=offer,
        offered=True,
    )
    if asked is not None and asked.outcome == "await_user_reply":
        return asked
    field = str(offer.get("requested_field") or "")
    return question_stage_result(
        CalculatedAnswer(
            answer_text=missing_inputs_lead(user.language_preference),
            patch={},
            template=None,
            question_field=field,
            pending=offer,
            missing_inputs=tuple(offer.get("requested_fields") or [field]),
        ),
        decision=research_decision(interpretation, user, INPUT_MISSING_REASON_CODE),
    )


def pending_calculation_reply(
    interpretation: StructuredInterpretation, metadata: dict[str, Any]
) -> dict[str, Any] | None:
    """A reply to the answer's one question completes its calculation, unless
    the primary read routed the reply to an action of its own."""
    from argus.agent_runtime.interpreter.research_routing import (
        research_turn_has_conflicting_owner,
    )

    pending = pending_calculation(metadata)
    if pending is None or interpretation.asset_discovery is not None:
        return None
    return None if research_turn_has_conflicting_owner(interpretation) else pending


def pending_calculation(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """The calculations a reply completes: the answer asked the user for their
    figures and is waiting for them."""
    if metadata.get("last_stage_outcome") != "await_user_reply":
        return None
    clarification = metadata.get("clarification")
    payload = clarification.get("payload") if isinstance(clarification, dict) else None
    if isinstance(payload, dict) and pending_requests(payload):
        return payload
    return None


def pending_requests(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The calculations a pending question completes, in the answer's order; a
    payload stored before answers carried several holds its one calculation."""
    if not isinstance(payload, Mapping):
        return []
    items = payload.get(PENDING_PAYLOAD_KEY)
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    single = payload.get(LEGACY_PENDING_PAYLOAD_KEY)
    return [single] if isinstance(single, dict) else []


def completed_pending(
    pending: Mapping[str, Any],
    voiced: Sequence[AnswerCalculation],
    notes: list[str],
) -> list[AnswerCalculation]:
    """The pending question's own calculations, each blank it asked for (a null
    input, or a requested field it never listed) filled from the reply when the
    reply states it; every other figure keeps its stored value and source,
    whatever the voiced reply wrote."""
    try:
        stored = [
            AnswerCalculation.model_validate(item) for item in pending_requests(pending)
        ]
    except ValidationError:
        return list(voiced)
    if not stored:
        return list(voiced)
    replied = dict(zip(calculation_names(voiced), voiced, strict=True))
    by_calculation = pending.get(REQUESTED_BY_CALCULATION_KEY)
    requested = {
        str(name)
        for name in pending.get("requested_fields") or [pending.get("requested_field")]
        if name
    }
    changed = len(voiced) != len(stored)
    completed: list[AnswerCalculation] = []
    for name, request in zip(calculation_names(stored), stored, strict=True):
        answer = replied.get(name)
        same = (
            answer is not None
            and answer.kind == request.kind
            and answer.solve_for == request.solve_for
        )
        changed = changed or not same
        filled = {item.name: item for item in answer.inputs} if same and answer else {}
        inputs: list[AnswerCalculationInput] = []
        scoped = by_calculation.get(name) if isinstance(by_calculation, Mapping) else None
        asked = (
            {str(field) for field in scoped}
            if isinstance(scoped, list)
            else requested or {item.name for item in request.inputs if item.value is None}
        )
        for item in request.inputs:
            reply = filled.pop(item.name, None)
            if item.value is None:
                stated = reply is not None and reply.value is not None
                if stated and item.name not in asked:
                    changed = True
                owed = stated and item.name in asked and reply.source != "assumption"
                inputs.append(reply if owed else item)
                continue
            if reply is not None and (
                reply.value != item.value or reply.source != item.source
            ):
                changed = True
            inputs.append(item)
        for field in [field for field in filled if field in asked]:
            reply = filled.pop(field)
            if reply.value is not None and reply.source != "assumption":
                inputs.append(reply)
        changed = changed or bool(filled)
        completed.append(request.model_copy(update={"inputs": inputs}))
    if changed and PENDING_KEPT_REASON_CODE not in notes:
        notes.append(PENDING_KEPT_REASON_CODE)
        logger.info(
            "A pending reply changed figures its question held; the stored ones stand",
            failure_classification=PENDING_KEPT_REASON_CODE,
        )
    return completed


def question_stage_result(
    answered: CalculatedAnswer, *, decision: InterpretDecision | None
) -> StageResult:
    """One plain question for the figures only the user knows, with the pending
    calculations the reply completes."""
    field = str(answered.question_field)
    owed = list(answered.missing_inputs or (field,))
    return StageResult(
        outcome="await_user_reply",
        decision=decision,
        stage_patch={
            "assistant_prompt": answered.answer_text,
            "requested_field": field,
            "missing_required_fields": owed,
            "clarification": {
                "kind": "clarification",
                "reason_code": INPUT_MISSING_REASON_CODE,
                # Display transport: the app writes the question from the typed
                # missing inputs and their label keys, in the reader's language.
                "prompt_source": "degraded_fallback",
                "requested_field": field,
                "requested_fields": owed,
                "missing_inputs": [
                    {"name": name, "label": field_label(name).model_dump(mode="json")}
                    for name in owed
                ],
                "semantic_needs": [],
                "payload": answered.pending or {},
                "options": [],
            },
        },
    )


def missing_inputs_lead(language: str) -> str:
    """The stored line of a question for figures only the user knows; the app
    names each figure from the typed missing inputs."""
    if str(language or "").startswith("es"):
        return "Para calcularlo, necesito algunos de tus propios datos."
    return "To work this out, I need a few of your own figures."


def _restates(message: str, lead: str) -> bool:
    """Whether a lead is the user's own question and nothing more."""

    def plain(text: str) -> str:
        return "".join(ch for ch in str(text).casefold() if ch.isalnum())

    return bool(plain(lead)) and plain(lead) == plain(message)


def _voice(messages: list[dict[str, str]]) -> CalculatedVoicedAnswer | None:
    for model_name in openrouter_structured_model_candidates():
        try:
            voiced = invoke_openrouter_json_schema_sync(
                task="knowledge_voicing",
                messages=messages,
                schema_model=CalculatedVoicedAnswer,
                schema_name="CalculatedVoicedAnswer",
                model_name=model_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Calculated answer voicing failed error={exc!r}")
            continue
        if isinstance(voiced, CalculatedVoicedAnswer) and voiced.lead.strip():
            return voiced
    return None


def _messages(
    *,
    message: str,
    language: str,
    history: Sequence[Any],
    market_facts: dict[str, str],
    not_looked_up: Sequence[str],
    pending: dict[str, Any] | None,
    lookup_failed: bool = False,
    offered: bool = False,
) -> list[dict[str, str]]:
    context = [
        NO_SEARCH_ANSWER_GUIDANCE,
        f"Reply in {language}. ",
        ANSWER_CALCULATION_INSTRUCTIONS,
        calculation_kinds_clause(),
    ]
    lines: list[str] = []
    for turn in select_thread_history(history or [], recent_limit=_HISTORY_TURNS):
        role = str(
            getattr(turn, "role", "")
            or (turn.get("role") if isinstance(turn, dict) else "")
        )
        content = str(
            getattr(turn, "content", "")
            or (turn.get("content") if isinstance(turn, dict) else "")
        )
        if role and content:
            lines.append(f"{role}: {content}")
    if lines:
        context.append("Recent conversation, oldest first:\n" + "\n".join(lines) + "\n")
    if market_facts:
        context.append(
            "Argus market data:\n"
            + "\n".join(f"{name}: {value}" for name, value in market_facts.items())
            + "\n"
        )
    if not_looked_up:
        context.append(
            "Could not be looked up for this answer, so say so plainly: "
            + ", ".join(not_looked_up)
            + ".\n"
        )
    elif lookup_failed:
        context.append(
            "The lookup for this answer failed: say so plainly in one short sentence, "
            "then answer what you can from the user's figures, Argus market data and "
            "assumptions you state. Never restate the question as the answer.\n"
        )
    if pending:
        calculations = pending_requests(pending)
        payload = json.dumps(calculations, ensure_ascii=False)
        kinds = ", ".join(str(item.get("kind")) for item in calculations)
        if offered:
            context.append(
                "The reader chose to work this out with their own figures. Keep "
                f"these calculations ({kinds}) and the inputs they already hold with "
                "their sources, and ask one plain question for every figure only the "
                f"reader knows: {payload}\n"
            )
        else:
            asked = ", ".join(
                pending.get("requested_fields") or [str(pending.get("requested_field"))]
            )
            context.append(
                f"Argus asked the user for {asked} of these calculations ({kinds}). "
                "Keep their names, kinds and inputs so far, and fill the answered "
                f"figures: {payload}\n"
            )
    return [
        {"role": "system", "content": "".join(context)},
        {"role": "user", "content": str(message)},
    ]

"""Grounded knowledge answers for non-strategy turns.

The answer router: a facts question gets an answer from the most authoritative
source available, then the Try next surface. Own market data first, the
configured search provider for current external facts, and the interpreter's
own prose for concepts. Classification is an LLM call; nothing here routes on
keywords.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from argus.agent_runtime.interpreter.draft_shape import (
    strategy_has_execution_evidence,
)
from argus.agent_runtime.interpreter.research_routing import (
    educational_question_has_no_query,
    primary_read_is_arithmetic,
    primary_research_query,
)
from argus.agent_runtime.next_experiments import (
    NEXT_EXPERIMENT_ACTION_LABELS,
    NEXT_EXPERIMENTS_VERSION,
    next_experiment_label_key,
)
from argus.agent_runtime.profile.response_profile import (
    resolve_effective_response_profile,
)
from argus.agent_runtime.stages.interpret_types import (
    InterpretDecision,
    StageResult,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import (
    RunState,
    StrategySummary,
    TaskSnapshot,
    UserState,
)
from argus.agent_runtime.strategy_contract import (
    resolve_date_range,
    resolve_executable_date_range,
)
from argus.domain.research.config import research_rail_enabled
from argus.domain.research.search.config import discovery_search_config
from argus.domain.research.search.contracts import SearchUnavailableError
from argus.domain.research.search.selection import search_provider_for_config
from argus.llm.openrouter import (
    invoke_openrouter_json_schema,
    openrouter_structured_model_candidates,
)
from argus.log_sink import exception_origin

_KNOWLEDGE_INTENTS = frozenset(
    {"unsupported_or_out_of_scope", "conversation_followup", "beginner_guidance"}
)
# Acts owned by other surfaces (discovery, results, cards) never route here.
_KNOWLEDGE_ACTS = frozenset({"educational_question", "unsupported_request"})
# Routes on the typed payload, not the act label: an unsupported_request turn
# carrying unsupported_constraints is a refusal decision with recovery options,
# never a question the knowledge/research rail may answer with stats.
_UNSUPPORTED_PAYLOAD_REASON_CODE = "unsupported_payload_kept_recovery_route"
# A different stand-down from the one above: this one fires only when the
# payload is empty and the draft itself describes a test, so it needs its
# own name to stay distinguishable in reason_codes and eval traces.
_UNSUPPORTED_EXECUTION_REASON_CODE = "unsupported_execution_kept_recovery_route"
_SEARCH_MAX_RESULTS = 5


def _with_bold_figure(text: str) -> str:
    """Guarantee the first figure in a palette line is bold.

    Presentation only: this walks tokens for a digit-bearing one, it does not
    interpret language or route anything.
    """
    if not text or "**" in text:
        return text
    tokens = text.split(" ")
    for index, token in enumerate(tokens):
        if any(character.isdigit() for character in token):
            core = token.rstrip(".,;:)")
            suffix = token[len(core) :]
            if index + 1 < len(tokens) and tokens[index + 1].startswith("%"):
                trailing = tokens[index + 1].rstrip(".,;:)")
                rest = tokens[index + 1][len(trailing) :]
                tokens[index] = f"**{core} {trailing}**{rest or suffix}"
                del tokens[index + 1]
            else:
                tokens[index] = f"**{core}**{suffix}"
            return " ".join(tokens)
    return text


class VoicedAnswer(BaseModel):
    """Voicing contract: the model composes from a palette of blocks it may
    use or skip; the code renders whatever arrived, so the answer is creative
    in shape but always well formed."""

    lead: str
    bullets: list[str] = Field(default_factory=list)
    note: str | None = None

    def as_markdown(self) -> str:
        # Rendering enforces the palette the prompt asks for, so a provider
        # that follows the JSON schema but ignores prose instructions still
        # produces the contracted emphasis.
        blocks: list[str] = []
        lead = _with_bold_figure(" ".join(self.lead.split()))
        if lead:
            blocks.append(lead)
        lines = [
            f"- {_with_bold_figure(' '.join(bullet.split()))}"
            for bullet in self.bullets[:4]
            if bullet.strip()
        ]
        if lines:
            blocks.append("\n".join(lines))
        note = " ".join((self.note or "").split())
        if note:
            if not (note.startswith("*") and note.endswith("*")):
                note = f"*{note.strip('*_ ')}*"
            blocks.append(note)
        return "\n\n".join(blocks)


class KnowledgeQueryExtraction(BaseModel):
    """LLM classification of a non-strategy turn's knowledge source."""

    question_kind: Literal["market_stats", "current_external", "concept", "none"]
    symbols: list[str] = Field(default_factory=list)
    date_range_raw_text: str | None = None


def _describes_a_test_it_cannot_run(
    interpretation: StructuredInterpretation,
) -> bool:
    """A typed refusal that already names what to run over what period.

    Typed fields only: the act label plus the draft the interpreter filled
    from the user's own words. Nothing here reads the message.
    """
    if interpretation.semantic_turn_act != "unsupported_request":
        return False
    draft = interpretation.candidate_strategy_draft
    has_asset = any(
        str(symbol or "").strip()
        for symbol in (getattr(draft, "asset_universe", None) or [])
    )
    if not has_asset:
        return False
    window = getattr(draft, "date_range", None)
    if not (window.values() if isinstance(window, dict) else window):
        return False
    return _draft_carries_a_stated_test_window(draft)


def _draft_carries_a_stated_test_window(strategy: Any) -> bool:
    """Whether the draft carries a window the user themselves stated.

    Presence of date_range is not the fact. The runtime also writes it by
    inheriting a previous result's window, and draft_shape documents
    date_range as a reference field that must never pull a turn onto the
    strategy route. What makes it a stated window is the interpreter's own
    record that the user's message contained it: an evidence span, or
    explicit_user provenance.
    """
    extra = getattr(strategy, "extra_parameters", None) or {}
    provenance = extra.get("field_provenance")
    if isinstance(provenance, dict) and provenance.get("date_range") == "explicit_user":
        return True
    spans = extra.get("evidence_spans")
    if isinstance(spans, dict) and str(spans.get("date_range") or "").strip():
        return True
    return bool(str(extra.get("date_range_raw_text") or "").strip())


def _record_rail_decline(interpretation: StructuredInterpretation) -> None:
    """The typed facts of a knowledge-shaped read the rail did not answer, so
    the route a turn took is traced to its read rather than guessed at."""
    from argus.agent_runtime.interpreter.research_routing import (
        research_turn_has_conflicting_owner,
    )

    query = interpretation.research_query
    logger.info(
        "Research rail declined a knowledge-shaped read intent={} act={} "
        "question_kind={} scenario={} conflicting_owner={}",
        interpretation.intent,
        interpretation.semantic_turn_act,
        getattr(query, "question_kind", None),
        getattr(query, "scenario_question", None),
        research_turn_has_conflicting_owner(interpretation),
    )


async def knowledge_answer_stage_result(
    *,
    interpretation: StructuredInterpretation,
    state: RunState,
    user: UserState,
    snapshot: TaskSnapshot | None,
    selected_thread_metadata: dict[str, Any],
) -> StageResult | None:
    if interpretation.semantic_turn_act == "answer_pending_need":
        # The current interpretation, not the previous question's existence,
        # decides whether this turn answers that pending need.
        return None
    if getattr(interpretation, "asset_discovery", None) is not None:
        return None
    if interpretation.unsupported_constraints:
        # A typed refusal payload owns its recovery route: the primary read
        # already named what cannot run and the nearest supported alternative,
        # so a message-only classifier must not answer the turn as a question.
        if _UNSUPPORTED_PAYLOAD_REASON_CODE not in interpretation.reason_codes:
            interpretation.reason_codes.append(_UNSUPPORTED_PAYLOAD_REASON_CODE)
        logger.info(
            "Knowledge claim stood down for a typed unsupported payload " "categories={}",
            [item.category for item in interpretation.unsupported_constraints],
            categories=[item.category for item in interpretation.unsupported_constraints],
        )
        return None
    if educational_question_has_no_query(interpretation):
        return None
    if primary_read_is_arithmetic(interpretation):
        # The user's own numbers are enough: the no-search answer computes it.
        from argus.agent_runtime.calculated_answer import calculated_answer_stage_result

        computed = await calculated_answer_stage_result(
            interpretation=interpretation, state=state, user=user
        )
        if computed is not None:
            return computed
    rail_claim = (
        research_rail_enabled() and primary_research_query(interpretation) is not None
    )
    if (
        strategy_has_execution_evidence(interpretation.candidate_strategy_draft)
        and not rail_claim
    ):
        return None
    knowledge_shaped = interpretation.intent in _KNOWLEDGE_INTENTS and (
        interpretation.semantic_turn_act is None
        or interpretation.semantic_turn_act in _KNOWLEDGE_ACTS
    )
    if not knowledge_shaped and not rail_claim:
        return None
    if research_rail_enabled():
        # The primary interpreter already supplied question shape and subjects.
        # No raw-message classifier may reconsider its intent here.
        from argus.agent_runtime.research_answer import research_answer_stage_result

        researched = await research_answer_stage_result(
            interpretation=interpretation, state=state, user=user
        )
        if researched is None:
            _record_rail_decline(interpretation)
        return researched
    if not knowledge_shaped:
        # Flag off, the widened entry does not exist: only the legacy
        # knowledge shapes reach the pre-rail answerer.
        return None
    # The classifier owns the stats-vs-run boundary: an unsupported_request
    # turn with a resolved asset may be a statistics question (answer it from
    # data) or a request to run something Argus cannot execute (never answer
    # that with underlying stats; it must keep its recovery route).
    query = await _classify_question(
        message=state.current_user_message,
        language=user.language_preference,
    )
    if query is None or query.question_kind in ("concept", "none"):
        return None
    if refusal_route_survives_classification(interpretation):
        note_refusal_route_kept(interpretation)
        return None
    answer: str | None = None
    reason_code = ""
    if query.question_kind == "market_stats":
        answer = await _market_stats_answer(
            query=query,
            interpretation=interpretation,
            message=state.current_user_message,
            language=user.language_preference,
            user=user,
        )
        reason_code = "knowledge_answer_market_stats"
    if answer is None and query.question_kind in ("market_stats", "current_external"):
        answer = await _external_facts_answer(
            message=state.current_user_message,
            language=user.language_preference,
            user=user,
        )
        reason_code = "knowledge_answer_current_external"
    if answer is None:
        return None
    return _stage_result(
        answer=answer,
        reason_code=reason_code,
        interpretation=interpretation,
        query=query,
        user=user,
    )


def refusal_route_survives_classification(
    interpretation: StructuredInterpretation,
) -> bool:
    """A typed refusal over a user-stated window keeps its recovery route.

    The caller records the stand-down. This also protects the legacy
    flag-off knowledge classifier from answering a run request with stats.
    """
    return _describes_a_test_it_cannot_run(interpretation)


def note_refusal_route_kept(interpretation: StructuredInterpretation) -> None:
    """Record that a claimed turn was sent back to its refusal route."""
    if _UNSUPPORTED_EXECUTION_REASON_CODE not in interpretation.reason_codes:
        interpretation.reason_codes.append(_UNSUPPORTED_EXECUTION_REASON_CODE)
    draft = interpretation.candidate_strategy_draft
    logger.info(
        "Knowledge claim stood down after classification for an unsupported "
        "request that describes a test assets={} date_range={}",
        list(getattr(draft, "asset_universe", None) or []),
        getattr(draft, "date_range", None),
        failure_classification="unsupported_execution_kept_recovery_route",
    )


async def _classify_question(
    *,
    message: str,
    language: str | None,
) -> KnowledgeQueryExtraction | None:
    prompt = (
        "Classify the user's message for answering, not for execution.\n"
        "- market_stats: asks about performance, statistics, price history, or "
        "behavior of specific tradable assets or indexes.\n"
        "- current_external: asks about news, current events, macro facts, or "
        "anything needing fresh external information.\n"
        "- concept: asks what something means or how something works.\n"
        "- none: anything else, including requests to run or build something.\n"
        "symbols: provider tickers for the assets discussed; map well-known "
        "indexes to their liquid proxy (S&P 500 -> SPY). date_range_raw_text: "
        "the period exactly as the user phrased it, if any.\n"
        f"User message ({language or 'unknown'}): {message}"
    )
    try:
        extraction = await invoke_openrouter_json_schema(
            task="knowledge_route",
            messages=[{"role": "user", "content": prompt}],
            schema_model=KnowledgeQueryExtraction,
            schema_name="KnowledgeQueryExtraction",
        )
    except Exception as exc:  # noqa: BLE001
        origin = exception_origin(exc)
        logger.debug(
            "Knowledge route classification failed error_type={} error_origin={}",
            type(exc).__name__,
            origin,
            error_type=type(exc).__name__,
            error_origin=origin,
        )
        return None
    if not isinstance(extraction, KnowledgeQueryExtraction):
        return None
    return extraction


async def _market_stats_answer(
    *,
    query: KnowledgeQueryExtraction,
    interpretation: StructuredInterpretation,
    message: str,
    language: str | None,
    user: UserState | None = None,
) -> str | None:
    draft = interpretation.candidate_strategy_draft
    symbols = [
        symbol.strip().upper()
        for symbol in (query.symbols or draft.asset_universe or [])
        if str(symbol).strip()
    ]
    if not symbols:
        return None
    symbol = symbols[0]
    # The executable-window owner, the same one execute and confirm use. It
    # reads the typed range, then the interpreter's date_range_intent, so a
    # one-endpoint dict does not silently become a trailing year just by
    # being truthy. Only when it still has nothing does the classifier's raw
    # prose get a turn.
    requested_period = str(query.date_range_raw_text or "").strip()
    window = resolve_executable_date_range(
        draft.date_range,
        extra_parameters=getattr(draft, "extra_parameters", None),
    )
    if window.used_default and requested_period:
        from_classifier = resolve_date_range(requested_period)
        if not from_classifier.used_default:
            window = from_classifier
    if window.used_default and requested_period:
        # A substituted window is a deterministic compensation for a period
        # this layer could not parse, and the figures below are voiced as the
        # answer either way. Unrecorded, that substitution is invisible.
        logger.info(
            "Knowledge answer window defaulted despite a stated period "
            "requested_period={} symbol={} window={}",
            requested_period,
            symbol,
            window.label,
            requested_period=requested_period,
            symbol=symbol,
            resolved_window=window.label,
            failure_classification="knowledge_answer_period_defaulted",
        )
    try:
        # Lazy: the API import boundary keeps the backtest compute stack out
        # of startup; these load only when a market-stats answer actually runs.
        from argus.domain.engine import classify_symbol
        from argus.domain.market_data.provider import fetch_price_series

        asset = classify_symbol(symbol)
        series = await asyncio.to_thread(
            fetch_price_series,
            asset.symbol,
            asset.asset_class,
            window.start,
            window.end,
            "1d",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Knowledge answer market data fetch failed",
            symbol=symbol,
            error=str(exc),
        )
        return None
    facts = _series_facts(
        series=series,
        symbol=symbol,
        window_label=window.label,
        start=window.start,
        end=window.end,
    )
    if facts is None:
        return None
    return await _voiced_answer(
        message=message,
        language=language,
        facts=facts,
        fallback=_numeric_fallback(facts),
        user=user,
    )


def _series_facts(
    *,
    series: Any,
    symbol: str,
    window_label: str,
    start: date,
    end: date,
) -> dict[str, Any] | None:
    values = series.tolist() if hasattr(series, "tolist") else list(series or [])
    closes = [float(value) for value in values if value is not None]
    if len(closes) < 2:
        return None
    first, last = closes[0], closes[-1]
    total_return_pct = (last / first - 1.0) * 100.0
    peak = closes[0]
    max_drawdown_pct = 0.0
    for value in closes:
        peak = max(peak, value)
        drawdown = (value / peak - 1.0) * 100.0
        max_drawdown_pct = min(max_drawdown_pct, drawdown)
    daily_returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
    annualized_vol_pct = (variance**0.5) * (252**0.5) * 100.0
    return {
        "symbol": symbol,
        "window_label": window_label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "sessions": len(closes),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "annualized_volatility_pct": round(annualized_vol_pct, 2),
        "first_close": round(first, 2),
        "last_close": round(last, 2),
    }


def _numeric_fallback(facts: dict[str, Any]) -> str:
    return (
        f"**{facts['symbol']}**, {facts['start']} → {facts['end']}:\n\n"
        f"- Total return: **{facts['total_return_pct']:+.2f}%**\n"
        f"- Max drawdown: **{facts['max_drawdown_pct']:.2f}%**\n"
        f"- Volatility: **{facts['annualized_volatility_pct']:.2f}%** (annualized)"
    )


async def _external_facts_answer(
    *,
    message: str,
    language: str | None,
    user: UserState | None = None,
) -> str | None:
    config = discovery_search_config()
    try:
        provider = search_provider_for_config(provider_id=config.provider_id)
        packet = await asyncio.to_thread(
            provider.search,
            message,
            max_results=_SEARCH_MAX_RESULTS,
            timeout_seconds=config.timeout_seconds,
        )
    except (SearchUnavailableError, Exception) as exc:  # noqa: BLE001
        logger.warning("Knowledge answer search unavailable", error=str(exc))
        return None
    if not packet.results:
        return None
    snippets = "\n".join(
        f"- {result.title}: {result.snippet} ({result.url})" for result in packet.results
    )
    facts = {"search_results": snippets, "provider": packet.provider_id}
    sources = "\n".join(f"- {result.url}" for result in packet.results[:3])
    fallback = f"{packet.results[0].snippet}\n\nFuentes:\n{sources}"
    voiced = await _voiced_answer(
        message=message,
        language=language,
        facts=facts,
        fallback=fallback,
        user=user,
    )
    if voiced is None:
        return None
    if "http" not in voiced:
        voiced = f"{voiced}\n\n{sources}"
    return voiced


async def _voiced_answer(
    *,
    message: str,
    language: str | None,
    facts: dict[str, Any],
    fallback: str,
    user: UserState | None = None,
) -> str | None:
    fact_lines = "\n".join(f"{key}: {value}" for key, value in facts.items())
    profile = resolve_effective_response_profile(
        user=user or UserState(user_id="anonymous"),
        explicit_overrides=None,
    )
    if profile.effective_expertise_mode == "beginner":
        audience = (
            "The reader is new to investing: say what each number means in "
            "plain words and gloss any term like drawdown or volatility in a "
            "few words. No jargon walls."
        )
    else:
        audience = (
            "The reader is comfortable with market terms: be direct and "
            "concrete with the figures."
        )
    prompt = (
        "Answer the user's question using ONLY these facts. Reply in the "
        f"user's language ({language or 'the language of the question'}). "
        f"{audience} No advice, no invented data, no em dashes, no headings, "
        "no tables.\n"
        "Compose from this palette, choosing the shape that fits the answer "
        "best; vary it, keep it airy and beautiful:\n"
        "- lead (required): one short sentence that answers the question, "
        "with the single most important figure in **bold**.\n"
        "- bullets (optional, up to 4): short plain-words phrases, one figure "
        "per phrase in **bold**; use them when several figures matter, skip "
        "them when one figure tells the story.\n"
        "- note (optional): one closing sentence in *italics*, a gloss, "
        "caveat, or the window covered. Never repeat a figure already shown.\n"
        "If the facts include search results, put one source URL in each "
        "bullet you draw from it.\n"
        f"Question: {message}\nFacts:\n{fact_lines}"
    )
    # Voice over the direct JSON transport with the proven structured tier;
    # the numeric fallback keeps the answer honest when voicing cannot run.
    for model_name in openrouter_structured_model_candidates():
        try:
            voiced = await invoke_openrouter_json_schema(
                task="knowledge_voicing",
                messages=[{"role": "user", "content": prompt}],
                schema_model=VoicedAnswer,
                schema_name="VoicedAnswer",
                model_name=model_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Knowledge answer voicing failed error={exc!r}")
            continue
        if isinstance(voiced, VoicedAnswer) and voiced.lead.strip():
            return voiced.as_markdown()
    return fallback


def _try_next_sidecar(
    *,
    query: KnowledgeQueryExtraction,
    interpretation: StructuredInterpretation,
    language: str | None,
) -> dict[str, Any] | None:
    symbols = [
        symbol.strip().upper()
        for symbol in (
            query.symbols or interpretation.candidate_strategy_draft.asset_universe
        )
        if str(symbol).strip()
    ]
    if not symbols:
        return None
    labels = NEXT_EXPERIMENT_ACTION_LABELS.get(
        "es-419" if str(language or "").startswith("es") else "en",
        NEXT_EXPERIMENT_ACTION_LABELS["en"],
    )
    english = NEXT_EXPERIMENT_ACTION_LABELS["en"]
    rows = []
    for kind in ("compare_buy_and_hold", "recurring_monthly_buys"):
        label_key = next_experiment_label_key(kind)
        rows.append(
            {
                "kind": kind,
                "label": english.get(label_key, kind),
                "label_key": label_key,
                "localized_label": labels.get(label_key),
            }
        )
    return {"version": NEXT_EXPERIMENTS_VERSION, "rows": rows}


def _stage_result(
    *,
    answer: str,
    reason_code: str,
    interpretation: StructuredInterpretation,
    query: KnowledgeQueryExtraction,
    user: UserState,
    decision: InterpretDecision | None = None,
) -> StageResult:
    if decision is not None:
        # A typed entry keeps its identity; the serving path only adds its
        # reason code (#344: relabeling dropped the discovery payload).
        decision = decision.model_copy(
            update={
                "reason_codes": list(dict.fromkeys([*decision.reason_codes, reason_code]))
            }
        )
    else:
        decision = InterpretDecision(
            intent="conversation_followup",
            task_relation="continue",
            requires_clarification=False,
            user_goal_summary=interpretation.user_goal_summary,
            candidate_strategy_draft=StrategySummary(),
            missing_required_fields=[],
            optional_parameter_opportunity=[],
            confidence=0.85,
            arbitration_mode="deterministic",
            reason_codes=[reason_code],
            effective_response_profile=resolve_effective_response_profile(
                user=user,
                explicit_overrides=None,
            ),
            semantic_turn_act="educational_question",
        )
    stage_patch: dict[str, Any] = {"assistant_response": answer}
    sidecar = _try_next_sidecar(
        query=query,
        interpretation=interpretation,
        language=user.language_preference,
    )
    if sidecar is not None:
        stage_patch["next_experiments"] = sidecar
    return StageResult(
        outcome="ready_to_respond",
        decision=decision,
        stage_patch=stage_patch,
    )

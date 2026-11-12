"""One eligibility and privacy projection for every selected public turn."""

from __future__ import annotations

import unicodedata
from typing import Any, get_args
from urllib.parse import urlsplit

from pydantic import ValidationError

from argus.api.public_excerpt_fact_schemas import (
    PublicExcerptFactBank,
    ReceiptConfig,
    ReceiptCosts,
    ReceiptDates,
    ReceiptFigures,
    ReceiptParameters,
    ReceiptStrategy,
)
from argus.api.public_excerpt_schemas import (
    PublicExcerptBacktestTurn,
    PublicExcerptCalculation,
    PublicExcerptCalculationFact,
    PublicExcerptCalculationSource,
    PublicExcerptCalculationText,
    PublicExcerptCalculationTurn,
    PublicExcerptOfferedNextStep,
    PublicExcerptResearchSource,
    PublicExcerptResearchTurn,
)
from argus.api.schemas import Message
from argus.domain.backtest_message_projection import result_fact_bank
from argus.domain.capability_registry import ALLOWED_TEMPLATES, SUPPORTED_STRATEGY_TYPES
from argus.domain.public_excerpts import (
    _CONTROL_CHARS,
    PublicExcerptSanitizationError,
    PublicExcerptSourceError,
    _assumptions,
    _strategy_facts,
    _visual,
    audit_public_excerpt_document,
)
from argus.domain.research.contracts import QuestionShape
from argus.domain.result_figures import with_result_figures


def refuse(reason: str, field: str | None = None) -> None:
    raise PublicExcerptSourceError(reason, reason=reason, field=field)


def audit_text(value: object, *, field: str, private_ids: tuple[str, ...]) -> str | None:
    if value is None and field == "owner_note":
        return None
    if not isinstance(value, str):
        refuse("unsafe_text", field)
    assert isinstance(value, str)
    if field == "owner_note":
        value = " ".join(
            "".join(
                " " if unicodedata.category(c) in _CONTROL_CHARS else c for c in value
            ).split()
        )
    elif any(
        unicodedata.category(c) in _CONTROL_CHARS and c not in "\n\r\t" for c in value
    ):
        refuse("unsafe_text", field)
    if not value.strip():
        if field == "owner_note":
            return None
        refuse("missing_question" if field == "question" else "unsafe_text", field)
    if field == "owner_note" and len(value) > 280:
        refuse("text_too_long", field)
    try:
        audit_public_excerpt_document(
            {field: value}, private_ids=private_ids, check_value_markers=False
        )
    except PublicExcerptSanitizationError:
        refuse("unsafe_text", field)
    return value


def _offered_step(metadata: dict[str, Any]) -> PublicExcerptOfferedNextStep | None:
    block = metadata.get("next_experiments")
    rows = block.get("rows") if isinstance(block, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") not in get_args(
            PublicExcerptOfferedNextStep.model_fields["kind"].annotation
        ):
            continue
        parts = row.get("label_parts")
        if not isinstance(parts, list):
            continue
        symbols = list(
            dict.fromkeys(
                part["value"]
                for part in parts
                if isinstance(part, dict)
                and part.get("type") == "ticker"
                and isinstance(part.get("value"), str)
            )
        )
        if 1 <= len(symbols) <= 5:
            return PublicExcerptOfferedNextStep(kind=row["kind"], symbols=symbols)
    return None


def project_research_turn(
    *,
    message: Message,
    question: str,
    owner_note: str | None,
    language: str,
    private_ids: tuple[str, ...],
) -> PublicExcerptResearchTurn:
    metadata = message.metadata or {}
    source = metadata.get("research")
    if (
        not isinstance(source, dict)
        or source.get("schema_version") != "argus_research/v1"
    ):
        refuse("unsupported_turn")
    # Every rail shape is a receipt, the quote included. The find operation's
    # sidecar is a list of tickers rather than an answer and is not one.
    if source.get("shape") not in set(get_args(QuestionShape)):
        refuse("unsupported_shape")
    question = audit_text(question, field="question", private_ids=private_ids)
    answer = audit_text(message.content, field="answer", private_ids=private_ids)
    note = audit_text(owner_note, field="owner_note", private_ids=private_ids)
    try:
        sources = [
            PublicExcerptResearchSource.model_validate(row)
            for row in source.get("sources", [])
        ]
        for row in sources:
            parsed = urlsplit(row.url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.netloc.lower() != row.domain.lower()
            ):
                refuse("invalid_source", "sources")
        assert answer is not None
        payload = PublicExcerptResearchTurn(
            question=question,
            answer=answer,
            sources=sources,
            retrieved_at=source.get("retrieved_at"),
            anchor_symbols=source.get("anchor_symbols", []),
            asset_class=source.get("asset_class"),
            offered_next_step=_offered_step(metadata),
            owner_note=note,
            content_language=language,
        )
        audit_public_excerpt_document(
            payload.model_dump(mode="json"),
            private_ids=private_ids,
            check_value_markers=False,
        )
        return payload
    except (
        ValidationError,
        PublicExcerptSanitizationError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, PublicExcerptSourceError):
            raise
        refuse("invalid_source", "sources")


def _subset(value: object, model: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {key: source[key] for key in model.model_fields if key in source}


def _require_complete_figures(
    facts: PublicExcerptFactBank, metrics: dict[str, Any]
) -> None:
    config = facts.config_snapshot
    named_benchmark = any(
        name is not None and name.strip()
        for name in (
            facts.benchmark_symbol,
            config.benchmark_symbol,
            config.resolved_parameters.benchmark_symbol
            if config.resolved_parameters
            else None,
            config.parameters.benchmark_symbol if config.parameters else None,
        )
    )
    required = ["total_return_pct"]
    if named_benchmark:
        required.extend(("benchmark_return_pct", "delta_vs_benchmark_pct"))
        if facts.figures.benchmark_comparison_claim in (None, "unknown"):
            refuse("unsupported_backtest")
    if any(getattr(facts.figures, key) is None for key in required):
        refuse("unsupported_backtest")
    # Private display projection tolerates old strings and coerces booleans.
    # Publishing requires typed source numbers, using the existing closed model.
    aggregate = metrics.get("aggregate")
    performance = aggregate.get("performance") if isinstance(aggregate, dict) else None
    if not isinstance(performance, dict):
        refuse("unsupported_backtest")
    ReceiptFigures.model_validate({key: performance.get(key) for key in required})


def project_backtest_turn(
    *,
    run: Any,
    title: str,
    question: str | None = None,
    answer: str | None = None,
    owner_note: str | None,
    language: str,
    private_ids: tuple[str, ...],
) -> PublicExcerptBacktestTurn:
    if run is None or run.status != "completed":
        refuse("not_completed")
    bank = with_result_figures(result_fact_bank(run))
    config = _subset(bank["config_snapshot"], ReceiptConfig)
    if config.get("template") not in ALLOWED_TEMPLATES | SUPPORTED_STRATEGY_TYPES:
        refuse("unsupported_backtest")
    if isinstance(config.get("date_range"), dict):
        config["date_range"] = _subset(config["date_range"], ReceiptDates)
    if not (
        config.get("date_range") or (config.get("start_date") and config.get("end_date"))
    ):
        refuse("unsupported_backtest")
    # Copy owned typed config fields. Never derive another strategy or metric.
    for key, model in (
        ("resolved_strategy", ReceiptStrategy),
        ("resolved_parameters", ReceiptParameters),
        ("parameters", ReceiptParameters),
    ):
        if key in config:
            config[key] = _subset(config[key], model)
    source_card = bank.get("result_card") or {}
    try:
        # Existing receipt completeness checks remain shared. Their legacy text
        # projection is discarded; v2 publishes only the card's typed facts.
        has_rule_spec = any(
            isinstance(config.get(key), dict) and config[key].get("rule_spec")
            for key in ("resolved_strategy", "resolved_parameters", "parameters")
        )
        if not has_rule_spec:
            _strategy_facts(run.config_snapshot)
        _assumptions(run.config_snapshot, benchmark_symbol=run.benchmark_symbol)
        facts = PublicExcerptFactBank(
            symbols=bank["symbols"],
            asset_class=bank["asset_class"],
            benchmark_symbol=bank["benchmark_symbol"],
            config_snapshot=config,
            figures=_subset(bank.get("figures"), ReceiptFigures),
            result_card={
                "execution_costs": _subset(source_card["execution_costs"], ReceiptCosts)
            }
            if source_card.get("execution_costs")
            else {},
        )
        _require_complete_figures(facts, bank["metrics"])
        payload = PublicExcerptBacktestTurn(
            idea_title=audit_text(title, field="question", private_ids=private_ids),
            question=audit_text(question, field="question", private_ids=private_ids)
            if question is not None
            else None,
            answer=audit_text(answer, field="answer", private_ids=private_ids)
            if answer
            else answer,
            fact_bank=facts,
            visual=_visual(run.chart),
            owner_note=audit_text(
                owner_note, field="owner_note", private_ids=private_ids
            ),
            content_language=language,
        )
        audit_public_excerpt_document(
            payload.model_dump(mode="json"),
            private_ids=private_ids,
            check_value_markers=False,
        )
        return payload
    except (ValidationError, PublicExcerptSanitizationError, PublicExcerptSourceError):
        refuse("unsupported_backtest")


def project_calculation_turn(
    *,
    message: Message,
    question: str,
    owner_note: str | None,
    language: str,
    private_ids: tuple[str, ...],
) -> PublicExcerptCalculationTurn:
    """A computed answer as a frozen receipt: each card's typed facts, no recompute.

    The question and, for each calculation, the title, the computed answer and
    rows and notes publish with public or explicitly user-written inputs.
    A declaration whose rows restate inputs still requires known provenance;
    hidden account inputs are never added to the preview or public page.
    """
    from argus.domain.answer_dossiers import computed_answer_cards
    from argus.domain.personal_tool_catalog import personal_tool_catalog

    cards = computed_answer_cards(message.model_dump(mode="python"))
    if not cards:
        refuse("unsupported_turn")
    assert cards is not None
    catalog = personal_tool_catalog(include_unavailable=True)
    for card in cards:
        _refuse_unpublishable(card, catalog)
    asked = audit_text(question, field="question", private_ids=private_ids)
    note = audit_text(owner_note, field="owner_note", private_ids=private_ids)
    try:
        payload = PublicExcerptCalculationTurn(
            question=asked,
            answer_text=audit_text(
                message.content, field="answer", private_ids=private_ids
            ),
            calculations=[_public_calculation(card) for card in cards],
            computed_at=message.created_at,
            owner_note=note,
            content_language=language,
        )
        audit_public_excerpt_document(
            payload.model_dump(mode="json"),
            private_ids=private_ids,
            check_value_markers=False,
        )
        return payload
    except ValidationError:
        refuse("unsupported_turn")
    except PublicExcerptSanitizationError:
        refuse("unsafe_text")


def _refuse_unpublishable(card: Any, catalog: Any) -> None:
    declaration = catalog.get(card.tool_name)
    policy = declaration.policy.public_receipt if declaration is not None else "disabled"
    if policy == "disabled":
        refuse("unsupported_turn")
    presentation = card.presentation
    if card.outcome.status != "succeeded" or presentation.answer is None:
        refuse("not_completed")
    stated = [fact for fact in presentation.inputs if fact.value is not None]
    if policy == "cited_facts" and not all(_selected_input(fact) for fact in stated):
        refuse("private_inputs")


def _public_calculation(card: Any) -> PublicExcerptCalculation:
    presentation = card.presentation
    stated = [fact for fact in presentation.inputs if fact.value is not None]
    return PublicExcerptCalculation(
        title=_public_text(presentation.title),
        answer=_public_fact(presentation.answer),
        rows=[
            _public_fact(fact)
            for fact in presentation.rows
            if not fact.comparison_only
        ],
        inputs=[_public_fact(fact) for fact in stated if _selected_input(fact)],
        notes=[_public_text(item) for item in presentation.notes],
    )


def _selected_input(fact: Any) -> bool:
    source = fact.source
    return fact.visibility == "public" or (
        source is not None and source.kind in {"page", "user"}
    )


def _public_text(text: Any) -> PublicExcerptCalculationText:
    return PublicExcerptCalculationText(
        locale_key=text.locale_key, interpolation_args=dict(text.interpolation_args)
    )


def _public_fact(fact: Any) -> PublicExcerptCalculationFact:
    source = fact.source
    cited = None
    if source is not None and source.kind == "page":
        if source.url is not None:
            parsed = urlsplit(source.url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
            ):
                refuse("invalid_source", "sources")
        cited = PublicExcerptCalculationSource(
            title=source.title, url=source.url, date=source.date
        )
    return PublicExcerptCalculationFact(
        label=_public_text(fact.label),
        value=fact.value,
        value_text=_public_text(fact.value_text) if fact.value_text is not None else None,
        unit=_public_text(fact.unit) if fact.unit is not None else None,
        source=cited,
    )

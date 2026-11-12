"""A research answer's calculation, and the answer when a lookup fails.

The research provider returns prose and its calculations; they compute here
through the answer step, with the pages this answer retrieved as the only
pages an input may cite. An unusable calculation leaves the research prose
standing. When the lookup fails,
the no-search step answers from Argus market data and stated assumptions and
says what it could not look up: a failed lookup never becomes the answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pydantic import ValidationError

from argus.agent_runtime.answer_calculation import (
    calculation_names,
    card_in,
    cards_in,
    computed_answer_patch,
    latest_market_close,
    publish_calculations,
    render_offer_prose,
    resolve_calculation,
)
from argus.agent_runtime.calculated_answer import (
    CALCULATION_OFFERED_REASON_CODE,
    CalculatedAnswer,
    answer_from_published,
    calculated_answer,
    pending_requests,
)
from argus.agent_runtime.state.models import UserState
from argus.domain.calculations.answer_request import AnswerCalculation
from argus.domain.research.contracts import ResearchPacket, ResearchSource, RetrievedRow
from argus.llm.openrouter import resolve_openrouter_api_key

CALCULATION_NOT_COMPUTED_CODE = "calculation_inputs_not_found"
# Recorded when an offered calculation's prose left out a sentence or table row
# that leaned on a result the offer cannot show.
OFFER_PROSE_TRIMMED_REASON_CODE = "offer_prose_results_dropped"
MALFORMED_CALCULATION_REASON_CODE = "answer_calculation_malformed"
# Degraded research an answer without a lookup may replace; a survey or a claim
# withheld for want of a publisher keeps its own honest note.
LOOKUP_FAILURE_CODES = frozenset({"research_not_grounded"})
_MAX_MARKET_SUBJECTS = 3


@dataclass(frozen=True)
class NotComputed:
    """A calculation the answer returned but Argus could not compute from its sources."""

    code: str
    answer_text: str


def skipped_calculation(
    packet: ResearchPacket,
    notes: list[str],
    code: str,
) -> NotComputed:
    """Keep research independent of optional math, without unresolved references."""
    _note(notes, code)
    prose, dropped = render_offer_prose(packet.answer_markdown, {})
    if dropped:
        _note(notes, OFFER_PROSE_TRIMMED_REASON_CODE)
    return NotComputed(code, prose)


def packet_answer(
    packet: ResearchPacket,
    *,
    subjects: Sequence[dict[str, str]],
    user: UserState,
    language: str,
    notes: list[str],
    scenario: bool = False,
) -> CalculatedAnswer | NotComputed | None:
    """The answer's computed calculations, what they could not compute, or None
    when it returned none and its prose stands on its own."""
    if not packet.calculations:
        if "{{" in packet.answer_markdown:
            _note(notes, MALFORMED_CALCULATION_REASON_CODE)
            return skipped_calculation(packet, notes, CALCULATION_NOT_COMPUTED_CODE)
        if scenario:
            return skipped_calculation(packet, notes, "scenario_inputs_uncited")
        return None
    try:
        requests = [
            AnswerCalculation.model_validate(item) for item in packet.calculations
        ]
    except ValidationError:
        _note(notes, MALFORMED_CALCULATION_REASON_CODE)
        return skipped_calculation(packet, notes, CALCULATION_NOT_COMPUTED_CODE)
    from argus.domain.personal_tool_catalog import personal_tool_catalog

    retrieved = retrieved_pages(packet)
    evidence = cited_evidence(packet)
    published = publish_calculations(
        requests,
        template=packet.answer_markdown,
        language=language,
        catalog=personal_tool_catalog(),
        retrieved=retrieved,
        currency=user.currency,
        subject_symbol=_only_symbol(subjects),
        market_close=latest_market_close,
        notes=notes,
        evidence=evidence,
    )
    if published is None:
        return skipped_calculation(packet, notes, CALCULATION_NOT_COMPUTED_CODE)
    if published.not_looked_up:
        return skipped_calculation(packet, notes, CALCULATION_NOT_COMPUTED_CODE)
    if any(card.outcome.status != "succeeded" for card in cards_in(published.patch)):
        return skipped_calculation(packet, notes, "research_calculation_invalid")
    return answer_from_published(
        requests,
        published,
        prose=packet.answer_markdown,
        language=language,
        retrieved=retrieved,
        evidence=evidence,
    )


def offered_calculation(
    prose: str,
    offer: dict[str, Any],
    *,
    subjects: Sequence[dict[str, str]],
    user: UserState,
    notes: list[str],
) -> tuple[str, dict[str, Any]] | None:
    """A research answer never turns into a question: its calculations are offered
    on the reader's own figures, and the prose stands with any input it already
    holds filled and each sentence that leans on a result the offer cannot show
    left out. None only when nothing of the prose is left."""
    if "{{" in prose:
        from argus.domain.personal_tool_catalog import personal_tool_catalog

        try:
            requests = [
                AnswerCalculation.model_validate(item) for item in pending_requests(offer)
            ]
            retrieved = [
                ResearchSource.model_validate(page)
                for page in offer.get("retrieved") or []
            ]
            evidence = [
                RetrievedRow.model_validate(row) for row in offer.get("evidence") or []
            ]
            if not requests:
                return None
            cards = {}
            for name, request in zip(calculation_names(requests), requests, strict=True):
                resolved = resolve_calculation(
                    request,
                    catalog=personal_tool_catalog(),
                    retrieved=retrieved,
                    currency=user.currency,
                    subject_symbol=_only_symbol(subjects),
                    market_close=latest_market_close,
                    notes=notes,
                    evidence=evidence,
                )
                if resolved is None:
                    return None
                cards[name] = card_in(computed_answer_patch(resolved))
            prose, dropped = render_offer_prose(prose, cards)
        except (ValidationError, KeyError, ValueError):
            return None
        if not prose.strip():
            return None
        if dropped:
            _note(notes, OFFER_PROSE_TRIMMED_REASON_CODE)
    if CALCULATION_OFFERED_REASON_CODE not in notes:
        notes.append(CALCULATION_OFFERED_REASON_CODE)
    logger.info(
        "Calculation offered on the reader's own figures",
        failure_classification=CALCULATION_OFFERED_REASON_CODE,
        kinds=[item.get("kind") for item in pending_requests(offer)],
        requested_field=offer.get("requested_field"),
    )
    return prose, offer


def answer_without_lookup(
    *,
    message: str,
    language: str,
    user: UserState,
    subjects: Sequence[dict[str, str]],
    not_looked_up: Sequence[str],
    notes: list[str],
) -> CalculatedAnswer | None:
    """The no-search answer from Argus market data and stated assumptions."""
    if not message.strip() or not resolve_openrouter_api_key():
        return None
    from argus.agent_runtime.turn_execution import research_recovery_scope

    facts: dict[str, str] = {}
    for subject in list(subjects)[:_MAX_MARKET_SUBJECTS]:
        close = latest_market_close(subject["symbol"])
        if close is not None:
            facts[f"{subject['symbol']} latest close"] = f"{close[0]:,.2f} on {close[1]}"
    with research_recovery_scope():
        answered = calculated_answer(
            message=message,
            language=language,
            user=user,
            notes=notes,
            market_facts=facts,
            not_looked_up=not_looked_up,
            subject_symbol=_only_symbol(subjects),
            lookup_failed=True,
        )
    if answered is not None:
        logger.info(
            "Answered without the failed lookup",
            not_looked_up=list(not_looked_up),
            computed=bool(answered.patch),
        )
    return answered


def retrieved_pages(packet: ResearchPacket) -> list[ResearchSource]:
    """Every page this answer retrieved: its sources and its cited rows' pages."""
    pages = list(packet.sources)
    seen = {page.url for page in pages}
    for row in packet.rows:
        if row.source_url and row.source_url not in seen:
            seen.add(row.source_url)
            pages.append(
                ResearchSource(
                    url=row.source_url,
                    title=f"{row.subject} {row.label}".strip(),
                    source_date=row.as_of,
                )
            )
    return pages


def cited_evidence(packet: ResearchPacket) -> list[RetrievedRow]:
    """The cited figures read from the provider's own finance data: rows whose
    evidence is the tool result and whose URL the parser scrubbed."""
    return [row for row in packet.rows if row.source_url is None]


def _only_symbol(subjects: Sequence[dict[str, Any]]) -> str | None:
    """The subject a card that names no symbol borrows: only when the answer names
    exactly one, since with several a borrowed price could be another asset's."""
    symbols = [str(s["symbol"]) for s in subjects if s.get("symbol")]
    distinct = {symbol.strip().upper() for symbol in symbols}
    return symbols[0] if len(distinct) == 1 else None


def _note(notes: list[str], code: str) -> None:
    if code not in notes:
        notes.append(code)
    logger.info("Research calculation guard {}", code, failure_classification=code)

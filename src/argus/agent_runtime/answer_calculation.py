"""The answer step owns the math.

An answering model, the research provider or the no-search voicing model,
returns its prose and its ``AnswerCalculation`` list, one per option the reader
weighs. Each input is held to its source: a page retrieved for this answer,
Argus's own market data for a current price, the user's words, or an assumption
the answer states. Each declaration computes its own card. The prose states
figures only as references filled from those cards, ``{{name}}`` or, with more
than one calculation, ``{{calculation.name}}``; a reference that does not
resolve, or a money or percent figure written outside a reference, hands the
answer to Argus's own lead, and an assumed input the prose never names is listed
under the answer. Every guard that changes what the
model wrote records a reason code.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError

from argus.agent_runtime.stages.tool_execution import local_tool_call_patch
from argus.domain.calculations import is_free_calculation
from argus.domain.calculations._shared import (
    MISSING_INPUT_CODE,
    SYMBOL_FIELD,
    UNIT_CURRENCY_KEY,
    UNIT_MULTIPLE_KEY,
    UNIT_PERCENT_KEY,
)
from argus.domain.calculations.answer_request import (
    RUNTIME_ARGUMENTS,
    AnswerCalculation,
    AnswerCalculationInput,
)
from argus.domain.research.contracts import (
    CURRENCY_CODES,
    ResearchSource,
    RetrievedRow,
)
from argus.domain.tool_contracts import (
    TOOL_INPUT_SOURCES_FIELD,
    ToolCall,
    ToolFact,
    ToolFactSource,
    ToolResultCard,
)
from argus.domain.tool_declaration import ToolDeclaration, ToolInvocationError

DEFAULT_CURRENCY = "USD"
CURRENCY_FIELD = "currency"
PRICE_FIELD = "price"
# Message metadata that lets a recompute re-render the prose from its new card.
ANSWER_TEMPLATE_KEY = "answer_text_template"
# Message metadata naming each assumed input the prose never names; the app lists
# them under the answer from each card's own label and value.
ANSWER_ASSUMPTIONS_KEY = "answer_assumptions"

KIND_UNKNOWN_REASON_CODE = "answer_calculation_kind_unknown"
INPUT_UNDECLARED_REASON_CODE = "answer_input_undeclared"
PAGE_UNCITED_REASON_CODE = "answer_input_page_uncited"
MARKET_PRICE_UNAVAILABLE_REASON_CODE = "answer_market_price_unavailable"
MARKET_DATA_NOT_A_PRICE_REASON_CODE = "answer_market_data_not_a_price"
CURRENCY_MISMATCH_REASON_CODE = "calculation_input_currency_mismatch"
CURRENCY_DEFAULTED_REASON_CODE = "calculation_currency_defaulted"
FIGURE_CHECK_REASON_CODE = "answer_figures_replaced"
# Recorded, never replacing anything, when an answer's prose states a figure in
# digits that is neither a cited row nor a value of its calculation.
UNSOURCED_FIGURE_REASON_CODE = "answer_figures_unsourced"

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# A figure reference: a name, or a calculation's name then a name.
_REFERENCE_TEXT = r"\{\{\s*([^\W\d]\w*(?:\.[^\W\d]\w*)?)\s*\}\}"
_REFERENCE = re.compile(_REFERENCE_TEXT)
_WRITTEN_CURRENCY = re.compile(
    r"(?:\b([A-Z]{3})|[A-Z]{0,3}\$|€|£)\s?(" + _REFERENCE_TEXT + ")"
)
_WRITTEN_UNIT_AFTER = re.compile("(" + _REFERENCE_TEXT + r")\s?([A-Z]{3}\b|%|x\b)")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_PERCENT_FIGURE = re.compile(r"\d\s?%")
_SYMBOL_MONEY = re.compile(r"(?:[A-Z]{0,3}\$|€|£)\s?\d")
_CODE_MONEY = re.compile(r"\b([A-Z]{3})\s?\d|\d\s?([A-Z]{3})\b")
_MARKET_WINDOW_DAYS = 14

MarketClose = Callable[[str], tuple[float, str] | None]
# An answer's computed cards by calculation name, in the answer's order.
AnswerCards = Mapping[str, ToolResultCard]


@dataclass
class ResolvedCalculation:
    """A request held to its sources, as the declaration's arguments."""

    declaration: ToolDeclaration
    arguments: dict[str, Any]
    user_owed: list[str] = field(default_factory=list)
    not_looked_up: list[str] = field(default_factory=list)
    assumed: list[str] = field(default_factory=list)

    @property
    def computable(self) -> bool:
        return not self.user_owed and not self.not_looked_up


@dataclass(frozen=True)
class PublishedCalculation:
    """What an answer publishes: the cards' patch and prose, the template a
    recompute re-renders, the figures to ask for, or what was not found."""

    patch: dict[str, Any]
    answer_text: str | None
    template: dict[str, Any] | None
    question_field: str | None
    not_looked_up: tuple[str, ...]
    owed: tuple[str, ...] = ()
    assumptions: tuple[dict[str, str], ...] = ()
    # Each calculation's reference name with the blanks that calculation owes.
    owed_by_calculation: tuple[tuple[str, tuple[str, ...]], ...] = ()


def publish_calculations(
    requests: Sequence[AnswerCalculation],
    *,
    template: str,
    language: str,
    catalog: Any,
    retrieved: Sequence[ResearchSource],
    currency: str | None,
    subject_symbol: str | None,
    market_close: MarketClose,
    notes: list[str],
    evidence: Sequence[RetrievedRow] = (),
) -> PublishedCalculation | None:
    """The cards and prose for an answer's calculations, or None when one names an
    unknown kind. Nothing publishes until every calculation computes: an option
    left out would change what the answer lays side by side."""
    resolved: list[ResolvedCalculation] = []
    for request in requests:
        one = resolve_calculation(
            request,
            catalog=catalog,
            retrieved=retrieved,
            currency=currency,
            subject_symbol=subject_symbol,
            market_close=market_close,
            notes=notes,
            evidence=evidence,
        )
        if one is None:
            return None
        resolved.append(one)
    owed = list(dict.fromkeys(name for one in resolved for name in one.user_owed))
    not_looked_up = tuple(name for one in resolved for name in one.not_looked_up)
    if owed or not_looked_up:
        return PublishedCalculation(
            patch={},
            answer_text=None,
            template=None,
            question_field=owed[0] if owed else None,
            not_looked_up=not_looked_up,
            owed=tuple(owed),
            owed_by_calculation=tuple(
                (name, tuple(dict.fromkeys(one.user_owed)))
                for name, one in zip(calculation_names(requests), resolved, strict=True)
            ),
        )
    patches = [computed_answer_patch(one) for one in resolved]
    cards = dict(zip(calculation_names(requests), map(card_in, patches), strict=True))
    succeeded = all(card.outcome.status == "succeeded" for card in cards.values())
    text, failure = render_answer_text(template, cards)
    patch = combined_patch(patches)
    if succeeded and failure is not None:
        recovered, _ = _trim_unresolved_clauses(template, cards)
        missing = _missing_computed_references(recovered, cards)
        # A comparison must account for every option before its prose can stand.
        # Single-card explanations can still introduce their result through recovery.
        unsafe_comparison = len(cards) > 1 and bool(missing)
        _note(
            notes,
            FIGURE_CHECK_REASON_CODE,
            failure=failure,
            unresolved=unresolved_references(template, cards),
            recovery="labeled_card_results" if unsafe_comparison else "labeled_scenarios",
            missing_results=missing,
        )
        template = "" if unsafe_comparison else recovered
        referenced = _referenced_inputs(template, cards)
        for index, (request, (owner, card)) in enumerate(
            zip(requests, cards.items(), strict=True), start=1
        ):
            answer = card.presentation.answer
            if answer is not None and (owner, answer.name) not in referenced:
                # Only the model's display name is prose. Internal reference
                # keys are not localized labels; the attached card owns those.
                name = request.name.strip() if unsafe_comparison else request.name
                label = f"{name}: " if name else ""
                if unsafe_comparison:
                    label = f"{index}. {label}"
                template += f"\n\n{label}{{{{{owner}.{answer.name}}}}}"
        template = template.strip()
        text, failure = render_answer_text(template, cards)
    if succeeded and failure is None:
        assumptions = unstated_assumptions(template, cards)
        driving = _driving(cards, assumptions)
        if driving:
            # The prose stands; the check still records what it never named.
            _note(
                notes,
                FIGURE_CHECK_REASON_CODE,
                failure="assumption_not_stated",
                prose="kept",
                unstated=driving,
            )
        stored = {
            "cards": {name: card.artifact_id for name, card in cards.items()},
            "text": template,
            "language": language,
        }
        return PublishedCalculation(
            patch, text, stored, None, (), assumptions=tuple(assumptions)
        )
    _note(
        notes,
        FIGURE_CHECK_REASON_CODE,
        failure=failure,
        status=[card.outcome.status for card in cards.values()],
        unresolved=unresolved_references(template, cards),
        references=sorted(set(_REFERENCE.findall(template))),
        card_facts=sorted(
            f"{name}.{fact}"
            for name, card in cards.items()
            for fact in _reference_facts(card)
        ),
    )
    return PublishedCalculation(
        patch,
        render_offer_prose(template, cards)[0]
        if succeeded
        else fallback_answer_lead(language, succeeded=False),
        None,
        None,
        (),
        assumptions=tuple(unstated_assumptions("", cards)),
    )


def resolve_calculation(
    request: AnswerCalculation,
    *,
    catalog: Any,
    retrieved: Sequence[ResearchSource],
    currency: str | None,
    subject_symbol: str | None,
    market_close: MarketClose,
    notes: list[str],
    evidence: Sequence[RetrievedRow] = (),
) -> ResolvedCalculation | None:
    declaration = catalog.get(request.kind)
    if declaration is None or not is_free_calculation(declaration):
        _note(notes, KIND_UNKNOWN_REASON_CODE, kind=request.kind)
        return None
    declared = set(declaration.arguments_type.model_fields) - RUNTIME_ARGUMENTS
    solve_fields = {name for rule in declaration.rules for name in rule.fields}
    if request.solve_for is not None and request.solve_for not in solve_fields:
        _note(
            notes,
            "calculation_solve_for_ignored",
            kind=request.kind,
            field=request.solve_for,
        )
        request = request.model_copy(update={"solve_for": None})
    pages = {source.url: source for source in retrieved}
    symbol = _stated_symbol(request) or subject_symbol
    counted_in = _calculation_currency(
        request,
        currency,
        notes,
        declared=declared,
        pages=pages,
        evidence=evidence,
        symbol=symbol,
    )
    arguments: dict[str, Any] = {CURRENCY_FIELD: counted_in}
    if SYMBOL_FIELD in declared and symbol:
        arguments[SYMBOL_FIELD] = symbol
    sources: dict[str, ToolFactSource] = {}
    resolved = ResolvedCalculation(declaration=declaration, arguments=arguments)
    for item in request.inputs:
        name = item.name
        if name in (CURRENCY_FIELD, SYMBOL_FIELD) or name == request.solve_for:
            continue
        if name not in declared:
            _note(notes, INPUT_UNDECLARED_REASON_CODE, name=name)
            continue
        if item.currency and item.currency.strip().upper() != counted_in:
            resolved.not_looked_up.append(name)
            _note(notes, CURRENCY_MISMATCH_REASON_CODE, name=name, currency=item.currency)
            continue
        if item.source == "user":
            if item.value is None:
                # The declaration decides below which blanks the user owes; an
                # optional detail left blank keeps its default.
                continue
            arguments[name], sources[name] = item.value, ToolFactSource(kind="user")
        elif item.source == "assumption":
            if item.value is None:
                continue
            arguments[name], sources[name] = item.value, ToolFactSource(kind="assumption")
            resolved.assumed.append(name)
        elif item.source == "market_data":
            price = _market_price(name, symbol, market_close, notes)
            if price is None:
                resolved.not_looked_up.append(name)
                continue
            arguments[name], sources[name] = price
        else:
            source = _page_input_source(
                item, pages=pages, evidence=evidence, currency=counted_in, symbol=symbol
            )
            if source is None:
                resolved.not_looked_up.append(name)
                _note(notes, PAGE_UNCITED_REASON_CODE, name=name)
                continue
            arguments[name], sources[name] = item.value, source
    # The verified amount also owns the provenance of its denomination.
    # Finance evidence need not contain a separate numeric row for a code.
    currency_owner = next(
        (
            item
            for item in request.inputs
            if item.currency
            and item.currency.strip().upper() == counted_in
            and item.name in sources
            and sources[item.name].kind in {"user", "page"}
        ),
        None,
    )
    if currency_owner is not None:
        sources[CURRENCY_FIELD] = sources[currency_owner.name]
    if request.solve_for in declared:
        arguments[request.solve_for] = None
    if sources:
        arguments[TOOL_INPUT_SOURCES_FIELD] = {
            name: source.model_dump(mode="json") for name, source in sources.items()
        }
    if resolved.computable:
        resolved.user_owed.extend(
            _blank_inputs(declaration, arguments, request.solve_for)
        )
    return resolved


def computed_answer_patch(resolved: ResolvedCalculation) -> dict[str, Any]:
    """The card for the resolved inputs, in the execute loop's own patch shape."""
    declaration = resolved.declaration
    call = ToolCall(
        tool_name=declaration.name,
        call_id=f"answer-{uuid4()}",
        arguments=resolved.arguments,
    )
    return local_tool_call_patch(
        declaration=declaration, call=call, artifact_id=str(uuid4())
    )


def card_in(patch: dict[str, Any]) -> ToolResultCard:
    return ToolResultCard.model_validate(
        patch["final_response_payload"]["tool_result_cards"][0]
    )


def render_answer_text(template: str, cards: AnswerCards) -> tuple[str, str | None]:
    """The prose with each reference filled from its card, and the check's
    failure code when a figure did not come from a card."""
    unresolved: list[str] = []

    def fill(match: re.Match[str]) -> str:
        value = _resolved(match.group(1), cards)
        if value is None:
            unresolved.append(match.group(1))
            return match.group(0)
        return value if isinstance(value, str) else figure_text(value)

    text = _REFERENCE.sub(fill, _without_written_currency(template, cards))
    if unresolved or "{{" in text:
        return text, "invalid_figure_reference"
    if _missing_computed_references(template, cards):
        return text, "missing_computed_reference"
    return text, None


def _missing_computed_references(template: str, cards: AnswerCards) -> list[str]:
    """One completeness check for rendering and deciding whether to preserve prose."""
    referenced = _referenced_inputs(template, cards)
    return [
        f"{owner}.{card.presentation.answer.name}"
        for owner, card in cards.items()
        if card.outcome.status == "succeeded"
        and card.presentation.answer is not None
        and (owner, card.presentation.answer.name) not in referenced
    ]


def unstated_assumptions(template: str, cards: AnswerCards) -> list[dict[str, str]]:
    """Every input a card holds as an assumption that the prose never names, in
    the answer's order; the app lists them under the answer from each card's
    own label and value."""
    referenced = _referenced_inputs(template, cards)
    return [
        {"artifact_id": card.artifact_id, "name": fact.name}
        for owner, card in cards.items()
        for fact in card.presentation.inputs
        if fact.value is not None
        and fact.source is not None
        and fact.source.kind == "assumption"
        and (owner, fact.name) not in referenced
    ]


def _driving(cards: AnswerCards, assumptions: Sequence[Mapping[str, str]]) -> list[str]:
    """The listed assumptions that drive a result, for the figure check's record."""
    listed = {(item["artifact_id"], item["name"]) for item in assumptions}
    return [
        f"{owner}.{fact.name}"
        for owner, card in cards.items()
        for fact in card.presentation.inputs
        if fact.driving and (card.artifact_id, fact.name) in listed
    ]


def unresolved_references(template: str, cards: AnswerCards) -> list[str]:
    """The references no card fills, for the guard's record."""
    return sorted(
        {
            reference
            for reference in _REFERENCE.findall(template)
            if _resolved(reference, cards) is None
        }
    )


def calculation_names(requests: Sequence[AnswerCalculation]) -> list[str]:
    """Each calculation's reference name, folded and unique in its answer; one
    that gave no name takes its position."""
    names: list[str] = []
    for index, request in enumerate(requests, start=1):
        base = folded_name(request.name) or f"calculation_{index}"
        if base[0].isdigit():
            base = f"calculation_{base}"
        name, suffix = base, 2
        while name in names:
            name, suffix = f"{base}_{suffix}", suffix + 1
        names.append(name)
    return names


def combined_patch(patches: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Every card's patch as one, in the answer's order."""
    return {
        "tool_call_records": [
            record for patch in patches for record in patch["tool_call_records"]
        ],
        "final_response_payload": {
            "tool_result_cards": [
                card
                for patch in patches
                for card in patch["final_response_payload"]["tool_result_cards"]
            ]
        },
        "artifact_references": [
            reference for patch in patches for reference in patch["artifact_references"]
        ],
    }


def template_cards(template: Mapping[str, Any]) -> dict[str, str]:
    """The artifact each calculation name reads in a stored template; a template
    stored before answers carried several names its one card."""
    cards = template.get("cards")
    if isinstance(cards, Mapping):
        return {folded_name(str(name)): str(artifact) for name, artifact in cards.items()}
    artifact = template.get("artifact_id")
    return {"calculation": str(artifact)} if artifact else {}


def _located(reference: str, cards: AnswerCards) -> tuple[str, ToolFact | str] | None:
    """Where a reference reads: its named calculation, or the one calculation that
    holds the name; None when none does or several do."""
    calculation, _, name = reference.rpartition(".")
    key = folded_name(name)
    if calculation:
        owner = folded_name(calculation)
        card = cards.get(owner)
        value = None if card is None else _card_value(card, key)
        return None if value is None else (owner, value)
    found = [
        (owner, value)
        for owner, card in cards.items()
        if (value := _card_value(card, key)) is not None
    ]
    return found[0] if len(found) == 1 else None


def _resolved(reference: str, cards: AnswerCards) -> ToolFact | str | None:
    located = _located(reference, cards)
    return None if located is None else located[1]


def _card_value(card: ToolResultCard, name: str) -> ToolFact | str | None:
    fact = _reference_facts(card).get(name)
    return fact if fact is not None else _stated_argument(card, name)


def _as_fact(value: ToolFact | str | None) -> ToolFact | None:
    return value if isinstance(value, ToolFact) else None


def _referenced_inputs(template: str, cards: AnswerCards) -> set[tuple[str, str]]:
    """Each calculation and name a template's references read."""
    found: set[tuple[str, str]] = set()
    for reference in _REFERENCE.findall(template):
        located = _located(reference, cards)
        if located is not None:
            found.add((located[0], folded_name(reference.rpartition(".")[2])))
    return found


def folded_name(text: str) -> str:
    """A name as references and calculations match it: lowercase, with accents
    and spacing folded, so a calculation named in the reader's language reads."""
    folded = unicodedata.normalize("NFKD", str(text).strip().lower())
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\W+", "_", plain).strip("_")


def figure_text(fact: ToolFact) -> str:
    """A figure as the prose states it: the card's value with its unit."""
    value = fact.value
    if value is None or isinstance(value, (bool, str)):
        return str(value)
    key = fact.unit.locale_key if fact.unit is not None else None
    if key == UNIT_CURRENCY_KEY:
        return f"{_money_code(fact) or ''} {_number(value, money=True)}".strip()
    if key == UNIT_PERCENT_KEY:
        return f"{_number(value)}%"
    if key == UNIT_MULTIPLE_KEY:
        return f"{_number(value)}x"
    return _number(value)


def fallback_answer_lead(language: str, *, succeeded: bool) -> str:
    """Argus's own lead when the prose cannot carry the card's figures."""
    spanish = str(language or "").startswith("es")
    if succeeded:
        if spanish:
            return "Aquí está el cálculo con estos datos. Cambia cualquier dato para recalcularlo."
        return (
            "Here is the calculation from these inputs. Change any input to recompute it."
        )
    if spanish:
        return (
            "Los números tal como están no tienen solución. La tarjeta indica qué "
            "falta y ofrece una corrección."
        )
    return "The numbers as stated do not solve. The card names what is missing and offers a fix."


def latest_market_close(symbol: str) -> tuple[float, str] | None:
    """The latest daily close Argus's own market data has for a symbol, and its date."""
    try:
        # Lazy: the compute stack loads only when an answer needs a price.
        from argus.domain.engine import classify_symbol
        from argus.domain.market_data.new_york_clock import new_york_today
        from argus.domain.market_data.provider import fetch_price_series

        asset = classify_symbol(symbol)
        end = new_york_today()
        series = fetch_price_series(
            asset.symbol,
            asset.asset_class,
            end - timedelta(days=_MARKET_WINDOW_DAYS),
            end,
            "1d",
        )
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "Answer market close unavailable error_type={}",
            type(exc).__name__,
            error_type=type(exc).__name__,
        )
        return None
    closes = [
        (index, float(value))
        for index, value in zip(getattr(series, "index", []), list(series), strict=False)
        if value is not None
    ]
    if not closes:
        return None
    index, close = closes[-1]
    return close, str(index)[:10]


def cited_page_inputs(
    calculation: dict[str, Any] | None,
    sources: Sequence[ResearchSource],
    names: Sequence[str],
    *,
    evidence: Sequence[RetrievedRow] = (),
    currency: str = "",
    symbol: str | None = None,
) -> dict[str, tuple[Any, dict[str, Any]]]:
    """The named inputs a refreshed answer read from pages it retrieved, or from
    the provider's finance data the way publication binds them, each with its
    source; anything else in the calculation is ignored."""
    if not calculation:
        return {}
    try:
        request = AnswerCalculation.model_validate(calculation)
    except ValidationError:
        return {}
    pages = {source.url: source for source in sources}
    found: dict[str, tuple[Any, dict[str, Any]]] = {}
    for item in request.inputs:
        if item.name not in names or item.source != "page" or item.value is None:
            continue
        page = pages.get(item.source_url or "")
        if page is not None:
            found[item.name] = (
                item.value,
                page_source(page, item.as_of).model_dump(mode="json"),
            )
            continue
        cited = _evidenced(
            item.value, evidence, name=item.name, currency=currency, symbol=symbol
        )
        if cited is not None:
            found[item.name] = (
                item.value,
                evidence_source(cited).model_dump(mode="json"),
            )
    return found


def _reference_facts(card: ToolResultCard) -> dict[str, ToolFact]:
    presentation = card.presentation
    facts: dict[str, ToolFact] = {
        fact.name: fact for fact in presentation.inputs if fact.value is not None
    }
    facts.update({row.name: row for row in presentation.rows})
    if presentation.answer is not None:
        facts[presentation.answer.name] = presentation.answer
    return facts


def _money_code(fact: ToolFact | None) -> str | None:
    if fact is None or fact.unit is None or fact.unit.locale_key != UNIT_CURRENCY_KEY:
        return None
    return str(fact.unit.interpolation_args.get("code") or "").strip() or None


def _without_written_currency(template: str, cards: AnswerCards) -> str:
    """A reference renders with its own unit, so a currency the prose wrote just
    before or after a money reference, or a % or x written after a percent or
    multiple reference, is not stated twice."""

    def drop(match: re.Match[str]) -> str:
        code = _money_code(_as_fact(_resolved(match.group(3), cards)))
        if code is None or (match.group(1) and match.group(1) != code):
            return match.group(0)
        return match.group(2)

    def drop_after(match: re.Match[str]) -> str:
        fact = _as_fact(_resolved(match.group(2), cards))
        unit = match.group(3)
        key = fact.unit.locale_key if fact is not None and fact.unit is not None else None
        if (
            (fact is not None and unit == _money_code(fact))
            or (unit == "%" and key == UNIT_PERCENT_KEY)
            or (unit == "x" and key == UNIT_MULTIPLE_KEY)
        ):
            return match.group(1)
        return match.group(0)

    return _WRITTEN_UNIT_AFTER.sub(drop_after, _WRITTEN_CURRENCY.sub(drop, template))


def render_offer_prose(template: str, cards: AnswerCards) -> tuple[str, int]:
    """The prose of an offered calculation: references to figures its cards hold
    filled, and each sentence or table row that leans on a result the offer
    cannot show left out. Returns the text and how many were left out."""

    def fill(match: re.Match[str]) -> str:
        value = _resolved(match.group(1), cards)
        if value is None:
            return match.group(0)
        return value if isinstance(value, str) else figure_text(value)

    kept, dropped = _trim_unresolved_clauses(template, cards)
    return _REFERENCE.sub(fill, _without_written_currency(kept, cards)), dropped


def _trim_unresolved_clauses(template: str, cards: AnswerCards) -> tuple[str, int]:
    """Keep valid prose and its references, so recovered answers can recompute."""

    def unresolved(text: str) -> bool:
        return bool(unresolved_references(text, cards)) or "{{" in _REFERENCE.sub(
            "", text
        )

    kept: list[str] = []
    dropped = 0
    for line in template.split("\n"):
        if not unresolved(line):
            kept.append(line)
            continue
        if line.lstrip().startswith("|"):
            dropped += 1
            continue
        sentences = _SENTENCE_BREAK.split(line)
        remaining = [sentence for sentence in sentences if not unresolved(sentence)]
        dropped += len(sentences) - len(remaining)
        if remaining:
            kept.append(" ".join(remaining))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), dropped


def _stated_argument(card: ToolResultCard, name: str) -> str | None:
    """A declared input the card holds as text rather than as a figure, such as a
    start date or a choice, stated as the card received it."""
    value = card.arguments.get(name)
    return value if isinstance(value, str) and value.strip() else None


def states_a_figure(text: str) -> bool:
    """A money or percent figure written as digits rather than referenced."""
    if _PERCENT_FIGURE.search(text) or _SYMBOL_MONEY.search(text):
        return True
    return any(
        (match.group(1) or match.group(2)) in CURRENCY_CODES
        for match in _CODE_MONEY.finditer(text)
    )


def _number(value: float, *, money: bool = False) -> str:
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return f"{int(rounded):,}"
    if money:
        return f"{rounded:,.2f}"
    return f"{rounded:,.2f}".rstrip("0").rstrip(".")


def _calculation_currency(
    request: AnswerCalculation,
    currency: str | None,
    notes: list[str],
    *,
    declared: set[str],
    pages: Mapping[str, ResearchSource],
    evidence: Sequence[RetrievedRow],
    symbol: str | None,
) -> str:
    # A stated amount owns its denomination, even when the profile or a
    # separate currency input names another currency.
    denominations = {
        item.currency.strip().upper()
        for item in request.inputs
        if item.name in declared
        and item.name not in {CURRENCY_FIELD, SYMBOL_FIELD, request.solve_for}
        and item.source in {"user", "page"}
        and item.value is not None
        and item.currency
        and item.currency.strip().upper() in CURRENCY_CODES
        and (
            item.source == "user"
            or _page_input_source(
                item,
                pages=pages,
                evidence=evidence,
                currency=item.currency.strip().upper(),
                symbol=symbol,
            )
            is not None
        )
    }
    stated = ""
    for item in request.inputs:
        if item.name != CURRENCY_FIELD or not isinstance(item.value, str):
            continue
        code = item.value.strip().upper()
        if code not in CURRENCY_CODES:
            continue
        if (
            item.source == "page"
            and _page_input_source(
                item, pages=pages, evidence=evidence, currency=code, symbol=symbol
            )
            is None
        ):
            _note(notes, PAGE_UNCITED_REASON_CODE, name=item.name)
            continue
        if item.source == "market_data":
            _note(notes, MARKET_DATA_NOT_A_PRICE_REASON_CODE, name=item.name)
            continue
        stated = code
        break
    if len(denominations) == 1:
        return next(iter(denominations))
    if stated:
        return stated
    if currency:
        return currency.strip().upper()
    _note(notes, CURRENCY_DEFAULTED_REASON_CODE, currency=DEFAULT_CURRENCY)
    return DEFAULT_CURRENCY


def _page_input_source(
    item: AnswerCalculationInput,
    *,
    pages: Mapping[str, ResearchSource],
    evidence: Sequence[RetrievedRow],
    currency: str,
    symbol: str | None,
) -> ToolFactSource | None:
    """One source check for both an amount and its denomination."""
    if item.value is None:
        return None
    page = pages.get(item.source_url or "")
    if page is not None:
        return page_source(page, item.as_of)
    cited = _evidenced(
        item.value, evidence, name=item.name, currency=currency, symbol=symbol
    )
    return evidence_source(cited) if cited is not None else None


def _stated_symbol(request: AnswerCalculation) -> str | None:
    return next(
        (
            item.value.strip()
            for item in request.inputs
            if item.name == SYMBOL_FIELD
            and isinstance(item.value, str)
            and item.value.strip()
        ),
        None,
    )


def _market_price(
    name: str, symbol: str | None, market_close: MarketClose, notes: list[str]
) -> tuple[float, ToolFactSource] | None:
    if name != PRICE_FIELD:
        _note(notes, MARKET_DATA_NOT_A_PRICE_REASON_CODE, name=name)
        return None
    close = market_close(symbol) if symbol else None
    if close is None:
        _note(notes, MARKET_PRICE_UNAVAILABLE_REASON_CODE, symbol=symbol)
        return None
    value, as_of = close
    dated = as_of if _ISO_DATE.fullmatch(as_of or "") else None
    return value, ToolFactSource(kind="market_data", date=dated)


def page_source(page: ResearchSource, as_of: str | None) -> ToolFactSource:
    dated = next(
        (
            value[:10]
            for value in (as_of, page.source_date)
            if value and _ISO_DATE.fullmatch(value[:10])
        ),
        None,
    )
    title = page.title.strip() or urlparse(page.url).hostname or ""
    return ToolFactSource(
        kind="page", title=title[:300] or None, url=page.url[:2048], date=dated
    )


def _evidenced(
    value: Any,
    evidence: Sequence[RetrievedRow],
    *,
    name: str,
    currency: str,
    symbol: str | None,
) -> RetrievedRow | None:
    """The cited row stating this input's figure, when the page it names is the
    provider's own finance data, whose citation keeps no URL: the same number,
    about the same security, measuring what the input measures."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    percent = name.endswith("_pct")
    return next(
        (
            row
            for row in evidence
            if abs(float(row.value) - float(value))
            <= max(abs(float(row.value)) * 1e-6, 1e-9)
            and not (row.symbol and symbol and row.symbol.upper() != symbol.upper())
            and (row.kind == "percent") == percent
            and (row.kind != "currency" or row.unit.strip().upper() == currency)
        ),
        None,
    )


def evidence_source(row: RetrievedRow | None) -> ToolFactSource:
    """A figure cited from finance data names its subject and its row's date,
    never a URL."""
    assert row is not None
    dated = row.as_of[:10] if row.as_of and _ISO_DATE.fullmatch(row.as_of[:10]) else None
    title = f"{row.subject} {row.label}".strip()
    return ToolFactSource(kind="page", title=title[:300] or None, date=dated)


def _blank_inputs(
    declaration: ToolDeclaration, arguments: dict[str, Any], solve_for: str | None
) -> list[str]:
    """Inputs the declaration still needs, other than the one being solved."""
    try:
        declaration.validate_arguments(arguments)
    except ToolInvocationError as exc:
        failure = exc.outcome.failure
        if failure is None:
            return []
        if failure.code == MISSING_INPUT_CODE:
            return list(failure.fields)
        if failure.code == "exactly_one_unknown":
            return [
                name
                for name in failure.fields
                if arguments.get(name) is None and name != solve_for
            ]
        return []
    except ValidationError as exc:
        return [
            str(error["loc"][0])
            for error in exc.errors()
            if error.get("type") == "missing" and error.get("loc")
        ]
    except (ValueError, TypeError):
        return []
    outcome = declaration.invoke_sync(arguments)
    if outcome.failure is not None and outcome.failure.code == MISSING_INPUT_CODE:
        return list(outcome.failure.fields)
    return []


def _note(notes: list[str], code: str, **context: Any) -> None:
    if code not in notes:
        notes.append(code)
    # Context can contain model-supplied names, references and private values.
    logger.info("Answer calculation guard {}", code, failure_classification=code)


_PROSE_FIGURE = re.compile(
    r"(?<![\w/.,-])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(%|x\b)?"
    r"(?:\s+(billion|bn|million|thousand|mil millones|millones|mil))?(?![\w/-])"
)
_SCALES = {
    "billion": 1e9,
    "bn": 1e9,
    "mil millones": 1e9,
    "million": 1e6,
    "millones": 1e6,
    "thousand": 1e3,
    "mil": 1e3,
}


def _figure_value(token: str) -> tuple[float, int]:
    """The number a digit token states and its shown decimals, for either
    decimal separator."""
    last_dot, last_comma = token.rfind("."), token.rfind(",")
    decimal = "." if last_dot > last_comma else ","
    whole, _, fraction = token.rpartition(decimal)
    if (
        not whole
        or len(fraction) == 3
        and token.count(decimal) >= 1
        and (token.count(decimal) > 1 or last_dot > -1 and last_comma > -1 or not whole)
    ):
        whole, fraction = token, ""
    if (
        fraction
        and len(fraction) == 3
        and "." not in token.replace(decimal, "", 1)
        and "," not in token.replace(decimal, "", 1)
    ):
        # One separator followed by three digits reads as a thousands group.
        whole, fraction = token, ""
    digits = "".join(ch for ch in whole if ch.isdigit())
    number = float(digits or 0) + (float(f"0.{fraction}") if fraction.isdigit() else 0.0)
    return number, len(fraction) if fraction.isdigit() else 0


def unsourced_prose_figures(
    prose: str,
    *,
    cited: Sequence[float],
    cards: Sequence[ToolResultCard],
    names: Sequence[str] = (),
) -> list[str]:
    """The digit figures an answer's prose states that match neither a cited row
    nor a value of its calculation. Dates, years, a day number beside its year,
    numbers inside words and a number that names a cited product or a named
    model are not figures."""
    named = {
        token
        for text in names
        for token in re.findall(r"(?<![\d.,])\d+(?![\d.,])", str(text))
    }
    known = [float(value) for value in cited]
    for card in cards:
        presentation = card.presentation
        facts = [*presentation.inputs, *presentation.rows]
        if presentation.answer is not None:
            facts.append(presentation.answer)
        known.extend(
            float(fact.value)
            for fact in facts
            if isinstance(fact.value, (int, float)) and not isinstance(fact.value, bool)
        )
    text = _ISO_DATE.sub(" ", prose)
    unsourced: list[str] = []
    for match in _PROSE_FIGURE.finditer(text):
        token, suffix, scale = match.group(1), match.group(2), match.group(3)
        plain = not suffix and not scale and token.isdigit()
        if plain and re.fullmatch(r"(19|20)\d{2}", token):
            continue
        if plain and (token in named or _names_a_model(text, match.start())):
            continue
        if (
            plain
            and len(token) <= 2
            and _YEAR.search(text, match.end(), match.end() + 25)
        ):
            continue
        value, decimals = _figure_value(token)
        candidates = [value, value * _SCALES.get(str(scale or "").lower(), 1.0)]
        if any(
            abs(candidate - item) <= max(abs(item) * 0.005, 0.5 * 10**-decimals)
            for candidate in candidates
            for item in known
        ):
            continue
        unsourced.append(match.group(0).strip())
    return unsourced


def _names_a_model(text: str, start: int) -> bool:
    """A bare number right after a mid-sentence word that mixes capitals and
    lowercase, such as Porsche 911 or iPhone 16, names a model."""
    word = re.search(r"([^\W\d_]+) $", text[:start])
    if word is None:
        return False
    letters = word.group(1)
    if not (any(ch.isupper() for ch in letters) and any(ch.islower() for ch in letters)):
        return False
    before = text[: word.start(1)].rstrip()
    return bool(before) and before[-1] not in ".!?:\n"


def record_unsourced_figures(
    prose: str,
    *,
    cited: Sequence[float],
    cards: Sequence[ToolResultCard],
    notes: list[str],
    message: str,
    names: Sequence[str] = (),
) -> int:
    """Records, and never replaces, the figures an answer states with no source."""
    figures = unsourced_prose_figures(prose, cited=cited, cards=cards, names=names)
    if figures:
        if UNSOURCED_FIGURE_REASON_CODE not in notes:
            notes.append(UNSOURCED_FIGURE_REASON_CODE)
        logger.info(
            "Answer prose figures with no cited row or calculation value "
            "count={}",
            len(figures),
            figure_count=len(figures),
            failure_classification=UNSOURCED_FIGURE_REASON_CODE,
        )
    return len(figures)


def cards_in(patch: dict[str, Any] | None) -> list[ToolResultCard]:
    """Every card a computed patch carries."""
    payload = (patch or {}).get("final_response_payload") or {}
    return [
        ToolResultCard.model_validate(card)
        for card in payload.get("tool_result_cards") or []
    ]

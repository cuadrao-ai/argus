"""Generic calculation-receipt projection retained by the web fixture generator."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from argus.api.public_excerpt_schemas import (
    PublicExcerptCalculation,
    PublicExcerptCalculationFact,
    PublicExcerptCalculationSource,
    PublicExcerptCalculationText,
    PublicExcerptCalculationTurn,
)
from argus.api.schemas import Message
from argus.domain.decision_attachment import computation_from_message_metadata
from argus.domain.public_excerpts import (
    _CONTROL_CHARS,
    PublicExcerptSanitizationError,
    PublicExcerptSourceError,
    audit_public_excerpt_document,
)
from argus.domain.tool_contracts import ToolResultCard


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


def mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def message_metadata(message: Mapping[str, Any]) -> Mapping[str, Any]:
    return mapping(message.get("metadata"))


def computed_answer_cards(message: Mapping[str, Any]) -> list[ToolResultCard] | None:
    """The cards the answer's declared computation names, in its order, or
    ``None`` when a calculation it declares has no card that agrees."""
    metadata = message_metadata(message)
    computation = computation_from_message_metadata(metadata)
    if computation is None or message.get("role") != "assistant":
        return None
    raw_cards = metadata.get("tool_result_cards")
    if not isinstance(raw_cards, list):
        return None
    cards: list[ToolResultCard] = []
    for raw in raw_cards:
        try:
            cards.append(ToolResultCard.model_validate(raw))
        except ValueError:
            continue
    matched: list[int] = []
    for calculation in computation.calculations:
        position = next(
            (
                index
                for index, card in enumerate(cards)
                if index not in matched
                and card.tool_name == calculation.kind
                and card.arguments == calculation.inputs
            ),
            None,
        )
        if position is None:
            return None
        matched.append(position)
    return [cards[index] for index in matched]


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

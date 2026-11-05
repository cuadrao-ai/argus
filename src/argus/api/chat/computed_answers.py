"""Computed answers outside a turn: listed, compared, continued and refreshed.

Every read is owner-scoped and every write is the owner's. Listing, comparing
and continuing call no model, retrieval or provider. Refreshing the cited
inputs is the one paid action: the user starts it, it is claimed under the
existing research allowance and recorded in the ledger like a turn, and the
refreshed card comes back beside the stored answer, which is never rewritten.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from argus.api import state as api_state
from argus.api.computation_contract import (
    MAX_LISTED_ANSWERS,
    ComparedAnswer,
    ComputationComparison,
    ComputationDifference,
    ComputationRefreshResponse,
    ComputedAnswerRef,
    ComputedAnswerSummary,
)
from argus.api.conversation_surface import (
    conversation_scope,
    memory_conversation_in_scope,
)
from argus.api.decision_contract import DecisionComputation, DecisionRerun
from argus.api.message_store import (
    create_message,
    memory_conversation,
    owned_conversation_message,
)
from argus.api.schemas import Conversation, Message, User
from argus.api.search_computed import question_for_answer
from argus.domain.answer_dossiers import computed_answer_cards
from argus.domain.computation_compare import ComparisonKindMismatch, card_differences
from argus.domain.computation_marker import computation_from_tool_cards
from argus.domain.decision_attachment import computation_from_message_metadata
from argus.domain.owner_scope import PERSONAL, OwnerScope
from argus.domain.research.contracts import ResearchPacket
from argus.domain.run_dossiers import message_metadata, row_activity
from argus.domain.tool_contracts import (
    TOOL_INPUT_SOURCES_FIELD,
    ToolCall,
    ToolResultCard,
)

CONTINUED_FROM_KEY = "continued_from"
CONTINUED_TITLE = "New idea"
RERUN_IDENTITY = "decision_rerun"


class ComputedAnswerNotFoundError(LookupError):
    """The message is absent, not owned, not in the conversation, or not an answer."""


class ComputationUnsupportedError(ValueError):
    """The message declares no computation whose card it carries."""


class ComputationSelectionError(ValueError):
    """Two answers that cannot be lined up: the same one, or different kinds."""


class NothingToRefreshError(ValueError):
    """The answer cites no page for an input a retrieval can supply."""


class RefreshCapacityExhaustedError(RuntimeError):
    """The research allowance refused the retrieval before any provider work."""

    def __init__(self, *, guest_exhausted: bool) -> None:
        super().__init__("Research capacity exhausted")
        self.guest_exhausted = guest_exhausted


class RefreshUnavailableError(RuntimeError):
    """The retrieval could not run or did not answer."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OwnedAnswer:
    message: Message
    cards: list[ToolResultCard]
    computation: DecisionComputation
    asked: str | None


def owned_computed_answer(
    *, user: User, conversation_id: str, message_id: str
) -> OwnedAnswer:
    message = owned_conversation_message(
        user_id=user.id, conversation_id=conversation_id, message_id=message_id
    )
    if message is None or message.role != "assistant":
        raise ComputedAnswerNotFoundError("Message not found or not owned by user.")
    row = message.model_dump(mode="python")
    computation = computation_from_message_metadata(message.metadata)
    cards = computed_answer_cards(row)
    if computation is None or cards is None:
        raise ComputationUnsupportedError("This answer carries no computation.")
    return OwnedAnswer(
        message=message,
        cards=cards,
        computation=computation,
        asked=question_for_answer(user, row),
    )


def computed_answers_of_kind(
    *,
    user: User,
    scope: OwnerScope,
    kind: str,
    exclude_message_id: str | None = None,
) -> list[ComputedAnswerSummary]:
    """The owner's newest computed answers of one kind on one side, for a comparison
    to pick."""
    rows = sorted(
        _owned_rows_of_kind(user, scope, kind),
        key=lambda row: (row_activity(row), str(row.get("id") or "")),
        reverse=True,
    )
    items: list[ComputedAnswerSummary] = []
    for row in rows:
        if exclude_message_id is not None and str(row.get("id")) == exclude_message_id:
            continue
        cards = computed_answer_cards(row)
        computation = computation_from_message_metadata(message_metadata(row))
        # A comparison lines up one calculation with one; an answer that weighs
        # several options is not a result of one kind.
        if cards is None or computation is None or computation.kinds != [kind]:
            continue
        items.append(
            ComputedAnswerSummary(
                conversation_id=str(row.get("conversation_id")),
                message_id=str(row.get("id")),
                kind=kind,
                asked=question_for_answer(user, row),
                computed_at=row_activity(row),
                symbols=list(computation.symbols),
            )
        )
        if len(items) == MAX_LISTED_ANSWERS:
            break
    return items


def _owned_rows_of_kind(
    user: User, scope: OwnerScope, kind: str
) -> list[Mapping[str, Any]]:
    if api_state.supabase_gateway is not None:
        return api_state.supabase_gateway.computed_answers_of_kind(
            user_id=user.id, scope=scope, kind=kind, limit=MAX_LISTED_ANSWERS + 1
        )
    rows: list[Mapping[str, Any]] = []
    for conversation_id, messages in api_state.store.messages.items():
        if api_state.store.conversation_owners.get(
            conversation_id
        ) != user.id or not memory_conversation_in_scope(conversation_id, scope):
            continue
        conversation = api_state.store.conversations.get(conversation_id)
        if conversation is None or conversation.deleted_at is not None:
            continue
        rows.extend(
            message.model_dump(mode="python")
            for message in messages
            if message.role == "assistant"
        )
    return rows


def compare_computed_answers(
    *, user: User, left: ComputedAnswerRef, right: ComputedAnswerRef
) -> ComputationComparison:
    """Two owned answers of one kind side by side, differences from Python."""
    if (left.conversation_id, left.message_id) == (
        right.conversation_id,
        right.message_id,
    ):
        raise ComputationSelectionError("Choose two different answers to compare.")
    first = owned_computed_answer(
        user=user, conversation_id=left.conversation_id, message_id=left.message_id
    )
    second = owned_computed_answer(
        user=user, conversation_id=right.conversation_id, message_id=right.message_id
    )
    if len(first.cards) != 1 or len(second.cards) != 1:
        raise ComputationSelectionError(
            "Only answers with one calculation compare side by side."
        )
    try:
        differences = card_differences(first.cards[0], second.cards[0])
    except ComparisonKindMismatch as exc:
        raise ComputationSelectionError(str(exc)) from exc
    return ComputationComparison(
        kind=first.cards[0].tool_name,
        left=_compared(first),
        right=_compared(second),
        differences=[
            ComputationDifference(
                section=difference.section,
                name=difference.name,
                label=difference.label,
                unit=difference.unit,
                left=difference.left,
                right=difference.right,
                difference=difference.difference,
            )
            for difference in differences
        ],
    )


def _compared(answer: OwnedAnswer) -> ComparedAnswer:
    return ComparedAnswer(
        conversation_id=answer.message.conversation_id,
        message_id=answer.message.id,
        asked=answer.asked,
        computed_at=answer.message.created_at,
        card=answer.cards[0].model_dump(mode="json"),
    )


def continue_computed_answer(
    *, user: User, conversation_id: str, message_id: str
) -> tuple[Conversation, Message]:
    """A new chat whose one message carries only this result, linked to its source.

    Each card is copied under a new artifact identity so recomputing it in the
    new chat never touches the source; the source conversation is unchanged.
    """
    answer = owned_computed_answer(
        user=user, conversation_id=conversation_id, message_id=message_id
    )
    cards = [
        card.model_copy(update={"artifact_id": str(uuid4()), "input_revision": 0})
        for card in answer.cards
    ]
    computation = computation_from_tool_cards(cards)
    if computation is None:
        raise ComputationUnsupportedError("This answer carries no computation.")
    renamed = {
        source.artifact_id: copied.artifact_id
        for source, copied in zip(answer.cards, cards, strict=True)
    }
    source_scope = conversation_scope(user_id=user.id, conversation_id=conversation_id)
    conversation = _new_conversation(user, source_scope or PERSONAL)
    message = create_message(
        user_id=user.id,
        conversation_id=conversation.id,
        role="assistant",
        content=answer.message.content,
        metadata={
            "tool_result_cards": [card.model_dump(mode="json") for card in cards],
            "computation": computation.model_dump(mode="json"),
            CONTINUED_FROM_KEY: {
                "conversation_id": conversation_id,
                "message_id": message_id,
            },
            **_rebound_prose(answer.message.metadata or {}, renamed),
        },
    )
    return conversation, message


def _rebound_prose(metadata: dict[str, Any], renamed: dict[str, str]) -> dict[str, Any]:
    """The source answer's prose template and assumed-input line pointed at the
    copied cards, so a recompute in the new chat re-renders the prose too."""
    from argus.agent_runtime.answer_calculation import (
        ANSWER_ASSUMPTIONS_KEY,
        ANSWER_TEMPLATE_KEY,
    )

    template = metadata.get(ANSWER_TEMPLATE_KEY)
    if not isinstance(template, dict):
        return {}
    named = template.get("cards")
    if isinstance(named, dict):
        if not named or any(artifact not in renamed for artifact in named.values()):
            return {}
        rebound_template = {
            **template,
            "cards": {name: renamed[artifact] for name, artifact in named.items()},
        }
    elif template.get("artifact_id") in renamed:
        rebound_template = {**template, "artifact_id": renamed[template["artifact_id"]]}
    else:
        return {}
    rebound: dict[str, Any] = {ANSWER_TEMPLATE_KEY: rebound_template}
    assumptions = metadata.get(ANSWER_ASSUMPTIONS_KEY)
    if isinstance(assumptions, list):
        rebound[ANSWER_ASSUMPTIONS_KEY] = [
            {
                **item,
                "artifact_id": renamed.get(
                    item.get("artifact_id"), item.get("artifact_id")
                ),
            }
            for item in assumptions
            if isinstance(item, dict)
        ]
    return rebound


def _new_conversation(user: User, scope: OwnerScope) -> Conversation:
    """A continuation joins its source's side."""
    if api_state.supabase_gateway is not None:
        return api_state.supabase_gateway.create_conversation(
            user_id=user.id,
            title=CONTINUED_TITLE,
            title_source="system_default",
            language=user.language,
            scope=scope,
        )
    return memory_conversation(
        title=CONTINUED_TITLE,
        title_source="system_default",
        language=user.language,
        scope=scope,
        user_id=user.id,
    )


async def refresh_computed_answer(
    *,
    user: User,
    conversation_id: str,
    message_id: str,
    guest_visitor_key: str | None,
) -> ComputationRefreshResponse:
    """Look up the answer's cited inputs again and compute each card beside it. A
    page input is looked up through the research allowance; a market data input
    reads Argus's own latest close for free. The stored answer never moves."""
    from argus.agent_runtime import research_grounded as grounded
    from argus.agent_runtime.answer_calculation import cited_page_inputs
    from argus.agent_runtime.research_answer import _resolved_subjects
    from argus.agent_runtime.research_calculation import (
        cited_evidence,
        retrieved_pages,
    )
    from argus.agent_runtime.research_query import ResearchQueryExtraction
    from argus.api.chat.research_evidence import (
        claim_research_provider_attempt,
        release_research_provider_claim,
    )
    from argus.domain.capability_registry import get_tool_catalog
    from argus.domain.research.admission import (
        claim_current_research_attempt,
        research_attempt_admission_context,
    )
    from argus.domain.research.config import research_rail_enabled, retrieval_spec
    from argus.domain.research.contracts import ResearchUnavailableError

    answer = owned_computed_answer(
        user=user, conversation_id=conversation_id, message_id=message_id
    )
    catalog = get_tool_catalog()
    declarations = [catalog.get(card.tool_name) for card in answer.cards]
    cited = [_cited_inputs(card) for card in answer.cards]
    if not any(cited) or any(declaration is None for declaration in declarations):
        raise NothingToRefreshError("This answer cites no page to look up again.")
    if not research_rail_enabled():
        raise RefreshUnavailableError("not_configured")
    client = grounded._client()
    if client is None:
        raise RefreshUnavailableError("not_configured")
    subjects = _resolved_subjects(
        ResearchQueryExtraction(
            question_kind="company_lookup", symbols=list(answer.computation.symbols)
        )
    )
    language = grounded.language_tag(user.language)
    names = _calculation_names(answer)
    single = len(answer.cards) == 1
    prompt = grounded._research_prompt(
        message=answer.asked or str(getattr(declarations[0], "description", "")),
        subjects=subjects,
        period=None,
        language=language,
        question_kind=None,
        publisher_sources_required=True,
        scenario=True,
        country=user.country,
        currency=user.currency,
        lookup_inputs=[
            item if single else f"{name}.{item}"
            for name, inputs in zip(names, cited, strict=True)
            for item in inputs
        ],
    )
    spec = retrieval_spec(
        "balanced",
        question_kind="company_lookup",
        language_tag=language,
        country=user.country,
        scenario=True,
    )
    spend = grounded._TurnSpend()
    with research_attempt_admission_context(
        lambda: claim_research_provider_attempt(guest_visitor_key=guest_visitor_key),
        release=lambda admission: release_research_provider_claim(
            admission, guest_visitor_key=guest_visitor_key
        ),
    ):
        admission = claim_current_research_attempt()
        if not admission.available:
            raise RefreshCapacityExhaustedError(guest_exhausted=admission.guest_exhausted)
        try:
            packet = await spend.run(client, prompt, spec)
        except ResearchUnavailableError as exc:
            _record_refresh(
                user,
                conversation_id,
                grounded.returned_sources_research_sidecar(
                    sources=(), usage=spend.total, degraded_code="research_unavailable"
                ),
            )
            raise RefreshUnavailableError(exc.reason) from exc
    packet = packet.model_copy(update={"usage": spend.reported(packet.usage)})
    degraded = grounded._not_grounded_code(packet, survey=False)
    sidecar = grounded.build_research_sidecar(
        capability_class="balanced_lookup",
        shape="balanced",
        sources=grounded.typed_sources(packet),
        retrieved_rows=grounded.typed_rows(packet),
        retrieved_at=packet.retrieved_at.isoformat(),
        subjects=subjects,
        peers=[],
        usage={
            "invocations": packet.usage.invocations,
            "latency_ms": packet.usage.latency_ms,
            "cost_usd": packet.usage.cost_usd,
            "cache_status": "miss",
        },
        period_of_interest=None,
        degraded_code=degraded,
    )
    _record_refresh(user, conversation_id, sidecar)
    pages = retrieved_pages(packet)
    evidence = cited_evidence(packet)
    found = [
        {}
        if degraded is not None or not inputs
        else cited_page_inputs(
            _looked_up(packet, name=name, kind=card.tool_name, single=single),
            pages,
            inputs,
            evidence=evidence,
            currency=str(card.arguments.get("currency") or "").strip().upper(),
            symbol=str(card.arguments.get("symbol") or "") or None,
        )
        for name, card, inputs in zip(names, answer.cards, cited, strict=True)
    ]
    if not any(found):
        return ComputationRefreshResponse(
            computation=answer.computation,
            status="inputs_not_found",
            sources=list(sidecar["sources"]),
        )
    # Each card's market price is its own asset's; an answer's one symbol stands
    # in only for a card that names none.
    symbols = list(answer.computation.symbols)
    only = symbols[0] if len(symbols) == 1 else None
    return ComputationRefreshResponse(
        computation=answer.computation,
        status="refreshed",
        reruns=[
            _refreshed_rerun(
                card,
                declaration,
                inputs,
                symbol=str(card.arguments.get("symbol") or "") or only,
            )
            for card, declaration, inputs in zip(
                answer.cards, declarations, found, strict=True
            )
        ],
        sources=list(sidecar["sources"]),
    )


def _cited_inputs(card: ToolResultCard) -> list[str]:
    """The inputs a card read from a page, which a retrieval can look up again."""
    sources = card.arguments.get(TOOL_INPUT_SOURCES_FIELD)
    if not isinstance(sources, Mapping):
        return []
    return [
        name
        for name, source in sources.items()
        if isinstance(source, Mapping) and source.get("kind") == "page"
    ]


def _calculation_names(answer: OwnedAnswer) -> list[str]:
    """Each card's calculation name as the answer's template gave it, or its place."""
    from argus.agent_runtime.answer_calculation import ANSWER_TEMPLATE_KEY, template_cards

    template = (answer.message.metadata or {}).get(ANSWER_TEMPLATE_KEY)
    named = template_cards(template) if isinstance(template, Mapping) else {}
    by_artifact = {artifact: name for name, artifact in named.items()}
    return [
        by_artifact.get(card.artifact_id, f"calculation_{index}")
        for index, card in enumerate(answer.cards, start=1)
    ]


def _looked_up(
    packet: ResearchPacket, *, name: str, kind: str, single: bool
) -> dict[str, Any] | None:
    """The looked-up calculation for a stored card: the one of its kind when the
    answer holds one calculation, else the one under its name and kind."""
    from argus.agent_runtime.answer_calculation import folded_name

    return next(
        (
            item
            for item in packet.calculations
            if item.get("kind") == kind
            and (single or folded_name(str(item.get("name") or "")) == name)
        ),
        None,
    )


def _refreshed_rerun(
    card: ToolResultCard,
    declaration: Any,
    found: Mapping[str, tuple[Any, dict[str, Any]]],
    *,
    symbol: str | None,
) -> DecisionRerun:
    """A card computed again beside the stored one: each input found again, a
    cited input no page states today with its stored value and date, and a
    market data input at Argus's own latest close."""
    from argus.agent_runtime.answer_calculation import latest_market_close

    arguments = dict(card.arguments)
    stored_sources = arguments.get(TOOL_INPUT_SOURCES_FIELD)
    stored_sources = stored_sources if isinstance(stored_sources, Mapping) else {}
    refreshed: dict[str, Any] = {
        name: value
        for name, value in arguments.items()
        if name != TOOL_INPUT_SOURCES_FIELD
    }
    kept: dict[str, Any] = {name: dict(source) for name, source in stored_sources.items()}
    for name, (value, source) in found.items():
        refreshed[name] = value
        kept[name] = source
    for name, source in stored_sources.items():
        if isinstance(source, Mapping) and source.get("kind") == "market_data" and symbol:
            close = latest_market_close(symbol)
            if close is not None:
                refreshed[name] = close[0]
                kept[name] = {"kind": "market_data", "date": close[1]}
    refreshed[TOOL_INPUT_SOURCES_FIELD] = kept
    outcome = declaration.invoke_sync(refreshed)
    result = declaration.result_card(
        call=ToolCall(
            tool_name=declaration.name, call_id=RERUN_IDENTITY, arguments=refreshed
        ),
        outcome=outcome,
        artifact_id=RERUN_IDENTITY,
    )
    return DecisionRerun(
        kind=declaration.name,
        inputs=result.arguments,
        status="computed",
        result=result.model_dump(mode="json"),
    )


def _record_refresh(user: User, conversation_id: str, sidecar: dict[str, Any]) -> None:
    from argus.api.chat.research_evidence import record_research_turn_evidence

    record_research_turn_evidence(
        research=sidecar,
        user_id=user.id,
        conversation_id=conversation_id,
        message_id=None,
        request_id=f"computation_refresh:{uuid4()}",
    )

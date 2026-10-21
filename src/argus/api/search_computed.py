"""Computed answers in Search: the dossier beside the run dossier, and the asset row.

Hydrated after the existing read in both persistence modes, so the run
dossier projection and its SQL stay untouched. Bounded to the page Search
already selected; no model, retrieval or provider call.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from argus.api import state as api_state
from argus.api.conversation_surface import memory_conversation_in_scope
from argus.api.decision_contract import DecisionActionAvailability, DecisionNote
from argus.api.message_store import owned_conversation_message
from argus.api.schemas import (
    SearchAssetDecisionCounts,
    SearchAssetRollup,
    SearchItem,
    User,
)
from argus.domain.answer_dossiers import (
    ANSWER_REQUEST_MESSAGE_KEY,
    computed_answer_cards,
    computed_symbols,
    current_answer_decision,
    latest_computed_answer,
    project_answer_dossier,
    question_before,
    question_text,
)
from argus.domain.owner_scope import OwnerScope
from argus.domain.run_dossiers import message_metadata, row_activity
from argus.domain.search_text import normalize_search_symbol

_DECISION_STATES = ("promising", "watching", "rejected", "revisit_later")


def attach_answer_dossiers(
    items: Sequence[SearchItem],
    *,
    user: User,
    decision_action_availability: DecisionActionAvailability | None,
) -> list[SearchItem]:
    """Each conversation row gains its latest computed answer, when it has one."""
    if not items:
        return list(items)
    answers = _latest_answers(user, [item.conversation_id for item in items])
    if not answers:
        return list(items)
    decisions = _answer_decisions(user, [row["id"] for row, _ in answers.values()])
    attached: list[SearchItem] = []
    for item in items:
        found = answers.get(item.conversation_id)
        if found is None:
            attached.append(item)
            continue
        message, cards = found
        decision = decisions.get(str(message["id"]))
        dossier = project_answer_dossier(
            message=message,
            cards=cards,
            asked=question_for_answer(user, message),
            decision=decision.model_dump(mode="python") if decision else None,
            decision_action_availability=decision_action_availability,
        )
        attached.append(item.model_copy(update={"answer_dossier": dossier}))
    return attached


def with_computed_results(
    rollup: SearchAssetRollup | None,
    *,
    user: User,
    scope: OwnerScope,
    query: str,
    guest_conversation_id: str | None,
) -> SearchAssetRollup | None:
    """The asset row counts computed results involving the asset, not only runs."""
    normalized_query = normalize_search_symbol(query)
    if normalized_query is None:
        return rollup
    rows = _computed_symbol_rows(user, scope, guest_conversation_id)
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    display: dict[str, str] = {}
    for row in rows:
        for symbol in computed_symbols(row):
            normalized = normalize_search_symbol(symbol)
            if normalized is None:
                continue
            by_symbol.setdefault(normalized, []).append(row)
            display.setdefault(normalized, symbol)
    if rollup is not None:
        resolved = normalize_search_symbol(rollup.symbol)
    else:
        matching = sorted(
            symbol for symbol in by_symbol if symbol.startswith(normalized_query)
        )
        exact = [symbol for symbol in matching if symbol == normalized_query]
        resolved = exact[0] if exact else matching[0] if len(matching) == 1 else None
    if resolved is None:
        return rollup
    involved = by_symbol.get(resolved, [])
    if not involved:
        return rollup
    decisions = _answer_decisions(user, [str(row["id"]) for row in involved])
    counts = {state: 0 for state in _DECISION_STATES}
    touched: list[datetime] = [row_activity(row) for row in involved]
    for decision in decisions.values():
        if decision.decision_state in counts:
            counts[decision.decision_state] += 1
        touched.append(decision.updated_at)
    if rollup is None:
        return SearchAssetRollup(
            symbol=display[resolved],
            run_count=0,
            result_count=len(involved),
            decision_counts=SearchAssetDecisionCounts(**counts),
            last_touched_at=max(touched),
        )
    merged = {
        state: getattr(rollup.decision_counts, state) + counts[state]
        for state in _DECISION_STATES
    }
    return rollup.model_copy(
        update={
            "result_count": rollup.run_count + len(involved),
            "decision_counts": SearchAssetDecisionCounts(**merged),
            "last_touched_at": max(rollup.last_touched_at, *touched),
        }
    )


def _latest_answers(
    user: User, conversation_ids: Iterable[str]
) -> dict[str, tuple[Mapping[str, Any], Any]]:
    ids = list(dict.fromkeys(conversation_ids))
    found: dict[str, tuple[Mapping[str, Any], Any]] = {}
    if api_state.supabase_gateway is not None:
        rows = api_state.supabase_gateway.latest_computed_answers(
            user_id=user.id, conversation_ids=ids
        )
        for conversation_id, row in rows.items():
            cards = computed_answer_cards(row)
            if cards is not None:
                found[conversation_id] = (row, cards)
        return found
    for conversation_id in ids:
        if api_state.store.conversation_owners.get(conversation_id) != user.id:
            continue
        messages = [
            message.model_dump(mode="python")
            for message in api_state.store.messages.get(conversation_id, [])
        ]
        latest = latest_computed_answer(messages)
        if latest is not None:
            found[conversation_id] = latest
    return found


def question_for_answer(user: User, message: Mapping[str, Any]) -> str | None:
    """The question an answer answers: the user message it records, when it landed
    after later turns, else the owner's message just before it."""
    conversation_id = str(message.get("conversation_id") or "")
    requested = message_metadata(message).get(ANSWER_REQUEST_MESSAGE_KEY)
    if requested:
        asked = owned_conversation_message(
            user_id=user.id, conversation_id=conversation_id, message_id=str(requested)
        )
        if asked is not None and asked.role == "user":
            return question_text(asked.content)
    if api_state.supabase_gateway is not None:
        created_at = message.get("created_at")
        stamp = (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else str(created_at)
        )
        earlier = api_state.supabase_gateway.question_before_message(
            user_id=user.id, conversation_id=conversation_id, created_at=stamp
        )
        return question_before(message, [earlier]) if earlier is not None else None
    messages = [
        item.model_dump(mode="python")
        for item in api_state.store.messages.get(conversation_id, [])
    ]
    return question_before(message, messages)


def _answer_decisions(user: User, message_ids: Sequence[str]) -> dict[str, DecisionNote]:
    if not message_ids:
        return {}
    if api_state.supabase_gateway is not None:
        return api_state.supabase_gateway.current_decisions_for_attachments(
            user_id=user.id, artifact_ids=[], message_ids=list(message_ids)
        )
    wanted = set(message_ids)
    current: dict[str, DecisionNote] = {}
    for decision in api_state.store.decision_notes.values():
        if api_state.store.decision_note_owners.get(decision.id) != user.id:
            continue
        key = decision.source_message_id
        if key is None or key not in wanted:
            continue
        held = current.get(key)
        if held is None or (decision.updated_at, decision.id) > (
            held.updated_at,
            held.id,
        ):
            current[key] = decision
    return current


def _computed_symbol_rows(
    user: User, scope: OwnerScope, guest_conversation_id: str | None
) -> list[Mapping[str, Any]]:
    if api_state.supabase_gateway is not None:
        return api_state.supabase_gateway.computed_answer_rows_for_symbols(
            user_id=user.id, scope=scope, conversation_id=guest_conversation_id
        )
    rows: list[Mapping[str, Any]] = []
    for conversation_id, messages in api_state.store.messages.items():
        if api_state.store.conversation_owners.get(
            conversation_id
        ) != user.id or not memory_conversation_in_scope(conversation_id, scope):
            continue
        if guest_conversation_id is not None and conversation_id != guest_conversation_id:
            continue
        conversation = api_state.store.conversations.get(conversation_id)
        if conversation is not None and getattr(conversation, "deleted_at", None):
            continue
        for message in messages:
            row = message.model_dump(mode="python")
            if row.get("role") == "assistant" and computed_symbols(row):
                rows.append(row)
    return rows


def answer_decision_lookup(user: User, message_id: str) -> Mapping[str, Any] | None:
    decision = _answer_decisions(user, [message_id]).get(message_id)
    if decision is None:
        return None
    return current_answer_decision(message_id, [decision.model_dump(mode="python")])

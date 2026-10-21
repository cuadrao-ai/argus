from __future__ import annotations

from bisect import bisect_left
from collections import OrderedDict, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Iterable, Iterator, Mapping

from argus.api.chat.legacy_onboarding_markers import is_legacy_onboarding_marker
from argus.api.memory_ledger_index import (
    MemoryLedgerIndex,
    build_memory_ledger_index,
)
from argus.api.memory_ownership import memory_object_visible
from argus.api.memory_search_postings import (
    BoundedRankedCandidates,
    RankedCandidateCursor,
    RankedGroups,
    RankedPosting,
    bounded_ranked_candidate_indexes,
    build_ranked_postings,
    indexes_by_group,
    posting_candidate_might_match,
    ranked_groups,
)
from argus.api.schemas import SearchAssetRollup, User
from argus.api.search_utils import score_search_item, search_rank_key
from argus.domain.conversation_recall import (
    conversation_has_untaken_suggestion,
    project_asset_rollup,
    valid_next_experiments_metadata,
)
from argus.domain.owner_scope import OwnerScope, holds
from argus.domain.search_text import (
    normalize_search_symbol,
    normalize_search_text,
    search_has_indexable_token,
    search_text_matches_query,
)
from argus.domain.store import AlphaStore

_MEMORY_MATCH_OVERSAMPLE = 10
_MEMORY_MATCH_LIMIT_MAX = 1_010
_SOURCE_LAYERS = (
    "conversation",
    "message",
    "run",
    "idea",
    "evidence",
    "decision",
)


@dataclass(frozen=True)
class MemorySearchSnapshot:
    conversations: list[dict[str, Any]]
    runs: list[dict[str, Any]]
    ideas: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    asset_rollup: SearchAssetRollup | None
    ledger_counts: dict[str, int] | None


@dataclass(frozen=True)
class _Candidate:
    conversation_id: str
    source_id: str
    activity: datetime
    text: str


@dataclass(frozen=True)
class _ConversationQueryMatch:
    conversation_id: str
    candidate: _Candidate
    layer: str
    layer_rank: int
    score: int
    symbol_exact_match: bool
    match_count: int = 1


@dataclass(frozen=True)
class _MemorySearchIndex:
    revision: int
    conversations: dict[str, dict[str, Any]]
    recent_conversation_ids: tuple[str, ...]
    runs_by_conversation: dict[str, list[dict[str, Any]]]
    ideas_by_conversation: dict[str, list[dict[str, Any]]]
    evidence_by_conversation: dict[str, list[dict[str, Any]]]
    decisions_by_conversation: dict[str, list[dict[str, Any]]]
    messages_by_id: dict[str, dict[str, Any]]
    candidates_by_layer: dict[str, tuple[_Candidate, ...]]
    postings_by_layer: dict[str, dict[str, RankedPosting]]
    candidate_indexes_by_layer_and_conversation: dict[
        str,
        dict[str, tuple[int, ...]],
    ]
    all_conversation_ids: RankedGroups
    conversation_ids_by_title: dict[str, RankedGroups]
    conversation_ids_by_symbol: dict[str, RankedGroups]
    conversation_ids_by_symbol_tier: dict[
        str,
        dict[tuple[bool, bool], RankedGroups],
    ]
    conversation_ids_by_decision_state: dict[str, RankedGroups]
    asset_symbols: tuple[str, ...]
    asset_rollups_by_symbol: dict[str, SearchAssetRollup]
    conversation_activity_by_id: dict[str, datetime]
    conversation_symbols_by_id: dict[str, frozenset[str]]
    ledger_index: MemoryLedgerIndex


@dataclass
class _MemorySearchIndexCacheEntry:
    index: _MemorySearchIndex
    active_readers: int = 0
    retired: bool = False


_INDEX_CACHE_MAX_ENTRIES = 8
_INDEX_CACHE: OrderedDict[
    tuple[int, str, OwnerScope],
    _MemorySearchIndexCacheEntry,
] = OrderedDict()
_INDEX_CACHE_LOCK = RLock()


def bounded_memory_search_snapshot(
    *,
    store: AlphaStore,
    user: User,
    scope: OwnerScope,
    query: str,
    source_limit: int,
    include_conversation_rows: bool,
    cursor_updated_at: datetime | None = None,
    cursor_id: str | None = None,
    decision_state: str | None = None,
    include_ledger_groups: bool = False,
    guest_conversation_id: str | None = None,
    conversation_ids: Iterable[str] | None = None,
) -> MemorySearchSnapshot:
    """Read a bounded query page from a revision-keyed, non-durable index."""
    with _memory_search_index(store=store, user=user, scope=scope) as index:
        return _bounded_memory_search_snapshot_for_index(
            index=index,
            query=query,
            source_limit=source_limit,
            include_conversation_rows=include_conversation_rows,
            cursor_updated_at=cursor_updated_at,
            cursor_id=cursor_id,
            decision_state=decision_state,
            include_ledger_groups=include_ledger_groups,
            guest_conversation_id=guest_conversation_id,
            conversation_ids=conversation_ids,
        )


def _bounded_memory_search_snapshot_for_index(
    *,
    index: _MemorySearchIndex,
    query: str,
    source_limit: int,
    include_conversation_rows: bool,
    cursor_updated_at: datetime | None = None,
    cursor_id: str | None = None,
    decision_state: str | None = None,
    include_ledger_groups: bool = False,
    guest_conversation_id: str | None = None,
    conversation_ids: Iterable[str] | None = None,
) -> MemorySearchSnapshot:
    if source_limit < 1:
        raise ValueError("Memory search source limit must be positive.")
    requested_conversation_ids = tuple(
        dict.fromkeys(str(value) for value in (conversation_ids or ()))
    )
    if len(requested_conversation_ids) > 50:
        raise ValueError("Visible conversation recall accepts at most 50 ids.")
    if len(requested_conversation_ids) > source_limit:
        raise ValueError("Visible conversation recall exceeds its source limit.")
    candidate_limit = min(
        max(source_limit * _MEMORY_MATCH_OVERSAMPLE, _MEMORY_MATCH_OVERSAMPLE),
        _MEMORY_MATCH_LIMIT_MAX,
    )
    eligible_groups = index.all_conversation_ids
    if decision_state is not None:
        eligible_groups = index.conversation_ids_by_decision_state.get(
            decision_state,
            ranked_groups(()),
        )
    if guest_conversation_id is not None:
        eligible_groups = ranked_groups(
            (guest_conversation_id,)
            if guest_conversation_id in eligible_groups.members
            else ()
        )
    eligible_conversation_ids = eligible_groups.members
    symbol_query = normalize_search_symbol(query)
    resolved_symbol = _resolve_asset_symbol(index, query=query)
    exact_symbol = (
        symbol_query
        if symbol_query is not None and symbol_query in index.conversation_ids_by_symbol
        else None
    )

    selected_conversation_ids: set[str] = set()
    selected_message_ids: set[str] = set()
    selected_query_matches: dict[str, _ConversationQueryMatch] = {}
    if requested_conversation_ids:
        selected_conversation_ids.update(
            conversation_id
            for conversation_id in requested_conversation_ids
            if conversation_id in eligible_conversation_ids
        )
    elif include_conversation_rows:
        if query:
            if search_has_indexable_token(query):
                selected_query_matches = _query_conversation_window(
                    index,
                    query=query,
                    candidate_limit=candidate_limit,
                    eligible_groups=eligible_groups,
                    eligible_conversation_ids=eligible_conversation_ids,
                    cursor_updated_at=cursor_updated_at,
                    cursor_id=cursor_id,
                )
            elif exact_symbol is not None:
                selected_query_matches = _symbol_query_window(
                    index,
                    query=query,
                    symbol=exact_symbol,
                    candidate_limit=candidate_limit,
                    eligible_conversation_ids=eligible_conversation_ids,
                    cursor_updated_at=cursor_updated_at,
                    cursor_id=cursor_id,
                )
            selected_conversation_ids.update(selected_query_matches)
            selected_message_ids.update(
                match.candidate.source_id
                for match in selected_query_matches.values()
                if match.layer == "message"
            )
        else:
            selected_conversation_ids.update(
                _recent_conversation_window(
                    index,
                    candidate_limit=candidate_limit,
                    eligible_conversation_ids=eligible_conversation_ids,
                    cursor_updated_at=cursor_updated_at,
                    cursor_id=cursor_id,
                )
            )

    ledger_counts = (
        (
            _symbol_ledger_counts(
                index,
                symbol=exact_symbol,
                eligible_conversation_id=guest_conversation_id,
            )
            if exact_symbol is not None
            and query
            and not search_has_indexable_token(query)
            else _ledger_counts(
                index,
                query=query,
                eligible_conversation_id=guest_conversation_id,
            )
        )
        if include_ledger_groups
        else None
    )

    return MemorySearchSnapshot(
        conversations=[
            _conversation_with_query_match(
                index.conversations[conversation_id],
                selected_query_matches.get(conversation_id),
            )
            for conversation_id in selected_conversation_ids
            if conversation_id in index.conversations
        ],
        runs=[
            row
            for conversation_id in selected_conversation_ids
            for row in index.runs_by_conversation.get(conversation_id, [])
        ],
        ideas=[
            row
            for conversation_id in selected_conversation_ids
            for row in index.ideas_by_conversation.get(conversation_id, [])
        ],
        evidence=[
            row
            for conversation_id in selected_conversation_ids
            for row in index.evidence_by_conversation.get(conversation_id, [])
        ],
        decisions=[
            row
            for conversation_id in selected_conversation_ids
            for row in index.decisions_by_conversation.get(conversation_id, [])
        ],
        messages=[
            message
            for message_id, message in index.messages_by_id.items()
            if message_id in selected_message_ids
            or (
                str(message.get("conversation_id") or "") in selected_conversation_ids
                and message.get("role") == "assistant"
                and (
                    str((message.get("metadata") or {}).get("result_run_id") or "")
                    or str((message.get("metadata") or {}).get("latest_run_id") or "")
                )
            )
        ],
        asset_rollup=(
            index.asset_rollups_by_symbol.get(resolved_symbol)
            if resolved_symbol is not None
            else None
        ),
        ledger_counts=ledger_counts,
    )


@contextmanager
def _memory_search_index(
    *,
    store: AlphaStore,
    user: User,
    scope: OwnerScope,
) -> Iterator[_MemorySearchIndex]:
    cache_key = (id(store), user.id, scope)
    with _INDEX_CACHE_LOCK:
        entry = _INDEX_CACHE.get(cache_key)
        if entry is not None and entry.index.revision == store.search_revision:
            _INDEX_CACHE.move_to_end(cache_key)
        else:
            stale_entry = _INDEX_CACHE.pop(cache_key, None)
            if stale_entry is not None:
                _retire_memory_search_index(stale_entry)
            entry = _MemorySearchIndexCacheEntry(
                index=_build_memory_search_index(store=store, user=user, scope=scope),
            )
            _INDEX_CACHE[cache_key] = entry
            while len(_INDEX_CACHE) > _INDEX_CACHE_MAX_ENTRIES:
                _, evicted_entry = _INDEX_CACHE.popitem(last=False)
                _retire_memory_search_index(evicted_entry)
        entry.active_readers += 1
    try:
        yield entry.index
    finally:
        with _INDEX_CACHE_LOCK:
            entry.active_readers -= 1
            if entry.retired and entry.active_readers == 0:
                entry.index.ledger_index.close()


def _retire_memory_search_index(entry: _MemorySearchIndexCacheEntry) -> None:
    entry.retired = True
    if entry.active_readers == 0:
        entry.index.ledger_index.close()


def _build_memory_search_index(
    *,
    store: AlphaStore,
    user: User,
    scope: OwnerScope,
) -> _MemorySearchIndex:
    """Rebuild only when canonical memory changes, never for each keystroke."""
    revision = store.search_revision
    with store.conversation_message_lock:
        conversation_refs = [
            conversation
            for conversation in store.conversations.values()
            if memory_object_visible(
                owner_map=store.conversation_owners,
                object_id=conversation.id,
                user_id=user.id,
            )
            and holds(scope, store.conversation_spaces.get(conversation.id))
            and conversation.deleted_at is None
        ]
        visible_conversation_ids = {
            str(conversation.id) for conversation in conversation_refs
        }
        message_refs = [
            message
            for conversation_id, conversation_messages in store.messages.items()
            if conversation_id in visible_conversation_ids
            for message in conversation_messages
            if (
                message.role == "user"
                or (
                    message.role == "assistant"
                    and (
                        valid_next_experiments_metadata(
                            getattr(message, "metadata", None)
                        )
                        or bool(
                            (getattr(message, "metadata", None) or {}).get(
                                "result_run_id"
                            )
                        )
                        or bool(
                            (getattr(message, "metadata", None) or {}).get(
                                "latest_run_id"
                            )
                        )
                    )
                )
            )
            and not is_legacy_onboarding_marker(message.content)
        ]
    with store.backtest_finalization_lock:
        run_refs = [
            run
            for run in store.backtest_runs.values()
            if memory_object_visible(
                owner_map=store.backtest_run_owners,
                object_id=run.id,
                user_id=user.id,
            )
            and str(run.conversation_id or "") in visible_conversation_ids
        ]
        idea_refs = [
            idea
            for idea in store.ideas.values()
            if memory_object_visible(
                owner_map=store.idea_owners,
                object_id=idea.id,
                user_id=user.id,
            )
            and str(idea.source_conversation_id or "") in visible_conversation_ids
        ]
        evidence_refs = [
            artifact
            for artifact in store.evidence_artifacts.values()
            if memory_object_visible(
                owner_map=store.evidence_artifact_owners,
                object_id=artifact.id,
                user_id=user.id,
            )
            and str(artifact.source_conversation_id or "") in visible_conversation_ids
        ]
        decision_refs = [
            decision
            for decision in store.decision_notes.values()
            if memory_object_visible(
                owner_map=store.decision_note_owners,
                object_id=decision.id,
                user_id=user.id,
            )
            and str(decision.source_conversation_id or "") in visible_conversation_ids
        ]

    conversations = [row.model_dump() for row in conversation_refs]
    messages = [row.model_dump() for row in message_refs]
    runs = [row.model_dump() for row in run_refs]
    ideas = [row.model_dump() for row in idea_refs]
    evidence = [row.model_dump() for row in evidence_refs]
    decisions = [row.model_dump() for row in decision_refs]
    _attach_decision_message_text(
        store,
        decisions=decisions,
        visible_conversation_ids=visible_conversation_ids,
    )
    evidence_by_id = {str(row["id"]): row for row in evidence}
    runs_by_conversation = _group_rows(runs, field="conversation_id")
    ideas_by_conversation = _group_rows(ideas, field="source_conversation_id")
    evidence_by_conversation = _group_rows(
        evidence,
        field="source_conversation_id",
    )
    decisions_by_conversation = _group_rows(
        decisions,
        field="source_conversation_id",
    )
    messages_by_conversation = _group_rows(messages, field="conversation_id")
    for conversation in conversations:
        conversation_id = str(conversation["id"])
        latest_run = max(
            (
                run
                for run in runs_by_conversation.get(conversation_id, [])
                if run.get("status") == "completed"
            ),
            key=_mapping_activity,
            default=None,
        )
        conversation["_recall_summary"] = {
            "latest_suggestion_untaken": conversation_has_untaken_suggestion(
                run=latest_run,
                messages=messages_by_conversation.get(conversation_id, []),
            )
        }

    candidates: dict[str, list[_Candidate]] = {layer: [] for layer in _SOURCE_LAYERS}
    for conversation in conversations:
        conversation_id = str(conversation["id"])
        for suffix, text in (
            ("title", conversation.get("title")),
            ("preview", conversation.get("last_message_preview")),
        ):
            if text:
                candidates["conversation"].append(
                    _candidate(
                        conversation_id=conversation_id,
                        source_id=f"{conversation_id}:{suffix}",
                        row=conversation,
                        text=str(text),
                    )
                )
    for message in messages:
        if message.get("role") != "user":
            continue
        candidates["message"].append(
            _candidate(
                conversation_id=str(message["conversation_id"]),
                source_id=str(message["id"]),
                row=message,
                text=str(message["content"]),
            )
        )
    for run in runs:
        if run.get("status") == "completed":
            candidates["run"].append(
                _candidate(
                    conversation_id=str(run["conversation_id"]),
                    source_id=str(run["id"]),
                    row=run,
                    text=_run_search_text(run),
                )
            )
    for idea in ideas:
        candidates["idea"].append(
            _candidate(
                conversation_id=str(idea["source_conversation_id"]),
                source_id=str(idea["id"]),
                row=idea,
                text=f"{idea.get('title') or ''} {idea.get('summary') or ''}",
            )
        )
    for artifact in evidence:
        candidates["evidence"].append(
            _candidate(
                conversation_id=str(artifact["source_conversation_id"]),
                source_id=str(artifact["id"]),
                row=artifact,
                text=f"{artifact.get('title') or ''} {artifact.get('digest') or ''}",
            )
        )
    for decision in decisions:
        artifact = evidence_by_id.get(str(decision.get("evidence_artifact_id") or ""))
        candidates["decision"].append(
            _candidate(
                conversation_id=str(decision["source_conversation_id"]),
                source_id=str(decision["id"]),
                row=decision,
                text=_decision_search_text(decision, evidence=artifact),
            )
        )

    run_by_id = {str(row["id"]): row for row in runs}
    evidence_by_run = _group_rows(evidence, field="source_run_id")
    decisions_by_evidence = _group_rows(decisions, field="evidence_artifact_id")
    asset_run_ids: defaultdict[str, set[str]] = defaultdict(set)
    for run in sorted(runs, key=_mapping_activity, reverse=True):
        if run.get("status") != "completed":
            continue
        for symbol in run.get("symbols") or []:
            normalized = normalize_search_symbol(symbol)
            if normalized is None:
                continue
            asset_run_ids[normalized].add(str(run["id"]))
    asset_rollups_by_symbol: dict[str, SearchAssetRollup] = {}
    for symbol, run_ids in asset_run_ids.items():
        asset_runs = sorted(
            (run_by_id[run_id] for run_id in run_ids if run_id in run_by_id),
            key=_mapping_activity,
            reverse=True,
        )
        asset_evidence = [
            artifact for run_id in run_ids for artifact in evidence_by_run.get(run_id, [])
        ]
        asset_evidence_ids = {str(artifact["id"]) for artifact in asset_evidence}
        rollup = project_asset_rollup(
            runs=asset_runs,
            evidence=asset_evidence,
            decisions=[
                decision
                for evidence_id in asset_evidence_ids
                for decision in decisions_by_evidence.get(evidence_id, [])
            ],
            query=symbol,
        )
        if rollup is not None:
            asset_rollups_by_symbol[symbol] = rollup
    decision_states_by_conversation: defaultdict[str, set[str]] = defaultdict(set)
    for decision in decisions:
        conversation_id = decision.get("source_conversation_id")
        decision_state = decision.get("decision_state")
        if conversation_id is not None and decision_state is not None:
            decision_states_by_conversation[str(conversation_id)].add(str(decision_state))
    conversation_activity_by_id = {
        conversation_id: max(
            _mapping_activity(row)
            for row in (
                conversation,
                *runs_by_conversation.get(conversation_id, []),
                *ideas_by_conversation.get(conversation_id, []),
                *evidence_by_conversation.get(conversation_id, []),
                *decisions_by_conversation.get(conversation_id, []),
            )
        )
        for conversation_id, conversation in (
            (str(row["id"]), row) for row in conversations
        )
    }
    conversation_symbols_by_id = {
        conversation_id: frozenset(
            normalized_symbol
            for run in runs_by_conversation.get(conversation_id, [])
            if run.get("status", "completed") == "completed"
            for symbol in _run_symbols(run)
            if (normalized_symbol := normalize_search_symbol(symbol)) is not None
        )
        for conversation_id in conversation_activity_by_id
    }
    conversations_by_id = {str(row["id"]): row for row in conversations}
    sorted_candidates = {
        layer: tuple(
            sorted(
                rows,
                key=lambda row: (
                    int(bool(conversations_by_id[row.conversation_id].get("pinned"))),
                    conversation_activity_by_id[row.conversation_id],
                    row.activity,
                    row.conversation_id,
                    row.source_id,
                ),
                reverse=True,
            )
        )
        for layer, rows in candidates.items()
    }
    postings = {
        layer: build_ranked_postings(
            (candidate.conversation_id, candidate.text) for candidate in rows
        )
        for layer, rows in sorted_candidates.items()
    }
    candidate_indexes_by_layer_and_conversation = {
        layer: indexes_by_group(candidate.conversation_id for candidate in rows)
        for layer, rows in sorted_candidates.items()
    }
    ledger_index = build_memory_ledger_index(
        candidates=(
            (candidate.conversation_id, candidate.text)
            for layer in _SOURCE_LAYERS
            for candidate in sorted_candidates[layer]
        ),
        decision_states_by_conversation=decision_states_by_conversation,
    )
    conversation_ids_in_seek_order = tuple(
        str(row["id"])
        for row in sorted(
            conversations,
            key=lambda row: _recent_conversation_seek_key(
                conversation_id=str(row["id"]),
                conversation=row,
                activity=conversation_activity_by_id[str(row["id"])],
            ),
            reverse=True,
        )
    )
    conversation_ids_by_title: defaultdict[str, list[str]] = defaultdict(list)
    conversation_ids_by_symbol: defaultdict[str, list[str]] = defaultdict(list)
    conversation_ids_by_symbol_tier: defaultdict[
        str,
        defaultdict[tuple[bool, bool], list[str]],
    ] = defaultdict(lambda: defaultdict(list))
    conversation_ids_by_decision_state: defaultdict[str, list[str]] = defaultdict(list)
    for conversation_id in conversation_ids_in_seek_order:
        normalized_title = normalize_search_text(
            conversations_by_id[conversation_id].get("title") or ""
        )
        if normalized_title:
            conversation_ids_by_title[normalized_title].append(conversation_id)
        for symbol in conversation_symbols_by_id[conversation_id]:
            conversation_ids_by_symbol[symbol].append(conversation_id)
            conversation_ids_by_symbol_tier[symbol][
                (
                    bool(conversations_by_id[conversation_id].get("pinned")),
                    normalized_title == normalize_search_text(symbol),
                )
            ].append(conversation_id)
        for state in decision_states_by_conversation.get(conversation_id, set()):
            conversation_ids_by_decision_state[state].append(conversation_id)

    return _MemorySearchIndex(
        revision=revision,
        conversations=conversations_by_id,
        recent_conversation_ids=conversation_ids_in_seek_order,
        runs_by_conversation=runs_by_conversation,
        ideas_by_conversation=ideas_by_conversation,
        evidence_by_conversation=evidence_by_conversation,
        decisions_by_conversation=decisions_by_conversation,
        messages_by_id={str(row["id"]): row for row in messages},
        candidates_by_layer=sorted_candidates,
        postings_by_layer=postings,
        candidate_indexes_by_layer_and_conversation=(
            candidate_indexes_by_layer_and_conversation
        ),
        all_conversation_ids=ranked_groups(conversation_ids_in_seek_order),
        conversation_ids_by_title={
            title: ranked_groups(conversation_ids)
            for title, conversation_ids in conversation_ids_by_title.items()
        },
        conversation_ids_by_symbol={
            symbol: ranked_groups(conversation_ids)
            for symbol, conversation_ids in conversation_ids_by_symbol.items()
        },
        conversation_ids_by_symbol_tier={
            symbol: {
                tier: ranked_groups(conversation_ids)
                for tier, conversation_ids in tier_groups.items()
            }
            for symbol, tier_groups in conversation_ids_by_symbol_tier.items()
        },
        conversation_ids_by_decision_state={
            state: ranked_groups(conversation_ids)
            for state, conversation_ids in conversation_ids_by_decision_state.items()
        },
        asset_symbols=tuple(sorted(asset_rollups_by_symbol)),
        asset_rollups_by_symbol=asset_rollups_by_symbol,
        conversation_activity_by_id=conversation_activity_by_id,
        conversation_symbols_by_id=conversation_symbols_by_id,
        ledger_index=ledger_index,
    )


def _bounded_matching_candidate_indexes(
    index: _MemorySearchIndex,
    *,
    layer: str,
    layer_rank: int,
    query: str,
    candidate_limit: int,
    eligible_groups: RankedGroups,
    cursor: RankedCandidateCursor | None,
    cursor_group_match: Callable[[str], RankedCandidateCursor | None],
) -> BoundedRankedCandidates:
    """Return a bounded final-rank candidate window for presentation only."""
    normalized_query = normalize_search_text(query)
    empty_groups = ranked_groups(())
    exact_title_groups = index.conversation_ids_by_title.get(
        normalized_query,
        empty_groups,
    )
    symbol_query = normalize_search_symbol(query)
    symbol_groups = (
        index.conversation_ids_by_symbol.get(symbol_query, empty_groups)
        if symbol_query is not None
        else empty_groups
    )
    candidates = index.candidates_by_layer[layer]
    return bounded_ranked_candidate_indexes(
        query=query,
        postings=index.postings_by_layer[layer],
        candidate_indexes_by_group=(
            index.candidate_indexes_by_layer_and_conversation[layer]
        ),
        exact_title_groups=exact_title_groups,
        symbol_groups=symbol_groups,
        eligible_groups=eligible_groups,
        cursor=cursor,
        layer_rank=layer_rank,
        candidate_limit=candidate_limit,
        group_id_for_index=lambda candidate_index: candidates[
            candidate_index
        ].conversation_id,
        group_is_pinned=lambda conversation_id: bool(
            index.conversations[conversation_id].get("pinned")
        ),
        group_activity=lambda conversation_id: (
            index.conversation_activity_by_id[conversation_id]
        ),
        candidate_matches=lambda candidate_index: search_text_matches_query(
            query=query,
            text=candidates[candidate_index].text,
        ),
        cursor_group_match=cursor_group_match,
        rank_key=lambda candidate_index: _candidate_query_rank_key(
            index,
            candidates[candidate_index],
            layer_rank=layer_rank,
            query=query,
        ),
    )


def _candidate_query_rank_key(
    index: _MemorySearchIndex,
    candidate: _Candidate,
    *,
    layer_rank: int,
    query: str,
) -> tuple[
    tuple[int, int, int, int, datetime, int, int, str],
    datetime,
    str,
    str,
]:
    conversation = index.conversations[candidate.conversation_id]
    return (
        search_rank_key(
            score=score_search_item(
                query=query,
                title=str(conversation.get("title") or "Untitled conversation"),
                matched_text=candidate.text,
                pinned=bool(conversation.get("pinned")),
                symbol_exact_match=(
                    normalize_search_symbol(query)
                    in index.conversation_symbols_by_id[candidate.conversation_id]
                ),
                match_layer_rank=layer_rank,
            ),
            kind="conversation",
            updated_at=index.conversation_activity_by_id[candidate.conversation_id],
            item_id=candidate.conversation_id,
        ),
        candidate.activity,
        candidate.text,
        candidate.source_id,
    )


def _query_conversation_window(
    index: _MemorySearchIndex,
    *,
    query: str,
    candidate_limit: int,
    eligible_groups: RankedGroups,
    eligible_conversation_ids: frozenset[str],
    cursor_updated_at: datetime | None,
    cursor_id: str | None,
) -> dict[str, _ConversationQueryMatch]:
    valid_cursor_id = (
        cursor_id
        if (
            cursor_id is not None
            and cursor_updated_at is not None
            and index.conversation_activity_by_id.get(cursor_id) == cursor_updated_at
        )
        else None
    )
    matches = _conversation_query_matches(
        index,
        query=query,
        candidate_limit=candidate_limit,
        eligible_groups=eligible_groups,
        eligible_conversation_ids=eligible_conversation_ids,
        cursor_id=valid_cursor_id,
    )
    ordered = sorted(
        matches.values(),
        key=lambda match: _conversation_query_rank_key(index, match),
        reverse=True,
    )
    selected = ordered[:candidate_limit]
    if cursor_updated_at is not None and valid_cursor_id is not None:
        cursor_match = matches.get(valid_cursor_id)
        if cursor_match is not None:
            cursor_key = _conversation_query_rank_key(index, cursor_match)
            cursor_window = [
                match
                for match in ordered
                if _conversation_query_rank_key(index, match) <= cursor_key
            ][:candidate_limit]
            selected.extend(cursor_window)
    return {match.conversation_id: match for match in selected}


def _conversation_query_matches(
    index: _MemorySearchIndex,
    *,
    query: str,
    candidate_limit: int,
    eligible_groups: RankedGroups,
    eligible_conversation_ids: frozenset[str],
    cursor_id: str | None,
) -> dict[str, _ConversationQueryMatch]:
    matches: dict[str, _ConversationQueryMatch] = {}
    layer_match_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    global_cursor_matches: dict[
        str,
        tuple[_ConversationQueryMatch, int] | None,
    ] = {}
    global_cursor_ranks: dict[str, RankedCandidateCursor | None] = {}

    def cursor_group_match(group_id: str) -> RankedCandidateCursor | None:
        if group_id in global_cursor_ranks:
            return global_cursor_ranks[group_id]
        if group_id not in global_cursor_matches:
            global_cursor_matches[group_id] = _exact_group_query_match(
                index,
                query=query,
                conversation_id=group_id,
            )
        exact_group_match = global_cursor_matches[group_id]
        if exact_group_match is None:
            global_cursor_ranks[group_id] = None
            return None
        resolved = _ranked_candidate_cursor(
            index,
            query=query,
            conversation_id=group_id,
            exact_group_match=exact_group_match,
        )
        global_cursor_ranks[group_id] = resolved
        return resolved

    cursor = (
        cursor_group_match(cursor_id)
        if cursor_id is not None and cursor_id in eligible_conversation_ids
        else None
    )

    for layer_rank, layer in enumerate(_SOURCE_LAYERS, start=1):
        rows = index.candidates_by_layer[layer]
        bounded = _bounded_matching_candidate_indexes(
            index,
            layer=layer,
            layer_rank=layer_rank,
            query=query,
            candidate_limit=candidate_limit,
            eligible_groups=eligible_groups,
            cursor=cursor,
            cursor_group_match=cursor_group_match,
        )
        for candidate_index in bounded.indexes:
            candidate = rows[candidate_index]
            conversation_id = candidate.conversation_id
            if conversation_id not in eligible_conversation_ids:
                continue
            layer_match_counts[(conversation_id, layer)] = bounded.match_counts[
                conversation_id
            ]
            proposed = _query_match_from_candidate(
                index,
                query=query,
                candidate=candidate,
                layer=layer,
                layer_rank=layer_rank,
            )
            current = matches.get(conversation_id)
            if current is None or _winning_match_key(proposed) > _winning_match_key(
                current
            ):
                matches[conversation_id] = proposed
    counted_matches = {
        conversation_id: replace(
            match,
            match_count=layer_match_counts[(conversation_id, match.layer)],
        )
        for conversation_id, match in matches.items()
    }
    if cursor is None:
        return counted_matches
    for conversation_id in tuple(counted_matches):
        cached = global_cursor_matches.get(conversation_id)
        if cached is not None:
            counted_matches[conversation_id] = cached[0]
    return counted_matches


def _ranked_candidate_cursor(
    index: _MemorySearchIndex,
    *,
    query: str,
    conversation_id: str,
    exact_group_match: tuple[_ConversationQueryMatch, int],
) -> RankedCandidateCursor:
    winning_match, winning_index = exact_group_match
    conversation = index.conversations[conversation_id]
    normalized_query = normalize_search_text(query)
    symbol_query = normalize_search_symbol(query)
    return RankedCandidateCursor(
        group_id=conversation_id,
        best_index=winning_index,
        match_count=winning_match.match_count,
        maximum_key=_candidate_query_rank_key(
            index,
            winning_match.candidate,
            layer_rank=winning_match.layer_rank,
            query=query,
        ),
        tier=(
            bool(conversation.get("pinned")),
            normalized_query
            == normalize_search_text(
                conversation.get("title") or "Untitled conversation"
            ),
            symbol_query in index.conversation_symbols_by_id[conversation_id],
        ),
        activity=index.conversation_activity_by_id[conversation_id],
        layer_rank=winning_match.layer_rank,
    )


def _exact_group_query_match(
    index: _MemorySearchIndex,
    *,
    query: str,
    conversation_id: str,
) -> tuple[_ConversationQueryMatch, int] | None:
    winning_match: _ConversationQueryMatch | None = None
    winning_index: int | None = None
    for layer_rank, layer in enumerate(_SOURCE_LAYERS, start=1):
        candidates = index.candidates_by_layer[layer]
        layer_match: _ConversationQueryMatch | None = None
        layer_index: int | None = None
        layer_count = 0
        for candidate_index in index.candidate_indexes_by_layer_and_conversation[
            layer
        ].get(
            conversation_id,
            (),
        ):
            candidate = candidates[candidate_index]
            if not posting_candidate_might_match(
                query=query,
                postings=index.postings_by_layer[layer],
                candidate_index=candidate_index,
            ):
                continue
            if not search_text_matches_query(query=query, text=candidate.text):
                continue
            layer_count += 1
            proposed = _query_match_from_candidate(
                index,
                query=query,
                candidate=candidate,
                layer=layer,
                layer_rank=layer_rank,
            )
            if layer_match is None or _winning_match_key(proposed) > _winning_match_key(
                layer_match
            ):
                layer_match = proposed
                layer_index = candidate_index
        if layer_match is not None and (
            winning_match is None
            or _winning_match_key(layer_match) > _winning_match_key(winning_match)
        ):
            winning_match = replace(layer_match, match_count=layer_count)
            winning_index = layer_index
    if winning_match is None or winning_index is None:
        return None
    return winning_match, winning_index


def _query_match_from_candidate(
    index: _MemorySearchIndex,
    *,
    query: str,
    candidate: _Candidate,
    layer: str,
    layer_rank: int,
) -> _ConversationQueryMatch:
    conversation_id = candidate.conversation_id
    conversation = index.conversations[conversation_id]
    symbol_exact_match = (
        normalize_search_symbol(query)
        in index.conversation_symbols_by_id[conversation_id]
    )
    return _ConversationQueryMatch(
        conversation_id=conversation_id,
        candidate=candidate,
        layer=layer,
        layer_rank=layer_rank,
        score=score_search_item(
            query=query,
            title=str(conversation.get("title") or "Untitled conversation"),
            matched_text=candidate.text,
            pinned=bool(conversation.get("pinned")),
            symbol_exact_match=symbol_exact_match,
            match_layer_rank=layer_rank,
        ),
        symbol_exact_match=symbol_exact_match,
    )


def _winning_match_key(
    match: _ConversationQueryMatch,
) -> tuple[int, int, datetime, str]:
    return (
        match.score,
        match.layer_rank,
        match.candidate.activity,
        match.candidate.text,
    )


def _conversation_query_rank_key(
    index: _MemorySearchIndex,
    match: _ConversationQueryMatch,
) -> tuple[int, int, int, int, datetime, int, int, str]:
    return search_rank_key(
        score=match.score,
        kind="conversation",
        updated_at=index.conversation_activity_by_id[match.conversation_id],
        item_id=match.conversation_id,
    )


def _conversation_with_query_match(
    conversation: dict[str, Any],
    match: _ConversationQueryMatch | None,
) -> dict[str, Any]:
    if match is None:
        return conversation
    projected = dict(conversation)
    projected["_recall_match"] = {
        "matched_text": match.candidate.text,
        "layer": match.layer,
        "layer_rank": match.layer_rank,
        "activity_at": match.candidate.activity,
        "symbol_exact_match": match.symbol_exact_match,
        "message_id": (match.candidate.source_id if match.layer == "message" else None),
        "match_count": match.match_count,
    }
    return projected


def _recent_conversation_window(
    index: _MemorySearchIndex,
    *,
    candidate_limit: int,
    eligible_conversation_ids: set[str],
    cursor_updated_at: datetime | None,
    cursor_id: str | None,
) -> list[str]:
    eligible = [
        conversation_id
        for conversation_id in index.recent_conversation_ids
        if conversation_id in eligible_conversation_ids
    ]
    if cursor_updated_at is None or cursor_id is None:
        return eligible[:candidate_limit]
    cursor_conversation = index.conversations.get(cursor_id)
    cursor_activity = index.conversation_activity_by_id.get(cursor_id)
    if (
        cursor_conversation is None
        or cursor_activity is None
        or cursor_activity != cursor_updated_at
    ):
        return eligible[:candidate_limit]
    cursor_key = _recent_conversation_seek_key(
        conversation_id=cursor_id,
        conversation=cursor_conversation,
        activity=cursor_activity,
    )
    cursor_window = [
        conversation_id
        for conversation_id in eligible
        if _recent_conversation_seek_key(
            conversation_id=conversation_id,
            conversation=index.conversations[conversation_id],
            activity=index.conversation_activity_by_id[conversation_id],
        )
        <= cursor_key
    ][:candidate_limit]
    return list(dict.fromkeys((*eligible[:candidate_limit], *cursor_window)))


def _symbol_query_window(
    index: _MemorySearchIndex,
    *,
    query: str,
    symbol: str,
    candidate_limit: int,
    eligible_conversation_ids: frozenset[str],
    cursor_updated_at: datetime | None,
    cursor_id: str | None,
) -> dict[str, _ConversationQueryMatch]:
    symbol_groups = index.conversation_ids_by_symbol.get(
        symbol,
        ranked_groups(()),
    )
    eligible_symbol_ids = symbol_groups.members & eligible_conversation_ids
    tier_groups = index.conversation_ids_by_symbol_tier.get(symbol, {})
    tiers = ((True, True), (True, False), (False, True), (False, False))

    def rank_key(
        conversation_id: str,
    ) -> tuple[int, int, int, int, datetime, int, int, str]:
        conversation = index.conversations[conversation_id]
        layer_rank = _SOURCE_LAYERS.index("run") + 1
        return search_rank_key(
            score=score_search_item(
                query=query,
                title=str(conversation.get("title") or "Untitled conversation"),
                # Every id in this symbol index has a completed run containing
                # the exact symbol, so the matched-text contribution is fixed.
                matched_text=symbol,
                pinned=bool(conversation.get("pinned")),
                symbol_exact_match=True,
                match_layer_rank=layer_rank,
            ),
            kind="conversation",
            updated_at=index.conversation_activity_by_id[conversation_id],
            item_id=conversation_id,
        )

    def collect_ids(
        *,
        maximum_key: tuple[int, int, int, int, datetime, int, int, str] | None = None,
        cursor_tier: tuple[bool, bool] | None = None,
    ) -> list[str]:
        selected: list[str] = []
        cursor_tier_index = tiers.index(cursor_tier) if cursor_tier is not None else 0
        for tier_index, tier in enumerate(tiers):
            if tier_index < cursor_tier_index:
                continue
            remaining = candidate_limit - len(selected)
            if remaining <= 0:
                break
            groups = tier_groups.get(tier, ranked_groups(()))
            start = 0
            if cursor_tier == tier and cursor_id is not None:
                start = groups.positions.get(cursor_id, 0)
                while (
                    start > 0
                    and index.conversation_activity_by_id[groups.ordered[start - 1]]
                    == cursor_updated_at
                ):
                    start -= 1

            tier_ids: list[str] = []
            cutoff_activity: datetime | None = None
            for conversation_id in groups.ordered[start:]:
                if conversation_id not in eligible_symbol_ids:
                    continue
                activity = index.conversation_activity_by_id[conversation_id]
                if cutoff_activity is not None and activity < cutoff_activity:
                    break
                if maximum_key is not None and rank_key(conversation_id) > maximum_key:
                    continue
                tier_ids.append(conversation_id)
                if len(tier_ids) >= remaining:
                    cutoff_activity = activity
            tier_ids.sort(key=rank_key, reverse=True)
            selected.extend(tier_ids[:remaining])
        return selected

    selected_ids = collect_ids()
    if (
        cursor_updated_at is not None
        and cursor_id is not None
        and cursor_id in eligible_symbol_ids
        and index.conversation_activity_by_id.get(cursor_id) == cursor_updated_at
    ):
        conversation = index.conversations[cursor_id]
        cursor_tier = (
            bool(conversation.get("pinned")),
            normalize_search_text(conversation.get("title") or "Untitled conversation")
            == normalize_search_text(query),
        )
        selected_ids.extend(
            collect_ids(
                maximum_key=rank_key(cursor_id),
                cursor_tier=cursor_tier,
            )
        )

    selected: dict[str, _ConversationQueryMatch] = {}
    for conversation_id in dict.fromkeys(selected_ids):
        match = _symbol_query_match(
            index,
            query=query,
            symbol=symbol,
            conversation_id=conversation_id,
        )
        if match is not None:
            selected[conversation_id] = match
    return selected


def _symbol_query_match(
    index: _MemorySearchIndex,
    *,
    query: str,
    symbol: str,
    conversation_id: str,
) -> _ConversationQueryMatch | None:
    matching_runs = [
        row
        for row in index.runs_by_conversation.get(conversation_id, ())
        if row.get("status", "completed") == "completed"
        and any(normalize_search_symbol(value) == symbol for value in _run_symbols(row))
    ]
    run = max(
        matching_runs,
        key=lambda row: (
            _mapping_activity(row),
            str(row.get("id") or ""),
        ),
        default=None,
    )
    if run is None:
        return None
    candidate = _candidate(
        conversation_id=conversation_id,
        source_id=str(run.get("id") or conversation_id),
        row=run,
        text=_run_search_text(run),
    )
    layer_rank = _SOURCE_LAYERS.index("run") + 1
    conversation = index.conversations[conversation_id]
    return _ConversationQueryMatch(
        conversation_id=conversation_id,
        candidate=candidate,
        layer="run",
        layer_rank=layer_rank,
        score=score_search_item(
            query=query,
            title=str(conversation.get("title") or "Untitled conversation"),
            matched_text=candidate.text,
            pinned=bool(conversation.get("pinned")),
            symbol_exact_match=True,
            match_layer_rank=layer_rank,
        ),
        symbol_exact_match=True,
        match_count=len(matching_runs),
    )


def _recent_conversation_seek_key(
    *,
    conversation_id: str,
    conversation: Mapping[str, Any],
    activity: datetime,
) -> tuple[int, datetime, str]:
    return (
        int(bool(conversation.get("pinned"))),
        activity,
        conversation_id,
    )


def _ledger_counts(
    index: _MemorySearchIndex,
    *,
    query: str,
    eligible_conversation_id: str | None,
) -> dict[str, int]:
    return index.ledger_index.counts(
        query=query,
        eligible_conversation_id=eligible_conversation_id,
    )


def _symbol_ledger_counts(
    index: _MemorySearchIndex,
    *,
    symbol: str,
    eligible_conversation_id: str | None,
) -> dict[str, int]:
    symbol_conversations = index.conversation_ids_by_symbol.get(
        symbol,
        ranked_groups(()),
    ).members
    if eligible_conversation_id is not None:
        symbol_conversations &= frozenset((eligible_conversation_id,))
    return {
        state: len(
            symbol_conversations
            & index.conversation_ids_by_decision_state.get(
                state,
                ranked_groups(()),
            ).members
        )
        for state in ("promising", "watching", "rejected", "revisit_later")
    }


def _resolve_asset_symbol(
    index: _MemorySearchIndex,
    *,
    query: str,
) -> str | None:
    normalized_query = normalize_search_symbol(query)
    if normalized_query is None:
        return None
    match_index = bisect_left(index.asset_symbols, normalized_query)
    if match_index >= len(index.asset_symbols):
        return None
    first_match = index.asset_symbols[match_index]
    if not first_match.startswith(normalized_query):
        return None
    if first_match == normalized_query:
        return normalized_query
    next_index = match_index + 1
    if next_index < len(index.asset_symbols) and index.asset_symbols[
        next_index
    ].startswith(normalized_query):
        return None
    return first_match


def _candidate(
    *,
    conversation_id: str,
    source_id: str,
    row: Mapping[str, Any],
    text: str,
) -> _Candidate:
    return _Candidate(
        conversation_id=conversation_id,
        source_id=source_id,
        activity=_mapping_activity(row),
        text=text,
    )


def _mapping_activity(row: Mapping[str, Any]) -> datetime:
    value = row.get("updated_at") or row.get("created_at")
    return (
        value
        if isinstance(value, datetime)
        else datetime.min.replace(tzinfo=timezone.utc)
    )


def _group_rows(
    rows: Iterable[dict[str, Any]],
    *,
    field: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(field)
        if value is not None:
            grouped[str(value)].append(row)
    return dict(grouped)


def _run_search_text(run: Mapping[str, Any]) -> str:
    card = run.get("conversation_result_card")
    card = card if isinstance(card, Mapping) else {}
    config = run.get("config_snapshot")
    config = config if isinstance(config, Mapping) else {}
    return " ".join(
        value
        for value in (
            str(card.get("title") or ""),
            " ".join(str(symbol) for symbol in run.get("symbols") or []),
            str(config.get("template") or card.get("strategy_label") or ""),
        )
        if value
    )


def _run_symbols(run: Mapping[str, Any]) -> list[str]:
    symbols = run.get("symbols")
    if isinstance(symbols, list) and symbols:
        return [str(symbol) for symbol in symbols]
    card = run.get("conversation_result_card")
    card_symbols = card.get("symbols") if isinstance(card, Mapping) else None
    return (
        [str(symbol) for symbol in card_symbols] if isinstance(card_symbols, list) else []
    )


def _decision_search_text(
    decision: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any] | None,
) -> str:
    return " ".join(
        value
        for value in (
            str(decision.get("note") or ""),
            str(decision.get("decision_state") or ""),
            str(evidence.get("title") or "") if evidence is not None else "",
            str(evidence.get("digest") or "") if evidence is not None else "",
            str(decision.get("attachment_text") or ""),
        )
        if value
    )


def _attach_decision_message_text(
    store: Any,
    *,
    decisions: list[dict[str, Any]],
    visible_conversation_ids: set[str],
) -> None:
    """A computed-answer decision recalls through the answer it attaches to,
    the way a backtest decision recalls through its evidence title and digest.
    The text rides the decision row as ``attachment_text``."""
    wanted = {
        str(message_id)
        for decision in decisions
        if (message_id := decision.get("source_message_id"))
    }
    if not wanted:
        return
    with store.conversation_message_lock:
        text_by_message_id = {
            message.id: message.content
            for conversation_id in visible_conversation_ids
            for message in store.messages.get(conversation_id, [])
            if message.id in wanted and message.role == "assistant"
        }
    for decision in decisions:
        message_id = decision.get("source_message_id")
        if message_id is not None and message_id in text_by_message_id:
            decision["attachment_text"] = text_by_message_id[message_id]

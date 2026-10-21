from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from argus.api import state as api_state
from argus.api.memory_search_candidates import bounded_memory_search_snapshot
from argus.api.schemas import (
    DecisionActionAvailability,
    SearchAssetRollup,
    SearchItem,
    User,
)
from argus.domain.conversation_recall import (
    project_conversation_recall,
)
from argus.domain.owner_scope import PERSONAL, OwnerScope

ScoredSearchItem = tuple[int, SearchItem]


@dataclass(frozen=True)
class MemorySearchRead:
    scored_items: list[ScoredSearchItem]
    asset_rollup: SearchAssetRollup | None
    ledger_counts: dict[str, int] | None = None


def memory_search_read(
    *,
    user: User,
    scope: OwnerScope,
    query: str,
    source_limit: int,
    decision_action_availability: DecisionActionAvailability | None = "available",
    include_conversation_rows: bool = True,
    cursor_updated_at: datetime | None = None,
    cursor_id: str | None = None,
    decision_state: str | None = None,
    include_ledger_groups: bool = False,
    guest_conversation_id: str | None = None,
    conversation_ids: Iterable[str] | None = None,
) -> MemorySearchRead:
    """Project owned memory records through the same conversation read model."""
    snapshot = bounded_memory_search_snapshot(
        store=api_state.store,
        user=user,
        scope=scope,
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
    return MemorySearchRead(
        scored_items=(
            _project_rows(
                conversations=snapshot.conversations,
                runs=snapshot.runs,
                ideas=snapshot.ideas,
                evidence=snapshot.evidence,
                decisions=snapshot.decisions,
                messages=snapshot.messages,
                query=query,
                decision_action_availability=decision_action_availability,
                language=user.language,
            )
            if include_conversation_rows
            else []
        ),
        asset_rollup=snapshot.asset_rollup,
        ledger_counts=snapshot.ledger_counts,
    )


def scored_memory_search_items(*, user: User, query: str) -> list[ScoredSearchItem]:
    return memory_search_read(
        user=user,
        scope=PERSONAL,
        query=query,
        source_limit=101,
    ).scored_items


def scored_supabase_search_items(
    *,
    raw: dict[str, list[dict[str, object]]],
    query: str,
    decision_action_availability: DecisionActionAvailability | None = "available",
    language: str = "en",
) -> list[ScoredSearchItem]:
    """Adapt persistent and injected-gateway rows to the shared projector."""
    if "conversation_recall" in raw:
        rows = raw["conversation_recall"]
        projected: list[ScoredSearchItem] = []
        for row in rows:
            raw_item = row.get("item")
            if not isinstance(raw_item, dict):
                continue
            normalized_item = dict(raw_item)
            raw_dossier = normalized_item.get("dossier")
            if isinstance(raw_dossier, dict):
                normalized_dossier = dict(raw_dossier)
                raw_actions = normalized_dossier.get("actions")
                if isinstance(raw_actions, list):
                    normalized_dossier["actions"] = [
                        {
                            **action,
                            "availability": decision_action_availability,
                        }
                        if isinstance(action, dict) and action.get("type") == "decision"
                        else action
                        for action in raw_actions
                        if not (
                            isinstance(action, dict)
                            and action.get("type") == "decision"
                            and decision_action_availability is None
                        )
                    ]
                normalized_item["dossier"] = normalized_dossier
            item = SearchItem.model_validate(normalized_item)
            projected.append((int(row.get("score") or 0), item))
        return projected

    conversations: dict[str, dict[str, Any]] = {
        str(row["id"]): dict(row)
        for row in raw.get("conversations", [])
        if row.get("id") is not None and row.get("deleted_at") is None
    }
    runs = [dict(row) for row in raw.get("runs", [])]
    ideas = [dict(row) for row in raw.get("ideas", [])]
    evidence = [dict(row) for row in raw.get("evidence", [])]
    decisions = [dict(row) for row in raw.get("decisions", [])]
    messages = [dict(row) for row in raw.get("messages", [])]

    # Compatibility for narrow injected gateways: production readers include
    # canonical conversations, while test doubles may return only a matched
    # child record.
    for row in (*runs, *ideas, *evidence, *decisions):
        conversation_id = _conversation_id(row)
        if conversation_id is None or conversation_id in conversations:
            continue
        conversations[conversation_id] = {
            "id": conversation_id,
            "title": row.get("title")
            or row.get("artifact_title")
            or row.get("artifact_digest")
            or "Untitled conversation",
            "last_message_preview": None,
            "pinned": False,
            "updated_at": row.get("updated_at") or row.get("created_at"),
        }

    # The old bounded reader hydrates a decision's evidence inline.
    for decision in decisions:
        artifact_id = decision.get("evidence_artifact_id")
        if artifact_id is None or any(
            str(row.get("id")) == str(artifact_id) for row in evidence
        ):
            continue
        evidence.append(
            {
                "id": artifact_id,
                "source_conversation_id": decision.get("source_conversation_id"),
                "source_run_id": decision.get("source_run_id"),
                "title": decision.get("artifact_title"),
                "digest": decision.get("artifact_digest"),
                "payload": decision.get("artifact_payload"),
                "created_at": decision.get("created_at"),
                "updated_at": decision.get("updated_at"),
            }
        )

    return _project_rows(
        conversations=list(conversations.values()),
        runs=runs,
        ideas=ideas,
        evidence=evidence,
        decisions=decisions,
        messages=messages,
        query=query,
        decision_action_availability=decision_action_availability,
        language=language,
    )


def _project_rows(
    *,
    conversations: list[Mapping[str, Any]],
    runs: list[Mapping[str, Any]],
    ideas: list[Mapping[str, Any]],
    evidence: list[Mapping[str, Any]],
    decisions: list[Mapping[str, Any]],
    messages: list[Mapping[str, Any]],
    query: str,
    decision_action_availability: DecisionActionAvailability | None = "available",
    language: str = "en",
) -> list[ScoredSearchItem]:
    runs_by_conversation = _group_by_conversation(runs)
    ideas_by_conversation = _group_by_conversation(ideas)
    evidence_by_conversation = _group_by_conversation(evidence)
    decisions_by_conversation = _group_by_conversation(decisions)
    messages_by_conversation = _group_by_conversation(messages)
    projected: list[ScoredSearchItem] = []
    for conversation in conversations:
        conversation_id = str(conversation.get("id") or "")
        item = project_conversation_recall(
            conversation=conversation,
            runs=runs_by_conversation[conversation_id],
            ideas=ideas_by_conversation[conversation_id],
            evidence=evidence_by_conversation[conversation_id],
            decisions=decisions_by_conversation[conversation_id],
            messages=messages_by_conversation[conversation_id],
            query=query,
            decision_action_availability=decision_action_availability,
            language=language,
        )
        if item is not None:
            projected.append(item)
    return projected


def _group_by_conversation(
    rows: list[Mapping[str, Any]],
) -> defaultdict[str, list[Mapping[str, Any]]]:
    grouped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        conversation_id = _conversation_id(row)
        if conversation_id is not None:
            grouped[conversation_id].append(row)
    return grouped


def _conversation_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("conversation_id") or row.get("source_conversation_id")
    return str(value) if value is not None else None

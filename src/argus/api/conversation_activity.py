"""Persistence-neutral conversation activity projection and read mutations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, cast

from argus.api import state as api_state
from argus.api.conversation_previews import latest_conversation_messages
from argus.api.schemas import ConversationActivity
from argus.domain.conversation_activity import (
    ActivityReadState,
    ActivitySource,
    Boundary,
    CursorSource,
    SourceKind,
    project_conversation_activity,
    terminal_attention_status,
)
from argus.domain.job_settlement import (
    JOB_RESULT_HYDRATEABLE,
    RESEARCH_OPERATION_SCOPE,
    evaluate,
)
from argus.domain.store import AlphaStore, utcnow

_EVIDENCE_IDENTITY_KEYS = ("evidence_artifact_id", "idea_id", "idea_version_id")

_MAX_CONVERSATIONS = 100


class ConversationActivityConflict(ValueError):
    """A valid cursor does not identify an eligible terminal source anymore."""


def _as_datetime(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        time_separator = max(normalized.find("T"), normalized.find(" "))
        hour_separator = normalized.find(":", time_separator + 1)
        seconds_separator = normalized.find(":", hour_separator + 1)
        if time_separator >= 0 and hour_separator >= 0 and seconds_separator >= 0:
            offset_start = len(normalized)
            for marker in ("+", "-"):
                candidate = normalized.find(marker, seconds_separator + 1)
                if candidate != -1:
                    offset_start = min(offset_start, candidate)
            fraction_start = normalized.find(".", seconds_separator + 1, offset_start)
            if fraction_start != -1:
                fraction = normalized[fraction_start + 1 : offset_start]
                if fraction.isdigit() and 1 <= len(fraction) <= 6:
                    normalized = (
                        f"{normalized[: fraction_start + 1]}"
                        f"{fraction.ljust(6, '0')}"
                        f"{normalized[offset_start:]}"
                    )
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise RuntimeError(f"Invalid conversation activity {field}.") from exc
    else:
        raise RuntimeError(f"Missing conversation activity {field}.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"Naive conversation activity {field}.")
    return parsed.astimezone(timezone.utc)


def source_from_row(raw: Mapping[str, Any]) -> ActivitySource:
    """Decode one persisted activity row; Postgres proofs read through here."""

    source_kind = raw.get("source_kind")
    if source_kind not in {"chat_turn", "backtest_job"}:
        raise RuntimeError("Invalid conversation activity source kind.")
    return ActivitySource(
        conversation_id=str(raw.get("conversation_id") or ""),
        source_kind=cast(SourceKind, source_kind),
        source_id=str(raw.get("source_id") or ""),
        status=str(raw.get("status") or ""),
        occurred_at=_as_datetime(raw.get("occurred_at"), field="occurred_at"),
        stage_outcome=(
            str(raw["stage_outcome"])
            if isinstance(raw.get("stage_outcome"), str)
            else None
        ),
        result_hydrateable=raw.get("result_hydrateable") is True,
    )


def _read_state_from_row(raw: Mapping[str, Any] | None) -> ActivityReadState | None:
    if raw is None:
        return None
    occurred_at = raw.get("read_through_occurred_at")
    source_kind = raw.get("read_through_source_kind")
    source_id = raw.get("read_through_source_id")
    boundary: Boundary | None = None
    if occurred_at is not None or source_kind is not None or source_id is not None:
        if source_kind not in {"chat_turn", "backtest_job"} or source_id is None:
            raise RuntimeError("Invalid conversation read boundary.")
        boundary = Boundary(
            source_kind=cast(SourceKind, source_kind),
            source_id=str(source_id),
            occurred_at=_as_datetime(occurred_at, field="read boundary"),
        )
    manual_unread_at = raw.get("manual_unread_at")
    return ActivityReadState(
        read_through=boundary,
        manual_unread_at=(
            _as_datetime(manual_unread_at, field="manual unread timestamp")
            if manual_unread_at is not None
            else None
        ),
    )


def _memory_result_hydrateable(
    store: AlphaStore,
    *,
    user_id: str,
    conversation_id: str,
    job: Mapping[str, Any],
) -> bool:
    # Memory twin of argus_private.backtest_job_result_hydrateable: the rule is
    # argus.domain.job_settlement.JOB_RESULT_HYDRATEABLE for both; this layer
    # only says how it observes each fact.
    return evaluate(
        JOB_RESULT_HYDRATEABLE,
        {
            "job_succeeded": lambda: job.get("status") == "succeeded",
            "run_result_readable": lambda: _memory_run_result_readable(
                store,
                user_id=user_id,
                conversation_id=conversation_id,
                result_run_id=job.get("result_run_id"),
            ),
            "research_scope": lambda: (
                job.get("operation_scope") == RESEARCH_OPERATION_SCOPE
            ),
            "research_result_message_present": lambda: (
                _memory_research_result_message_present(
                    store,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    job=job,
                )
            ),
        },
    )


def _memory_run_result_readable(
    store: AlphaStore,
    *,
    user_id: str,
    conversation_id: str,
    result_run_id: Any,
) -> bool:
    if not isinstance(result_run_id, str):
        return False
    run = store.backtest_runs.get(result_run_id)
    if run is None or store.backtest_run_owners.get(result_run_id) != user_id:
        return False
    if run.status != "completed" or run.conversation_id != conversation_id:
        return False
    card = run.conversation_result_card
    if not all(
        isinstance(card.get(key), str) and card[key] for key in _EVIDENCE_IDENTITY_KEYS
    ):
        return False
    artifact_id = str(card["evidence_artifact_id"])
    artifact = store.evidence_artifacts.get(artifact_id)
    return bool(
        artifact is not None
        and store.evidence_artifact_owners.get(artifact_id) == user_id
        and artifact.source_run_id == result_run_id
        and artifact.source_conversation_id == conversation_id
        and artifact.idea_id == card["idea_id"]
        and artifact.idea_version_id == card["idea_version_id"]
    )


def _memory_research_result_message_present(
    store: AlphaStore,
    *,
    user_id: str,
    conversation_id: str,
    job: Mapping[str, Any],
) -> bool:
    # The job owner's assistant message, in the job's conversation. Memory
    # messages carry no owner of their own; the conversation's owner is that
    # fact here, as messages.user_id is in SQL.
    metadata = job.get("execution_metadata")
    message_id = (
        metadata.get("research_result_message_id")
        if isinstance(metadata, Mapping)
        else None
    )
    if not isinstance(message_id, str) or not message_id:
        return False
    if store.conversation_owners.get(conversation_id) != user_id:
        return False
    return any(
        message.id == message_id and message.role == "assistant"
        for message in store.messages.get(conversation_id, [])
    )


def _memory_sources(
    store: AlphaStore,
    *,
    user_id: str,
    conversation_ids: set[str],
) -> list[ActivitySource]:
    messages_by_id = {
        message.id: message
        for conversation_id in conversation_ids
        for message in store.messages.get(conversation_id, [])
    }
    sources: list[ActivitySource] = []
    for row in store.chat_turn_lifecycles.values():
        conversation_id = str(row.get("conversation_id") or "")
        if row.get("user_id") != user_id or conversation_id not in conversation_ids:
            continue
        status = str(row.get("status") or "")
        if status not in {
            "accepted",
            "running",
            "completed",
            "recoverable_failed",
            "abandoned",
            "reconciled",
        }:
            continue
        occurred_at = row.get("updated_at")
        if status in {"completed", "recoverable_failed", "abandoned", "reconciled"}:
            occurred_at = row.get("terminal_at")
        projected_status = status
        if status == "reconciled":
            projected_status = f"reconciled:{row.get('reconciled_outcome') or ''}"
        assistant = messages_by_id.get(str(row.get("assistant_message_id") or ""))
        metadata = assistant.metadata if assistant is not None else None
        stage_outcome = (
            str(metadata["agent_runtime_stage_outcome"])
            if isinstance(metadata, dict)
            and isinstance(metadata.get("agent_runtime_stage_outcome"), str)
            else None
        )
        sources.append(
            ActivitySource(
                conversation_id=conversation_id,
                source_kind="chat_turn",
                source_id=str(row.get("turn_id") or ""),
                status=projected_status,
                occurred_at=_as_datetime(occurred_at, field="turn timestamp"),
                stage_outcome=stage_outcome,
            )
        )
    for row in store.backtest_jobs.values():
        conversation_id = str(row.get("conversation_id") or "")
        if row.get("user_id") != user_id or conversation_id not in conversation_ids:
            continue
        status = str(row.get("status") or "")
        if status not in {
            "queued",
            "running",
            "succeeded",
            "failed",
            "canceled",
            "expired",
        }:
            continue
        result_hydrateable = _memory_result_hydrateable(
            store,
            user_id=user_id,
            conversation_id=conversation_id,
            job=row,
        )
        occurred_at = row.get("updated_at")
        if status in {"failed", "canceled", "expired"} or result_hydrateable:
            occurred_at = row.get("finished_at") or occurred_at
        sources.append(
            ActivitySource(
                conversation_id=conversation_id,
                source_kind="backtest_job",
                source_id=str(row.get("id") or ""),
                status=status,
                occurred_at=_as_datetime(occurred_at, field="job timestamp"),
                result_hydrateable=result_hydrateable,
            )
        )
    return sources


def _bounded_ids(conversation_ids: Sequence[str]) -> list[str]:
    distinct = list(dict.fromkeys(conversation_ids))
    if len(distinct) > _MAX_CONVERSATIONS:
        raise ValueError("At most 100 conversations may be projected at once.")
    return distinct


@dataclass(frozen=True)
class ConversationActivityService:
    """Select memory or Supabase truth behind one projection contract."""

    def project(
        self,
        *,
        user_id: str,
        conversation_ids: Sequence[str],
        reconcile: bool = False,
    ) -> dict[str, ConversationActivity]:
        requested = _bounded_ids(conversation_ids)
        if not requested:
            return {}
        gateway = api_state.supabase_gateway
        if gateway is not None:
            if reconcile:
                gateway.reconcile_conversation_activity_turns(
                    user_id=user_id,
                    conversation_ids=requested,
                )
            rows = gateway.read_conversation_activity_batch(
                user_id=user_id,
                conversation_ids=requested,
            )
            latest = latest_conversation_messages(
                user_id=user_id, conversation_ids=requested
            )
            indexed = {str(row.get("conversation_id") or ""): row for row in rows}
            if set(indexed) != set(requested):
                raise RuntimeError("Conversation activity projection was incomplete.")
            result: dict[str, ConversationActivity] = {}
            for conversation_id in requested:
                row = indexed[conversation_id]
                raw_sources = row.get("sources")
                if not isinstance(raw_sources, list):
                    raise RuntimeError("Invalid conversation activity sources.")
                raw_read_state = row.get("read_state")
                if raw_read_state is not None and not isinstance(raw_read_state, dict):
                    raise RuntimeError("Invalid conversation read state.")
                result[conversation_id] = project_conversation_activity(
                    conversation_id=conversation_id,
                    sources=[
                        source_from_row(raw)
                        for raw in raw_sources
                        if isinstance(raw, dict)
                    ],
                    read_state=_read_state_from_row(raw_read_state),
                ).model_copy(
                    update={
                        "latest_message_id": latest.get(conversation_id, {}).get("id")
                    }
                )
            return result

        store = api_state.store
        requested_set = set(requested)
        sources = _memory_sources(
            store,
            user_id=user_id,
            conversation_ids=requested_set,
        )
        latest = latest_conversation_messages(user_id=user_id, conversation_ids=requested)
        return {
            conversation_id: project_conversation_activity(
                conversation_id=conversation_id,
                sources=sources,
                read_state=_read_state_from_row(
                    store.conversation_read_states.get((user_id, conversation_id))
                ),
            ).model_copy(
                update={"latest_message_id": latest.get(conversation_id, {}).get("id")}
            )
            for conversation_id in requested
        }

    def mutate(
        self,
        *,
        user_id: str,
        conversation_id: str,
        action: Literal["mark_unread", "mark_read"],
        cursor_source: CursorSource | None,
    ) -> ConversationActivity:
        gateway = api_state.supabase_gateway
        if gateway is not None:
            outcome = gateway.mutate_conversation_activity_read_state(
                user_id=user_id,
                conversation_id=conversation_id,
                action=action,
                source_kind=(cursor_source.source_kind if cursor_source else None),
                source_id=(cursor_source.source_id if cursor_source else None),
            ).get("outcome")
            if outcome == "missing":
                raise KeyError(conversation_id)
            if outcome == "conflict":
                raise ConversationActivityConflict(conversation_id)
            if outcome not in {"applied", "noop"}:
                raise RuntimeError("Conversation activity mutation was rejected.")
            return self.project(
                user_id=user_id,
                conversation_ids=[conversation_id],
            )[conversation_id]

        store = api_state.store
        key = (user_id, conversation_id)
        with (
            store.conversation_read_state_lock,
            store.chat_turn_lifecycle_lock,
            store.backtest_admission_lock,
            store.backtest_finalization_lock,
        ):
            raw_state = dict(store.conversation_read_states.get(key) or {})
            if action == "mark_unread":
                if raw_state.get("manual_unread_at") is None:
                    raw_state["manual_unread_at"] = utcnow()
                store.conversation_read_states[key] = raw_state
            elif action == "mark_read":
                if cursor_source is not None:
                    sources = _memory_sources(
                        store,
                        user_id=user_id,
                        conversation_ids={conversation_id},
                    )
                    source = next(
                        (
                            item
                            for item in sources
                            if item.source_kind == cursor_source.source_kind
                            and item.source_id == cursor_source.source_id
                            and terminal_attention_status(item) is not None
                        ),
                        None,
                    )
                    if source is None:
                        raise ConversationActivityConflict(conversation_id)
                    current = _read_state_from_row(raw_state)
                    if (
                        current is None
                        or current.read_through is None
                        or current.read_through < source.boundary
                    ):
                        raw_state.update(
                            {
                                "read_through_occurred_at": source.occurred_at,
                                "read_through_source_kind": source.source_kind,
                                "read_through_source_id": source.source_id,
                            }
                        )
                raw_state["manual_unread_at"] = None
                if raw_state:
                    store.conversation_read_states[key] = raw_state
            else:
                raise RuntimeError("Conversation activity mutation was rejected.")
        return self.project(
            user_id=user_id,
            conversation_ids=[conversation_id],
        )[conversation_id]


conversation_activity_service = ConversationActivityService()

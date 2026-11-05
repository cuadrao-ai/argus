from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, TypeVar
from uuid import uuid4

from argus.api.schemas import (
    Collection,
    Conversation,
    DecisionNote,
    EvidenceArtifact,
    Idea,
    IdeaVersion,
    Message,
    Strategy,
    User,
)

_Key = TypeVar("_Key")
_Value = TypeVar("_Value")


class _SearchRevisionDict(dict[_Key, _Value]):
    """Dict that invalidates the non-durable memory recall projection."""

    def __init__(
        self,
        values: dict[_Key, _Value],
        *,
        on_change: Callable[[], None],
    ) -> None:
        super().__init__(values)
        self._on_change = on_change

    def __setitem__(self, key: _Key, value: _Value) -> None:
        super().__setitem__(key, value)
        self._on_change()

    def __delitem__(self, key: _Key) -> None:
        super().__delitem__(key)
        self._on_change()

    def clear(self) -> None:
        super().clear()
        self._on_change()

    def pop(self, key: _Key, default: Any = None) -> Any:
        existed = key in self
        value = super().pop(key, default)
        if existed:
            self._on_change()
        return value

    def popitem(self) -> tuple[_Key, _Value]:
        value = super().popitem()
        self._on_change()
        return value

    def setdefault(self, key: _Key, default: _Value | None = None) -> _Value:
        existed = key in self
        value = super().setdefault(key, default)  # type: ignore[arg-type]
        if not existed:
            self._on_change()
        return value

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._on_change()

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[_Key, _Value]:
        return deepcopy(dict(self), memo)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AlphaStore:
    users: dict[str, User] = field(default_factory=dict)
    conversations: dict[str, Conversation] = field(default_factory=dict)
    conversation_owners: dict[str, str] = field(default_factory=dict)
    # A Business conversation's space id; a conversation absent here is Personal.
    conversation_spaces: dict[str, str] = field(default_factory=dict)
    messages: dict[str, list[Message]] = field(default_factory=dict)
    strategies: dict[str, Strategy] = field(default_factory=dict)
    strategy_owners: dict[str, str] = field(default_factory=dict)
    collections: dict[str, Collection] = field(default_factory=dict)
    collection_owners: dict[str, str] = field(default_factory=dict)
    collection_strategies: dict[str, set[str]] = field(default_factory=dict)
    backtest_runs: dict[str, Any] = field(default_factory=dict)
    backtest_run_owners: dict[str, str] = field(default_factory=dict)
    backtest_finalizations: dict[tuple[str, str], str] = field(default_factory=dict)
    backtest_finalization_lock: Any = field(
        default_factory=RLock,
        repr=False,
        compare=False,
    )
    conversation_message_lock: Any = field(
        default_factory=RLock,
        repr=False,
        compare=False,
    )
    chat_turn_lifecycles: dict[str, dict[str, Any]] = field(default_factory=dict)
    chat_turn_lifecycle_lock: Any = field(
        default_factory=RLock,
        repr=False,
        compare=False,
    )
    conversation_read_states: dict[tuple[str, str], dict[str, Any]] = field(
        default_factory=dict
    )
    conversation_read_state_lock: Any = field(
        default_factory=RLock,
        repr=False,
        compare=False,
    )
    ideas: dict[str, Idea] = field(default_factory=dict)
    idea_owners: dict[str, str] = field(default_factory=dict)
    idea_versions: dict[str, IdeaVersion] = field(default_factory=dict)
    idea_version_owners: dict[str, str] = field(default_factory=dict)
    evidence_artifacts: dict[str, EvidenceArtifact] = field(default_factory=dict)
    evidence_artifact_owners: dict[str, str] = field(default_factory=dict)
    decision_notes: dict[str, DecisionNote] = field(default_factory=dict)
    decision_note_owners: dict[str, str] = field(default_factory=dict)
    public_excerpt_snapshots: dict[str, Any] = field(default_factory=dict)
    idempotency: dict[tuple[str, str, str], Any] = field(default_factory=dict)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    visitor_usage_counters: dict[tuple[str, str, str], dict[str, Any]] = field(
        default_factory=dict
    )
    usage_counters: dict[tuple[str, str, str], dict[str, Any]] = field(
        default_factory=dict
    )
    # (subject_key, milestone) -> claim expiry. Twin of guest_funnel_milestones.
    guest_funnel_milestones: dict[tuple[str, str], datetime] = field(default_factory=dict)
    backtest_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    backtest_job_reservations: dict[tuple[str, str, str], str] = field(
        default_factory=dict
    )
    search_revision: int = field(default=0, repr=False, compare=False)
    backtest_admission_lock: Any = field(
        default_factory=RLock,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "conversations",
            "conversation_owners",
            "conversation_spaces",
            "messages",
            "backtest_runs",
            "backtest_run_owners",
            "ideas",
            "idea_owners",
            "evidence_artifacts",
            "evidence_artifact_owners",
            "decision_notes",
            "decision_note_owners",
        ):
            values = getattr(self, field_name)
            setattr(
                self,
                field_name,
                _SearchRevisionDict(values, on_change=self.bump_search_revision),
            )

    def bump_search_revision(self) -> None:
        self.search_revision += 1

    def reset(self) -> None:
        self.users.clear()
        self.conversations.clear()
        self.conversation_owners.clear()
        self.conversation_spaces.clear()
        self.messages.clear()
        self.strategies.clear()
        self.strategy_owners.clear()
        self.collections.clear()
        self.collection_owners.clear()
        self.collection_strategies.clear()
        self.backtest_runs.clear()
        self.backtest_run_owners.clear()
        self.backtest_finalizations.clear()
        self.chat_turn_lifecycles.clear()
        self.conversation_read_states.clear()
        self.ideas.clear()
        self.idea_owners.clear()
        self.idea_versions.clear()
        self.idea_version_owners.clear()
        self.evidence_artifacts.clear()
        self.evidence_artifact_owners.clear()
        self.decision_notes.clear()
        self.decision_note_owners.clear()
        self.public_excerpt_snapshots.clear()
        self.idempotency.clear()
        self.feedback.clear()
        self.usage_counters.clear()
        self.visitor_usage_counters.clear()
        self.guest_funnel_milestones.clear()
        self.backtest_jobs.clear()
        self.backtest_job_reservations.clear()

    def get_or_create_dev_user(self) -> User:
        user_id = "00000000-0000-0000-0000-000000000001"
        if user_id not in self.users:
            now = utcnow()
            self.users[user_id] = User(
                id=user_id,
                email="developer@argus.local",
                username="mock-developer",
                display_name="Mock Developer",
                language="en",
                locale="en-US",
                is_admin=True,
                created_at=now,
                updated_at=now,
            )
        return self.users[user_id]

    def new_id(self) -> str:
        return str(uuid4())

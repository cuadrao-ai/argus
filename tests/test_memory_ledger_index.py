from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from argus.api import memory_ledger_index, memory_search_candidates
from argus.api import state as api_state
from argus.api.memory_ledger_index import MemoryLedgerWorkLimitExceeded
from argus.api.schemas import Conversation, DecisionNote, DecisionState, Message
from argus.domain.owner_scope import PERSONAL


@pytest.fixture(autouse=True)
def _reset_memory_store() -> None:
    api_state.store.reset()


def _add_decided_messages(
    *,
    conversation_id: str,
    contents: tuple[str, ...],
    decision_state: DecisionState,
) -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)
    api_state.store.conversations[conversation_id] = Conversation(
        id=conversation_id,
        title=f"Unrelated {conversation_id}",
        created_at=now,
        updated_at=now,
        language="en",
    )
    api_state.store.conversation_owners[conversation_id] = user.id
    api_state.store.messages[conversation_id] = [
        Message(
            id=f"{conversation_id}-message-{index}",
            conversation_id=conversation_id,
            role="user",
            content=content,
            created_at=now,
            metadata={},
        )
        for index, content in enumerate(contents)
    ]
    decision_id = f"{conversation_id}-decision"
    api_state.store.decision_notes[decision_id] = DecisionNote(
        id=decision_id,
        idea_id=f"{conversation_id}-idea",
        idea_version_id=f"{conversation_id}-version",
        evidence_artifact_id=f"{conversation_id}-artifact",
        source_conversation_id=conversation_id,
        decision_state=decision_state,
        note="Separate judgment.",
        created_at=now,
        updated_at=now,
    )
    api_state.store.decision_note_owners[decision_id] = user.id


def test_memory_ledger_index_uses_fts5_and_excludes_undecided_candidates() -> None:
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(
            ("conversation-decided", "needle exact"),
            ("conversation-undecided", "needle exact"),
        ),
        decision_states_by_conversation={
            "conversation-decided": {"watching"},
        },
    )
    sql, parameters = memory_ledger_index._matching_counts_query(
        tokens=("needle",),
        fts_query='"needle"',
        eligible_conversation_id=None,
    )

    plan = index._connection.execute(
        f"EXPLAIN QUERY PLAN {sql}",
        parameters,
    ).fetchall()
    indexed_rows = index._connection.execute(
        "SELECT COUNT(*) FROM searchable_candidates"
    ).fetchone()

    assert indexed_rows == (1,)
    assert any(
        "SCAN searchable_candidates VIRTUAL TABLE INDEX" in str(row[3]) for row in plan
    )


def test_memory_ledger_index_serializes_shared_connection_queries() -> None:
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(("conversation-decided", "shared needle"),),
        decision_states_by_conversation={
            "conversation-decided": {"watching"},
        },
    )
    expected = {
        "promising": 0,
        "watching": 1,
        "rejected": 0,
        "revisit_later": 0,
    }

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(
            executor.map(
                lambda _: index.counts(
                    query="shared needle",
                    eligible_conversation_id=None,
                ),
                range(64),
            )
        )

    assert results == (expected,) * 64


def test_memory_ledger_index_close_releases_sqlite_connection() -> None:
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(("conversation-decided", "shared needle"),),
        decision_states_by_conversation={
            "conversation-decided": {"watching"},
        },
    )

    index.close()

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        index.counts(query="shared needle", eligible_conversation_id=None)


@pytest.mark.parametrize("query", ("broadanchor", "broadanchor zz"))
def test_memory_ledger_rejects_corpus_above_fixed_limit(
    query: str,
) -> None:
    candidate_count = memory_ledger_index.MEMORY_LEDGER_CANDIDATE_LIMIT + 1
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(
            (f"conversation-{candidate_index}", "broadanchor searchable text")
            for candidate_index in range(candidate_count)
        ),
        decision_states_by_conversation={
            f"conversation-{candidate_index}": {"watching"}
            for candidate_index in range(candidate_count)
        },
    )

    with pytest.raises(MemoryLedgerWorkLimitExceeded):
        index.counts(query=query, eligible_conversation_id=None)


def test_memory_ledger_rejects_over_limit_disjoint_corpus_before_fts() -> None:
    candidate_count = memory_ledger_index.MEMORY_LEDGER_CANDIDATE_LIMIT + 1
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(
            (
                f"conversation-{candidate_index}",
                "alpha only" if candidate_index % 2 == 0 else "beta only",
            )
            for candidate_index in range(candidate_count)
        ),
        decision_states_by_conversation={
            f"conversation-{candidate_index}": {"watching"}
            for candidate_index in range(candidate_count)
        },
    )

    assert index.counts(query="", eligible_conversation_id=None) == {
        "promising": 0,
        "watching": candidate_count,
        "rejected": 0,
        "revisit_later": 0,
    }
    index._connection.close()

    with pytest.raises(MemoryLedgerWorkLimitExceeded):
        index.counts(query="alpha beta", eligible_conversation_id=None)


def test_memory_ledger_accepts_exact_candidate_limit() -> None:
    candidate_count = memory_ledger_index.MEMORY_LEDGER_CANDIDATE_LIMIT
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(
            (f"conversation-{candidate_index}", "bounded needle")
            for candidate_index in range(candidate_count)
        ),
        decision_states_by_conversation={
            f"conversation-{candidate_index}": {"watching"}
            for candidate_index in range(candidate_count)
        },
    )

    assert index.counts(query="needle", eligible_conversation_id=None) == {
        "promising": 0,
        "watching": candidate_count,
        "rejected": 0,
        "revisit_later": 0,
    }


def test_memory_ledger_corpus_limit_ignores_ineligible_and_empty_candidates() -> None:
    candidate_limit = memory_ledger_index.MEMORY_LEDGER_CANDIDATE_LIMIT
    empty_ids = tuple(
        f"empty-conversation-{candidate_index}"
        for candidate_index in range(candidate_limit + 1)
    )

    def _candidates() -> Iterator[tuple[str, str]]:
        for candidate_index in range(candidate_limit + 1):
            yield (
                f"undecided-conversation-{candidate_index}",
                "undecided searchable text",
            )
        for conversation_id in empty_ids:
            yield conversation_id, "  "
        yield "eligible-conversation", "eligible needle"

    index = memory_ledger_index.build_memory_ledger_index(
        candidates=_candidates(),
        decision_states_by_conversation={
            **{conversation_id: {"watching"} for conversation_id in empty_ids},
            "eligible-conversation": {"promising"},
        },
    )

    assert index.counts(query="needle", eligible_conversation_id=None) == {
        "promising": 1,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }


def test_memory_ledger_registered_empty_counts_are_revision_precomputed() -> None:
    index = memory_ledger_index.build_memory_ledger_index(
        candidates=(("conversation-decided", "unused searchable text"),),
        decision_states_by_conversation={
            "conversation-decided": {"watching"},
        },
    )
    index._connection.close()

    assert index.counts(query="", eligible_conversation_id=None) == {
        "promising": 0,
        "watching": 1,
        "rejected": 0,
        "revisit_later": 0,
    }


def test_memory_ledger_counts_broad_matches_without_python_exact_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = api_state.store.get_or_create_dev_user()

    for index in range(5_000):
        _add_decided_messages(
            conversation_id=f"conversation-ledger-{index:04d}",
            contents=(f"Needle in distinct transcript {index}",),
            decision_state="watching",
        )

    def _fail_python_exact_scan(*, query: str, text: object) -> bool:
        raise AssertionError(
            f"ledger aggregation scanned Python candidate text for {query!r}"
        )

    monkeypatch.setattr(
        memory_search_candidates,
        "search_text_matches_query",
        _fail_python_exact_scan,
    )

    snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="needle",
        source_limit=1,
        include_conversation_rows=False,
        include_ledger_groups=True,
    )

    assert snapshot.ledger_counts == {
        "promising": 0,
        "watching": 5_000,
        "rejected": 0,
        "revisit_later": 0,
    }
    assert snapshot.conversations == []


def test_memory_ledger_counts_require_one_exact_candidate_and_dedupe() -> None:
    user = api_state.store.get_or_create_dev_user()
    _add_decided_messages(
        conversation_id="conversation-ledger-false-positive",
        contents=("abc bcd cde def",),
        decision_state="watching",
    )
    _add_decided_messages(
        conversation_id="conversation-ledger-split-tokens",
        contents=("alpha only", "beta only"),
        decision_state="promising",
    )
    _add_decided_messages(
        conversation_id="conversation-ledger-exact-tokens",
        contents=("alpha beta together", "repeat alpha beta together"),
        decision_state="rejected",
    )

    false_positive = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="abcdef",
        source_limit=1,
        include_conversation_rows=False,
        include_ledger_groups=True,
    )
    exact_candidate = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="alpha beta",
        source_limit=1,
        include_conversation_rows=False,
        include_ledger_groups=True,
    )

    assert false_positive.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }
    assert exact_candidate.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 1,
        "revisit_later": 0,
    }


def test_memory_ledger_counts_unicode_punctuation_and_guest_scope() -> None:
    user = api_state.store.get_or_create_dev_user()
    guest_conversation_id = "conversation-ledger-unicode-guest"
    _add_decided_messages(
        conversation_id=guest_conversation_id,
        contents=("Review ẞ/EUR — CAFÉ after the close.",),
        decision_state="revisit_later",
    )
    _add_decided_messages(
        conversation_id="conversation-ledger-unicode-other",
        contents=("Review ss/eur café in another conversation.",),
        decision_state="watching",
    )

    snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="ss/eur café",
        source_limit=1,
        include_conversation_rows=False,
        include_ledger_groups=True,
        guest_conversation_id=guest_conversation_id,
    )

    assert snapshot.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 1,
    }


def test_memory_ledger_index_rebuilds_after_search_revision() -> None:
    user = api_state.store.get_or_create_dev_user()
    initial = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="revision needle",
        source_limit=1,
        include_conversation_rows=False,
        include_ledger_groups=True,
    )

    _add_decided_messages(
        conversation_id="conversation-ledger-revision",
        contents=("A revision needle appears after the first search.",),
        decision_state="promising",
    )
    rebuilt = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="revision needle",
        source_limit=1,
        include_conversation_rows=False,
        include_ledger_groups=True,
    )

    assert initial.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }
    assert rebuilt.ledger_counts == {
        "promising": 1,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from argus.api import memory_ledger_index
from argus.api import state as api_state
from argus.api.memory_ledger_index import MemoryLedgerWorkLimitExceeded


@pytest.fixture(autouse=True)
def _reset_memory_store() -> None:
    api_state.store.reset()


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

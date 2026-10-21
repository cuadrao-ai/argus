from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import pytest
from argus.api import memory_search_candidates, search_assembly
from argus.api import state as api_state
from argus.api.schemas import (
    BacktestRun,
    Conversation,
    DecisionNote,
    EvidenceArtifact,
    Message,
)
from argus.api.search_utils import search_rank_key
from argus.domain.owner_scope import PERSONAL


@pytest.fixture(autouse=True)
def _reset_memory_store() -> None:
    api_state.store.reset()


class _LockAwareMessage:
    role = "user"

    def __init__(
        self,
        *,
        conversation_id: str,
        message_id: str,
        content: str,
        lock: Lock,
    ) -> None:
        self.conversation_id = conversation_id
        self.id = message_id
        self.content = content
        self.created_at = datetime.now(timezone.utc)
        self._lock = lock

    def model_dump(self) -> dict[str, Any]:
        acquired = self._lock.acquire(blocking=False)
        assert acquired, "memory search copied a message under the finalization lock"
        self._lock.release()
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "metadata": None,
        }


class _CountingSortedSymbols:
    def __init__(self, values: list[str]) -> None:
        self._values = tuple(sorted(values))
        self.lookups = 0

    def __len__(self) -> int:
        return len(self._values)

    def __getitem__(self, index: int) -> str:
        self.lookups += 1
        return self._values[index]

    def __iter__(self):
        raise AssertionError("asset-prefix lookup scanned the full symbol index")

    def reset(self) -> None:
        self.lookups = 0


def _owned_conversation(*, conversation_id: str, title: str) -> None:
    now = datetime.now(timezone.utc)
    user = api_state.store.get_or_create_dev_user()
    api_state.store.conversations[conversation_id] = Conversation(
        id=conversation_id,
        title=title,
        created_at=now,
        updated_at=now,
        language="en",
    )
    api_state.store.conversation_owners[conversation_id] = user.id


def test_memory_asset_prefix_resolution_uses_a_bounded_sorted_window() -> None:
    symbols = _CountingSortedSymbols(
        [
            *(f"asset{index:05d}" for index in range(10_000)),
            "aapl",
            "btc",
            "btc/usd",
            "msft",
            "ss/eur",
            "tsla",
            "tsm",
            "j\u030c/usd",
        ]
    )
    index = type("_AssetIndex", (), {"asset_symbols": symbols})()
    max_lookups = len(symbols).bit_length() + 2

    for query, expected in (
        ("AAPL", "aapl"),
        ("BTC", "btc"),
        ("btc/", "btc/usd"),
        ("ts", None),
        ("J\u030c/", "j\u030c/usd"),
        ("ss/e", "ss/eur"),
        ("zzzz", None),
        ("", None),
        ("BTC USD", None),
    ):
        symbols.reset()
        assert (
            memory_search_candidates._resolve_asset_symbol(index, query=query) == expected
        )
        assert symbols.lookups <= max_lookups


def test_memory_search_index_cache_evicts_and_closes_only_after_active_readers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Ledger:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class _Index:
        def __init__(self, revision: int) -> None:
            self.revision = revision
            self.ledger_index = _Ledger()

    built: list[_Index] = []

    def _build(*, store: Any, user: Any, scope: Any) -> _Index:
        del user, scope
        index = _Index(store.search_revision)
        built.append(index)
        return index

    monkeypatch.setattr(memory_search_candidates, "_INDEX_CACHE", OrderedDict())
    monkeypatch.setattr(memory_search_candidates, "_INDEX_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(
        memory_search_candidates,
        "_build_memory_search_index",
        _build,
    )
    user = api_state.store.get_or_create_dev_user()
    stores = [type(api_state.store)() for _ in range(3)]

    with memory_search_candidates._memory_search_index(
        scope=PERSONAL,
        store=stores[0],
        user=user,
    ):
        with memory_search_candidates._memory_search_index(
            scope=PERSONAL,
            store=stores[1],
            user=user,
        ):
            pass
        with memory_search_candidates._memory_search_index(
            scope=PERSONAL,
            store=stores[2],
            user=user,
        ):
            assert built[0].ledger_index.close_calls == 0

    assert len(memory_search_candidates._INDEX_CACHE) == 2
    assert built[0].ledger_index.close_calls == 1

    stores[1].bump_search_revision()
    with memory_search_candidates._memory_search_index(
        scope=PERSONAL,
        store=stores[1],
        user=user,
    ):
        pass

    assert len(memory_search_candidates._INDEX_CACHE) == 2
    assert built[1].ledger_index.close_calls == 1


def test_memory_asset_rollup_is_precomputed_once_per_search_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)
    conversation_id = "conversation-popular-asset-history"
    _owned_conversation(
        conversation_id=conversation_id,
        title="Popular asset history",
    )

    def _store_run(index: int) -> None:
        run = BacktestRun(
            id=f"run-popular-asset-{index:03d}",
            conversation_id=conversation_id,
            strategy_id=None,
            status="completed",
            asset_class="equity",
            symbols=["AAPL"],
            allocation_method="equal_weight",
            benchmark_symbol="SPY",
            metrics={},
            config_snapshot={},
            conversation_result_card={"title": f"AAPL result {index}"},
            created_at=now + timedelta(minutes=index),
        )
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user.id

    for index in range(200):
        _store_run(index)

    first = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="AAPL",
        source_limit=1,
        include_conversation_rows=False,
    )
    assert first.asset_rollup is not None
    assert first.asset_rollup.run_count == 200

    def _fail_if_lineage_is_revisited(_: object) -> datetime:
        raise AssertionError("asset lineage was traversed again at query time")

    with monkeypatch.context() as query_patch:
        query_patch.setattr(
            memory_search_candidates,
            "_mapping_activity",
            _fail_if_lineage_is_revisited,
        )
        second = memory_search_candidates.bounded_memory_search_snapshot(
            scope=PERSONAL,
            store=api_state.store,
            user=user,
            query="AAP",
            source_limit=1,
            include_conversation_rows=False,
        )

    assert second.asset_rollup is not None
    assert second.asset_rollup.symbol == "AAPL"
    assert second.asset_rollup.run_count == 200

    _store_run(200)
    refreshed = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="AAP",
        source_limit=1,
        include_conversation_rows=False,
    )

    assert refreshed.asset_rollup is not None
    assert refreshed.asset_rollup.run_count == 201


def test_memory_search_bounds_message_candidates_and_copies_outside_finalization_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = api_state.store.get_or_create_dev_user()
    finalization_lock = Lock()
    monkeypatch.setattr(
        api_state.store,
        "backtest_finalization_lock",
        finalization_lock,
    )
    captured_messages: list[dict[str, Any]] = []
    index_builds = 0

    for conversation_index in range(40):
        conversation_id = f"conversation-{conversation_index}"
        _owned_conversation(
            conversation_id=conversation_id,
            title=f"Unrelated memory {conversation_index}",
        )
        api_state.store.messages[conversation_id] = [
            _LockAwareMessage(
                conversation_id=conversation_id,
                message_id=f"message-{conversation_index}-{message_index}",
                content=(
                    "needle in the transcript"
                    if conversation_index == 39 and message_index == 9
                    else f"ordinary transcript text {message_index}"
                ),
                lock=finalization_lock,
            )
            for message_index in range(10)
        ]

    def _capture_rows(**kwargs: Any) -> list[search_assembly.ScoredSearchItem]:
        captured_messages.extend(kwargs["messages"])
        return []

    monkeypatch.setattr(search_assembly, "_project_rows", _capture_rows)
    original_builder = memory_search_candidates._build_memory_search_index

    def _counted_builder(**kwargs: Any) -> Any:
        nonlocal index_builds
        index_builds += 1
        return original_builder(**kwargs)

    monkeypatch.setattr(
        memory_search_candidates,
        "_build_memory_search_index",
        _counted_builder,
    )

    search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="needle",
        source_limit=2,
    )
    search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="transcript",
        source_limit=2,
    )

    assert index_builds == 1
    assert captured_messages[0]["id"] == "message-39-9"
    assert len(captured_messages) <= 21


def test_memory_search_bounds_exact_checks_before_scoring_common_postings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(200):
        conversation_id = f"conversation-common-posting-{index:03d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Unrelated title {index}",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.messages[conversation_id] = [
            Message(
                id=f"message-common-posting-{index:03d}",
                conversation_id=conversation_id,
                role="user",
                content="needle in a common transcript",
                created_at=now + timedelta(minutes=index),
                metadata={},
            )
        ]
    api_state.store.messages["conversation-common-posting-100"] = [
        Message(
            id=f"message-common-posting-cursor-{index:02d}",
            conversation_id="conversation-common-posting-100",
            role="user",
            content=f"needle in cursor transcript {index}",
            created_at=now + timedelta(minutes=100, microseconds=index),
            metadata={},
        )
        for index in range(15)
    ]

    exact_checks = 0
    original_matcher = memory_search_candidates.search_text_matches_query

    def _counted_matcher(*, query: str, text: object) -> bool:
        nonlocal exact_checks
        exact_checks += 1
        return original_matcher(query=query, text=text)

    monkeypatch.setattr(
        memory_search_candidates,
        "search_text_matches_query",
        _counted_matcher,
    )

    snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="needle",
        source_limit=1,
        include_conversation_rows=True,
    )

    assert len(snapshot.conversations) == 10
    assert exact_checks <= 10

    exact_checks = 0
    cursor_snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="needle",
        source_limit=1,
        include_conversation_rows=True,
        cursor_updated_at=now + timedelta(minutes=100),
        cursor_id="conversation-common-posting-100",
    )

    cursor_ids = {row["id"] for row in cursor_snapshot.conversations}
    assert {
        "conversation-common-posting-100",
        "conversation-common-posting-099",
    }.issubset(cursor_ids)
    assert len(cursor_snapshot.conversations) <= 20
    # The two ten-group presentation windows stay bounded. The cursor
    # conversation's fifteen messages are additionally checked so its public
    # match count remains exact rather than becoming a page-cap lower bound.
    assert exact_checks <= 35


def test_memory_search_keeps_bounded_match_counts_for_the_winning_layer() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)
    conversation_id = "conversation-with-several-matches"
    _owned_conversation(
        conversation_id=conversation_id,
        title="Unrelated title",
    )
    api_state.store.messages[conversation_id] = [
        Message(
            id=f"message-with-match-{index}",
            conversation_id=conversation_id,
            role="user",
            content=f"Needle in transcript turn {index}",
            created_at=now + timedelta(minutes=index),
            metadata={},
        )
        for index in range(3)
    ]

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="needle",
        source_limit=1,
    )

    assert len(read.scored_items) == 1
    assert read.scored_items[0][1].match.layer == "message"
    assert read.scored_items[0][1].match.count == 3


def test_memory_search_does_not_let_false_positive_trigrams_hide_an_exact_match() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(10):
        conversation_id = f"conversation-false-positive-{index:02d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title="Unrelated title",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.messages[conversation_id] = [
            Message(
                id=f"message-false-positive-{index:02d}",
                conversation_id=conversation_id,
                role="user",
                content="abc bcd cde def",
                created_at=now + timedelta(minutes=index),
                metadata={},
            )
        ]

    target_id = "conversation-exact-after-false-positives"
    api_state.store.conversations[target_id] = Conversation(
        id=target_id,
        title="Unrelated target",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
        language="en",
    )
    api_state.store.conversation_owners[target_id] = user.id
    api_state.store.messages[target_id] = [
        Message(
            id="message-exact-after-false-positives",
            conversation_id=target_id,
            role="user",
            content="abcdef exact match",
            created_at=now - timedelta(days=1),
            metadata={},
        )
    ]

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="abcdef",
        source_limit=1,
    )

    assert [item.id for _, item in read.scored_items] == [target_id]


def test_memory_search_applies_decision_filter_before_filling_candidate_window() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(101):
        conversation_id = f"conversation-filtered-newer-{index:03d}"
        decision_id = f"decision-filtered-newer-{index:03d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title="Unrelated title",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.messages[conversation_id] = [
            Message(
                id=f"message-filtered-newer-{index:03d}",
                conversation_id=conversation_id,
                role="user",
                content="needle in a filtered conversation",
                created_at=now + timedelta(minutes=index),
                metadata={},
            )
        ]
        api_state.store.decision_notes[decision_id] = DecisionNote(
            id=decision_id,
            idea_id=f"idea-filtered-newer-{index:03d}",
            idea_version_id=f"version-filtered-newer-{index:03d}",
            evidence_artifact_id=f"artifact-filtered-newer-{index:03d}",
            source_conversation_id=conversation_id,
            decision_state="promising",
            note="Not part of the requested state.",
            created_at=now,
            updated_at=now,
        )
        api_state.store.decision_note_owners[decision_id] = user.id

    target_id = "conversation-eligible-older"
    target_decision_id = "decision-eligible-older"
    api_state.store.conversations[target_id] = Conversation(
        id=target_id,
        title="Unrelated target",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
        language="en",
    )
    api_state.store.conversation_owners[target_id] = user.id
    api_state.store.messages[target_id] = [
        Message(
            id="message-eligible-older",
            conversation_id=target_id,
            role="user",
            content="needle in the eligible conversation",
            created_at=now - timedelta(days=1),
            metadata={},
        )
    ]
    api_state.store.decision_notes[target_decision_id] = DecisionNote(
        id=target_decision_id,
        idea_id="idea-eligible-older",
        idea_version_id="version-eligible-older",
        evidence_artifact_id="artifact-eligible-older",
        source_conversation_id=target_id,
        decision_state="watching",
        note="The requested state.",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    api_state.store.decision_note_owners[target_decision_id] = user.id

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="needle",
        source_limit=1,
        decision_state="watching",
    )

    assert [item.id for _, item in read.scored_items] == [target_id]


def test_memory_search_preserves_text_rank_at_equal_conversation_activity() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(10):
        conversation_id = f"z-conversation-token-match-{index:02d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title="Unrelated title",
            created_at=now,
            updated_at=now,
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.messages[conversation_id] = [
            Message(
                id=f"message-token-match-{index:02d}",
                conversation_id=conversation_id,
                role="user",
                content="alpha separated from beta",
                created_at=now,
                metadata={},
            )
        ]

    target_id = "a-conversation-contiguous-match"
    api_state.store.conversations[target_id] = Conversation(
        id=target_id,
        title="Unrelated target",
        created_at=now,
        updated_at=now,
        language="en",
    )
    api_state.store.conversation_owners[target_id] = user.id
    api_state.store.messages[target_id] = [
        Message(
            id="message-contiguous-match",
            conversation_id=target_id,
            role="user",
            content="alpha beta",
            created_at=now,
            metadata={},
        )
    ]

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="alpha beta",
        source_limit=1,
    )
    ranked = sorted(
        read.scored_items,
        key=lambda pair: search_rank_key(
            score=pair[0],
            kind=pair[1].type,
            updated_at=pair[1].updated_at,
            item_id=pair[1].id,
        ),
        reverse=True,
    )

    assert ranked[0][1].id == target_id


def test_memory_search_casefolds_stored_symbols_for_exact_rank() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)
    symbol_conversation_id = "conversation-expanding-casefold-symbol"
    object_conversation_id = "conversation-normal-object-match"

    _owned_conversation(
        conversation_id=symbol_conversation_id,
        title="Unrelated symbol conversation",
    )
    _owned_conversation(
        conversation_id=object_conversation_id,
        title="Unrelated object conversation",
    )

    symbol_run = BacktestRun(
        id="run-expanding-casefold-symbol",
        conversation_id=symbol_conversation_id,
        strategy_id=None,
        status="completed",
        asset_class="currency_pair",
        symbols=["ẞ/EUR"],
        allocation_method="equal_weight",
        benchmark_symbol="ẞ/EUR",
        metrics={},
        config_snapshot={},
        conversation_result_card={"title": "Expanding casefold result"},
        created_at=now,
    )
    api_state.store.backtest_runs[symbol_run.id] = symbol_run
    api_state.store.backtest_run_owners[symbol_run.id] = user.id

    object_match = EvidenceArtifact(
        id="evidence-normal-object-match",
        idea_id="idea-normal-object-match",
        idea_version_id="version-normal-object-match",
        source_conversation_id=object_conversation_id,
        source_run_id="run-normal-object-match",
        lifecycle="captured",
        title="Ordinary evidence",
        digest="Review ss/eur in this artifact.",
        payload={},
        created_at=now,
        updated_at=now,
    )
    api_state.store.evidence_artifacts[object_match.id] = object_match
    api_state.store.evidence_artifact_owners[object_match.id] = user.id

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="ss/eur",
        source_limit=2,
    )
    ranked = sorted(
        read.scored_items,
        key=lambda pair: search_rank_key(
            score=pair[0],
            kind=pair[1].type,
            updated_at=pair[1].updated_at,
            item_id=pair[1].id,
        ),
        reverse=True,
    )

    assert [item.id for _, item in ranked] == [
        symbol_conversation_id,
        object_conversation_id,
    ]


def test_memory_search_counts_winning_layer_when_page_is_full() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)
    target_id = "conversation-full-page-count"

    for index in range(10):
        conversation_id = (
            target_id if index == 9 else f"conversation-full-page-{index:02d}"
        )
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title="Unrelated title",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.messages[conversation_id] = [
            Message(
                id=f"message-full-page-{index:02d}-{message_index}",
                conversation_id=conversation_id,
                role="user",
                content=f"needle in message {message_index}",
                created_at=now
                + timedelta(
                    minutes=index,
                    microseconds=message_index,
                ),
                metadata={},
            )
            for message_index in range(3 if conversation_id == target_id else 1)
        ]

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="needle",
        source_limit=1,
    )

    assert len(read.scored_items) == 10
    target = next(item for _, item in read.scored_items if item.id == target_id)
    assert target.match is not None
    assert target.match.count == 3


def test_memory_search_cursor_window_crosses_matching_layers() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(10):
        conversation_id = f"conversation-pinned-title-match-{index:02d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Needle pinned title {index}",
            pinned=True,
            created_at=now + timedelta(minutes=index),
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id

    cursor_id = "conversation-message-cursor"
    api_state.store.conversations[cursor_id] = Conversation(
        id=cursor_id,
        title="Unrelated cursor title",
        created_at=now,
        updated_at=now,
        language="en",
    )
    api_state.store.conversation_owners[cursor_id] = user.id
    api_state.store.messages[cursor_id] = [
        Message(
            id="message-cursor-match",
            conversation_id=cursor_id,
            role="user",
            content="needle in the cursor transcript",
            created_at=now,
            metadata={},
        )
    ]

    target_id = "conversation-older-title-match"
    api_state.store.conversations[target_id] = Conversation(
        id=target_id,
        title="Needle older title match",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
        language="en",
    )
    api_state.store.conversation_owners[target_id] = user.id

    snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="needle",
        source_limit=1,
        include_conversation_rows=True,
        cursor_updated_at=now,
        cursor_id=cursor_id,
    )

    assert target_id in {row["id"] for row in snapshot.conversations}


def test_memory_search_cursor_keeps_each_rows_global_winning_layer() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(10):
        conversation_id = f"conversation-newer-decision-{index:02d}"
        decision_id = f"decision-newer-{index:02d}"
        _owned_conversation(
            conversation_id=conversation_id,
            title="Unrelated decision title",
        )
        api_state.store.decision_notes[decision_id] = DecisionNote(
            id=decision_id,
            idea_id=f"idea-newer-{index:02d}",
            idea_version_id=f"version-newer-{index:02d}",
            evidence_artifact_id=f"artifact-newer-{index:02d}",
            source_conversation_id=conversation_id,
            decision_state="watching",
            note="Needle in a newer decision.",
            created_at=now + timedelta(minutes=index),
            updated_at=now + timedelta(minutes=index),
        )
        api_state.store.decision_note_owners[decision_id] = user.id

    cursor_id = "conversation-global-layer-cursor"
    _owned_conversation(
        conversation_id=cursor_id,
        title="Unrelated cursor title",
    )
    api_state.store.messages[cursor_id] = [
        Message(
            id="message-global-layer-cursor",
            conversation_id=cursor_id,
            role="user",
            content="needle in cursor transcript",
            created_at=now,
            metadata={},
        )
    ]

    target_id = "conversation-wrapper-and-decision-target"
    target_decision_id = "decision-wrapper-and-decision-target"
    _owned_conversation(
        conversation_id=target_id,
        title="Needle wrapper title",
    )
    api_state.store.decision_notes[target_decision_id] = DecisionNote(
        id=target_decision_id,
        idea_id="idea-wrapper-and-decision-target",
        idea_version_id="version-wrapper-and-decision-target",
        evidence_artifact_id="artifact-wrapper-and-decision-target",
        source_conversation_id=target_id,
        decision_state="watching",
        note="Needle in the target decision.",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    api_state.store.decision_note_owners[target_decision_id] = user.id

    snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="needle",
        source_limit=1,
        include_conversation_rows=True,
        cursor_updated_at=api_state.store.conversations[cursor_id].updated_at,
        cursor_id=cursor_id,
    )

    target = next(row for row in snapshot.conversations if row["id"] == target_id)
    assert target["_recall_match"]["layer"] == "decision"


def test_memory_search_cursor_slots_exclude_rows_that_win_above_cursor() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(10):
        conversation_id = f"conversation-hidden-winner-{index:02d}"
        decision_id = f"decision-hidden-winner-{index:02d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Needle wrapper {index}",
            created_at=now + timedelta(minutes=index),
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.decision_notes[decision_id] = DecisionNote(
            id=decision_id,
            idea_id=f"idea-hidden-winner-{index:02d}",
            idea_version_id=f"version-hidden-winner-{index:02d}",
            evidence_artifact_id=f"artifact-hidden-winner-{index:02d}",
            source_conversation_id=conversation_id,
            decision_state="watching",
            note="Needle decision above the cursor.",
            created_at=now + timedelta(minutes=index),
            updated_at=now + timedelta(minutes=index),
        )
        api_state.store.decision_note_owners[decision_id] = user.id

    cursor_id = "conversation-slot-cursor"
    _owned_conversation(
        conversation_id=cursor_id,
        title="Unrelated cursor title",
    )
    api_state.store.messages[cursor_id] = [
        Message(
            id="message-slot-cursor",
            conversation_id=cursor_id,
            role="user",
            content="needle in cursor transcript",
            created_at=now,
            metadata={},
        )
    ]

    target_id = "conversation-genuinely-below-cursor"
    api_state.store.conversations[target_id] = Conversation(
        id=target_id,
        title="Needle genuinely below",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
        language="en",
    )
    api_state.store.conversation_owners[target_id] = user.id

    snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="needle",
        source_limit=1,
        include_conversation_rows=True,
        cursor_updated_at=api_state.store.conversations[cursor_id].updated_at,
        cursor_id=cursor_id,
    )

    assert target_id in {row["id"] for row in snapshot.conversations}


def test_memory_candidate_window_uses_final_conversation_rank_beyond_source_cap() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(11):
        conversation_id = f"conversation-source-newer-{index:02d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Unrelated title {index}",
            last_message_preview="Unrelated recent activity",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id
        api_state.store.messages[conversation_id] = [
            Message(
                id=f"message-source-newer-{index:02d}",
                conversation_id=conversation_id,
                role="user",
                content="needle in an ordinary message",
                created_at=now + timedelta(minutes=index + 1),
                metadata={},
            )
        ]

    target_id = "conversation-old-match-recent-activity"
    api_state.store.conversations[target_id] = Conversation(
        id=target_id,
        title="Unrelated target title",
        last_message_preview="Newest unrelated activity",
        created_at=now - timedelta(days=2),
        updated_at=now + timedelta(days=1),
        language="en",
    )
    api_state.store.conversation_owners[target_id] = user.id
    api_state.store.messages[target_id] = [
        Message(
            id="message-old-match",
            conversation_id=target_id,
            role="user",
            content="needle in an old message",
            created_at=now - timedelta(days=1),
            metadata={},
        )
    ]

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="needle",
        source_limit=1,
    )
    ranked = sorted(
        read.scored_items,
        key=lambda pair: search_rank_key(
            score=pair[0],
            kind=pair[1].type,
            updated_at=pair[1].updated_at,
            item_id=pair[1].id,
        ),
        reverse=True,
    )

    assert ranked[0][1].id == target_id


def test_memory_recents_window_uses_final_seek_key_before_candidate_cap() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(210):
        conversation_id = f"conversation-recent-window-{index:03d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Recent conversation {index}",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id

    pinned_id = "conversation-old-but-pinned"
    api_state.store.conversations[pinned_id] = Conversation(
        id=pinned_id,
        title="Old pinned conversation",
        pinned=True,
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=3),
        language="en",
    )
    api_state.store.conversation_owners[pinned_id] = user.id

    decision_activity_id = "conversation-old-with-recent-decision"
    api_state.store.conversations[decision_activity_id] = Conversation(
        id=decision_activity_id,
        title="Old conversation with a new decision",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
        language="en",
    )
    api_state.store.conversation_owners[decision_activity_id] = user.id
    decision_id = "decision-recent-window"
    api_state.store.decision_notes[decision_id] = DecisionNote(
        id=decision_id,
        idea_id="idea-recent-window",
        idea_version_id="version-recent-window",
        evidence_artifact_id="artifact-recent-window",
        source_conversation_id=decision_activity_id,
        decision_state="watching",
        note="A newer decision on an older chat.",
        created_at=now + timedelta(days=1),
        updated_at=now + timedelta(days=1),
    )
    api_state.store.decision_note_owners[decision_id] = user.id

    base_snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="",
        source_limit=21,
        include_conversation_rows=True,
    )
    cursor_snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="",
        source_limit=21,
        include_conversation_rows=True,
        cursor_updated_at=now + timedelta(minutes=209),
        cursor_id="conversation-recent-window-209",
    )

    assert len(base_snapshot.conversations) == 210
    assert {
        pinned_id,
        decision_activity_id,
    }.issubset({row["id"] for row in base_snapshot.conversations})
    assert {
        pinned_id,
        decision_activity_id,
    }.issubset({row["id"] for row in cursor_snapshot.conversations})


def test_memory_recents_cursor_window_uses_final_seek_key_beyond_head() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)

    for index in range(10):
        conversation_id = f"conversation-old-pinned-{index:02d}"
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=f"Old pinned conversation {index}",
            pinned=True,
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2, minutes=index),
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id

    for conversation_id, updated_at in (
        ("conversation-cursor", now),
        ("conversation-after-cursor", now - timedelta(minutes=1)),
    ):
        api_state.store.conversations[conversation_id] = Conversation(
            id=conversation_id,
            title=conversation_id,
            created_at=updated_at,
            updated_at=updated_at,
            language="en",
        )
        api_state.store.conversation_owners[conversation_id] = user.id

    base_snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="",
        source_limit=1,
        include_conversation_rows=True,
    )
    cursor_snapshot = memory_search_candidates.bounded_memory_search_snapshot(
        scope=PERSONAL,
        store=api_state.store,
        user=user,
        query="",
        source_limit=1,
        include_conversation_rows=True,
        cursor_updated_at=now,
        cursor_id="conversation-cursor",
    )

    base_ids = {row["id"] for row in base_snapshot.conversations}
    cursor_ids = {row["id"] for row in cursor_snapshot.conversations}
    assert "conversation-cursor" not in base_ids
    assert "conversation-after-cursor" not in base_ids
    assert {
        "conversation-cursor",
        "conversation-after-cursor",
    }.issubset(cursor_ids)


def test_memory_search_preserves_the_latest_untaken_assistant_offer() -> None:
    user = api_state.store.get_or_create_dev_user()
    now = datetime.now(timezone.utc)
    conversation_id = "conversation-with-untaken-offer"
    _owned_conversation(
        conversation_id=conversation_id,
        title="Gold follow-up ideas",
    )
    run = BacktestRun(
        id="run-with-untaken-offer",
        conversation_id=conversation_id,
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["GLD"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={},
        conversation_result_card={"title": "GLD result"},
        created_at=now,
    )
    artifact = EvidenceArtifact(
        id="evidence-with-untaken-offer",
        idea_id="idea-with-untaken-offer",
        idea_version_id="version-with-untaken-offer",
        source_conversation_id=conversation_id,
        source_run_id=run.id,
        lifecycle="decided",
        title="GLD result evidence",
        digest="GLD completed against SPY.",
        payload={},
        created_at=now,
        updated_at=now,
    )
    decision = DecisionNote(
        id="decision-with-untaken-offer",
        idea_id=artifact.idea_id,
        idea_version_id=artifact.idea_version_id,
        evidence_artifact_id=artifact.id,
        source_conversation_id=conversation_id,
        decision_state="watching",
        note="Keep watching this setup.",
        created_at=now,
        updated_at=now,
    )
    offer = Message(
        id="assistant-offer",
        conversation_id=conversation_id,
        role="assistant",
        content="Try one of these supported follow-ups.",
        created_at=now,
        metadata={
            "result_run_id": run.id,
            "next_experiments": {
                "version": "argus_next_experiments/v1",
                "rows": [{"kind": "parameter_sweep"}],
            },
        },
    )
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user.id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user.id
    api_state.store.decision_notes[decision.id] = decision
    api_state.store.decision_note_owners[decision.id] = user.id
    api_state.store.messages[conversation_id] = [offer]

    read = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="",
        source_limit=1,
    )

    assert len(read.scored_items) == 1
    _, item = read.scored_items[0]
    assert item.dossier is not None
    assert item.dossier.result_message_id == offer.id
    assert "left_off" not in item.dossier.model_dump()

    assistant_text_search = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="supported follow-ups",
        source_limit=1,
    )
    assert assistant_text_search.scored_items == []

    api_state.store.messages[conversation_id] = [
        offer,
        Message(
            id="later-user-reply",
            conversation_id=conversation_id,
            role="user",
            content="I already followed up.",
            created_at=now + timedelta(microseconds=1),
            metadata={},
        ),
    ]
    followed_up = search_assembly.memory_search_read(
        scope=PERSONAL,
        user=user,
        query="",
        source_limit=1,
    )
    followed_up_dossier = followed_up.scored_items[0][1].dossier
    assert followed_up_dossier is not None
    assert followed_up_dossier.result_message_id == offer.id
    assert "left_off" not in followed_up_dossier.model_dump()

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import pytest
from argus.domain.owner_scope import PERSONAL


class _RecordingCursor:
    def __init__(self, result_sets: list[list[dict[str, Any]]]) -> None:
        self._result_sets = result_sets
        self.executions: list[tuple[Any, dict[str, Any]]] = []

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: Any, params: dict[str, Any]) -> None:
        self.executions.append((query, params))

    def fetchall(self) -> list[dict[str, Any]]:
        return self._result_sets.pop(0)


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self, **_kwargs: Any) -> _RecordingCursor:
        return self._cursor


class _RecordingPool:
    def __init__(self, result_sets: list[list[dict[str, Any]]]) -> None:
        self.cursor = _RecordingCursor(result_sets)
        self.acquisition_timeouts: list[float] = []

    @contextmanager
    def connection(self, *, timeout: float):
        self.acquisition_timeouts.append(timeout)
        yield _RecordingConnection(self.cursor)


def _reader_types():
    try:
        from argus.domain.postgres_search_reader import (
            PostgresSearchReader,
            SearchCursorError,
        )
    except ModuleNotFoundError:
        pytest.fail("bounded Postgres Search reader is not implemented")
    return PostgresSearchReader, SearchCursorError


CONVERSATION_ID = "00000000-0000-0000-0000-000000000101"
OWNER_ID = "00000000-0000-0000-0000-000000000001"
ACTIVITY_AT = "2026-07-27T12:00:00+00:00"


def _conversation_candidate() -> dict[str, Any]:
    return {
        "source_type": "conversation",
        "pinned_rank": 0,
        "exact_rank": 0,
        "symbol_rank": 0,
        "layer_rank": 6,
        "text_rank": 50,
        "payload": {
            "id": CONVERSATION_ID,
            "title": "Search chat",
            "last_message_preview": "Search preview",
            "updated_at": "2026-07-26T12:00:00+00:00",
            "pinned": False,
            "deleted_at": None,
            "_recall_match": {
                "matched_text": "Search decision evidence",
                "layer_rank": 6,
                "layer": "decision",
                "match_count": 1,
                "message_id": None,
                "symbol_exact_match": False,
                "activity_at": ACTIVITY_AT,
            },
        },
    }


def _hydration_row() -> dict[str, Any]:
    return {
        "conversation_payload": {
            "id": CONVERSATION_ID,
            "title": "Search chat",
            "last_message_preview": "Search preview",
            "updated_at": "2026-07-26T12:00:00+00:00",
            "pinned": False,
            "deleted_at": None,
            "_recall_summary": {
                "run_count": 7,
                "total_runs": 7,
                "decided_runs": 5,
                "symbols": ["AAPL", "MSFT"],
                "strategy_families": ["buy_and_hold"],
                "start_date": "2019-01-01",
                "end_date": "2026-07-27",
                "decision_states": ["promising", "watching"],
                "latest_run_decided": False,
                "latest_suggestion_untaken": False,
                "latest_activity": ACTIVITY_AT,
            },
        },
        "latest_run_payload": {
            "id": "00000000-0000-0000-0000-000000000401",
            "conversation_id": CONVERSATION_ID,
            "status": "completed",
            "asset_class": "equity",
            "symbols": ["AAPL"],
            "benchmark_symbol": "SPY",
            "config_snapshot": {
                "template": "buy_and_hold",
                "timeframe": "1D",
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "resolved_parameters": {
                    "sizing_mode": "capital_amount",
                    "capital_amount": 10_000,
                },
            },
            "conversation_result_card": {
                "title": "Latest run",
                "evidence_artifact_id": "latest-evidence",
                "idea_id": "latest-idea",
                "idea_version_id": "latest-idea-version",
            },
            "created_at": ACTIVITY_AT,
            "updated_at": ACTIVITY_AT,
        },
        "judged_run_payload": {
            "id": "00000000-0000-0000-0000-000000000402",
            "conversation_id": CONVERSATION_ID,
            "status": "completed",
            "symbols": ["MSFT"],
            "benchmark_symbol": "SPY",
            "config_snapshot": {"template": "buy_and_hold"},
            "conversation_result_card": {
                "title": "Judged older run",
                "evidence_artifact_id": "judged-evidence",
                "idea_id": "judged-idea",
                "idea_version_id": "judged-idea-version",
            },
            "created_at": "2025-01-01T12:00:00+00:00",
            "updated_at": "2025-01-01T12:00:00+00:00",
        },
        "latest_evidence_payload": {
            "id": "00000000-0000-0000-0000-000000000301",
            "source_conversation_id": CONVERSATION_ID,
            "source_run_id": "00000000-0000-0000-0000-000000000401",
            "title": "Latest evidence",
            "digest": "Latest quick take",
            "payload": {},
            "updated_at": ACTIVITY_AT,
        },
        "latest_decision_payload": {
            "id": "00000000-0000-0000-0000-000000000501",
            "source_conversation_id": CONVERSATION_ID,
            "evidence_artifact_id": "00000000-0000-0000-0000-000000000302",
            "source_run_id": "00000000-0000-0000-0000-000000000402",
            "decision_state": "promising",
            "note": "Search decision.",
            "artifact_title": "Older evidence",
            "artifact_digest": "Older quick take",
            "artifact_payload": {},
            "updated_at": ACTIVITY_AT,
        },
        "latest_run_decision_payload": {
            "id": "00000000-0000-0000-0000-000000000502",
            "source_conversation_id": CONVERSATION_ID,
            "evidence_artifact_id": "00000000-0000-0000-0000-000000000301",
            "decision_state": "watching",
            "note": "Latest-run decision.",
            "updated_at": "2026-07-26T13:00:00+00:00",
        },
        "latest_result_message_payload": {
            "id": "00000000-0000-0000-0000-000000000201",
            "conversation_id": CONVERSATION_ID,
            "role": "assistant",
            "content": "Latest run result",
            "metadata": {"result_run_id": "00000000-0000-0000-0000-000000000401"},
            "created_at": ACTIVITY_AT,
        },
    }


def test_search_first_page_is_one_candidate_one_hydration_and_one_ledger_read() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool(
        [
            [_conversation_candidate()],
            [_hydration_row()],
            [
                {"decision_state": "promising", "count": 1},
                {"decision_state": "watching", "count": 1},
            ],
        ]
    )

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="search",
        source_limit=4,
        include_ledger_groups=True,
    )

    assert {source: len(rows) for source, rows in result.rows.items()} == {
        "conversations": 1,
        "strategies": 0,
        "collections": 0,
        "runs": 1,
        "ideas": 0,
        "evidence": 1,
        "decisions": 1,
        "messages": 1,
    }
    assert result.rows["conversations"][0]["_recall_match"] == {
        "matched_text": "Search decision evidence",
        "layer_rank": 6,
        "layer": "decision",
        "match_count": 1,
        "message_id": None,
        "symbol_exact_match": False,
        "activity_at": ACTIVITY_AT,
    }
    assert result.rows["conversations"][0]["_recall_summary"]["total_runs"] == 7
    assert result.ledger_counts == {
        "promising": 1,
        "watching": 1,
        "rejected": 0,
        "revisit_later": 0,
    }
    hydration_sql = str(pool.cursor.executions[1][0])
    assert "message.metadata->'result_card'" in hydration_sql
    assert hydration_sql.index("message.metadata->'result_card'") < hydration_sql.index(
        "message.created_at desc"
    )
    assert len(pool.cursor.executions) == 3
    assert pool.cursor.executions[0][1]["source_limit"] == 4
    assert pool.acquisition_timeouts == [2.0]


def test_search_hydrates_latest_recall_decision_without_a_run_dossier() -> None:
    reader_type, _ = _reader_types()
    hydration = _hydration_row()
    hydration["latest_run_payload"] = None
    hydration["latest_evidence_payload"] = None
    hydration["latest_run_decision_payload"] = None
    hydration["latest_result_message_payload"] = None
    hydration["latest_recall_decision_payload"] = {
        "id": "00000000-0000-0000-0000-000000000501",
        "source_conversation_id": CONVERSATION_ID,
        "evidence_artifact_id": "00000000-0000-0000-0000-000000000302",
        "decision_state": "promising",
        "note": "Search decision.",
        "artifact_digest": "Search decision evidence",
        "updated_at": ACTIVITY_AT,
    }
    pool = _RecordingPool(
        [
            [_conversation_candidate()],
            [hydration],
        ]
    )

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="search",
        source_limit=4,
    )

    assert result.rows["runs"] == []
    assert result.rows["evidence"] == []
    assert result.rows["decisions"] == [hydration["latest_recall_decision_payload"]]
    hydration_sql = pool.cursor.executions[1][0]
    assert "latest_recall_decision_payload" in str(hydration_sql)


def test_search_visible_id_recall_is_one_bounded_hydration_and_one_ledger_read() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool(
        [
            [_hydration_row()],
            [
                {"decision_state": "promising", "count": 1},
                {"decision_state": "watching", "count": 1},
            ],
        ]
    )

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="",
        source_limit=1,
        conversation_ids=[CONVERSATION_ID],
        include_ledger_groups=True,
    )

    assert [row["id"] for row in result.rows["conversations"]] == [CONVERSATION_ID]
    assert len(pool.cursor.executions) == 2
    hydration_sql, hydration_params = pool.cursor.executions[0]
    assert "conversation.id = any(%(conversation_ids)s::uuid[])" in str(hydration_sql)
    assert [str(value) for value in hydration_params["conversation_ids"]] == [
        CONVERSATION_ID
    ]
    assert "conversation_candidates" not in str(hydration_sql)
    assert result.ledger_counts == {
        "promising": 1,
        "watching": 1,
        "rejected": 0,
        "revisit_later": 0,
    }


def test_search_visible_id_recall_rejects_more_than_fifty_before_database_read() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([])

    with pytest.raises(ValueError, match="at most 50"):
        reader_type(pool).search_rows(
            scope=PERSONAL,
            user_id=OWNER_ID,
            query="",
            source_limit=50,
            conversation_ids=[
                f"00000000-0000-0000-0000-{index:012d}" for index in range(51)
            ],
        )

    assert pool.cursor.executions == []


def test_search_rejects_nonpositive_bound_before_database_read() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([])

    with pytest.raises(ValueError, match="positive"):
        reader_type(pool).search_rows(
            scope=PERSONAL,
            user_id=OWNER_ID,
            query="search",
            source_limit=0,
        )

    assert pool.cursor.executions == []


@pytest.mark.parametrize("query", ["a", "GL D", "__"])
def test_search_defers_nonempty_queries_without_an_indexable_token(
    query: str,
) -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([])

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query=query,
        source_limit=4,
        include_ledger_groups=True,
    )

    assert all(not rows for rows in result.rows.values())
    assert result.asset_rollup is None
    assert result.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }
    assert pool.cursor.executions == []
    assert pool.acquisition_timeouts == []


@pytest.mark.parametrize("symbol", ["GL", "ss/e"])
def test_search_allows_symbol_only_queries_without_text_scans(symbol: str) -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[], []])

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query=symbol,
        source_limit=4,
        include_ledger_groups=True,
    )

    assert result.asset_rollup is None
    assert result.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }
    assert len(pool.cursor.executions) == 2
    rendered, params = pool.cursor.executions[0]
    sql_text = rendered.as_string()
    assert params["symbol_query"] == symbol.casefold()
    assert params["text_search_enabled"] is False
    assert "%(text_search_enabled)s::boolean as text_search_enabled" in sql_text
    assert "not input.text_search_enabled" in sql_text
    assert (
        "btrim(public.argus_search_symbol_casefold(" 'run.symbols[1])) collate "C"'
    ) in sql_text
    assert all(
        execution_params["text_search_enabled"] is False
        for _, execution_params in pool.cursor.executions
    )


def test_empty_search_keeps_recents_and_ledger_reads_enabled() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[], []])

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="",
        source_limit=4,
        include_ledger_groups=True,
    )

    assert result.ledger_counts == {
        "promising": 0,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }
    assert len(pool.cursor.executions) == 2
    assert pool.cursor.executions[0][1]["text_search_enabled"] is True


def test_conversation_search_sql_guards_all_text_match_sources() -> None:
    from argus.domain.postgres_search_reader import _conversation_search_sql

    rendered = _conversation_search_sql(has_anchor=False).as_string()

    assert rendered.count("input.text_search_enabled") == 7
    assert "not input.text_search_enabled" in rendered


def test_search_indexability_separates_two_character_symbols_from_text() -> None:
    from argus.domain.search_text import search_query_is_indexable

    assert search_query_is_indexable("GL") is True
    assert search_query_is_indexable("ss/e") is True
    assert search_query_is_indexable("J\u030c/USD") is True
    for deferred in ("G", "GL D", "__", "___", "\x00__", "/-."):
        assert search_query_is_indexable(deferred) is False


def test_symbol_only_search_accepts_a_conversation_cursor() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[_conversation_candidate()], []])

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="ba",
        source_limit=4,
        cursor_updated_at=datetime(2026, 7, 27, 12, tzinfo=timezone.utc),
        cursor_id=CONVERSATION_ID,
    )

    assert result.rows["conversations"] == []
    assert len(pool.cursor.executions) == 2
    assert pool.cursor.executions[0][1]["text_search_enabled"] is False
    assert "public.backtest_runs" in pool.cursor.executions[0][0].as_string()


def test_symbol_only_search_uses_exact_run_symbols_without_broad_text() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="ba",
        source_limit=4,
    )

    rendered, params = pool.cursor.executions[0]
    sql_text = rendered.as_string()
    assert params["text_search_enabled"] is False
    assert "conversation_page" in sql_text
    assert "unnest(run.symbols)" not in sql_text
    assert "unnest(symbol_run.symbols)" not in sql_text
    for slot in range(1, 6):
        assert (
            "btrim(public.argus_search_symbol_casefold("
            f'run.symbols[{slot}])) collate "C"'
        ) in sql_text
        assert (
            "btrim(public.argus_search_symbol_casefold("
            f'symbol_run.symbols[{slot}])) collate "C"'
        ) in sql_text
    assert "where input.text_search_enabled" in sql_text


def test_symbol_only_ledger_uses_indexed_run_symbol_slots() -> None:
    from argus.domain.postgres_search_reader import _conversation_ledger_sql

    rendered = _conversation_ledger_sql(has_anchor=False).as_string()

    assert "unnest(run.symbols)" not in rendered
    for slot in range(1, 6):
        assert (
            "btrim(public.argus_search_symbol_casefold("
            f'run.symbols[{slot}])) collate "C"'
        ) in rendered


@pytest.mark.parametrize("pivot_rows", [[], [_conversation_candidate()] * 2])
def test_search_cursor_missing_foreign_or_ambiguous_pivot_fails_closed(
    pivot_rows: list[dict[str, Any]],
) -> None:
    reader_type, cursor_error = _reader_types()
    pool = _RecordingPool([pivot_rows])

    with pytest.raises(cursor_error):
        reader_type(pool).search_rows(
            scope=PERSONAL,
            user_id=OWNER_ID,
            query="search",
            source_limit=4,
            cursor_updated_at=datetime(2026, 7, 27, 12, tzinfo=timezone.utc),
            cursor_id=CONVERSATION_ID,
        )

    assert len(pool.cursor.executions) == 1


def test_search_naive_cursor_fails_before_database_read() -> None:
    reader_type, cursor_error = _reader_types()
    pool = _RecordingPool([])

    with pytest.raises(cursor_error):
        reader_type(pool).search_rows(
            scope=PERSONAL,
            user_id=OWNER_ID,
            query="search",
            source_limit=4,
            cursor_updated_at=datetime(2026, 7, 27),
            cursor_id=CONVERSATION_ID,
        )

    assert pool.cursor.executions == []


@pytest.mark.parametrize(
    "cursor_id",
    ["{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"],
)
def test_search_noncanonical_cursor_uuid_fails_before_database_read(
    cursor_id: str,
) -> None:
    reader_type, cursor_error = _reader_types()
    pool = _RecordingPool([])

    with pytest.raises(cursor_error):
        reader_type(pool).search_rows(
            scope=PERSONAL,
            user_id=OWNER_ID,
            query="search",
            source_limit=4,
            cursor_updated_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            cursor_id=cursor_id,
        )

    assert pool.cursor.executions == []


def test_search_nul_query_keeps_normalized_text_but_never_binds_raw_nul() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="nee\x00dle",
        source_limit=4,
    )

    params = pool.cursor.executions[0][1]
    assert params["normalized_query"] == "nee dle"
    assert params["symbol_query"] is None
    assert "\x00" not in str(params)


def test_search_binds_punctuation_preserving_single_symbol_query() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="  bTc/uSd  ",
        source_limit=4,
    )

    params = pool.cursor.executions[0][1]
    assert params["normalized_query"] == "btc usd"
    assert params["symbol_query"] == "btc/usd"


def test_symbol_sql_normalizer_uses_raw_expanding_and_combining_casefolds() -> None:
    from argus.domain.search_sql_text import symbol_normalizer_expression
    from psycopg import sql

    rendered = symbol_normalizer_expression(sql.Identifier("symbol")).as_string()

    assert "'ß', 'ss'" in rendered
    assert "'ǰ', 'ǰ'" in rendered
    assert "btrim(" not in rendered
    assert "regexp_replace(" not in rendered


def test_search_does_not_bind_true_multi_symbol_query() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="BTC/USD TSLA",
        source_limit=4,
    )

    params = pool.cursor.executions[0][1]
    assert params["normalized_query"] == "btc usd tsla"
    assert params["symbol_query"] is None


def test_search_uses_bound_token_array_without_row_token_splitting() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="Alpha x beta alpha",
        source_limit=4,
    )

    query, params = pool.cursor.executions[0]
    rendered = query.as_string()

    assert "regexp_split_to_table" not in rendered
    assert params["token_patterns"] == ["%alpha%", "%x%", "%beta%"]
    assert params["anchor_pattern"] == "%alpha%"
    assert "unnest(%(token_patterns)s::text[])" in rendered
    assert "%(anchor_pattern)s" in rendered
    assert "token_0_pattern" not in rendered


def test_search_sql_shape_is_constant_as_token_count_grows() -> None:
    reader_type, _ = _reader_types()

    def rendered_sql_shape(query: str) -> tuple[int, int]:
        pool = _RecordingPool([[]])
        reader_type(pool).search_rows(
            scope=PERSONAL,
            user_id=OWNER_ID,
            query=query,
            source_limit=4,
        )
        rendered = pool.cursor.executions[0][0].as_string()
        return len(rendered), rendered.count('collate "und-x-icu"')

    assert rendered_sql_shape(
        " ".join(f"needle{index:03d}" for index in range(400))
    ) == rendered_sql_shape("needle000")


def test_search_groups_all_matching_layers_before_conversation_limit() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="alpha",
        source_limit=4,
    )

    assert len(pool.cursor.executions) == 1
    rendered = pool.cursor.executions[0][0].as_string()
    for source_table in (
        "public.conversations",
        "public.messages",
        "public.backtest_runs",
        "public.ideas",
        "public.evidence_artifacts",
        "public.decision_notes",
    ):
        assert source_table in rendered
    assert "message.role = 'user'" in rendered
    assert "row_number() over" in rendered
    assert "partition by matches.conversation_id" in rendered
    assert rendered.rfind("limit") > rendered.rfind("partition by")
    # Each child layer joins its canonical active conversation before grouping.
    assert rendered.count("conversation.deleted_at is null") >= 7


def test_conversation_symbol_rank_uses_canonical_expanding_casefold() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="ss/eur",
        source_limit=2,
    )

    rendered = pool.cursor.executions[0][0].as_string()
    assert (
        "btrim(public.argus_search_symbol_casefold(" 'symbol_run.symbols[1])) collate "C"'
    ) in rendered
    assert "input.symbol_query = lower(symbol)" not in rendered


def test_asset_rollup_is_one_bounded_owner_scoped_row_outside_conversation_limit() -> (
    None
):
    reader_type, _ = _reader_types()
    pool = _RecordingPool(
        [
            [
                {
                    "source_type": "asset_rollup",
                    "payload": {
                        "type": "asset_rollup",
                        "symbol": "TSLA",
                        "run_count": 12,
                        "decision_counts": {
                            "promising": 3,
                            "watching": 2,
                            "rejected": 1,
                            "revisit_later": 0,
                        },
                        "last_touched_at": ACTIVITY_AT,
                    },
                }
            ]
        ]
    )

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="tsl",
        source_limit=4,
    )

    assert result.rows["conversations"] == []
    assert result.asset_rollup is not None
    assert result.asset_rollup.symbol == "TSLA"
    assert result.asset_rollup.run_count == 12
    assert len(pool.cursor.executions) == 1
    rendered, params = pool.cursor.executions[0]
    sql_text = rendered.as_string()
    assert "count(distinct lineage.run_id)" in sql_text
    assert "count(distinct lineage.run_id) filter" in sql_text
    assert "conversation.deleted_at is null" in sql_text
    assert "run.status = 'completed'" in sql_text
    assert "limit 1" in sql_text
    assert "conversation_page" in sql_text
    assert sql_text.index("limit (select source_limit from input)") < sql_text.index(
        "'asset_rollup'::text as source_type"
    )
    assert params["source_limit"] == 4
    assert str(params["user_id"]) == OWNER_ID


def test_asset_rollup_bounds_indexed_symbol_candidates_before_lineage_hydration() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="gold",
        source_limit=4,
    )

    rendered, params = pool.cursor.executions[0]
    sql_text = rendered.as_string()
    symbol_candidates = sql_text.index("asset_symbol_candidates as (")
    candidate_limit = sql_text.index(
        "limit (select asset_symbol_limit from input)",
        symbol_candidates,
    )
    lineage = sql_text.index("asset_run_lineage as (")

    assert symbol_candidates < candidate_limit < lineage
    candidate_sql = sql_text[symbol_candidates:candidate_limit]
    assert 'btrim(public.argus_search_symbol_casefold(run.symbols[1])) collate "C"' in (
        candidate_sql
    )
    assert "input.symbol_query" in candidate_sql
    assert "input.symbol_prefix_end" in candidate_sql
    assert "public.evidence_artifacts" not in candidate_sql
    assert "public.decision_notes" not in candidate_sql
    selected_symbol = sql_text.index("asset_selected_symbol as (")
    matching_runs = sql_text.index("asset_matching_runs as materialized (")
    first_evidence_read = sql_text.index(
        "public.evidence_artifacts",
        matching_runs,
    )
    first_decision_read = sql_text.index(
        "public.decision_notes",
        matching_runs,
    )
    asset_rollup = sql_text.index("asset_rollup as (", lineage)
    lineage_sql = sql_text[lineage:asset_rollup]
    assert selected_symbol < matching_runs < first_evidence_read
    assert matching_runs < first_decision_read
    assert "conversation.id" not in lineage_sql
    assert lineage_sql.count("run.conversation_id") == 3
    assert (
        sql_text[symbol_candidates:selected_symbol].count(
            "limit (select asset_symbol_limit from input)"
        )
        == 5
    )
    assert params["asset_symbol_limit"] == 2
    assert params["symbol_query"] == "gold"
    assert params["symbol_prefix_end"] == "gole"


def test_search_guest_workspace_scope_is_inside_every_match_layer_before_limit() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="alpha",
        source_limit=1,
        guest_scope=True,
        guest_conversation_id=CONVERSATION_ID,
    )

    rendered, params = pool.cursor.executions[0]
    sql_text = rendered.as_string()
    asset_start = sql_text.index("asset_symbol_candidates")
    conversation_sql = sql_text[:asset_start]
    asset_sql = sql_text[asset_start:]
    assert sql_text.count("conversation.id = input.guest_conversation_id") >= 6
    assert conversation_sql.rfind(
        "conversation.id = input.guest_conversation_id"
    ) < conversation_sql.rfind("row_number() over")
    assert "conversation.id = input.guest_conversation_id" in asset_sql
    assert str(params["guest_conversation_id"]) == CONVERSATION_ID
    assert params["source_limit"] == 1


def test_search_decision_filter_and_ledger_match_all_conversation_layers() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[], []])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="alpha",
        source_limit=4,
        decision_state="watching",
        include_ledger_groups=True,
    )

    candidate_sql = pool.cursor.executions[0][0].as_string()
    ledger_sql = pool.cursor.executions[1][0].as_string()
    for source_table in (
        "public.conversations",
        "public.backtest_runs",
        "public.ideas",
        "public.evidence_artifacts",
        "public.decision_notes",
    ):
        assert source_table in candidate_sql
        assert source_table in ledger_sql
    assert "count(distinct conversation_id)" in ledger_sql
    assert pool.cursor.executions[1][1]["decision_state"] is None


@pytest.mark.parametrize("has_anchor", [False, True])
def test_search_decision_filter_precedes_every_source_match_cap(
    has_anchor: bool,
) -> None:
    from argus.domain.postgres_search_reader import (
        _DECISION_ATTACHMENTS,
        _conversation_match_ctes,
    )

    # Five non-decision sources, plus one decision branch per discovery index:
    # the decision's own note and state, and each attachment's text.
    decision_branches = 1 + len(_DECISION_ATTACHMENTS) if has_anchor else 1
    expected_prefilter_count = 5 + decision_branches
    sql_text = " ".join(
        _conversation_match_ctes(has_anchor=has_anchor).as_string().split()
    )
    bounded_sources = sql_text[: sql_text.index("winning_matches as (")]

    assert (
        bounded_sources.count("source_decision.decision_state = input.decision_state")
        == expected_prefilter_count
    )
    assert bounded_sources.rfind(
        "source_decision.decision_state = input.decision_state"
    ) < bounded_sources.rfind("limit (select match_limit from input)")


def test_conversation_ledger_counts_use_indexed_uncapped_match_membership() -> None:
    from argus.domain.postgres_search_reader import _conversation_ledger_sql

    sql_text = " ".join(_conversation_ledger_sql(has_anchor=True).as_string().split())

    assert "ranked_conversations" not in sql_text
    assert "match_limit" not in sql_text
    assert "limit (select match_limit from input)" not in sql_text
    assert sql_text.count("like %(anchor_pattern)s") >= 7
    assert "count(distinct conversation_id)::integer as count" in sql_text
    assert "group by decision_state" in sql_text


def test_search_cursor_pivots_on_conversation_projection_and_canonical_activity() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[_conversation_candidate()], []])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="Alpha x",
        source_limit=4,
        cursor_updated_at=datetime(2026, 7, 27, 12, tzinfo=timezone.utc),
        cursor_id=CONVERSATION_ID,
    )

    pivot_query, pivot_params = pool.cursor.executions[0]
    rendered = pivot_query.as_string()
    assert "ranked.conversation_id = input.cursor_id" in rendered
    assert "ranked.activity_at = input.cursor_updated_at" in rendered
    assert "run.id = %(cursor_id)s::uuid" not in rendered
    assert "decision.id = %(cursor_id)s::uuid" not in rendered
    page_params = pool.cursor.executions[1][1]
    assert page_params["cursor_layer_rank"] == 6
    assert pivot_params["cursor_id"] == page_params["cursor_id"]


def test_search_hydration_is_one_owner_scoped_full_aggregate_without_child_cap() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[_conversation_candidate()], [_hydration_row()]])

    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="search",
        source_limit=4,
    )

    assert result.rows["conversations"][0]["_recall_summary"] == {
        "run_count": 7,
        "total_runs": 7,
        "decided_runs": 5,
        "symbols": ["AAPL", "MSFT"],
        "strategy_families": ["buy_and_hold"],
        "start_date": "2019-01-01",
        "end_date": "2026-07-27",
        "decision_states": ["promising", "watching"],
        "latest_run_decided": False,
        "latest_suggestion_untaken": False,
        "latest_activity": ACTIVITY_AT,
    }
    assert [row["conversation_id"] for row in result.rows["runs"]] == [CONVERSATION_ID]
    assert len(pool.cursor.executions) == 2
    hydration_sql, params = pool.cursor.executions[1]
    rendered = str(hydration_sql)
    assert "recall_rank <= 5" not in rendered
    assert "count(*)::integer as run_count" in rendered
    assert "select distinct decision.decision_state" in rendered
    assert "min(" in rendered and "max(" in rendered
    assert "limit 1" in rendered
    assert params["conversation_ids"] == [CONVERSATION_ID]
    assert str(params["user_id"]) == OWNER_ID


def test_search_hydration_projects_only_a_bounded_untaken_suggestion_bit() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[_conversation_candidate()], [_hydration_row()]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="search",
        source_limit=4,
    )

    hydration_sql = " ".join(str(pool.cursor.executions[1][0]).split())
    assert "'latest_suggestion_untaken'" in hydration_sql
    assert "offer.metadata->>'result_run_id' = latest_run.id::text" in hydration_sql
    assert "argus_next_experiments/v1" in hydration_sql
    assert "not exists" in hydration_sql
    assert "later_message.role = 'user'" in hydration_sql
    assert "latest_suggestion.untaken" in hydration_sql
    assert "'content', offer.content" not in hydration_sql
    assert "'metadata', offer.metadata" not in hydration_sql


def test_search_hydration_activity_mirrors_ranked_message_activity_scope() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[_conversation_candidate()], [_hydration_row()]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="search",
        source_limit=4,
    )

    ranking_sql = " ".join(pool.cursor.executions[0][0].as_string().split())
    hydration_sql = " ".join(str(pool.cursor.executions[1][0]).split())
    assert (
        "select max(message.created_at) "
        "from public.messages as message "
        "where message.user_id = input.user_id "
        "and message.conversation_id = conversation.id"
    ) in ranking_sql
    assert (
        "select max(message.created_at) "
        "from public.messages as message "
        "where message.user_id = %(user_id)s "
        "and message.conversation_id = conversation.id"
    ) in hydration_sql


def test_search_full_aggregate_projects_exact_dossier_without_hydrating_all_children() -> (
    None
):
    from argus.api.search_assembly import scored_supabase_search_items

    reader_type, _ = _reader_types()
    pool = _RecordingPool([[_conversation_candidate()], [_hydration_row()]])
    result = reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="search",
        source_limit=4,
    )

    scored = scored_supabase_search_items(raw=result.rows, query="search")

    assert len(scored) == 1
    _, item = scored[0]
    assert item.id == CONVERSATION_ID
    assert item.matched_text == "Search decision evidence"
    assert item.updated_at.isoformat() == ACTIVITY_AT
    assert item.decision_states == ("promising", "watching")
    assert item.total_runs == 7
    assert item.decided_runs == 5
    assert item.dossier is not None
    assert item.dossier.run_id == "00000000-0000-0000-0000-000000000401"
    assert item.dossier.result_message_id == "00000000-0000-0000-0000-000000000201"
    assert item.dossier.tested.symbols == ["AAPL"]
    assert item.dossier.tested.start_date.isoformat() == "2025-01-01"
    assert item.dossier.decision is not None
    assert item.dossier.decision.run_label == "Latest run"
    assert item.dossier.outcome.run_label == "Latest run"
    assert [action.type for action in item.dossier.actions] == [
        "retest_run",
        "decision",
    ]
    decision_action = item.dossier.actions[1]
    assert decision_action.type == "decision"
    assert decision_action.availability == "available"
    assert decision_action.evidence_artifact_id == (
        "00000000-0000-0000-0000-000000000301"
    )
    assert decision_action.decision_state == "watching"
    legacy_scored = scored_supabase_search_items(
        raw=result.rows,
        query="search",
        decision_action_availability=None,
    )
    assert legacy_scored[0][1].dossier is not None
    assert [action.type for action in legacy_scored[0][1].dossier.actions] == [
        "retest_run"
    ]
    hydration_sql = str(pool.cursor.executions[1][0])
    assert "latest_run_decision_payload" in hydration_sql
    assert "decision.evidence_artifact_id" in hydration_sql


def test_persistent_title_match_never_trusts_an_unrelated_preview_hint() -> None:
    from argus.api.search_assembly import scored_supabase_search_items

    candidate = _conversation_candidate()
    candidate["payload"].update(
        {
            "title": "Gold allocation",
            "last_message_preview": "Review again later",
            "_recall_match": {
                "matched_text": "Review again later",
                "layer_rank": 1,
                "symbol_exact_match": False,
                "activity_at": ACTIVITY_AT,
            },
        }
    )
    hydration = _hydration_row()
    hydration["conversation_payload"].update(
        {
            "title": "Gold allocation",
            "last_message_preview": "Review again later",
        }
    )
    reader_type, _ = _reader_types()
    result = reader_type(_RecordingPool([[candidate], [hydration]])).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="gold",
        source_limit=4,
    )

    scored = scored_supabase_search_items(raw=result.rows, query="gold")

    assert len(scored) == 1
    _, item = scored[0]
    assert item.matched_text == "Gold allocation"


def test_persistent_preview_match_returns_preview_with_unrelated_title() -> None:
    from argus.api.search_assembly import scored_supabase_search_items

    candidate = _conversation_candidate()
    candidate["payload"].update(
        {
            "title": "Review again later",
            "last_message_preview": "Gold allocation",
            "_recall_match": {
                "matched_text": "Gold allocation",
                "layer_rank": 1,
                "symbol_exact_match": False,
                "activity_at": ACTIVITY_AT,
            },
        }
    )
    hydration = _hydration_row()
    hydration["conversation_payload"].update(
        {
            "title": "Review again later",
            "last_message_preview": "Gold allocation",
        }
    )
    reader_type, _ = _reader_types()
    result = reader_type(_RecordingPool([[candidate], [hydration]])).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="gold",
        source_limit=4,
    )

    scored = scored_supabase_search_items(raw=result.rows, query="gold")

    assert len(scored) == 1
    _, item = scored[0]
    assert item.matched_text == "Gold allocation"


def test_conversation_recall_anchor_predicates_match_the_shipped_indexes() -> None:
    from argus.domain.postgres_search_reader import (
        _DECISION_INDEX_HAYSTACK,
        _EVIDENCE_INDEX_HAYSTACK,
        _RUN_INDEX_HAYSTACK,
        _conversation_match_ctes,
        _normalized,
    )

    rendered = " ".join(_conversation_match_ctes(has_anchor=True).as_string().split())
    indexed_haystacks = (
        (
            "conversation.title || ' ' "
            "|| coalesce(conversation.last_message_preview, '')"
        ),
        "message.content",
        _RUN_INDEX_HAYSTACK,
        "idea.title || ' ' || coalesce(idea.summary, '')",
        _EVIDENCE_INDEX_HAYSTACK,
        _DECISION_INDEX_HAYSTACK,
    )

    for haystack in indexed_haystacks:
        normalized = " ".join(_normalized(haystack).as_string().split())
        assert f"{normalized} like %(anchor_pattern)s" in rendered


def test_decision_match_combines_owned_evidence_text_with_indexed_prefilters() -> None:
    from argus.domain.postgres_search_reader import (
        _DECISION_ATTACHMENTS,
        _DECISION_INDEX_HAYSTACK,
        _conversation_match_ctes,
        _normalized,
    )

    rendered = " ".join(_conversation_match_ctes(has_anchor=True).as_string().split())
    decision_branch = rendered[: rendered.index(" matches as (")]

    # Every attachment is left-joined so a decision without evidence lineage
    # still matches; each attachment's index also discovers candidates.
    assert (
        "left join public.evidence_artifacts as evidence "
        "on evidence.id = decision.evidence_artifact_id"
    ) in decision_branch
    assert "decision.evidence_artifact_id = evidence.id" in decision_branch
    assert "decision.source_message_id = decision_message.id" in decision_branch
    assert "union all" in decision_branch
    assert "select distinct on (candidate.source_id)" in decision_branch
    indexes = [_DECISION_INDEX_HAYSTACK, *(a.index_text for a in _DECISION_ATTACHMENTS)]
    for haystack in indexes:
        normalized = " ".join(_normalized(haystack).as_string().split())
        assert f"{normalized} like %(anchor_pattern)s" in decision_branch
    assert "nullif(evidence.digest, '')" in decision_branch
    assert decision_branch.count("unnest(%(token_patterns)s::text[])") == len(indexes)


def test_conversation_recall_caps_every_source_before_window_ranking() -> None:
    reader_type, _ = _reader_types()
    pool = _RecordingPool([[]])

    reader_type(pool).search_rows(
        scope=PERSONAL,
        user_id=OWNER_ID,
        query="the",
        source_limit=30,
    )

    rendered, params = pool.cursor.executions[0]
    sql_text = rendered.as_string()
    normalized_sql = " ".join(sql_text.split())
    assert "%(match_limit)s::integer as match_limit" in sql_text
    bounded_matches = normalized_sql[
        normalized_sql.index("matches as (") : normalized_sql.index(
            "winning_matches as ("
        )
    ]
    assert bounded_matches.count("limit (select match_limit from input)") == 6
    assert (
        bounded_matches.count(
            "count(*) over ( partition by source_match.conversation_id )"
        )
        == 6
    )
    assert (
        bounded_matches.count(
            "row_number() over ( partition by source_match.conversation_id "
            "order by source_match.candidate_at desc, source_match.matched_text "
            'collate "und-x-icu" desc, source_match.source_id desc )'
        )
        == 6
    )
    for bounded_window in bounded_matches.split("limit (select match_limit from input)")[
        :-1
    ]:
        assert "count(*) over" in bounded_window
        assert "row_number() over" in bounded_window
    winning_matches = sql_text[
        sql_text.index("winning_matches as (") : sql_text.index(
            "ranked_conversations as ("
        )
    ]
    assert "count(*) over" not in winning_matches
    assert params["match_limit"] == 300


def test_conversation_recall_adds_bounded_cursor_relative_source_windows() -> None:
    from argus.domain.postgres_search_reader import _conversation_match_ctes

    sql_text = " ".join(
        _conversation_match_ctes(
            has_anchor=False,
            has_cursor=True,
        )
        .as_string()
        .split()
    )
    base_matches = sql_text[
        sql_text.index("base_matches as (") : sql_text.index("cursor_matches as (")
    ]
    cursor_matches = sql_text[
        sql_text.index("cursor_matches as (") : sql_text.index("winning_matches as (")
    ]

    assert base_matches.count("limit (select match_limit from input)") == 6
    assert base_matches.count("select max(source_activity.activity_at)") == 6
    assert base_matches.count("order by conversation.pinned::integer desc") == 6
    assert base_matches.count("source_winner.layer_rank desc") == 6
    assert base_matches.count("conversation.id desc") >= 6
    assert cursor_matches.count("limit (select match_limit from input)") == 6
    bounded_cursor_windows = cursor_matches
    assert bounded_cursor_windows.count("order by conversation.pinned::integer desc") == 6
    assert bounded_cursor_windows.count("input.has_cursor") == 6
    assert bounded_cursor_windows.count("conversation.id = input.cursor_id") == 6
    assert bounded_cursor_windows.count(") <= row(") == 6
    assert bounded_cursor_windows.count("conversation.pinned::integer") == 12
    assert bounded_cursor_windows.count("input.cursor_exact_rank") == 6
    assert bounded_cursor_windows.count("input.cursor_symbol_rank") == 6
    assert bounded_cursor_windows.count("input.cursor_layer_rank") == 6
    assert bounded_cursor_windows.count("input.cursor_updated_at") == 6
    assert bounded_cursor_windows.count("input.cursor_text_rank") == 6
    assert bounded_cursor_windows.count("input.cursor_id") == 12
    assert bounded_cursor_windows.count("conversation.id desc") >= 6
    assert bounded_cursor_windows.count("select max(source_activity.activity_at)") == 12
    candidate_keys = bounded_cursor_windows.split(") <= row(")[:-1]
    assert len(candidate_keys) == 6
    for candidate_key in candidate_keys:
        candidate_key = candidate_key[candidate_key.rfind("row(") :]
        assert (
            candidate_key.index("conversation.pinned::integer")
            < candidate_key.index("input.normalized_query <> ''")
            < candidate_key.index("symbol_run.conversation_id = conversation.id")
            < candidate_key.index("source_winner.layer_rank")
        )

    anchored_sql = " ".join(
        _conversation_match_ctes(
            has_anchor=True,
            has_cursor=True,
        )
        .as_string()
        .split()
    )
    anchored_decisions = anchored_sql[
        anchored_sql.index("decision_candidates as (") : anchored_sql.index(
            "base_matches as ("
        )
    ]
    anchored_cursor_matches = anchored_sql[
        anchored_sql.index("cursor_matches as (") : anchored_sql.index(
            "winning_matches as ("
        )
    ]
    # One anchored discovery per index: the decision's own note and state,
    # and each attachment's text.
    from argus.domain.postgres_search_reader import _DECISION_ATTACHMENTS

    assert anchored_decisions.count("like %(anchor_pattern)s") == 1 + len(
        _DECISION_ATTACHMENTS
    )
    assert "select distinct on (candidate.source_id)" in anchored_decisions
    assert "limit (select match_limit from input)" not in anchored_decisions
    assert (
        anchored_cursor_matches.count("order by conversation.pinned::integer desc") == 6
    )
    assert anchored_cursor_matches.count("limit (select match_limit from input)") == 6


def test_conversation_recall_match_cap_has_an_absolute_ceiling() -> None:
    from argus.domain.postgres_search_reader import _conversation_match_limit

    assert _conversation_match_limit(1) == 10
    assert _conversation_match_limit(101) == 1_010
    assert _conversation_match_limit(1_000) == 1_010

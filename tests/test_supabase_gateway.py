from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call

import pytest
from argus.api.schemas import BacktestRun, Message
from argus.domain.backtest_finalization import (
    BacktestFinalizationInput,
    finalize_backtest_completion,
)
from argus.domain.evidence import build_backtest_evidence_capture, build_decision_note
from argus.domain.owner_scope import PERSONAL
from argus.domain.postgres_search_reader import SearchReadResult
from argus.domain.search_text import search_text_matches_query
from argus.domain.store import utcnow
from argus.domain.supabase_conversation_messages import (
    ConversationMessagePersistenceMixin,
)
from argus.domain.supabase_gateway import (
    DecisionCaptureIntegrityError,
    QuotaExceededError,
    SupabaseGateway,
)


def test_gateway_inherits_focused_conversation_message_persistence() -> None:
    assert issubclass(SupabaseGateway, ConversationMessagePersistenceMixin)
    for method_name in (
        "get_message",
        "latest_message",
        "create_message",
        "claim_response_option_action",
    ):
        assert method_name not in SupabaseGateway.__dict__


def test_batched_fetch_helper_exists_for_unbounded_queries():
    gateway = SupabaseGateway(client=MagicMock())
    assert hasattr(gateway, "_fetch_all_rows")


def test_list_messages_projects_completed_workflow_result_for_reload() -> None:
    client = MagicMock()
    gateway = SupabaseGateway(client=client)
    queued = Message(
        id="message-1",
        conversation_id="conversation-1",
        role="assistant",
        content="Queued",
        metadata={
            "backtest_job_id": "job-1",
            "backtest_job": {"id": "job-1", "status": "queued"},
        },
        created_at=utcnow(),
    )
    gateway._fetch_all_rows = MagicMock(  # type: ignore[method-assign]
        return_value=[queued.model_dump(mode="json")]
    )
    gateway.get_backtest_jobs_by_ids = MagicMock(  # type: ignore[method-assign]
        return_value={
            "job-1": {
                "id": "job-1",
                "conversation_id": "conversation-1",
                "status": "succeeded",
                "result_run_id": "run-1",
                "execution_metadata": {
                    "workflow_backtest": {"result_readout": "Completed readout"}
                },
            }
        }
    )
    gateway.get_backtest_runs_by_ids = MagicMock(  # type: ignore[method-assign]
        return_value={
            "run-1": BacktestRun(
                id="run-1",
                conversation_id="conversation-1",
                strategy_id=None,
                status="completed",
                asset_class="equity",
                symbols=["AAPL"],
                allocation_method="equal_weight",
                benchmark_symbol="SPY",
                metrics={},
                config_snapshot={"template": "buy_and_hold"},
                conversation_result_card={
                    "title": "AAPL result",
                    "evidence_artifact_id": "evidence-1",
                    "decision_note_id": "decision-1",
                    "decision_state": "promising",
                },
                created_at=utcnow(),
                chart=None,
                trades=[],
            )
        }
    )

    messages = gateway.list_messages(
        user_id="user-1",
        conversation_id="conversation-1",
        limit=None,
    )

    assert messages[0].content == "Completed readout"
    assert messages[0].metadata["result_card"]["decision_note_id"] == "decision-1"
    gateway.get_backtest_jobs_by_ids.assert_called_once_with(
        user_id="user-1",
        conversation_id="conversation-1",
        job_ids=["job-1"],
    )
    gateway.get_backtest_runs_by_ids.assert_called_once_with(
        user_id="user-1",
        conversation_id="conversation-1",
        run_ids=["run-1"],
    )


def _message_query_mock(*, row: dict[str, Any]) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    query = MagicMock()
    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = SimpleNamespace(data=[row])
    return client, query


def test_get_message_scopes_lookup_to_owner_conversation_and_message_id() -> None:
    client, query = _message_query_mock(
        row={
            "id": "assistant-1",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Choose a timeframe.",
            "metadata": {},
            "created_at": "2026-07-17T10:00:00+00:00",
        }
    )
    gateway = SupabaseGateway(client=client)

    message = gateway.get_message(
        user_id="user-1",
        conversation_id="conversation-1",
        message_id="assistant-1",
    )

    assert message is not None
    assert message.id == "assistant-1"
    assert query.eq.call_args_list == [
        (("user_id", "user-1"),),
        (("conversation_id", "conversation-1"),),
        (("id", "assistant-1"),),
    ]
    query.limit.assert_called_once_with(1)


def test_latest_message_uses_owner_scope_and_descending_bounded_query() -> None:
    client, query = _message_query_mock(
        row={
            "id": "assistant-latest",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Latest recovery.",
            "metadata": {},
            "created_at": "2026-07-17T10:01:00+00:00",
        }
    )
    gateway = SupabaseGateway(client=client)

    message = gateway.latest_message(
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert message is not None
    assert message.id == "assistant-latest"
    assert query.eq.call_args_list == [
        (("user_id", "user-1"),),
        (("conversation_id", "conversation-1"),),
    ]
    assert query.order.call_args_list == [
        (("created_at",), {"desc": True}),
        (("id",), {"desc": True}),
    ]
    query.limit.assert_called_once_with(1)


def test_conversation_has_user_message_uses_owned_role_scoped_existence_query() -> None:
    client, query = _message_query_mock(
        row={
            "id": "user-message-1",
            "conversation_id": "conversation-1",
            "role": "user",
            "content": "Test Apple.",
            "metadata": {},
            "created_at": "2026-07-17T10:00:00+00:00",
        }
    )
    gateway = SupabaseGateway(client=client)

    exists = gateway.conversation_has_user_message(
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert exists is True
    assert query.eq.call_args_list == [
        (("user_id", "user-1"),),
        (("conversation_id", "conversation-1"),),
        (("role", "user"),),
    ]
    query.limit.assert_called_once_with(1)


def _json_filter_value(row: dict[str, Any], key: str) -> object:
    value: object = row
    for part in key.replace("->>", "->").split("->"):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class _DecisionResultClient:
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_table = rows_by_table
        self.queries: list[_DecisionResultQuery] = []

    def table(self, table_name: str) -> "_DecisionResultQuery":
        query = _DecisionResultQuery(self, table_name)
        self.queries.append(query)
        return query


class _DecisionResultQuery:
    def __init__(self, client: _DecisionResultClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload: dict[str, Any] | None = None
        self.equal_filters: list[tuple[str, object]] = []
        self.in_filters: list[tuple[str, tuple[object, ...]]] = []
        self.range_window: tuple[int, int] | None = None
        self.executed = False

    def select(self, _columns: str) -> "_DecisionResultQuery":
        self.operation = "select"
        return self

    def update(self, payload: dict[str, Any]) -> "_DecisionResultQuery":
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, key: str, value: object) -> "_DecisionResultQuery":
        self.equal_filters.append((key, value))
        return self

    def in_(self, key: str, values: list[object]) -> "_DecisionResultQuery":
        self.in_filters.append((key, tuple(values)))
        return self

    def order(
        self,
        _column: str,
        *,
        desc: bool = False,
    ) -> "_DecisionResultQuery":
        return self

    def range(self, start: int, end: int) -> "_DecisionResultQuery":
        self.range_window = (start, end)
        return self

    def execute(self) -> SimpleNamespace:
        self.executed = True
        rows = [
            row
            for row in self.client.rows_by_table[self.table_name]
            if all(
                _json_filter_value(row, key) == value for key, value in self.equal_filters
            )
            and all(
                _json_filter_value(row, key) in values for key, values in self.in_filters
            )
        ]
        if self.operation == "update":
            assert self.payload is not None
            for row in rows:
                row.update(self.payload)
            return SimpleNamespace(data=rows)
        if self.range_window is not None:
            start, end = self.range_window
            rows = rows[start : end + 1]
        return SimpleNamespace(data=rows)


def test_decision_enrichment_targets_every_direct_and_projected_result_identity() -> None:
    now = utcnow()
    run = BacktestRun(
        id="run-1",
        conversation_id="conversation-1",
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={},
        config_snapshot={"template": "buy_and_hold"},
        conversation_result_card={
            "title": "AAPL result",
            "evidence_artifact_id": "evidence-1",
        },
        created_at=now,
        chart=None,
        trades=[],
    )
    messages = [
        {
            "id": "direct-run",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Completed.",
            "metadata": {
                "result_run_id": "run-1",
                "result_card": {
                    "title": "Direct result",
                    "evidence_artifact_id": "evidence-1",
                },
            },
            "created_at": now.isoformat(),
        },
        {
            "id": "direct-artifact",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Saved result.",
            "metadata": {
                "result_card": {
                    "title": "Artifact result",
                    "evidence_artifact_id": "evidence-1",
                }
            },
            "created_at": now.isoformat(),
        },
        {
            "id": "projected-root-alias",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Queued.",
            "metadata": {
                "backtest_job_id": "job-1",
                "backtest_job": {"id": "job-1", "status": "queued"},
            },
            "created_at": now.isoformat(),
        },
        {
            "id": "projected-nested-alias",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Queued.",
            "metadata": {
                "backtest_job": {"id": "job-1", "status": "queued"},
            },
            "created_at": now.isoformat(),
        },
        {
            "id": "unrelated-result",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "role": "assistant",
            "content": "Other result.",
            "metadata": {
                "result_run_id": "run-2",
                "result_card": {
                    "title": "Other",
                    "evidence_artifact_id": "evidence-2",
                },
            },
            "created_at": now.isoformat(),
        },
    ]
    client = _DecisionResultClient(
        {
            "messages": messages,
            "backtest_jobs": [
                {
                    "id": "job-1",
                    "user_id": "user-1",
                    "conversation_id": "conversation-1",
                    "status": "succeeded",
                    "result_run_id": "run-1",
                    "execution_metadata": {
                        "workflow_backtest": {"result_readout": "Completed."}
                    },
                }
            ],
        }
    )
    gateway = SupabaseGateway(client=client)  # type: ignore[arg-type]
    gateway.get_backtest_run = MagicMock(return_value=run)  # type: ignore[method-assign]
    gateway.update_backtest_run_result_card = MagicMock(  # type: ignore[method-assign]
        return_value=run
    )
    gateway.list_messages = MagicMock(  # type: ignore[method-assign]
        side_effect=AssertionError("decision enrichment must not scan the transcript")
    )

    gateway.mark_result_card_decision_for_run(
        user_id="user-1",
        run_id="run-1",
        evidence_artifact_id="evidence-1",
        decision_id="decision-1",
        decision_state="promising",
    )

    by_id = {row["id"]: row for row in messages}
    for message_id in (
        "direct-run",
        "direct-artifact",
        "projected-root-alias",
        "projected-nested-alias",
    ):
        metadata = by_id[message_id]["metadata"]
        assert metadata["result_card"]["decision_note_id"] == "decision-1"
        assert metadata["result_card"]["decision_state"] == "promising"
        assert metadata["decision_note_id"] == "decision-1"
        assert metadata["decision_state"] == "promising"
    assert "decision_note_id" not in by_id["unrelated-result"]["metadata"]
    gateway.list_messages.assert_not_called()

    select_queries = [
        query
        for query in client.queries
        if query.operation == "select" and query.executed
    ]
    assert select_queries
    assert all(query.range_window is not None for query in select_queries)
    assert all(
        ("user_id", "user-1") in query.equal_filters
        and ("conversation_id", "conversation-1") in query.equal_filters
        for query in select_queries
    )


def test_conversation_message_append_migration_is_one_locked_service_role_boundary() -> (
    None
):
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "supabase/migrations/20260717000001_serialize_conversation_message_append.sql"
    )

    assert migration_path.exists()
    sql = " ".join(migration_path.read_text().lower().split())
    assert "create or replace function public.append_conversation_message" in sql
    assert "for update" in sql
    assert "order by m.created_at desc, m.id desc" in sql
    assert "m.created_at < v_existing.created_at" in sql
    assert "m.id < v_existing.id" in sql
    assert "interval '1 microsecond'" in sql
    assert "greatest" in sql
    assert "c.user_id = p_user_id" in sql
    assert "m.conversation_id = p_conversation_id" in sql
    assert "jsonb_array_elements" in sql
    assert "p_expected_source_assistant_id" in sql
    assert "p_expected_source_metadata" in sql
    assert "p_option_id" in sql
    assert "p_replacement_values" in sql
    assert "revoke all on function public.append_conversation_message" in sql
    for role in ("public", "anon", "authenticated"):
        assert f"from {role}" in sql
    assert "grant execute on function public.append_conversation_message" in sql
    assert "to service_role" in sql
    assert "revoke insert, update, delete on public.messages" in sql
    assert "from anon, authenticated" in sql

    gateway_source = (
        Path(__file__).resolve().parents[1] / "src/argus/domain/supabase_gateway.py"
    ).read_text()
    message_persistence_source = (
        Path(__file__).resolve().parents[1]
        / "src/argus/domain/supabase_conversation_messages.py"
    ).read_text()
    assert 'table("messages").insert' not in gateway_source
    assert 'table("messages").insert' not in message_persistence_source
    assert (
        'self.client.rpc(\n            "append_conversation_message"'
        in message_persistence_source
    )
    assert gateway_source.count('table("messages").update') == 1
    assert 'table("messages").update({"metadata": metadata})' in gateway_source


def test_supabase_search_matcher_handles_punctuation_and_multi_token_queries():
    assert search_text_matches_query(
        query="AAPL MSFT TSLA",
        text="AAPL, MSFT, TSLA comprar y mantener contra SPY.",
    )
    assert search_text_matches_query(
        query="aap",
        text="AAPL, MSFT, TSLA comprar y mantener contra SPY.",
    )
    assert not search_text_matches_query(
        query="AAPL NVDA",
        text="AAPL, MSFT, TSLA comprar y mantener contra SPY.",
    )


def test_p1_spine_migration_enforces_artifact_truth_immutability() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "supabase/migrations/20260621053126_enforce_p1_evidence_immutability.sql"
    ).read_text()

    assert "prevent_idea_version_immutable_update" in migration
    assert "prevent_evidence_artifact_immutable_update" in migration
    assert "create trigger prevent_idea_versions_immutable_update" in migration
    assert "create trigger prevent_evidence_artifacts_immutable_update" in migration

    for field in (
        "canonical_spec",
        "strategy_snapshot",
        "source_run_id",
        "version_number",
    ):
        assert f"new.{field} is distinct from old.{field}" in migration

    for field in (
        "artifact_type",
        "digest",
        "payload",
        "source_run_id",
        "title",
    ):
        assert f"new.{field} is distinct from old.{field}" in migration

    assert "new.lifecycle is distinct from old.lifecycle" not in migration
    assert "new.updated_at is distinct from old.updated_at" not in migration


class _RecordingSupabaseClient:
    def __init__(self) -> None:
        self.inserted_message: dict[str, object] | None = None
        self.inserted_by_table: dict[str, dict[str, object]] = {}

    def table(self, table_name: str):
        return _RecordingTable(self, table_name)

    def rpc(self, function_name: str, params: dict[str, object]):
        assert function_name == "append_conversation_message"
        self.inserted_message = {
            "user_id": params["p_user_id"],
            "conversation_id": params["p_conversation_id"],
            "role": params["p_role"],
            "content": params["p_content"],
            "metadata": params["p_metadata"],
            "created_at": params["p_created_at"],
        }
        return _RecordingMessageRpc(params)


class _RecordingMessageRpc:
    def __init__(self, params: dict[str, object]) -> None:
        self.params = params

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(
            data=[
                {
                    "message": {
                        "id": self.params["p_message_id"],
                        "conversation_id": self.params["p_conversation_id"],
                        "role": self.params["p_role"],
                        "content": self.params["p_content"],
                        "metadata": self.params["p_metadata"],
                        "created_at": self.params["p_created_at"],
                    },
                    "source_message": None,
                    "replayed": False,
                }
            ]
        )


class _RecordingTable:
    def __init__(self, client: _RecordingSupabaseClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.payload: dict[str, object] = {}

    def insert(self, payload: dict[str, object]):
        if self.table_name == "messages":
            self.client.inserted_message = payload
        self.client.inserted_by_table[self.table_name] = payload
        self.payload = payload
        return self

    def update(self, payload: dict[str, object]):
        self.payload = payload
        return self

    def eq(self, *_args: object):
        return self

    def execute(self):
        if self.table_name == "messages":
            return SimpleNamespace(data=[{"id": "msg-1", **self.payload}])
        return SimpleNamespace(data=[self.payload])


class _SerializedMessageRpcCall:
    def __init__(self, client: "_SerializedMessageRpcClient", params: dict[str, Any]):
        self.client = client
        self.params = params

    def execute(self) -> SimpleNamespace:
        with self.client.lock:
            message_id = str(self.params["p_message_id"])
            existing = next(
                (
                    message
                    for message in self.client.messages
                    if message["id"] == message_id
                ),
                None,
            )
            if existing is not None:
                preceding = [
                    message
                    for message in self.client.messages
                    if (message["created_at"], message["id"])
                    < (existing["created_at"], existing["id"])
                ]
                source = (
                    max(
                        preceding,
                        key=lambda message: (
                            message["created_at"],
                            message["id"],
                        ),
                    )
                    if preceding
                    else None
                )
                return SimpleNamespace(
                    data=[
                        {
                            "message": existing,
                            "source_message": source,
                            "replayed": True,
                        }
                    ]
                )

            expected_source_id = self.params.get("p_expected_source_assistant_id")
            source = None
            if expected_source_id is not None:
                latest = max(
                    self.client.messages,
                    key=lambda message: (message["created_at"], message["id"]),
                )
                source = next(
                    (
                        message
                        for message in self.client.messages
                        if message["id"] == expected_source_id
                    ),
                    None,
                )
                options = (
                    source.get("metadata", {}).get("clarification", {}).get("options", [])
                    if source is not None
                    else []
                )
                if (
                    latest["id"] != expected_source_id
                    or source is None
                    or source["role"] != "assistant"
                    or (
                        self.params.get("p_expected_source_metadata") is not None
                        and source.get("metadata")
                        != self.params.get("p_expected_source_metadata")
                    )
                    or not any(
                        option.get("id") == self.params.get("p_option_id")
                        and option.get("replacement_values")
                        == self.params.get("p_replacement_values")
                        for option in options
                    )
                ):
                    return SimpleNamespace(data=[])

            message = {
                "id": message_id,
                "conversation_id": self.params["p_conversation_id"],
                "role": self.params["p_role"],
                "content": self.params["p_content"],
                "metadata": self.params["p_metadata"],
                "created_at": self._next_created_at(),
            }
            self.client.messages.append(message)
            if source is not None:
                self.client.source_by_request[message_id] = source
            return SimpleNamespace(
                data=[
                    {
                        "message": message,
                        "source_message": source,
                        "replayed": False,
                    }
                ]
            )

    def _next_created_at(self) -> str:
        requested = datetime.fromisoformat(str(self.params["p_created_at"]))
        if not self.client.messages:
            return requested.isoformat()
        latest = max(
            datetime.fromisoformat(str(message["created_at"]))
            for message in self.client.messages
        )
        return max(requested, latest + timedelta(microseconds=1)).isoformat()


class _SerializedMessageRpcClient:
    def __init__(self, *, messages: list[dict[str, Any]]) -> None:
        self.messages = list(messages)
        self.source_by_request: dict[str, dict[str, Any]] = {}
        self.lock = RLock()
        self.claim_started = Event()
        self.append_started = Event()

    def rpc(self, function_name: str, params: dict[str, Any]):
        assert function_name == "append_conversation_message"
        if params.get("p_expected_source_assistant_id") is None:
            self.append_started.set()
        else:
            self.claim_started.set()
        return _SerializedMessageRpcCall(self, params)


def _serialized_source_message() -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000301",
        "conversation_id": "00000000-0000-0000-0000-000000000302",
        "role": "assistant",
        "content": "AAPL needs a supported timeframe.",
        "metadata": {
            "clarification": {
                "options": [
                    {
                        "id": "option_0",
                        "replacement_values": {"timeframe": "1D"},
                    }
                ]
            }
        },
        "created_at": "2026-07-17T12:00:00+00:00",
    }


def _response_option_request(message_id: str) -> Message:
    return Message(
        id=message_id,
        conversation_id="00000000-0000-0000-0000-000000000302",
        role="user",
        content="Retry with daily bars",
        metadata={"chat_action": {"type": "select_response_option"}},
        created_at=utcnow(),
    )


def _claim_response_option(
    gateway: SupabaseGateway,
    *,
    request_message: Message,
) -> tuple[Message, Message] | None:
    claim = getattr(gateway, "claim_response_option_action", None)
    assert callable(claim)
    return claim(
        user_id="00000000-0000-0000-0000-000000000303",
        conversation_id=request_message.conversation_id,
        source_assistant_id="00000000-0000-0000-0000-000000000301",
        option_id="option_0",
        replacement_values={"timeframe": "1D"},
        request_message=request_message,
    )


def test_supabase_newer_message_wins_before_response_option_admission() -> None:
    client = _SerializedMessageRpcClient(messages=[_serialized_source_message()])
    gateway = SupabaseGateway(client=client)
    request_message = _response_option_request("00000000-0000-0000-0000-000000000304")

    executor = ThreadPoolExecutor(max_workers=1)
    client.lock.acquire()
    try:
        claimed = executor.submit(
            _claim_response_option,
            gateway,
            request_message=request_message,
        )
        assert client.claim_started.wait(timeout=5)
        gateway.create_message(
            user_id="00000000-0000-0000-0000-000000000303",
            conversation_id=request_message.conversation_id,
            role="assistant",
            content="NVDA needs a supported timeframe.",
            metadata={"clarification": {"options": []}},
        )
    finally:
        client.lock.release()

    assert claimed.result(timeout=5) is None
    executor.shutdown()


def test_supabase_response_option_admission_wins_before_newer_message() -> None:
    client = _SerializedMessageRpcClient(messages=[_serialized_source_message()])
    gateway = SupabaseGateway(client=client)
    request_message = _response_option_request("00000000-0000-0000-0000-000000000305")

    executor = ThreadPoolExecutor(max_workers=1)
    client.lock.acquire()
    try:
        newer_message = executor.submit(
            gateway.create_message,
            user_id="00000000-0000-0000-0000-000000000303",
            conversation_id=request_message.conversation_id,
            role="assistant",
            content="NVDA needs a supported timeframe.",
            metadata={"clarification": {"options": []}},
        )
        assert client.append_started.wait(timeout=5)
        accepted = _claim_response_option(
            gateway,
            request_message=request_message,
        )
    finally:
        client.lock.release()

    assert accepted is not None
    source_message, accepted_request = accepted
    assert source_message.id == "00000000-0000-0000-0000-000000000301"
    assert accepted_request.id == request_message.id
    assert newer_message.result(timeout=5).content == (
        "NVDA needs a supported timeframe."
    )
    executor.shutdown()


def test_supabase_duplicate_response_option_click_is_exactly_once_and_replay_safe() -> (
    None
):
    client = _SerializedMessageRpcClient(messages=[_serialized_source_message()])
    gateway = SupabaseGateway(client=client)
    first_request = _response_option_request("00000000-0000-0000-0000-000000000306")
    second_request = _response_option_request("00000000-0000-0000-0000-000000000307")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda request_message: _claim_response_option(
                    gateway,
                    request_message=request_message,
                ),
                (first_request, second_request),
            )
        )

    accepted = [result for result in results if result is not None]
    assert len(accepted) == 1
    accepted_request = accepted[0][1]
    replay = _claim_response_option(
        gateway,
        request_message=accepted_request,
    )
    assert replay is not None
    assert replay[1].id == accepted_request.id
    assert sum(message["id"] == accepted_request.id for message in client.messages) == 1


def test_supabase_exact_replay_uses_source_immediately_before_request_after_later_messages() -> (
    None
):
    client = _SerializedMessageRpcClient(messages=[_serialized_source_message()])
    gateway = SupabaseGateway(client=client)
    request = _response_option_request("00000000-0000-0000-0000-000000000309")

    accepted = _claim_response_option(gateway, request_message=request)
    assert accepted is not None
    gateway.create_message(
        user_id="00000000-0000-0000-0000-000000000303",
        conversation_id=request.conversation_id,
        role="assistant",
        content="A later assistant turn.",
        metadata={},
    )

    replay = _claim_response_option(gateway, request_message=request)

    assert replay is not None
    assert replay[0].id == "00000000-0000-0000-0000-000000000301"
    assert replay[1].id == request.id
    assert sum(message["id"] == request.id for message in client.messages) == 1


def test_supabase_timestamp_tie_uses_id_and_next_append_is_strictly_newer() -> None:
    first = _serialized_source_message()
    tied_latest = {
        **_serialized_source_message(),
        "id": "00000000-0000-0000-0000-000000000399",
        "content": "Tied but deterministically newer.",
    }
    client = _SerializedMessageRpcClient(messages=[first, tied_latest])
    gateway = SupabaseGateway(client=client)

    rejected = _claim_response_option(
        gateway,
        request_message=_response_option_request("00000000-0000-0000-0000-000000000308"),
    )
    appended = gateway.create_message(
        user_id="00000000-0000-0000-0000-000000000303",
        conversation_id=first["conversation_id"],
        role="assistant",
        content="Strictly newer after a tie.",
    )

    assert rejected is None
    assert appended.created_at > datetime.fromisoformat(first["created_at"])


def test_create_message_writes_empty_metadata_object_when_omitted():
    client = _RecordingSupabaseClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_conversation = MagicMock(return_value=object())

    message = gateway.create_message(
        user_id="user-1",
        conversation_id="conversation-1",
        role="user",
        content="Backtest buying and holding Apple over the past year.",
    )

    assert client.inserted_message is not None
    assert client.inserted_message["metadata"] == {}
    assert message.metadata == {}


def test_create_message_replays_one_server_owned_message_identity() -> None:
    client = _SerializedMessageRpcClient(messages=[])
    gateway = SupabaseGateway(client=client)
    message_id = "00000000-0000-0000-0000-000000000401"
    payload = {
        "user_id": "00000000-0000-0000-0000-000000000303",
        "conversation_id": "00000000-0000-0000-0000-000000000302",
        "role": "user",
        "content": "Run backtest",
        "metadata": {
            "chat_action": {
                "type": "run_backtest",
                "payload": {"confirmation_id": "confirmation-replay-1"},
            }
        },
        "message_id": message_id,
    }

    first = gateway.create_message(**payload)
    replay = gateway.create_message(**payload)

    assert first.id == message_id
    assert replay == first
    assert [message["id"] for message in client.messages] == [message_id]


def test_context_packet_and_route_receipt_persistence_payloads_are_explicit():
    client = _RecordingSupabaseClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_backtest_run = MagicMock(return_value=object())  # type: ignore[method-assign]
    gateway._context_packet_owned_by_user = MagicMock(return_value=True)  # type: ignore[attr-defined,method-assign]

    packet_row = gateway.create_context_packet(
        user_id="user-1",
        packet={
            "id": "packet-1",
            "provider": "fred",
            "packet_type": "macro",
            "scope": {"series_id": "FEDFUNDS"},
            "source_ids": ["FEDFUNDS:2024-01-01"],
            "retrieved_at": "2026-05-19T00:00:00+00:00",
            "coverage_start": "2024-01-01",
            "coverage_end": "2024-01-31",
            "freshness": "fresh",
            "facts": [],
            "limitations": ["Context only."],
            "not_for": "simulation_truth",
        },
    )
    attachment_row = gateway.attach_context_packet_to_run(
        user_id="user-1",
        attachment={
            "packet_id": "packet-1",
            "run_id": "run-1",
            "immutable_snapshot": True,
        },
    )
    receipt_row = gateway.create_route_receipt(
        user_id="user-1",
        conversation_id="conversation-1",
        receipt={
            "task": "interpretation",
            "tier": "structured",
            "model": "structured/primary",
            "fallback_model": "structured/fallback",
            "mode": "json_schema",
            "schema_name": "LLMInterpretationResponse",
            "latency_ms": 123,
            "outcome": "succeeded",
            "fallback_used": False,
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "context_packet_ids": ["packet-1"],
            "created_at": "2026-05-19T00:00:00+00:00",
        },
    )

    assert packet_row["packet"]["not_for"] == "simulation_truth"
    assert client.inserted_by_table["context_packets"]["user_id"] == "user-1"
    assert attachment_row["context_packet_id"] == "packet-1"
    assert attachment_row["immutable_snapshot"] is True
    assert receipt_row["conversation_id"] == "conversation-1"
    assert receipt_row["latency_ms"] == 123
    assert receipt_row["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
    assert receipt_row["context_packet_ids"] == ["packet-1"]


def test_cost_ledger_entry_persistence_payload_is_explicit() -> None:
    client = _RecordingSupabaseClient()
    gateway = SupabaseGateway(client=client)

    row = gateway.create_cost_ledger_entry(
        entry={
            "source": "api_turn",
            "service": "openrouter",
            "provider": "openrouter",
            "model": "structured/primary",
            "feature_area": "chat_runtime",
            "task": "interpretation",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "message_id": "message-1",
            "backtest_run_id": None,
            "backtest_job_id": None,
            "route_receipt_id": "receipt-1",
            "request_id": "req-1",
            "correlation_id": "req-1:conversation-1:message-1",
            "usage_metadata": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "usage_cost_usd": 0.00031,
            },
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "billable_unit": "token",
            "billable_quantity": 15,
            "cost_amount": 0.00031,
            "cost_currency": "USD",
            "cost_source": "provider_reported",
            "latency_ms": 123,
            "status": "succeeded",
            "metadata": {"source": "api_turn"},
            "occurred_at": "2026-07-02T12:00:00+00:00",
        }
    )

    payload = client.inserted_by_table["cost_ledger_entries"]
    assert row["correlation_id"] == "req-1:conversation-1:message-1"
    assert payload["provider"] == "openrouter"
    assert payload["model"] == "structured/primary"
    assert payload["total_tokens"] == 15
    assert payload["cost_amount"] == 0.00031
    assert payload["route_receipt_id"] == "receipt-1"


def _completed_run(
    *,
    conversation_id: str | None = "conversation-1",
    strategy_id: str | None = None,
) -> BacktestRun:
    return BacktestRun(
        id="run-1",
        conversation_id=conversation_id,
        strategy_id=strategy_id,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={"aggregate": {"performance": {"total_return_pct": 12.4}}},
        config_snapshot={"template": "buy_and_hold", "symbols": ["AAPL"]},
        conversation_result_card={
            "title": "AAPL buy and hold",
            "rows": [
                {"key": "total_return_pct", "label": "Total Return", "value": "+12.4%"}
            ],
            "assumptions": ["Benchmark: SPY"],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )


class _FinalizationRpcClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, function_name: str, params: dict[str, Any]):
        self.calls.append((function_name, params))
        return _FinalizationRpc(params)


class _FinalizationRpc:
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(
            data=[
                {
                    "run": self.params["p_run"],
                    "idea": self.params["p_idea"],
                    "idea_version": self.params["p_idea_version"],
                    "evidence_artifact": self.params["p_evidence_artifact"],
                }
            ]
        )


def _backtest_finalization_input() -> BacktestFinalizationInput:
    run = _completed_run()
    return BacktestFinalizationInput(
        user_id="user-1",
        execution_identity="backtest_job:job-1",
        run=run,
        result_card=dict(run.conversation_result_card),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        finalized_at=utcnow(),
    )


def test_supabase_finalizer_uses_one_rpc_and_returns_canonical_identity() -> None:
    client = _FinalizationRpcClient()
    gateway = SupabaseGateway(client=client)

    finalized = finalize_backtest_completion(
        gateway,
        _backtest_finalization_input(),
    )

    assert [name for name, _params in client.calls] == ["finalize_backtest_completion"]
    params = client.calls[0][1]
    assert params["p_user_id"] == "user-1"
    assert params["p_execution_identity"] == "backtest_job:job-1"
    assert params["p_run"]["id"] == "run-1"
    assert params["p_run"]["conversation_result_card"]["evidence_artifact_id"] == (
        "artifact-1"
    )
    assert finalized.identity.run_id == "run-1"
    assert finalized.identity.evidence_artifact_id == "artifact-1"


def test_create_backtest_run_rejects_unowned_parent_conversation() -> None:
    client = _RecordingSupabaseClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_conversation = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Conversation not found"):
        gateway.create_backtest_run(user_id="user-1", run=_completed_run())

    assert "backtest_runs" not in client.inserted_by_table


def test_create_backtest_run_rejects_unowned_parent_strategy() -> None:
    client = _RecordingSupabaseClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_conversation = MagicMock(return_value=object())  # type: ignore[method-assign]
    gateway.get_strategy = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Strategy not found"):
        gateway.create_backtest_run(
            user_id="user-1",
            run=_completed_run(strategy_id="strategy-other"),
        )

    assert "backtest_runs" not in client.inserted_by_table


def test_attach_context_packet_rejects_unowned_parent_run() -> None:
    client = _RecordingSupabaseClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_backtest_run = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Backtest run not found"):
        gateway.attach_context_packet_to_run(
            user_id="user-1",
            attachment={"packet_id": "packet-1", "run_id": "run-other"},
        )

    assert "run_context_packets" not in client.inserted_by_table


def test_usage_limits_check_all_windows_before_incrementing() -> None:
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.limit.return_value = table
    table.execute.side_effect = [
        SimpleNamespace(data=[{"id": "day-counter", "used_count": 1}]),
        SimpleNamespace(data=[{"id": "hour-counter", "used_count": 60}]),
    ]
    gateway = SupabaseGateway(client=client)

    with pytest.raises(QuotaExceededError, match="chat_messages \\(hour\\)"):
        gateway.check_and_increment_usage_limits(
            user_id="user-1",
            resource="chat_messages",
            limits=[("day", 200), ("hour", 60)],
        )

    table.update.assert_not_called()


def test_list_current_usage_counters_is_owner_scoped_and_bounded() -> None:
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.in_.return_value = table
    table.limit.return_value = table
    table.execute.return_value = SimpleNamespace(
        data=[
            {
                "resource": "chat_messages",
                "limit_count": 200,
                "used_count": 12,
                "period_end": "2026-07-17T00:00:00+00:00",
            },
            {
                "resource": "backtest_runs",
                "limit_count": 50,
                "used_count": 3,
                "period_end": "2026-07-17T00:00:00+00:00",
            },
        ]
    )
    gateway = SupabaseGateway(client=client)
    at = datetime(2026, 7, 16, 15, 30, tzinfo=timezone.utc)

    rows = gateway.list_current_usage_counters(
        user_id="user-1",
        resources=("chat_messages", "backtest_runs"),
        period="day",
        at=at,
    )

    assert rows == table.execute.return_value.data
    client.table.assert_called_once_with("usage_counters")
    table.select.assert_called_once_with("resource,limit_count,used_count,period_end")
    assert table.eq.call_args_list == [
        call("user_id", "user-1"),
        call("period", "day"),
        call("period_start", "2026-07-16T00:00:00+00:00"),
    ]
    table.in_.assert_called_once_with("resource", ["chat_messages", "backtest_runs"])
    table.limit.assert_called_once_with(2)


def test_usage_limit_precheck_rejects_without_mutating_counter() -> None:
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.limit.return_value = table
    table.execute.side_effect = [
        SimpleNamespace(data=[{"id": "day-counter", "used_count": 1}]),
        SimpleNamespace(data=[{"id": "hour-counter", "used_count": 10}]),
    ]
    gateway = SupabaseGateway(client=client)

    with pytest.raises(QuotaExceededError, match="backtest_runs \\(hour\\)"):
        gateway.check_usage_limits(
            user_id="user-1",
            resource="backtest_runs",
            limits=[("day", 50), ("hour", 10)],
        )

    table.insert.assert_not_called()
    table.update.assert_not_called()


class _BacktestJobClient:
    def __init__(self, existing_jobs: list[dict[str, Any]] | None = None) -> None:
        self.existing_jobs = existing_jobs or []
        self.inserted_jobs: list[dict[str, Any]] = []
        self.updated_jobs: list[dict[str, Any]] = []
        self.updated_job_filters: list[dict[str, object]] = []
        self.select_calls: list[str] = []
        self.in_filters: list[tuple[str, list[object]]] = []
        self.or_filters: list[str] = []

    def table(self, table_name: str):
        assert table_name == "backtest_jobs"
        return _BacktestJobTable(self)


class _BacktestJobTable:
    def __init__(self, client: _BacktestJobClient) -> None:
        self.client = client
        self.operation: str | None = None
        self.payload: dict[str, Any] | None = None
        self.filters: dict[str, object] = {}
        self.in_filters: dict[str, list[object]] = {}
        self.limit_count: int | None = None
        self.select_columns = "*"

    def select(self, columns: str):
        self.operation = "select"
        self.select_columns = columns
        self.client.select_calls.append(columns)
        return self

    def insert(self, payload: dict[str, Any]):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]):
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, key: str, value: object):
        self.filters[key] = value
        return self

    def or_(self, filter_string: str):
        self.client.or_filters.append(filter_string)
        return self

    def in_(self, key: str, values: list[object]):
        self.in_filters[key] = values
        self.client.in_filters.append((key, values))
        return self

    def limit(self, count: int):
        self.limit_count = count
        return self

    def order(self, _column: str, *, desc: bool = False):
        return self

    def execute(self):
        if self.operation == "select":
            rows = [
                row
                for row in self.client.existing_jobs
                if all(row.get(key) == value for key, value in self.filters.items())
                and all(row.get(key) in values for key, values in self.in_filters.items())
            ]
            if self.limit_count is not None:
                rows = rows[: self.limit_count]
            if self.select_columns != "*":
                selected = {column.strip() for column in self.select_columns.split(",")}
                rows = [
                    {key: value for key, value in row.items() if key in selected}
                    for row in rows
                ]
            return SimpleNamespace(data=rows)
        if self.operation == "insert" and self.payload is not None:
            idempotency_key = self.payload.get("idempotency_key")
            if idempotency_key is not None and any(
                row.get("user_id") == self.payload.get("user_id")
                and row.get("operation_scope") == self.payload.get("operation_scope")
                and row.get("idempotency_key") == idempotency_key
                for row in self.client.existing_jobs
            ):
                raise _UniqueViolationError
            self.client.inserted_jobs.append(self.payload)
            row = {"id": f"job-{len(self.client.inserted_jobs)}", **self.payload}
            self.client.existing_jobs.append(row)
            return SimpleNamespace(data=[row])
        if self.operation == "update" and self.payload is not None:
            matches = [
                row
                for row in self.client.existing_jobs
                if all(row.get(key) == value for key, value in self.filters.items())
            ]
            if not matches:
                return SimpleNamespace(data=[])
            updated = {**matches[0], **self.payload}
            self.client.updated_jobs.append(updated)
            self.client.updated_job_filters.append(dict(self.filters))
            return SimpleNamespace(data=[updated])
        return SimpleNamespace(data=[])


class _UniqueViolationError(RuntimeError):
    code = "23505"


def test_create_backtest_job_inserts_queued_shadow_payload() -> None:
    client = _BacktestJobClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_conversation = MagicMock(return_value=object())  # type: ignore[method-assign]

    row = gateway.create_backtest_job(
        user_id="user-1",
        conversation_id="conversation-1",
        request_message_id="message-1",
        confirmation_message_id=None,
        idempotency_key="idem-1",
        payload_hash="sha256:abc",
        launch_payload={
            "schema_version": "backtest_job_launch/v1",
            "source": "chat_runtime",
            "request": {"symbol": "AAPL"},
        },
        execution_metadata={"shadow_mode": True, "source": "api_chat"},
    )

    assert row["id"] == "job-1"
    assert client.inserted_jobs == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "request_message_id": "message-1",
            "confirmation_message_id": None,
            "idempotency_key": "idem-1",
            "payload_hash": "sha256:abc",
            "launch_payload": {
                "schema_version": "backtest_job_launch/v1",
                "source": "chat_runtime",
                "request": {"symbol": "AAPL"},
            },
            "status": "queued",
            "priority": "normal",
            "attempts": 0,
            "max_attempts": 1,
            "execution_metadata": {"shadow_mode": True, "source": "api_chat"},
        }
    ]


def test_record_backtest_job_rejection_replays_one_terminal_receipt() -> None:
    client = _BacktestJobClient()
    gateway = SupabaseGateway(client=client)

    payload = {
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "request_message_id": "message-1",
        "confirmation_message_id": "confirmation-message-1",
        "operation_scope": "chat.run_backtest",
        "rejected_idempotency_key": "confirmation-spent",
        "identity_hash": "sha256:identity",
        "payload_hash": "sha256:payload",
        "launch_payload": {"request": {"symbols": ["NVDA", "MSFT"]}},
        "failure_code": "idempotency_conflict",
        "failure_detail": "confirmation_identity_already_spent",
        "retryable": False,
        "execution_metadata": {"refused_before_dispatch": True},
    }

    row = gateway.record_backtest_job_rejection(**payload)
    replay = gateway.record_backtest_job_rejection(**payload)

    assert replay["id"] == row["id"]
    assert replay["idempotency_key"] == row["idempotency_key"]
    assert len(client.inserted_jobs) == 1
    assert row["id"] == "job-1"
    [receipt] = client.inserted_jobs
    assert receipt["status"] == "failed"
    assert receipt["idempotency_key"].startswith("rejection:")
    assert receipt["idempotency_key"] != "confirmation-spent"
    assert receipt["identity_hash"] == "sha256:identity"
    assert receipt["failure_code"] == "idempotency_conflict"
    assert receipt["failure_detail"] == "confirmation_identity_already_spent"
    assert receipt["finished_at"]


def test_record_backtest_job_rejection_rejects_mismatched_receipt_collision() -> None:
    client = _BacktestJobClient()
    gateway = SupabaseGateway(client=client)

    common = {
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "request_message_id": "message-1",
        "confirmation_message_id": "confirmation-message-1",
        "operation_scope": "chat.run_backtest",
        "rejected_idempotency_key": "confirmation-spent",
        "identity_hash": "sha256:identity",
        "payload_hash": "sha256:payload",
        "launch_payload": {"request": {"symbols": ["NVDA", "MSFT"]}},
        "failure_code": "idempotency_conflict",
        "failure_detail": "confirmation_identity_already_spent",
        "retryable": False,
        "execution_metadata": {"refused_before_dispatch": True},
    }

    gateway.record_backtest_job_rejection(**common)
    client.existing_jobs[0]["failure_detail"] = "unexpected_existing_detail"

    with pytest.raises(RuntimeError, match="did not match the attempted rejection"):
        gateway.record_backtest_job_rejection(**common)


def test_backtest_reservation_query_includes_internal_launch_payload() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "operation_scope": "chat.run_backtest",
        "idempotency_key": "confirmation-1",
        "status": "queued",
        "launch_payload": {"kind": "run_backtest_job"},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.get_backtest_job_reservation(
        user_id="user-1",
        operation_scope="chat.run_backtest",
        idempotency_key="confirmation-1",
    )

    assert row is not None
    assert row["launch_payload"] == {"kind": "run_backtest_job"}
    assert "launch_payload" in client.select_calls[-1].split(",")


def test_backtest_reservations_batch_query_is_owner_conversation_scope_and_key_bounded() -> (
    None
):
    client = _BacktestJobClient(
        existing_jobs=[
            {
                "id": "job-1",
                "user_id": "user-1",
                "conversation_id": "conversation-1",
                "operation_scope": "chat.run_backtest",
                "idempotency_key": "confirmation-1",
                "launch_payload": {"kind": "run_backtest_job"},
            },
            {
                "id": "job-foreign",
                "user_id": "user-2",
                "conversation_id": "conversation-1",
                "operation_scope": "chat.run_backtest",
                "idempotency_key": "confirmation-2",
                "launch_payload": {"kind": "run_backtest_job"},
            },
        ]
    )
    gateway = SupabaseGateway(client=client)

    rows = gateway.list_backtest_job_reservations(
        user_id="user-1",
        conversation_id="conversation-1",
        operation_scope="chat.run_backtest",
        idempotency_keys=["confirmation-1", "confirmation-2", "confirmation-1"],
    )

    assert [row["id"] for row in rows] == ["job-1"]
    assert client.in_filters == [
        ("idempotency_key", ["confirmation-1", "confirmation-2"])
    ]
    assert "launch_payload" in client.select_calls[-1].split(",")


def test_create_backtest_job_rejects_unowned_parent_conversation_before_insert() -> None:
    client = _BacktestJobClient()
    gateway = SupabaseGateway(client=client)
    gateway.get_conversation = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Conversation not found"):
        gateway.create_backtest_job(
            user_id="user-1",
            conversation_id="conversation-other",
            payload_hash="sha256:abc",
            launch_payload={"request": {"symbol": "AAPL"}},
        )

    assert client.inserted_jobs == []


def test_create_backtest_job_reuses_existing_idempotency_key() -> None:
    existing_job = {
        "id": "job-existing",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "idempotency_key": "idem-1",
        "payload_hash": "sha256:existing",
        "launch_payload": {},
        "status": "queued",
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.create_backtest_job(
        user_id="user-1",
        conversation_id="conversation-1",
        idempotency_key=" idem-1 ",
        payload_hash="sha256:new",
        launch_payload={"request": {"symbol": "MSFT"}},
    )

    assert row == existing_job
    assert client.inserted_jobs == []


def test_count_backtest_jobs_filters_status_user_and_limit() -> None:
    client = _BacktestJobClient(
        existing_jobs=[
            {"id": "job-1", "user_id": "user-1", "status": "queued"},
            {"id": "job-2", "user_id": "user-1", "status": "queued"},
            {"id": "job-3", "user_id": "user-2", "status": "queued"},
            {"id": "job-4", "user_id": "user-1", "status": "running"},
        ]
    )
    gateway = SupabaseGateway(client=client)

    assert (
        gateway.count_backtest_jobs(
            status="queued",
            user_id="user-1",
            limit=1,
        )
        == 1
    )
    assert gateway.count_backtest_jobs(status="queued", limit=10) == 3


def test_list_backtest_jobs_filters_status_user_and_limit() -> None:
    client = _BacktestJobClient(
        existing_jobs=[
            {"id": "job-1", "user_id": "user-1", "status": "running"},
            {"id": "job-2", "user_id": "user-1", "status": "running"},
            {"id": "job-3", "user_id": "user-2", "status": "running"},
            {"id": "job-4", "user_id": "user-1", "status": "queued"},
        ]
    )
    gateway = SupabaseGateway(client=client)

    rows = gateway.list_backtest_jobs(
        status="running",
        user_id="user-1",
        limit=1,
    )

    assert rows == [{"id": "job-1", "user_id": "user-1", "status": "running"}]


def test_merge_backtest_job_execution_metadata_preserves_existing_fields() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "execution_metadata": {"shadow_mode": True},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.merge_backtest_job_execution_metadata(
        user_id="user-1",
        job_id="job-1",
        execution_metadata={"workflow_dispatch": {"task_run_id": "task-run-1"}},
    )

    assert row["execution_metadata"] == {
        "shadow_mode": True,
        "workflow_dispatch": {"task_run_id": "task-run-1"},
    }
    assert client.updated_jobs[0]["execution_metadata"] == row["execution_metadata"]


def test_link_backtest_job_result_marks_succeeded_when_api_owns_shadow_lifecycle() -> (
    None
):
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "queued",
        "result_run_id": None,
        "execution_metadata": {"shadow_mode": True},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.link_backtest_job_result(
        user_id="user-1",
        job_id="job-1",
        result_run_id="run-1",
        execution_metadata={
            "api_in_process_result": {"result_run_id": "run-1"},
        },
        mark_succeeded=True,
    )

    assert row["status"] == "succeeded"
    assert row["result_run_id"] == "run-1"
    assert row["finished_at"]
    assert row["execution_metadata"] == {
        "shadow_mode": True,
        "api_in_process_result": {"result_run_id": "run-1"},
    }
    from argus.domain.backtest_job_lifecycle import (
        job_success_write_postgrest_filter,
    )

    assert client.or_filters == [
        job_success_write_postgrest_filter()
    ], "the success write must carry the generated lifecycle filter"


def test_link_backtest_job_result_does_not_overwrite_existing_result() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "succeeded",
        "result_run_id": "run-existing",
        "execution_metadata": {},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.link_backtest_job_result(
        user_id="user-1",
        job_id="job-1",
        result_run_id="run-new",
    )

    assert row == existing_job
    assert client.updated_jobs == []


def test_mark_backtest_job_running_filters_by_user_and_increments_attempts() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "queued",
        "attempts": 0,
        "started_at": None,
        "execution_metadata": {"shadow_mode": True},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.mark_backtest_job_running(
        user_id="user-1",
        job_id="job-1",
        execution_metadata={"workflow_backtest": {"workflow_run_id": "task-run-1"}},
    )

    assert row["status"] == "running"
    assert row["attempts"] == 1
    assert row["started_at"]
    assert row["execution_metadata"] == {
        "shadow_mode": True,
        "workflow_backtest": {"workflow_run_id": "task-run-1"},
    }
    assert client.updated_jobs[0]["user_id"] == "user-1"
    assert client.updated_jobs[0]["id"] == "job-1"
    assert client.updated_job_filters[0] == {
        "user_id": "user-1",
        "id": "job-1",
        "status": "queued",
    }


def test_mark_backtest_job_running_rejects_already_running_job() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "running",
        "attempts": 1,
        "started_at": "2026-07-13T08:00:00+00:00",
        "execution_metadata": {"workflow_run_id": "first-worker"},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    with pytest.raises(ValueError, match="cannot be started or retried"):
        gateway.mark_backtest_job_running(
            user_id="user-1",
            job_id="job-1",
            execution_metadata={"workflow_run_id": "overlapping-worker"},
        )

    assert client.updated_jobs == []


def test_mark_backtest_job_running_rejects_lost_compare_and_set_race() -> None:
    queued_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "queued",
        "attempts": 0,
        "started_at": None,
        "execution_metadata": {},
    }
    client = _BacktestJobClient(existing_jobs=[dict(queued_job)])
    gateway = SupabaseGateway(client=client)

    def stale_queued_read(*, user_id: str, job_id: str) -> dict[str, Any]:
        assert user_id == "user-1"
        assert job_id == "job-1"
        client.existing_jobs[0]["status"] = "running"
        return dict(queued_job)

    gateway.get_backtest_job = stale_queued_read  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="cannot be started or retried"):
        gateway.mark_backtest_job_running(
            user_id="user-1",
            job_id="job-1",
            execution_metadata={"workflow_run_id": "overlapping-worker"},
        )

    assert client.updated_jobs == []


def test_mark_backtest_job_running_allows_finalization_retry() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "failed",
        "attempts": 1,
        "started_at": "2026-07-13T08:00:00+00:00",
        "failure_code": "finalization_failed",
        "failure_detail": "execution_failed",
        "retryable": True,
        "execution_metadata": {},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.mark_backtest_job_running(
        user_id="user-1",
        job_id="job-1",
        execution_metadata={"workflow_run_id": "finalization-retry"},
    )

    assert row["status"] == "running"
    assert row["attempts"] == 2
    assert client.updated_job_filters[0] == {
        "user_id": "user-1",
        "id": "job-1",
        "status": "failed",
        "failure_code": "finalization_failed",
        "retryable": True,
    }


def test_mark_backtest_job_failed_filters_by_user_and_sets_failure_metadata() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "running",
        "failure_code": None,
        "failure_detail": None,
        "retryable": False,
        "execution_metadata": {"shadow_mode": True},
        "updated_at": "2026-07-24T12:00:01+00:00",
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.mark_backtest_job_failed(
        user_id="user-1",
        job_id="job-1",
        failure_code="upstream_dependency_error",
        failure_detail="market_data_issue",
        retryable=True,
        execution_metadata={"workflow_backtest": {"failure_category": "market_data"}},
        expected_status="running",
        expected_updated_at="2026-07-24T12:00:01+00:00",
    )

    assert row["status"] == "failed"
    assert row["failure_code"] == "upstream_dependency_error"
    assert row["failure_detail"] == "market_data_issue"
    assert row["retryable"] is True
    assert row["finished_at"]
    assert row["execution_metadata"] == {
        "shadow_mode": True,
        "workflow_backtest": {"failure_category": "market_data"},
    }
    assert client.updated_jobs[0]["user_id"] == "user-1"
    assert client.updated_jobs[0]["id"] == "job-1"
    assert client.updated_job_filters[0]["status"] == "running"
    assert client.updated_job_filters[0]["updated_at"] == ("2026-07-24T12:00:01+00:00")


def test_mark_backtest_job_failed_does_not_overwrite_status_after_cas_loss() -> None:
    existing_job = {
        "id": "job-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "status": "succeeded",
        "result_run_id": "run-1",
        "execution_metadata": {},
    }
    client = _BacktestJobClient(existing_jobs=[existing_job])
    gateway = SupabaseGateway(client=client)

    row = gateway.mark_backtest_job_failed(
        user_id="user-1",
        job_id="job-1",
        failure_code="workflow_dispatch_missing",
        failure_detail="Dispatch response was lost.",
        retryable=True,
        expected_status="queued",
    )

    assert row == {}
    assert client.updated_jobs == []


class _MockAuthAdmin:
    def get_user_by_email(self, _email: str) -> object:
        raise RuntimeError("fall back to profile lookup")

    def list_users(self, **_kwargs: object) -> object:
        raise RuntimeError("fall back to profile lookup")


class _MockAuth:
    admin = _MockAuthAdmin()


class _ExistingProfileClient:
    def __init__(self) -> None:
        self.auth = _MockAuth()
        self.upserted_profile: dict[str, object] | None = None
        self.profile = {
            "id": "user-1",
            "email": "developer@argus.local",
            "username": "mock-developer",
            "display_name": "Mock Developer",
            "language": "en",
            "locale": "en-US",
            "is_admin": True,
            "onboarding": {
                "completed": True,
                "stage": "completed",
                "language_confirmed": True,
                "primary_goal": "test_stock_idea",
            },
            "created_at": "2026-05-14T00:00:00+00:00",
            "updated_at": "2026-05-14T00:00:00+00:00",
        }

    def table(self, table_name: str):
        assert table_name == "profiles"
        return _ExistingProfileTable(self)


class _ExistingProfileTable:
    def __init__(self, client: _ExistingProfileClient) -> None:
        self.client = client
        self.selected = "*"

    def select(self, selected: str):
        self.selected = selected
        return self

    def eq(self, *_args: object):
        return self

    def limit(self, *_args: object):
        return self

    def single(self):
        return self

    def upsert(self, payload: dict[str, object], **_kwargs: object):
        self.client.upserted_profile = payload
        self.client.profile = {**self.client.profile, **payload}
        return self

    def execute(self):
        if self.selected == "id":
            return SimpleNamespace(data=[{"id": self.client.profile["id"]}])
        return SimpleNamespace(data=[self.client.profile])


def test_mock_user_lookup_preserves_existing_profile_onboarding():
    client = _ExistingProfileClient()
    gateway = SupabaseGateway(
        client=client,
        mock_user_email="developer@argus.local",
        mock_user_password="password",
    )

    user = gateway.get_or_create_mock_user()

    assert client.upserted_profile is None
    assert user.onboarding.completed is True
    assert user.onboarding.primary_goal == "test_stock_idea"


class _P1EvidenceClient:
    def __init__(self) -> None:
        self.rows_by_table: dict[str, list[dict[str, Any]]] = {
            "ideas": [],
            "idea_versions": [],
            "evidence_artifacts": [],
            "decision_notes": [],
        }
        self.operations: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.raise_on_next_idea_version_insert = False
        self.raise_on_next_idea_active_update = False
        self.raise_on_next_artifact_insert = False
        self.commit_artifact_before_insert_error = False
        self.return_empty_decision_rpc = False
        self.concurrent_rows_on_artifact_insert_error: dict[
            str, list[dict[str, Any]]
        ] = {}

    def table(self, table_name: str):
        return _P1EvidenceTable(self, table_name)

    def rpc(self, function_name: str, params: dict[str, Any]):
        self.rpc_calls.append((function_name, params))
        return _P1EvidenceRpc(self, function_name, params)


class _P1EvidenceTable:
    def __init__(self, client: _P1EvidenceClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.action = "select"
        self.payload: dict[str, Any] = {}
        self.filters: dict[str, Any] = {}

    def select(self, *_args: object, **_kwargs: object):
        self.action = "select"
        return self

    def insert(self, payload: dict[str, Any]):
        self.action = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload: dict[str, Any]):
        self.action = "update"
        self.payload = dict(payload)
        return self

    def delete(self):
        self.action = "delete"
        return self

    def eq(self, key: str, value: object):
        self.filters[key] = value
        return self

    def limit(self, *_args: object):
        return self

    def execute(self):
        if self.action == "insert":
            self.client.operations.append(
                ("insert", self.table_name, dict(self.payload), {})
            )
            if (
                self.table_name == "idea_versions"
                and self.client.raise_on_next_idea_version_insert
            ):
                self.client.raise_on_next_idea_version_insert = False
                raise RuntimeError("idea version insert failed")
            if (
                self.table_name == "evidence_artifacts"
                and self.client.raise_on_next_artifact_insert
            ):
                self.client.raise_on_next_artifact_insert = False
                if self.client.commit_artifact_before_insert_error:
                    self.client.rows_by_table[self.table_name].append(dict(self.payload))
                for (
                    table_name,
                    rows,
                ) in self.client.concurrent_rows_on_artifact_insert_error.items():
                    self.client.rows_by_table[table_name].extend(
                        dict(row) for row in rows
                    )
                raise RuntimeError("duplicate source_run_id")
            self.client.rows_by_table[self.table_name].append(dict(self.payload))
            return SimpleNamespace(data=[dict(self.payload)])

        rows = [
            row
            for row in self.client.rows_by_table[self.table_name]
            if all(row.get(key) == value for key, value in self.filters.items())
        ]
        if self.action == "delete":
            self.client.operations.append(
                ("delete", self.table_name, {}, dict(self.filters))
            )
            self.client.rows_by_table[self.table_name] = [
                row
                for row in self.client.rows_by_table[self.table_name]
                if not all(row.get(key) == value for key, value in self.filters.items())
            ]
            return SimpleNamespace(data=[dict(row) for row in rows])
        if self.action == "update":
            self.client.operations.append(
                ("update", self.table_name, dict(self.payload), dict(self.filters))
            )
            if (
                self.table_name == "ideas"
                and "active_version_id" in self.payload
                and self.payload["active_version_id"] is not None
                and self.client.raise_on_next_idea_active_update
            ):
                self.client.raise_on_next_idea_active_update = False
                raise RuntimeError("idea active version update failed")
            for row in rows:
                row.update(self.payload)
            return SimpleNamespace(data=[dict(row) for row in rows])
        return SimpleNamespace(data=[dict(row) for row in rows])


class _P1EvidenceRpc:
    def __init__(
        self,
        client: _P1EvidenceClient,
        function_name: str,
        params: dict[str, Any],
    ) -> None:
        self.client = client
        self.function_name = function_name
        self.params = params

    def execute(self):
        assert self.function_name == "upsert_current_decision_note"
        if self.client.return_empty_decision_rpc:
            return SimpleNamespace(data=[])
        user_id = self.params["p_user_id"]
        artifact_id = self.params["p_evidence_artifact_id"]
        artifact = next(
            row
            for row in self.client.rows_by_table["evidence_artifacts"]
            if row.get("user_id") == user_id and row.get("id") == artifact_id
        )
        idea = next(
            row
            for row in self.client.rows_by_table["ideas"]
            if row.get("user_id") == user_id and row.get("id") == artifact["idea_id"]
        )
        version = next(
            row
            for row in self.client.rows_by_table["idea_versions"]
            if row.get("user_id") == user_id
            and row.get("id") == artifact["idea_version_id"]
        )
        existing = next(
            (
                row
                for row in self.client.rows_by_table["decision_notes"]
                if row.get("user_id") == user_id
                and row.get("evidence_artifact_id") == artifact_id
            ),
            None,
        )
        if existing is None:
            existing = {
                "id": self.params["p_decision_id"],
                "user_id": user_id,
                "idea_id": artifact["idea_id"],
                "idea_version_id": artifact["idea_version_id"],
                "evidence_artifact_id": artifact_id,
                "source_conversation_id": artifact["source_conversation_id"],
                "decision_state": self.params["p_decision_state"],
                "note": self.params["p_note"],
                "created_at": utcnow().isoformat(),
                "updated_at": utcnow().isoformat(),
            }
            self.client.rows_by_table["decision_notes"].append(existing)
        else:
            existing.update(
                {
                    "decision_state": self.params["p_decision_state"],
                    "note": self.params["p_note"],
                    "updated_at": utcnow().isoformat(),
                }
            )

        artifact["lifecycle"] = "decided"
        idea["lifecycle"] = "decided"
        version["lifecycle"] = "decided"
        return SimpleNamespace(
            data=[
                {
                    "decision": dict(existing),
                    "evidence_artifact": dict(artifact),
                    "idea": dict(idea),
                    "idea_version": dict(version),
                }
            ]
        )


def _gateway_for_p1_client(client: _P1EvidenceClient) -> SupabaseGateway:
    gateway = SupabaseGateway(client=client)
    gateway._require_owned_conversation = MagicMock()  # type: ignore[method-assign]
    gateway._require_owned_backtest_run_if_present = MagicMock()  # type: ignore[method-assign]
    gateway._require_owned_idea = MagicMock()  # type: ignore[method-assign]
    gateway._require_owned_idea_version = MagicMock()  # type: ignore[method-assign]
    gateway._require_owned_evidence_artifact = MagicMock()  # type: ignore[method-assign]
    return gateway


def test_p1_evidence_capture_gateway_satisfies_active_version_fk_order() -> None:
    client = _P1EvidenceClient()
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        now=utcnow(),
    )

    persisted = gateway.create_backtest_evidence_capture(
        user_id="user-1",
        captured=captured,
    )

    assert persisted.idea.active_version_id == "version-1"
    assert [
        (operation, table) for operation, table, _payload, _filters in client.operations
    ] == [
        ("insert", "ideas"),
        ("insert", "idea_versions"),
        ("update", "ideas"),
        ("insert", "evidence_artifacts"),
    ]
    idea_insert = client.operations[0][2]
    idea_update = client.operations[2][2]
    assert idea_insert["active_version_id"] is None
    assert idea_update["active_version_id"] == "version-1"


def test_p1_evidence_capture_gateway_reuses_existing_source_run() -> None:
    client = _P1EvidenceClient()
    existing = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-existing",
        idea_version_id="version-existing",
        evidence_artifact_id="artifact-existing",
        now=utcnow(),
    )
    client.rows_by_table["ideas"].append(
        {"user_id": "user-1", **existing.idea.model_dump(mode="json")}
    )
    client.rows_by_table["idea_versions"].append(
        {"user_id": "user-1", **existing.idea_version.model_dump(mode="json")}
    )
    client.rows_by_table["evidence_artifacts"].append(
        {"user_id": "user-1", **existing.evidence_artifact.model_dump(mode="json")}
    )
    gateway = _gateway_for_p1_client(client)
    candidate = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-new",
        idea_version_id="version-new",
        evidence_artifact_id="artifact-new",
        now=utcnow(),
    )

    persisted = gateway.create_backtest_evidence_capture(
        user_id="user-1",
        captured=candidate,
    )

    assert persisted.evidence_artifact.id == "artifact-existing"
    assert client.operations == []


def test_p1_evidence_capture_gateway_cleans_sidecars_after_version_failure() -> None:
    client = _P1EvidenceClient()
    client.raise_on_next_idea_version_insert = True
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-new",
        idea_version_id="version-new",
        evidence_artifact_id="artifact-new",
        now=utcnow(),
    )

    with pytest.raises(RuntimeError, match="idea version insert failed"):
        gateway.create_backtest_evidence_capture(user_id="user-1", captured=captured)

    assert client.rows_by_table["ideas"] == []
    assert client.rows_by_table["idea_versions"] == []
    assert client.rows_by_table["evidence_artifacts"] == []


def test_p1_evidence_capture_gateway_cleans_sidecars_after_active_version_failure() -> (
    None
):
    client = _P1EvidenceClient()
    client.raise_on_next_idea_active_update = True
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-new",
        idea_version_id="version-new",
        evidence_artifact_id="artifact-new",
        now=utcnow(),
    )

    with pytest.raises(RuntimeError, match="idea active version update failed"):
        gateway.create_backtest_evidence_capture(user_id="user-1", captured=captured)

    assert client.rows_by_table["ideas"] == []
    assert client.rows_by_table["idea_versions"] == []
    assert client.rows_by_table["evidence_artifacts"] == []


def test_p1_evidence_capture_gateway_cleans_sidecars_after_source_run_race() -> None:
    client = _P1EvidenceClient()
    existing = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-existing",
        idea_version_id="version-existing",
        evidence_artifact_id="artifact-existing",
        now=utcnow(),
    )
    client.raise_on_next_artifact_insert = True
    client.concurrent_rows_on_artifact_insert_error = {
        "ideas": [{"user_id": "user-1", **existing.idea.model_dump(mode="json")}],
        "idea_versions": [
            {"user_id": "user-1", **existing.idea_version.model_dump(mode="json")}
        ],
        "evidence_artifacts": [
            {"user_id": "user-1", **existing.evidence_artifact.model_dump(mode="json")}
        ],
    }
    gateway = _gateway_for_p1_client(client)
    candidate = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-new",
        idea_version_id="version-new",
        evidence_artifact_id="artifact-new",
        now=utcnow(),
    )

    persisted = gateway.create_backtest_evidence_capture(
        user_id="user-1",
        captured=candidate,
    )

    assert persisted.evidence_artifact.id == "artifact-existing"
    assert all(row["id"] != "idea-new" for row in client.rows_by_table["ideas"])
    assert all(
        row["id"] != "version-new" for row in client.rows_by_table["idea_versions"]
    )
    assert [
        (operation, table, filters)
        for operation, table, _payload, filters in client.operations
        if operation == "delete"
    ] == [
        ("delete", "idea_versions", {"user_id": "user-1", "id": "version-new"}),
        ("delete", "ideas", {"user_id": "user-1", "id": "idea-new"}),
    ]


def test_p1_evidence_capture_gateway_reuses_post_commit_artifact_insert_failure() -> None:
    client = _P1EvidenceClient()
    client.raise_on_next_artifact_insert = True
    client.commit_artifact_before_insert_error = True
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-new",
        idea_version_id="version-new",
        evidence_artifact_id="artifact-new",
        now=utcnow(),
    )

    persisted = gateway.create_backtest_evidence_capture(
        user_id="user-1",
        captured=captured,
    )

    assert persisted.evidence_artifact.id == "artifact-new"
    assert persisted.idea.id == "idea-new"
    assert persisted.idea_version.id == "version-new"
    assert [
        operation for operation in client.operations if operation[0] == "delete"
    ] == []


def test_p1_decision_gateway_rpc_marks_full_object_spine_decided() -> None:
    client = _P1EvidenceClient()
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        now=utcnow(),
    )
    client.rows_by_table["ideas"].append(
        {"user_id": "user-1", **captured.idea.model_dump(mode="json")}
    )
    client.rows_by_table["idea_versions"].append(
        {"user_id": "user-1", **captured.idea_version.model_dump(mode="json")}
    )
    client.rows_by_table["evidence_artifacts"].append(
        {"user_id": "user-1", **captured.evidence_artifact.model_dump(mode="json")}
    )
    first_decision = build_decision_note(
        evidence_artifact=captured.evidence_artifact,
        decision_id="decision-1",
        decision_state="watching",
        note="Track it.",
        now=utcnow(),
    )
    second_decision = build_decision_note(
        evidence_artifact=captured.evidence_artifact,
        decision_id="decision-2",
        decision_state="promising",
        note="Still promising.",
        now=utcnow(),
    )

    first = gateway.capture_current_decision_note(
        user_id="user-1", decision=first_decision
    )
    second = gateway.capture_current_decision_note(
        user_id="user-1", decision=second_decision
    )

    assert first[0].id == "decision-1"
    assert second[0].id == "decision-1"
    assert second[0].decision_state == "promising"
    assert second[1].lifecycle == "decided"
    assert second[2].lifecycle == "decided"
    assert second[3].lifecycle == "decided"
    assert len(client.rows_by_table["decision_notes"]) == 1
    assert client.rows_by_table["ideas"][0]["lifecycle"] == "decided"
    assert client.rows_by_table["idea_versions"][0]["lifecycle"] == "decided"
    assert client.rows_by_table["evidence_artifacts"][0]["lifecycle"] == "decided"


def test_capture_current_decision_note_raises_integrity_error_when_rpc_returns_empty() -> (
    None
):
    client = _P1EvidenceClient()
    client.return_empty_decision_rpc = True
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        now=utcnow(),
    )
    client.rows_by_table["ideas"].append(
        {"user_id": "user-1", **captured.idea.model_dump(mode="json")}
    )
    client.rows_by_table["idea_versions"].append(
        {"user_id": "user-1", **captured.idea_version.model_dump(mode="json")}
    )
    client.rows_by_table["evidence_artifacts"].append(
        {"user_id": "user-1", **captured.evidence_artifact.model_dump(mode="json")}
    )
    decision = build_decision_note(
        evidence_artifact=captured.evidence_artifact,
        decision_id="decision-1",
        decision_state="watching",
        note="Track it.",
        now=utcnow(),
    )

    with pytest.raises(DecisionCaptureIntegrityError, match="Decision capture"):
        gateway.capture_current_decision_note(user_id="user-1", decision=decision)


def test_p1_decision_gateway_upsert_keeps_one_current_decision() -> None:
    client = _P1EvidenceClient()
    gateway = _gateway_for_p1_client(client)
    captured = build_backtest_evidence_capture(
        run=_completed_run(),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        now=utcnow(),
    )
    client.rows_by_table["ideas"].append(captured.idea.model_dump(mode="json"))
    client.rows_by_table["idea_versions"].append(
        captured.idea_version.model_dump(mode="json")
    )
    client.rows_by_table["evidence_artifacts"].append(
        captured.evidence_artifact.model_dump(mode="json")
    )
    first_decision = build_decision_note(
        evidence_artifact=captured.evidence_artifact,
        decision_id="decision-1",
        decision_state="watching",
        note="Track it.",
        now=utcnow(),
    )
    second_decision = build_decision_note(
        evidence_artifact=captured.evidence_artifact,
        decision_id="decision-2",
        decision_state="promising",
        note="Still promising.",
        now=utcnow(),
    )

    first = gateway.upsert_decision_note(user_id="user-1", decision=first_decision)
    second = gateway.upsert_decision_note(user_id="user-1", decision=second_decision)

    assert first.id == "decision-1"
    assert second.id == "decision-1"
    assert second.decision_state == "promising"
    assert second.note == "Still promising."
    assert len(client.rows_by_table["decision_notes"]) == 1


def test_gateway_history_delegates_to_bounded_postgres_reader() -> None:
    reader = MagicMock()
    reader.list_rows.return_value = {
        "runs": [],
        "conversations": [],
        "strategies": [],
        "collections": [],
    }
    gateway = SupabaseGateway(client=MagicMock(), history_reader=reader)

    result = gateway.list_history_rows(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=21,
        archived=True,
        deleted=True,
        cursor_activity_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        cursor_id="11111111-1111-1111-1111-111111111111",
        cursor_pinned=True,
        cursor_type_rank=3,
    )

    assert result == reader.list_rows.return_value
    reader.list_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=21,
        archived=True,
        deleted=True,
        cursor_activity_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        cursor_id="11111111-1111-1111-1111-111111111111",
        cursor_pinned=True,
        cursor_type_rank=3,
    )


def test_gateway_history_fails_closed_without_postgres_reader() -> None:
    gateway = SupabaseGateway(client=MagicMock())

    with pytest.raises(RuntimeError, match="Postgres reader"):
        gateway.list_history_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            limit=21,
        )


class _SearchRowsTable:
    """Fake table that drives the search_rows query chain over canned rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [dict(r) for r in rows]
        self._range: tuple[int, int] | None = None
        self._limit: int | None = None

    def select(self, *_args: object, **_kwargs: object):
        return self

    def eq(self, *_args: object, **_kwargs: object):
        return self

    def is_(self, *_args: object, **_kwargs: object):
        return self

    def order(self, *_args: object, **_kwargs: object):
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def execute(self):
        rows = self._rows
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        elif self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in rows])


class _SearchRowsClient:
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self._rows_by_table = rows_by_table

    def table(self, name: str):
        return _SearchRowsTable(self._rows_by_table.get(name, []))


def _idea_ledger_search_client() -> _SearchRowsClient:
    return _SearchRowsClient(
        {
            "ideas": [
                {
                    "id": "idea-1",
                    "title": "AAPL momentum",
                    "summary": "momentum thesis",
                    "lifecycle": "decided",
                    "active_version_id": "ver-1",
                    "source_conversation_id": "conv-1",
                    "updated_at": "2026-06-29T12:00:00Z",
                }
            ],
            "decision_notes": [
                {
                    "id": "dec-1",
                    "idea_id": "idea-1",
                    "decision_state": "promising",
                    "note": "keep",
                    "evidence_artifact_id": "art-1",
                    "source_conversation_id": "conv-1",
                    "updated_at": "2026-06-29T12:00:00Z",
                }
            ],
        }
    )


def test_search_rows_delegates_to_private_postgres_reader():
    search_reader = MagicMock()
    expected = SearchReadResult(
        rows={
            "conversations": [],
            "strategies": [],
            "collections": [],
            "runs": [],
            "ideas": [],
            "evidence": [],
            "decisions": [],
        },
        ledger_counts=None,
    )
    search_reader.search_rows.return_value = expected
    gateway = SupabaseGateway(
        client=_idea_ledger_search_client(),
        search_reader=search_reader,
    )

    result = gateway.search_rows(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        query="momentum",
        source_limit=21,
        cursor_updated_at=None,
        cursor_id=None,
        decision_state=None,
        include_ledger_groups=False,
        guest_scope=False,
        guest_conversation_id=None,
    )

    assert result is expected
    search_reader.search_rows.assert_called_once_with(
        scope=PERSONAL,
        user_id="00000000-0000-0000-0000-000000000001",
        query="momentum",
        source_limit=21,
        cursor_updated_at=None,
        cursor_id=None,
        decision_state=None,
        include_ledger_groups=False,
        guest_scope=False,
        guest_conversation_id=None,
    )


def test_search_rows_requires_private_postgres_reader():
    gateway = SupabaseGateway(client=_idea_ledger_search_client())

    with pytest.raises(
        RuntimeError,
        match="Persistent Search requires its Postgres reader",
    ):
        gateway.search_rows(
            scope=PERSONAL,
            user_id="00000000-0000-0000-0000-000000000001",
            query="",
            source_limit=21,
        )

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pytest
from argus.agent_runtime.confirmation_artifacts import (
    confirmation_artifact_reference,
    validate_confirmation_execution_payload,
)
from argus.agent_runtime.stages.execute import _launch_payload
from argus.agent_runtime.state.models import RunState
from argus.api.chat.backtest_jobs import payload_hash
from argus.api.chat.confirmation import runtime_confirmation_card
from argus.api.main import app
from argus.api.schemas import BacktestRun, Conversation, Message, User
from argus.domain.backtest_admission import chat_run_identity_hash
from faker import Faker
from fastapi.testclient import TestClient

FULL_LAUNCH_PAYLOAD_HASH = (
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)
MATCHING_IDENTITY_HASH = (
    "sha256:bb4f6bca954472872955f0338d433c17e9e04f616451d8c6b134f74d36909bfc"
)


class _ByActionGateway:
    def __init__(
        self,
        *,
        reservation_exists: bool = True,
        identity_hash: str = MATCHING_IDENTITY_HASH,
        artifact_issue: Literal[
            "none",
            "missing",
            "foreign_conversation",
            "non_assistant",
            "missing_confirmation_id",
            "short_launch_hash",
            "missing_canonical_hash",
            "reference_hash_mismatch",
        ] = "none",
        run_exists: bool = True,
        confirmation_metadata: dict[str, object] | None = None,
    ) -> None:
        fake = Faker()
        self.user = User(
            id="user-1",
            email=fake.email(),
            username=None,
            display_name="Mock Developer",
            language="en",
            locale="en-US",
            is_admin=True,
            created_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        )
        self.reservation_exists = reservation_exists
        self.artifact_issue = artifact_issue
        self.run_exists = run_exists
        self.confirmation_metadata = confirmation_metadata
        self.reservation_calls: list[dict[str, str]] = []
        self.message_calls: list[dict[str, str]] = []
        self.failure_updates: list[dict[str, object]] = []
        self.run = _run()
        self.job: dict[str, object] = {
            "id": "job-by-action-1",
            "user_id": self.user.id,
            "conversation_id": "conversation-1",
            "request_message_id": "request-message-1",
            "confirmation_message_id": "confirmation-message-1",
            "operation_scope": "chat.run_backtest",
            "idempotency_key": "confirmation-1",
            "identity_hash": identity_hash,
            "payload_hash": FULL_LAUNCH_PAYLOAD_HASH,
            "status": "succeeded",
            "result_run_id": self.run.id,
            "failure_code": None,
            "failure_detail": None,
            "retryable": False,
            "queued_at": "2026-07-24T12:00:00+00:00",
            "started_at": "2026-07-24T12:00:01+00:00",
            "finished_at": "2026-07-24T12:00:04+00:00",
            "created_at": "2026-07-24T12:00:00+00:00",
            "updated_at": "2026-07-24T12:00:04+00:00",
            "execution_metadata": {
                "workflow_backtest": {
                    "result_readout": "**Quick take**\n\nOne canonical result.",
                    "result_readout_source": "llm_explain_stage",
                    "result_readout_fallback_used": False,
                }
            },
        }

    def get_or_create_mock_user(self) -> User:
        return self.user

    def get_backtest_job_reservation(
        self,
        *,
        user_id: str,
        operation_scope: str,
        idempotency_key: str,
    ) -> dict[str, object] | None:
        self.reservation_calls.append(
            {
                "user_id": user_id,
                "operation_scope": operation_scope,
                "idempotency_key": idempotency_key,
            }
        )
        return dict(self.job) if self.reservation_exists else None

    def get_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> Message | None:
        self.message_calls.append(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
            }
        )
        if self.artifact_issue == "missing":
            return None
        if self.confirmation_metadata is not None:
            return Message(
                id="confirmation-message-1",
                conversation_id=conversation_id,
                role="assistant",
                content="Ready to run.",
                metadata=self.confirmation_metadata,
                created_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            )
        card = {
            "confirmation_id": "confirmation-1",
            "launch_payload_hash": FULL_LAUNCH_PAYLOAD_HASH,
            "canonical_launch_payload_hash": FULL_LAUNCH_PAYLOAD_HASH,
        }
        if self.artifact_issue == "missing_confirmation_id":
            card.pop("confirmation_id")
        if self.artifact_issue == "short_launch_hash":
            card["launch_payload_hash"] = "aaaaaaaaaaaaaaaa"
            card["canonical_launch_payload_hash"] = "aaaaaaaaaaaaaaaa"
        if self.artifact_issue == "missing_canonical_hash":
            card.pop("canonical_launch_payload_hash")
            card["launch_payload_hash"] = FULL_LAUNCH_PAYLOAD_HASH
        reference_hash = (
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            if self.artifact_issue == "reference_hash_mismatch"
            else FULL_LAUNCH_PAYLOAD_HASH
        )
        return Message(
            id="confirmation-message-1",
            conversation_id=(
                "conversation-2"
                if self.artifact_issue == "foreign_conversation"
                else conversation_id
            ),
            role="user" if self.artifact_issue == "non_assistant" else "assistant",
            content="Ready to run.",
            metadata={
                "confirmation_card": card,
                "active_confirmation_reference": {
                    "artifact_kind": "confirmation",
                    "artifact_id": "confirmation-1",
                    "artifact_status": "active",
                    "metadata": {
                        "canonical_launch_payload_hash": reference_hash,
                    },
                },
            },
            created_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        )

    def get_backtest_run(
        self,
        *,
        user_id: str,
        run_id: str,
    ) -> BacktestRun | None:
        if not self.run_exists:
            return None
        if user_id == self.user.id and run_id == self.run.id:
            return self.run
        return None

    def get_backtest_job(
        self,
        *,
        user_id: str,
        job_id: str,
    ) -> dict[str, object] | None:
        if user_id == self.user.id and job_id == self.job["id"]:
            return dict(self.job)
        return None

    def mark_backtest_job_failed(self, **payload: object) -> dict[str, object]:
        self.failure_updates.append(payload)
        if self.job["status"] != payload.get("expected_status"):
            return {}
        self.job.update(
            {
                "status": "failed",
                "failure_code": payload["failure_code"],
                "failure_detail": payload["failure_detail"],
                "retryable": payload["retryable"],
                "finished_at": payload["finished_at"],
                "execution_metadata": payload["execution_metadata"],
            }
        )
        return dict(self.job)


def _run() -> BacktestRun:
    return BacktestRun(
        id="run-by-action-1",
        conversation_id="conversation-1",
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={
            "aggregate": {"performance": {"total_return_pct": 12.4}},
            "by_symbol": {},
        },
        config_snapshot={"template": "buy_and_hold", "benchmark_symbol": "SPY"},
        conversation_result_card={
            "title": "AAPL buy and hold",
            "date_range": {
                "start": "2025-07-24",
                "end": "2026-07-24",
                "display": "July 24, 2025 to July 24, 2026",
            },
            "status_label": "Simulation Complete",
            "rows": [],
            "assumptions": ["Long-only", "Benchmark: SPY"],
            "actions": [],
        },
        created_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        chart=None,
        trades=[],
    )


class _ConversationReloadGateway(_ByActionGateway):
    def __init__(self) -> None:
        super().__init__()
        self.raw_messages: list[Message] = []
        self.jobs_by_action: dict[str, dict[str, object]] = {}
        self.batch_reservation_calls: list[dict[str, object]] = []

    def get_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> Conversation | None:
        if user_id != self.user.id or conversation_id != "conversation-1":
            return None
        now = datetime(2026, 7, 24, tzinfo=timezone.utc)
        return Conversation(
            id=conversation_id,
            user_id=user_id,
            title="AAPL idea",
            title_source="system_default",
            language="en",
            created_at=now,
            updated_at=now,
        )

    def list_messages(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int | None,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
        page: bool = False,
    ) -> list[Message]:
        assert user_id == self.user.id
        assert conversation_id == "conversation-1"
        assert (cursor_created_at is None) == (cursor_id is None)
        ordered = sorted(
            self.raw_messages,
            key=lambda message: (message.created_at, message.id),
        )
        if cursor_created_at is not None and cursor_id is not None:
            cursor_key = (cursor_created_at, cursor_id)
            ordered = [
                message
                for message in ordered
                if (message.created_at, message.id) > cursor_key
            ]
        if page:
            assert limit is not None
            return ordered[: limit + 1]
        return ordered if limit is None else ordered[:limit]

    def list_message_page_context(
        self,
        *,
        user_id: str,
        conversation_id: str,
        page_messages: list[Message],
    ) -> tuple[list[Message], set[str]]:
        assert user_id == self.user.id
        assert conversation_id == "conversation-1"
        if not page_messages:
            return [], set()

        last_key = max(
            (message.created_at, message.id) for message in page_messages
        )
        later = [
            message
            for message in sorted(
                self.raw_messages,
                key=lambda message: (message.created_at, message.id),
            )
            if (message.created_at, message.id) > last_key
        ]
        witnesses: dict[str, Message] = {}

        later_user = next(
            (message for message in later if message.role == "user"),
            None,
        )
        if later_user is not None:
            witnesses[later_user.id] = later_user

        action_message_ids = {
            message.id
            for message in page_messages
            if message.role == "user"
            and isinstance(message.metadata, dict)
            and isinstance(message.metadata.get("chat_action"), dict)
            and message.metadata["chat_action"].get("type") == "run_backtest"
        }
        represented_request_ids: set[str] = set()
        for message in later:
            job = (
                message.metadata.get("backtest_job")
                if message.role == "assistant"
                and isinstance(message.metadata, dict)
                else None
            )
            if not isinstance(job, dict):
                continue
            request_message_id = job.get("request_message_id")
            if (
                isinstance(request_message_id, str)
                and request_message_id in action_message_ids
                and request_message_id not in represented_request_ids
            ):
                represented_request_ids.add(request_message_id)
                witnesses[message.id] = message

        return (
            sorted(
                witnesses.values(),
                key=lambda message: (message.created_at, message.id),
            ),
            represented_request_ids,
        )

    def list_backtest_job_reservations(
        self,
        *,
        user_id: str,
        conversation_id: str,
        operation_scope: str,
        idempotency_keys: list[str],
    ) -> list[dict[str, object]]:
        self.batch_reservation_calls.append(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "operation_scope": operation_scope,
                "idempotency_keys": list(idempotency_keys),
            }
        )
        return [
            dict(job)
            for confirmation_id in idempotency_keys
            for job in [self.jobs_by_action.get(confirmation_id)]
            if job is not None
        ]

    def reconcile_stale_chat_turns(self, **_: object) -> list[dict[str, object]]:
        return []

    def list_projectable_chat_turns(self, **_: object) -> list[dict[str, object]]:
        return []


def _run_action_message(
    index: int,
    confirmation_id: str,
    *,
    message_id: str | None = None,
) -> Message:
    return Message(
        id=message_id or f"request-message-{index}",
        conversation_id="conversation-1",
        role="user",
        content="Run backtest",
        metadata={
            "chat_action": {
                "type": "run_backtest",
                "payload": {"confirmation_id": confirmation_id},
            }
        },
        created_at=datetime(2026, 7, 24, 12, 0, index, tzinfo=timezone.utc),
    )


@pytest.fixture(autouse=True)
def _mock_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "true")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")


def test_by_action_lookup_reads_running_database_truth_without_render_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.chat.backtest_jobs import RenderTaskRunClient

    gateway = _ByActionGateway()
    gateway.job.update(
        {
            "status": "running",
            "result_run_id": None,
            "finished_at": None,
            "execution_metadata": {
                "workflow_dispatch": {"task_run_id": "task-run-private-1"}
            },
        }
    )
    render_calls: list[str] = []
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(
        RenderTaskRunClient,
        "get_task_run",
        lambda _self, task_run_id: render_calls.append(task_run_id),
    )

    response = TestClient(app).get("/api/v1/backtest-jobs/by-action/confirmation-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["id"] == "job-by-action-1"
    assert payload["job"]["status"] == "running"
    assert payload["run"] is None
    assert render_calls == []
    assert gateway.reservation_calls == [
        {
            "user_id": "user-1",
            "operation_scope": "chat.run_backtest",
            "idempotency_key": "confirmation-1",
        }
    ]


def test_by_action_lookup_returns_404_for_missing_owner_scoped_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ByActionGateway(reservation_exists=False)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get("/api/v1/backtest-jobs/by-action/confirmation-1")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "job-by-action-1" not in response.text
    assert gateway.message_calls == []
    assert gateway.reservation_calls[0]["operation_scope"] == "chat.run_backtest"


def test_by_action_owner_read_terminalizes_stale_undispatched_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.chat.backtest_jobs import RenderTaskRunClient

    gateway = _ByActionGateway()
    gateway.job.update(
        {
            "status": "queued",
            "result_run_id": None,
            "finished_at": None,
            "created_at": "2026-07-24T00:00:00+00:00",
            "launch_payload": {"kind": "run_backtest_job"},
            "execution_metadata": {},
        }
    )
    render_calls: list[str] = []
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    monkeypatch.setattr(
        RenderTaskRunClient,
        "get_task_run",
        lambda _self, task_run_id: render_calls.append(task_run_id),
    )

    response = TestClient(app).get("/api/v1/backtest-jobs/by-action/confirmation-1")

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "failed"
    assert response.json()["job"]["failure_code"] == "workflow_dispatch_missing"
    assert response.json()["job"]["retryable"] is True
    assert gateway.failure_updates[0]["expected_status"] == "queued"
    assert render_calls == []
    assert len(gateway.reservation_calls) == 1


def test_conversation_reload_projects_stale_run_job_without_assistant_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ConversationReloadGateway()
    gateway.job.update(
        {
            "status": "queued",
            "result_run_id": None,
            "finished_at": None,
            "created_at": "2026-07-24T00:00:00+00:00",
            "launch_payload": {"kind": "run_backtest_job"},
            "execution_metadata": {},
        }
    )
    gateway.raw_messages = [_run_action_message(1, "confirmation-1")]
    gateway.jobs_by_action = {"confirmation-1": gateway.job}
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get(
        "/api/v1/conversations/conversation-1/messages"
    )

    assert response.status_code == 200
    [message] = response.json()["items"]
    assert message["id"] == "request-message-1"
    assert message["metadata"]["backtest_job"]["status"] == "queued"
    assert message["metadata"]["backtest_job_id"] == "job-by-action-1"
    assert gateway.reservation_calls == []
    assert gateway.batch_reservation_calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "operation_scope": "chat.run_backtest",
            "idempotency_keys": ["confirmation-1"],
        }
    ]

    job_response = TestClient(app).get(
        "/api/v1/backtest-jobs/job-by-action-1"
    )

    assert job_response.status_code == 200
    assert job_response.json()["job"]["status"] == "failed"
    assert job_response.json()["job"]["failure_code"] == "workflow_dispatch_missing"
    assert gateway.failure_updates[0]["expected_status"] == "queued"
    assert gateway.failure_updates[0]["expected_updated_at"] == (
        "2026-07-24T12:00:04+00:00"
    )


def test_conversation_reload_batches_only_page_run_actions_across_cursors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ConversationReloadGateway()
    message_ids = {
        index: f"10000000-0000-0000-0000-{index:012d}"
        for index in range(1, 5)
    }
    gateway.raw_messages = [
        _run_action_message(
            index,
            f"confirmation-{index}",
            message_id=message_ids[index],
        )
        for index in range(1, 5)
    ]
    gateway.jobs_by_action = {
        f"confirmation-{index}": {
            **gateway.job,
            "id": f"job-{index}",
            "request_message_id": message_ids[index],
            "idempotency_key": f"confirmation-{index}",
        }
        for index in range(1, 5)
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    client = TestClient(app)

    first = client.get(
        "/api/v1/conversations/conversation-1/messages",
        params={"limit": 2},
    )

    assert first.status_code == 200
    assert [
        item["metadata"]["backtest_job"]["id"] for item in first.json()["items"]
    ] == ["job-1", "job-2"]
    assert first.json()["next_cursor"] is not None
    assert gateway.reservation_calls == []
    assert gateway.batch_reservation_calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "operation_scope": "chat.run_backtest",
            "idempotency_keys": ["confirmation-1", "confirmation-2"],
        }
    ]

    second = client.get(
        "/api/v1/conversations/conversation-1/messages",
        params={"limit": 2, "cursor": first.json()["next_cursor"]},
    )

    assert second.status_code == 200
    assert [
        item["metadata"]["backtest_job"]["id"] for item in second.json()["items"]
    ] == ["job-3", "job-4"]
    assert second.json()["next_cursor"] is None
    assert gateway.batch_reservation_calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "operation_scope": "chat.run_backtest",
            "idempotency_keys": ["confirmation-1", "confirmation-2"],
        },
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "operation_scope": "chat.run_backtest",
            "idempotency_keys": ["confirmation-3", "confirmation-4"],
        },
    ]


def test_conversation_reload_keeps_global_assistant_job_representation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ConversationReloadGateway()
    gateway.raw_messages = [
        _run_action_message(1, "confirmation-1"),
        Message(
            id="assistant-job-1",
            conversation_id="conversation-1",
            role="assistant",
            content="Queued.",
            metadata={
                "backtest_job_id": "job-by-action-1",
                "backtest_job": gateway.job,
            },
            created_at=datetime(2026, 7, 24, 12, 0, 2, tzinfo=timezone.utc),
        ),
    ]
    gateway.jobs_by_action = {"confirmation-1": gateway.job}
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get(
        "/api/v1/conversations/conversation-1/messages",
        params={"limit": 1},
    )

    assert response.status_code == 200
    [message] = response.json()["items"]
    assert "backtest_job" not in message["metadata"]
    assert gateway.reservation_calls == []
    assert gateway.batch_reservation_calls == []


def test_conversation_reload_rejects_batch_job_for_wrong_request_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ConversationReloadGateway()
    gateway.raw_messages = [_run_action_message(1, "confirmation-1")]
    gateway.jobs_by_action = {
        "confirmation-1": {
            **gateway.job,
            "request_message_id": "request-message-other",
        }
    }
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get(
        "/api/v1/conversations/conversation-1/messages"
    )

    assert response.status_code == 200
    [message] = response.json()["items"]
    assert "backtest_job" not in message["metadata"]
    assert gateway.batch_reservation_calls[0]["idempotency_keys"] == [
        "confirmation-1"
    ]


def test_by_action_lookup_returns_409_without_job_disclosure_on_identity_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ByActionGateway(
        identity_hash=(
            "sha256:cccccccccccccccccccccccccccccccc" "cccccccccccccccccccccccccccccccc"
        )
    )
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get("/api/v1/backtest-jobs/by-action/confirmation-1")

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"
    assert "job-by-action-1" not in response.text
    assert "run-by-action-1" not in response.text


@pytest.mark.parametrize(
    "artifact_issue",
    [
        "missing",
        "foreign_conversation",
        "non_assistant",
        "missing_confirmation_id",
        "short_launch_hash",
        "missing_canonical_hash",
        "reference_hash_mismatch",
    ],
)
def test_by_action_lookup_returns_safe_500_for_inconsistent_confirmation_artifact(
    monkeypatch: pytest.MonkeyPatch,
    artifact_issue: Literal[
        "missing",
        "foreign_conversation",
        "non_assistant",
        "missing_confirmation_id",
        "short_launch_hash",
        "missing_canonical_hash",
        "reference_hash_mismatch",
    ],
) -> None:
    from argus.api import state as api_state

    gateway = _ByActionGateway(artifact_issue=artifact_issue)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get("/api/v1/backtest-jobs/by-action/confirmation-1")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "job-by-action-1" not in response.text
    assert "run-by-action-1" not in response.text


def test_real_confirmation_persists_full_launch_identity_used_by_job_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    embedded_launch_request = {
        "strategy_type": "buy_and_hold",
        "symbol": "AAPL",
        "symbols": ["AAPL"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": {"start": "2024-01-01", "end": "2025-01-01"},
        "requested_date_range": None,
        "coverage_preflight": None,
        "entry_rule": None,
        "exit_rule": None,
        "rule_spec": None,
        "sizing_mode": "capital_amount",
        "capital_amount": 10_000.0,
        "position_size": None,
        "cadence": None,
        "parameters": {},
        "risk_rules": [],
        "benchmark_symbol": "SPY",
        "language": "en",
    }
    confirmation_payload = {
        "confirmation_id": "confirmation-1",
        "strategy": {
            "strategy_type": "buy_and_hold",
            "asset_universe": ["AAPL"],
            "asset_class": "equity",
            "date_range": {"start": "2024-01-01", "end": "2025-01-01"},
        },
        "optional_parameters": {},
        "launch_payload": embedded_launch_request,
        "validation": {"executable": True},
    }
    card = runtime_confirmation_card(
        {
            "stage_outcome": "await_approval",
            "confirmation_payload": confirmation_payload,
        },
        confirmation_id="confirmation-1",
        conversation_id="conversation-1",
    )
    assert card is not None
    reference = confirmation_artifact_reference(
        confirmation_id="confirmation-1",
        confirmation_payload=confirmation_payload,
        confirmation_card=card,
    )
    validation = validate_confirmation_execution_payload(confirmation_payload)
    assert validation.launch_payload is not None
    run_state = RunState(
        current_user_message="Run backtest",
        confirmation_payload=confirmation_payload,
    )
    actual_admitted_request = _launch_payload(run_state)
    admitted_payload_hash = payload_hash(actual_admitted_request)

    assert validation.launch_payload == actual_admitted_request
    assert "_execution_realism" not in actual_admitted_request
    assert actual_admitted_request["position_size"] is None
    assert actual_admitted_request["cadence"] is None
    explicit_realism = {
        "enabled": True,
        "fee_bps": 10.0,
        "slippage_bps": 5.0,
    }
    realism_validation = validate_confirmation_execution_payload(
        {
            **confirmation_payload,
            "launch_payload": {
                **embedded_launch_request,
                "_execution_realism": explicit_realism,
            },
        }
    )
    assert realism_validation.launch_payload is not None
    assert realism_validation.launch_payload["_execution_realism"] == explicit_realism
    assert "execution_realism" not in realism_validation.launch_payload
    assert card["canonical_launch_payload_hash"] == admitted_payload_hash
    assert (
        reference.metadata["canonical_launch_payload_hash"]
        == admitted_payload_hash
    )
    assert card["launch_payload_hash"] != admitted_payload_hash

    gateway = _ByActionGateway(
        confirmation_metadata={
            "confirmation_card": card,
            "confirmation_payload": confirmation_payload,
            "active_confirmation_reference": reference.model_dump(mode="python"),
        }
    )
    gateway.job["payload_hash"] = admitted_payload_hash
    gateway.job["identity_hash"] = chat_run_identity_hash(
        conversation_id="conversation-1",
        confirmation_id="confirmation-1",
        launch_payload_hash=admitted_payload_hash,
    )
    assert gateway.job["payload_hash"] == card["canonical_launch_payload_hash"]
    assert gateway.job["identity_hash"] == chat_run_identity_hash(
        conversation_id="conversation-1",
        confirmation_id="confirmation-1",
        launch_payload_hash=card["canonical_launch_payload_hash"],
    )
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get(
        "/api/v1/backtest-jobs/by-action/confirmation-1"
    )

    assert response.status_code == 200
    assert response.json()["job"]["id"] == "job-by-action-1"


def test_by_action_lookup_returns_safe_500_when_succeeded_job_has_no_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ByActionGateway(run_exists=False)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app).get("/api/v1/backtest-jobs/by-action/confirmation-1")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "job-by-action-1" not in response.text
    assert "run-by-action-1" not in response.text


@pytest.mark.parametrize("failing_read", ["reservation", "message"])
def test_by_action_lookup_shapes_persistence_read_failures_as_safe_500(
    monkeypatch: pytest.MonkeyPatch,
    failing_read: Literal["reservation", "message"],
) -> None:
    from argus.api import state as api_state

    gateway = _ByActionGateway()

    def fail_read(**_: object) -> None:
        raise RuntimeError("private persistence detail")

    if failing_read == "reservation":
        monkeypatch.setattr(gateway, "get_backtest_job_reservation", fail_read)
    else:
        monkeypatch.setattr(gateway, "get_message", fail_read)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/backtest-jobs/by-action/confirmation-1"
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == "internal_error"
    assert "private persistence detail" not in response.text
    assert "job-by-action-1" not in response.text


def test_by_action_lookup_shapes_malformed_durable_job_as_safe_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    gateway = _ByActionGateway()
    gateway.job["status"] = "unknown"
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/backtest-jobs/by-action/confirmation-1"
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == "internal_error"
    assert "job-by-action-1" not in response.text

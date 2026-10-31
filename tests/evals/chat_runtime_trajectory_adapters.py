from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
import respx
from argus.agent_runtime.graph.workflow import build_workflow
from argus.agent_runtime.stages.interpret import (
    InterpretationRequest,
    StructuredInterpretation,
)
from argus.agent_runtime.stages.interpret_types import AssetDiscoveryRequest
from argus.agent_runtime.state.models import StrategySummary
from argus.agent_runtime.tools.real_backtest import RealBacktestTool
from argus.api import state as api_state
from argus.api.chat.backtest_jobs import ShadowBacktestJobTool
from argus.api.chat.turn_lifecycle_hooks import ChatTurnLifecycleHooks
from argus.api.main import app
from argus.domain import backtest_admission
from argus.domain.backtest_finalization import MemoryBacktestFinalizationGateway
from argus.domain.store import utcnow
from argus.llm.openrouter import (
    _SCHEMA_IN_PROMPT_INSTRUCTION,
    clear_openrouter_route_receipts,
    invoke_openrouter_json_schema,
)
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from tests.evals.chat_runtime_eval_harness import (
    AlphaTrajectory,
    StepObservation,
    TrajectoryAdapters,
    TrajectoryStep,
    TrajectoryStepResult,
    parse_sse_events,
)


@dataclass
class _TrajectoryState:
    conversation_id: str
    artifact_aliases: dict[str, str] = field(default_factory=dict)
    raw_artifact_ids: dict[str, str] = field(default_factory=dict)
    disconnected_turn_id: str | None = None
    disconnected_request_id: str | None = None
    disconnected_raw_request_id: str | None = None
    replay_count: int = 0
    route_submission_count: int = 0


@dataclass(frozen=True)
class _StreamResult:
    raw_sse: str
    events: tuple[dict[str, Any], ...]
    final: dict[str, Any]
    receipts: tuple[dict[str, Any], ...]
    execution_summary: dict[str, Any]

    @property
    def typed_terminal(self) -> bool:
        return any(event.get("type") in {"final", "error"} for event in self.events)


class _TransportCut(BaseException):
    """Named test-only cut after route admission and before a client terminal."""


class _MemoryBacktestGateway:
    def __init__(self) -> None:
        self.route_receipts: list[dict[str, Any]] = []
        self.cost_ledger_entries: list[dict[str, Any]] = []

    def get_or_create_mock_user(self):
        return api_state.store.get_or_create_dev_user()

    def admit_backtest_job(
        self,
        *,
        allowance_limits: list[dict[str, object]] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        outcome = backtest_admission.admit_backtest_job_memory(
            api_state.store,
            **kwargs,
            allowance_limits=allowance_limits,
        )
        return {
            "decision": outcome.kind,
            "job": outcome.job,
            "retry_after_seconds": outcome.retry_after_seconds,
        }

    def get_backtest_job_reservation(
        self,
        *,
        user_id: str,
        operation_scope: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        job_id = api_state.store.backtest_job_reservations.get(
            (user_id, operation_scope, idempotency_key)
        )
        job = api_state.store.backtest_jobs.get(job_id or "")
        return dict(job) if job is not None else None

    def get_backtest_job(
        self,
        *,
        user_id: str,
        job_id: str,
    ) -> dict[str, Any] | None:
        job = api_state.store.backtest_jobs.get(job_id)
        if job is None or job.get("user_id") != user_id:
            return None
        return dict(job)

    def get_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message_id: str,
    ):
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            return None
        return next(
            (
                message
                for message in api_state.store.messages.get(conversation_id, [])
                if message.id == message_id
            ),
            None,
        )

    def get_backtest_run(self, *, user_id: str, run_id: str):
        run = api_state.store.backtest_runs.get(run_id)
        return run if run is not None and run.user_id == user_id else None

    def count_backtest_jobs(
        self,
        *,
        status: str,
        user_id: str | None = None,
        limit: int | None = None,
    ) -> int:
        count = sum(
            job.get("status") == status
            and (user_id is None or job.get("user_id") == user_id)
            for job in api_state.store.backtest_jobs.values()
        )
        return min(count, limit) if limit is not None else count

    def list_backtest_jobs(
        self,
        *,
        status: str,
        user_id: str | None = None,
        limit: int = 100,
        **_: Any,
    ) -> list[dict[str, Any]]:
        return [
            dict(job)
            for job in api_state.store.backtest_jobs.values()
            if job.get("status") == status
            and (user_id is None or job.get("user_id") == user_id)
        ][:limit]

    def merge_backtest_job_execution_metadata(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        job = api_state.store.backtest_jobs.get(job_id)
        if job is None or job.get("user_id") != user_id:
            return None
        merged = dict(job.get("execution_metadata") or {})
        for key, value in execution_metadata.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        job["execution_metadata"] = merged
        return dict(job)

    def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        job = api_state.store.backtest_jobs.get(job_id)
        return dict(job) if job is not None else None

    def mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
        started_at: str | None = None,
    ) -> dict[str, Any]:
        job = self._owned_job(user_id=user_id, job_id=job_id)
        claim_started_at = started_at or utcnow().isoformat()
        claimed_metadata = dict(execution_metadata)
        workflow_metadata = dict(claimed_metadata.get("workflow_backtest") or {})
        workflow_metadata["started_at"] = claim_started_at
        claimed_metadata["workflow_backtest"] = workflow_metadata
        job.update(
            {
                "status": "running",
                "started_at": claim_started_at,
                "attempts": int(job.get("attempts") or 0) + 1,
                "result_run_id": None,
                "finished_at": None,
                "failure_code": None,
                "failure_detail": None,
                "retryable": False,
                "execution_metadata": claimed_metadata,
            }
        )
        return dict(job)

    def finalize_backtest_completion(self, *, finalization: Any) -> Any:
        return MemoryBacktestFinalizationGateway(
            api_state.store
        ).finalize_backtest_completion(finalization=finalization)

    def link_backtest_job_result(
        self,
        *,
        user_id: str,
        job_id: str,
        result_run_id: str,
        execution_metadata: dict[str, Any] | None = None,
        mark_succeeded: bool = False,
    ) -> dict[str, Any]:
        job = self._owned_job(user_id=user_id, job_id=job_id)
        if not mark_succeeded:
            raise AssertionError(
                "completed trajectory result must mark its job succeeded"
            )
        job.update(
            {
                "status": "succeeded",
                "result_run_id": result_run_id,
                "failure_code": None,
                "failure_detail": None,
                "retryable": False,
                "finished_at": utcnow().isoformat(),
                "execution_metadata": self._merged_execution_metadata(
                    job,
                    execution_metadata,
                ),
            }
        )
        return dict(job)

    def mark_backtest_job_failed(
        self,
        *,
        user_id: str,
        job_id: str,
        failure_code: str,
        failure_detail: str,
        retryable: bool,
        execution_metadata: dict[str, Any] | None = None,
        finished_at: str | None = None,
    ) -> dict[str, Any]:
        job = self._owned_job(user_id=user_id, job_id=job_id)
        job.update(
            {
                "status": "failed",
                "failure_code": failure_code,
                "failure_detail": failure_detail,
                "retryable": retryable,
                "finished_at": finished_at or utcnow().isoformat(),
                "execution_metadata": self._merged_execution_metadata(
                    job,
                    execution_metadata,
                ),
            }
        )
        return dict(job)

    def create_route_receipt(
        self,
        *,
        user_id: str | None,
        receipt: dict[str, Any],
        conversation_id: str | None = None,
        run_id: str | None = None,
        message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stored = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "message_id": message_id,
            "metadata": dict(metadata or {}),
            "receipt": dict(receipt),
        }
        self.route_receipts.append(stored)
        return dict(stored)

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        stored = dict(entry)
        self.cost_ledger_entries.append(stored)
        return stored

    @staticmethod
    def _owned_job(*, user_id: str, job_id: str) -> dict[str, Any]:
        job = api_state.store.backtest_jobs.get(job_id)
        if job is None or job.get("user_id") != user_id:
            raise AssertionError("trajectory worker received an unknown backtest job")
        return job

    @staticmethod
    def _merged_execution_metadata(
        job: dict[str, Any],
        patch: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(job.get("execution_metadata") or {})
        merged.update(patch or {})
        return merged


class _DeterministicDispatcher:
    def dispatch(self, *, job_id: str, nonce: str) -> dict[str, Any]:
        return {
            "id": f"task-{job_id}",
            "status": "pending",
            "nonce": nonce,
        }


class _DeterministicInterpreter:
    async def ainvoke(
        self,
        request: InterpretationRequest,
    ) -> StructuredInterpretation:
        interpretation = self._interpret(request)
        provider_result = await invoke_openrouter_json_schema(
            task="interpretation",
            messages=[
                {
                    "role": "system",
                    "content": "Return the supplied typed interpretation unchanged.",
                },
                {
                    "role": "user",
                    "content": interpretation.model_dump_json(),
                },
            ],
            schema_model=StructuredInterpretation,
            schema_name="StructuredInterpretation",
            model_name="openai/trajectory-fixture",
        )
        if not isinstance(provider_result, StructuredInterpretation):
            raise AssertionError("typed trajectory provider returned no interpretation")
        return provider_result

    @staticmethod
    def _interpret(request: InterpretationRequest) -> StructuredInterpretation:
        message = request.current_user_message.strip()
        lowered = message.casefold()
        if "retail stock" in lowered:
            return StructuredInterpretation(
                intent="conversation_followup",
                task_relation="continue",
                requires_clarification=False,
                user_goal_summary="The user wants retail candidates to test.",
                asset_discovery=AssetDiscoveryRequest(
                    relationship="category",
                    category_description="retail stocks",
                    asset_class_hint="equity",
                    needs_current_facts=False,
                ),
                confidence=0.95,
                semantic_turn_act="asset_discovery",
            )
        if "aapl" in lowered and "rsi" in lowered:
            return _DeterministicInterpreter._rsi_threshold(
                request=request,
                symbol="AAPL",
            )
        if "impulso" in lowered or lowered == "reintentar":
            return StructuredInterpretation(
                intent="backtest_execution",
                task_relation="continue" if lowered == "reintentar" else "new_task",
                requires_clarification=True,
                user_goal_summary="El usuario necesita elegir una regla concreta.",
                candidate_strategy_draft=StrategySummary(
                    raw_user_phrasing=message,
                    strategy_type=None,
                    asset_universe=["BTC"],
                    asset_class="crypto",
                    timeframe="1D",
                    date_range="last year",
                ),
                missing_required_fields=["strategy_type"],
                assistant_response="¿Qué regla concreta quieres probar?",
                confidence=0.95,
                semantic_turn_act=(
                    "retry_failed_action" if lowered == "reintentar" else "new_idea"
                ),
            )
        if "500 dollars monthly in cart" in lowered:
            return _DeterministicInterpreter._buy_and_hold(
                request=request,
                symbol="CART",
                date_range={"start": "2020-01-01", "end": "2026-01-01"},
                capital_amount=500,
                cadence="monthly",
                strategy_type="dca_accumulation",
            )
        if "use nvda instead" in lowered:
            return _DeterministicInterpreter._buy_and_hold(
                request=request,
                symbol="NVDA",
                task_relation="refine",
                semantic_turn_act="refine_current_idea",
            )
        if "last six months" in lowered:
            return StructuredInterpretation(
                intent="backtest_execution",
                task_relation="refine",
                requires_clarification=False,
                user_goal_summary="The user changed the active date window.",
                candidate_strategy_draft=StrategySummary(
                    raw_user_phrasing=message,
                    date_range="last six months",
                    refinement_of="active confirmation",
                ),
                confidence=0.95,
                semantic_turn_act="refine_current_idea",
            )
        symbol = next(
            (
                candidate
                for candidate in ("AAPL", "TSLA", "BTC", "MSFT")
                if candidate.casefold() in lowered
            ),
            "AAPL",
        )
        return _DeterministicInterpreter._buy_and_hold(
            request=request,
            symbol=symbol,
        )

    @staticmethod
    def _buy_and_hold(
        *,
        request: InterpretationRequest,
        symbol: str,
        date_range: str | dict[str, Any] = "last year",
        capital_amount: float = 10_000,
        cadence: str | None = None,
        strategy_type: str = "buy_and_hold",
        task_relation: str = "new_task",
        semantic_turn_act: str = "new_idea",
    ) -> StructuredInterpretation:
        asset_class = "crypto" if symbol == "BTC" else "equity"
        return StructuredInterpretation(
            intent="backtest_execution",
            task_relation=task_relation,
            requires_clarification=False,
            user_goal_summary=f"The user wants to test {symbol}.",
            candidate_strategy_draft=StrategySummary(
                raw_user_phrasing=request.current_user_message,
                strategy_type=strategy_type,
                strategy_thesis=f"Buy and hold {symbol}.",
                asset_universe=[symbol],
                asset_class=asset_class,
                timeframe="1D",
                cadence=cadence,
                date_range=date_range,
                capital_amount=capital_amount,
            ),
            confidence=0.95,
            semantic_turn_act=semantic_turn_act,
        )

    @staticmethod
    def _rsi_threshold(
        *,
        request: InterpretationRequest,
        symbol: str,
    ) -> StructuredInterpretation:
        return StructuredInterpretation(
            intent="backtest_execution",
            task_relation="new_task",
            requires_clarification=False,
            user_goal_summary=f"The user wants to test {symbol} with RSI.",
            candidate_strategy_draft=StrategySummary(
                raw_user_phrasing=request.current_user_message,
                strategy_type="rsi_threshold",
                strategy_thesis=f"Test {symbol} with RSI.",
                asset_universe=[symbol],
                asset_class="equity",
                timeframe="1D",
                date_range="last year",
                entry_logic="Buy when RSI drops below 30",
                exit_logic="Sell when RSI rises above 55",
            ),
            confidence=0.95,
            semantic_turn_act="new_idea",
        )


class ConcreteTrajectoryRuntime:
    """Exercise trajectory steps through production HTTP and memory owners."""

    def __init__(self, *, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._client: TestClient | None = None
        self._states: dict[str, _TrajectoryState] = {}
        self._persisted_route_evidence: dict[str, list[dict[str, Any]]] = {}
        self._provider_router = respx.mock(assert_all_called=False)
        self._backtest_gateway = _MemoryBacktestGateway()
        self._workflow = build_workflow(
            tool=ShadowBacktestJobTool(
                delegate=None,
                gateway_getter=lambda: self._backtest_gateway,
                dev_memory_fallback_getter=lambda: False,
                dispatcher_getter=lambda: _DeterministicDispatcher(),
            ),
            structured_interpreter=_DeterministicInterpreter(),
            checkpointer=MemorySaver(),
        )
        self.adapters = TrajectoryAdapters(
            stream=self.stream,
            action=self.action,
            disconnect=self.disconnect,
            reload=self.reload,
            retry=self.retry,
            persistence=self.persistence,
        )

    def __enter__(self) -> ConcreteTrajectoryRuntime:
        from argus.api.routers import agent as agent_router
        from argus.domain.market_data import assets, provider

        self._monkeypatch.setattr(api_state, "supabase_gateway", None)
        self._monkeypatch.setenv("OPENROUTER_API_KEY", "trajectory-fixture-key")
        self._monkeypatch.setenv("CUADRAO_CHAT_MODEL", "openai/trajectory-fixture")
        self._monkeypatch.setenv("PERPLEXITY_API_KEY", "")
        self._monkeypatch.setenv("ARGUS_GROUNDED_DISCOVERY_ENABLED", "false")
        self._monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "true")
        self._monkeypatch.setenv("CUADRAO_RUNTIME_STREAM_WORKER", "false")
        self._monkeypatch.setenv("ARGUS_BACKTEST_JOBS_SHADOW_ENABLED", "true")
        self._monkeypatch.setenv("ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED", "true")
        self._monkeypatch.setenv("ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED", "true")
        self._monkeypatch.setattr(
            api_state,
            "get_agent_runtime_workflow",
            lambda _request=None: self._workflow,
        )
        self._monkeypatch.setattr(
            agent_router,
            "schedule_artifact_naming_after_stream",
            lambda **_: None,
        )
        self._monkeypatch.setattr(
            agent_router,
            "persist_route_receipts",
            self._capture_persisted_route_evidence,
        )
        self._monkeypatch.setitem(
            assets.SYNTHETIC_UNIT_ASSETS,
            "CART",
            ("equity", "Maplebear Inc.", "CART"),
        )
        synthetic_ohlcv = provider._synthetic_ohlcv
        synthetic_fixtures: dict[str, Any] = {}

        def trajectory_market_data(**kwargs: Any):
            symbol = str(kwargs.get("symbol") or "").upper()
            fixture = synthetic_fixtures.get(symbol)
            if fixture is None:
                fixture = synthetic_ohlcv(
                    symbol=symbol,
                    start_date=date(2020, 1, 1),
                    end_date=date(2026, 12, 31),
                    timeframe=str(kwargs["timeframe"]),
                )
                if symbol == "CART":
                    fixture = fixture.loc[fixture.index >= "2021-01-04"]
                synthetic_fixtures[symbol] = fixture
            return fixture.loc[
                (fixture.index >= str(kwargs["start_date"]))
                & (fixture.index <= str(kwargs["end_date"]))
            ].copy()

        self._monkeypatch.setattr(
            provider,
            "_synthetic_ohlcv",
            trajectory_market_data,
        )
        assets.clear_asset_cache()
        self._provider_router.start()
        self._provider_router.post("https://openrouter.ai/api/v1/chat/completions").mock(
            side_effect=self._typed_provider_response
        )
        clear_openrouter_route_receipts()
        self._client = TestClient(app)
        self._client.post("/api/v1/dev/reset")
        return self

    def __exit__(self, *_exc: object) -> None:
        from argus.domain.market_data.assets import clear_asset_cache

        if self._client is not None:
            self._client.close()
        self._provider_router.stop()
        clear_asset_cache()
        self._client = None

    @staticmethod
    def _typed_provider_response(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise AssertionError("trajectory provider received no messages")
        content = messages[-1].get("content")
        if not isinstance(content, str):
            raise AssertionError("trajectory provider received no typed content")
        response_format = payload.get("response_format")
        native_schema = (
            isinstance(response_format, dict)
            and response_format.get("type") == "json_schema"
        )
        first = messages[0]
        schema_content = first.get("content") if first.get("role") == "system" else None
        if (
            isinstance(schema_content, list)
            and len(schema_content) == 1
            and isinstance(schema_content[0], dict)
            and schema_content[0].get("type") == "text"
        ):
            schema_content = schema_content[0].get("text")
        prompt_schema = None
        if isinstance(schema_content, str) and schema_content.startswith(
            _SCHEMA_IN_PROMPT_INSTRUCTION
        ):
            try:
                prompt_schema = json.loads(
                    schema_content[len(_SCHEMA_IN_PROMPT_INSTRUCTION) :]
                )
            except json.JSONDecodeError:
                pass
        if native_schema or prompt_schema == StructuredInterpretation.model_json_schema():
            StructuredInterpretation.model_validate_json(content)
        else:
            content = (
                "I cannot look up current candidates while discovery is disabled. "
                "Name a symbol you already have in mind and I can test it."
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "cost": 0,
                },
            },
        )

    def _capture_persisted_route_evidence(
        self,
        *,
        receipts: list[Any],
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        self._persisted_route_evidence.setdefault(conversation_id, []).append(
            {
                "receipts": tuple(receipt.as_dict() for receipt in receipts),
                "turn_execution": dict((metadata or {}).get("turn_execution") or {}),
            }
        )

    @property
    def _http(self) -> TestClient:
        if self._client is None:
            raise RuntimeError("ConcreteTrajectoryRuntime must be entered")
        return self._client

    def _state(self, trajectory: AlphaTrajectory) -> _TrajectoryState:
        state = self._states.get(trajectory.label)
        if state is not None:
            return state
        self._http.post("/api/v1/dev/reset").raise_for_status()
        clear_openrouter_route_receipts()
        response = self._http.post(
            "/api/v1/conversations",
            json={"language": trajectory.locale},
        )
        response.raise_for_status()
        state = _TrajectoryState(
            conversation_id=str(response.json()["conversation"]["id"])
        )
        self._states[trajectory.label] = state
        return state

    def stream(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        history: tuple[TrajectoryStepResult, ...],
    ) -> StepObservation:
        del history
        state = self._state(trajectory)
        result = self._submit_stream(
            trajectory=trajectory,
            step=step,
            body={
                "conversation_id": state.conversation_id,
                "language": trajectory.locale,
                **step.request,
            },
        )
        artifact_identity, action_identity = self._observe_artifact(
            trajectory=trajectory,
            state=state,
            final=result.final,
        )
        return self._stream_observation(
            result=result,
            state=state,
            artifact_identity=artifact_identity,
            action_identity=action_identity,
            recovery_code=self._recovery_code(result.final),
            checkpoints=self._stream_checkpoints(
                trajectory=trajectory,
                state=state,
                final=result.final,
                artifact_identity=artifact_identity,
            ),
        )

    def reload(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        history: tuple[TrajectoryStepResult, ...],
    ) -> StepObservation:
        del history
        state = self._state(trajectory)
        if trajectory.label == "alpha_session_07" and step.request.get("after"):
            self._age_disconnected_turn_for_reconciliation(state=state)
        response = self._http.get(
            f"/api/v1/conversations/{state.conversation_id}/messages"
        )
        response.raise_for_status()
        items = response.json()["items"]
        if trajectory.label == "alpha_session_07" and step.request.get("after"):
            return self._observe_abandoned_reload(state=state, messages=items)
        artifact_alias = self._latest_projected_artifact_alias(
            state=state,
            messages=items,
        )
        checkpoints = (
            {"admission.execution_count": self._execution_count(state=state)}
            if trajectory.label == "alpha_session_06"
            else {}
        )
        if trajectory.label == "alpha_session_04":
            confirmation_alias = self._confirmation_alias(state=state)
            approval_coverage = self._confirmation_coverage(
                state=state,
                confirmation_alias=confirmation_alias,
            )
            reloaded_coverage = self._projected_confirmation_coverage(
                state=state,
                confirmation_alias=confirmation_alias,
                messages=items,
            )
            job = self._job_for_confirmation(
                state=state,
                confirmation_alias=confirmation_alias,
            )
            checkpoints["effective_window.reload_matches_approval"] = (
                self._provider_adjusted_window(approval_coverage)
                and self._same_coverage(approval_coverage, reloaded_coverage)
                and self._same_coverage(
                    approval_coverage,
                    self._job_coverage(job),
                )
            )
        action_alias = self._persisted_action_alias(
            state=state,
            artifact_alias=artifact_alias,
        )
        return StepObservation(
            artifact_identity=artifact_alias,
            action_identity=action_alias,
            reload_state=artifact_alias,
            checkpoints=checkpoints,
        )

    def action(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        history: tuple[TrajectoryStepResult, ...],
    ) -> StepObservation:
        del history
        return self._run_action(trajectory=trajectory, step=step, is_retry=False)

    def disconnect(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        history: tuple[TrajectoryStepResult, ...],
    ) -> StepObservation:
        del history
        state = self._state(trajectory)
        submission = step.request["submission"]
        if submission["operation"] == "action":
            action = dict(submission["request"]["action"])
            payload = dict(action.get("payload") or {})
            alias = str(payload["confirmation_id"])
            raw_confirmation_id = state.raw_artifact_ids[alias]
            payload["confirmation_id"] = raw_confirmation_id
            action.update(
                label="Run backtest",
                presentation="confirmation",
                payload=payload,
            )
            before_submissions = state.route_submission_count
            with self._monkeypatch.context() as cut:
                complete = ChatTurnLifecycleHooks.complete

                def cut_after_admission(
                    hooks: ChatTurnLifecycleHooks,
                    **kwargs: Any,
                ):
                    if hooks.owner == "message_only":
                        raise _TransportCut("after_action_admission")
                    return complete(hooks, **kwargs)

                cut.setattr(
                    ChatTurnLifecycleHooks,
                    "complete",
                    cut_after_admission,
                )
                try:
                    state.route_submission_count += 1
                    self._http.post(
                        "/api/v1/chat/stream",
                        headers={"Idempotency-Key": raw_confirmation_id},
                        json={
                            "conversation_id": state.conversation_id,
                            "language": trajectory.locale,
                            "action": action,
                        },
                    )
                except BaseException as exc:
                    if not self._contains_transport_cut(exc):
                        raise
                else:
                    raise AssertionError("action transport cut did not fire")
            if state.route_submission_count != before_submissions + 1:
                raise AssertionError("disconnect submitted the action more than once")
            return StepObservation(
                artifact_identity=alias,
                action_identity=alias,
                typed_terminal=False,
                checkpoints={"by_action.reconciliation_required": True},
            )

        before_submissions = state.route_submission_count
        with self._monkeypatch.context() as cut:
            cut.setattr(
                ChatTurnLifecycleHooks,
                "mark_running",
                lambda _hooks: (_ for _ in ()).throw(
                    _TransportCut("after_turn_acceptance")
                ),
            )
            try:
                state.route_submission_count += 1
                self._http.post(
                    "/api/v1/chat/stream",
                    json={
                        "conversation_id": state.conversation_id,
                        "language": trajectory.locale,
                        **submission["request"],
                    },
                )
            except BaseException as exc:
                if not self._contains_transport_cut(exc):
                    raise
            else:
                raise AssertionError("ordinary-turn transport cut did not fire")
        if state.route_submission_count != before_submissions + 1:
            raise AssertionError("disconnect submitted the turn more than once")
        rows = [
            row
            for row in api_state.store.chat_turn_lifecycles.values()
            if row.get("conversation_id") == state.conversation_id
        ]
        if len(rows) != 2:
            raise AssertionError("disconnect did not create one adjacent lifecycle")
        accepted = max(rows, key=lambda row: str(row["accepted_at"]))
        if accepted.get("status") != "accepted":
            raise AssertionError("disconnect advanced beyond accepted")
        state.disconnected_turn_id = str(accepted["turn_id"])
        state.disconnected_request_id = f"{trajectory.label}:request:1"
        state.disconnected_raw_request_id = str(accepted["request_id"])
        alias = f"{trajectory.label}:turn:1"
        state.artifact_aliases[state.disconnected_turn_id] = alias
        state.raw_artifact_ids[alias] = state.disconnected_turn_id
        return StepObservation(
            artifact_identity=alias,
            persistence_state="accepted",
            typed_terminal=False,
            checkpoints={
                "agent_runtime_turn.turn_id": alias,
                "agent_runtime_turn.request_id": state.disconnected_request_id,
                "agent_runtime_turn.status": "accepted",
                "orphan_turn.client_terminal_invented": False,
            },
        )

    def retry(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        history: tuple[TrajectoryStepResult, ...],
    ) -> StepObservation:
        del history
        if trajectory.label in {"alpha_session_05", "alpha_session_06"}:
            return self._run_action(trajectory=trajectory, step=step, is_retry=True)
        if trajectory.label == "alpha_session_07":
            return self._retry_abandoned_turn(trajectory=trajectory, step=step)
        return self._retry_draft(trajectory=trajectory, step=step)

    def persistence(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        history: tuple[TrajectoryStepResult, ...],
    ) -> StepObservation:
        del step, history
        state = self._state(trajectory)
        artifact_alias, action_alias = self._persisted_artifact_identity(state=state)
        if trajectory.label == "alpha_session_01":
            return StepObservation(
                persistence_state=artifact_alias,
                checkpoints={
                    "stale_action.persisted_execution_count": (
                        self._execution_count_for_action(
                            state=state,
                            action_alias=f"{trajectory.label}:confirmation:1",
                        )
                    )
                },
            )
        if trajectory.label == "alpha_session_02":
            return StepObservation(
                artifact_identity=artifact_alias,
                checkpoints={
                    "terminal.repeated_fingerprint_count": (
                        self._repeated_terminal_fingerprint_count(state=state)
                    )
                },
            )
        if trajectory.label == "alpha_session_03":
            return StepObservation(
                artifact_identity=artifact_alias,
                action_identity=action_alias,
            )
        if trajectory.label == "alpha_session_04":
            confirmation_alias = self._confirmation_alias(state=state)
            coverage = self._confirmation_coverage(
                state=state,
                confirmation_alias=confirmation_alias,
            )
            job = self._job_for_confirmation(
                state=state,
                confirmation_alias=confirmation_alias,
            )
            durable = self._provider_adjusted_window(coverage) and self._same_coverage(
                coverage,
                self._job_coverage(job),
            )
            completed_result_durable = self._completed_result_matches_approval(
                state=state,
                confirmation_alias=confirmation_alias,
            )
            return StepObservation(
                persistence_state=(
                    "requested_and_effective_window"
                    if durable and completed_result_durable
                    else None
                ),
                checkpoints={
                    "effective_window.durable": durable,
                    "effective_window.completed_result_durable": (
                        completed_result_durable
                    ),
                },
            )
        if trajectory.label in {"alpha_session_05", "alpha_session_06"}:
            execution_count = self._execution_count(state=state)
            checkpoints = (
                {"admission.execution_count": execution_count}
                if trajectory.label == "alpha_session_05"
                else {"persistence.durable_identity_count": execution_count}
            )
            return StepObservation(
                artifact_identity=artifact_alias,
                action_identity=action_alias,
                checkpoints=checkpoints,
            )
        lifecycle = self._disconnected_lifecycle(state=state)
        alias = f"{trajectory.label}:turn:1"
        return StepObservation(
            artifact_identity=alias,
            persistence_state=str(lifecycle["status"]),
            checkpoints={
                "agent_runtime_turn.turn_id": alias,
                "agent_runtime_turn.request_id": state.disconnected_request_id,
                "agent_runtime_turn.status": lifecycle["status"],
                "persistence.durable_identity_count": (
                    self._matching_lifecycle_identity_count(state=state)
                ),
            },
        )

    def _submit_stream(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> _StreamResult:
        state = self._state(trajectory)
        evidence = self._persisted_route_evidence.setdefault(
            state.conversation_id,
            [],
        )
        evidence_start = len(evidence)
        state.route_submission_count += 1
        response = self._http.post(
            "/api/v1/chat/stream",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        if len(evidence) != evidence_start + 1:
            raise AssertionError("chat route did not persist one execution summary")
        persisted_evidence = evidence[-1]
        events = tuple(parse_sse_events(response.text))
        final = next(
            (
                event["payload"]
                for event in reversed(events)
                if event.get("type") == "final" and isinstance(event.get("payload"), dict)
            ),
            {},
        )
        return _StreamResult(
            raw_sse=response.text,
            events=events,
            final=final,
            receipts=tuple(persisted_evidence["receipts"]),
            execution_summary=dict(persisted_evidence["turn_execution"]),
        )

    def _stream_observation(
        self,
        *,
        result: _StreamResult,
        state: _TrajectoryState,
        artifact_identity: str | None = None,
        action_identity: str | None = None,
        recovery_code: str | None = None,
        checkpoints: dict[str, Any] | None = None,
        stale_action_executions: int = 0,
    ) -> StepObservation:
        return StepObservation(
            raw_sse=result.raw_sse,
            visible_response_category=self._visible_category(result.final),
            stage_outcome=self._observed_stage_outcome(result.final),
            artifact_identity=artifact_identity,
            action_identity=action_identity,
            recovery_code=recovery_code,
            route_receipts=result.receipts,
            typed_terminal=result.typed_terminal,
            fingerprint=self._persisted_fingerprint(result.execution_summary),
            checkpoints=checkpoints or {},
            stale_action_executions=stale_action_executions,
        )

    @staticmethod
    def _recovery_code(final: dict[str, Any]) -> str | None:
        recovery = final.get("recovery")
        if not isinstance(recovery, dict) or not recovery.get("code"):
            return None
        return str(recovery["code"])

    def _run_action(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
        is_retry: bool,
    ) -> StepObservation:
        state = self._state(trajectory)
        action = dict(step.request["action"])
        payload = dict(action.get("payload") or {})
        alias = str(payload["confirmation_id"])
        raw_confirmation_id = state.raw_artifact_ids[alias]
        payload["confirmation_id"] = raw_confirmation_id
        action.update(
            label="Run backtest",
            presentation="confirmation",
            payload=payload,
        )
        result = self._submit_stream(
            trajectory=trajectory,
            step=step,
            headers={"Idempotency-Key": raw_confirmation_id},
            body={
                "conversation_id": state.conversation_id,
                "language": trajectory.locale,
                "action": action,
            },
        )
        raw_job = result.final.get("backtest_job")
        if isinstance(raw_job, dict) and isinstance(raw_job.get("id"), str):
            raw_job_id = str(raw_job["id"])
            job_alias = f"{trajectory.label}:job:1"
            state.artifact_aliases[raw_job_id] = job_alias
            state.raw_artifact_ids[job_alias] = raw_job_id
        if is_retry:
            state.replay_count += 1
        recovery_code = self._recovery_code(result.final)
        artifact_identity, _ = self._persisted_artifact_identity(state=state)
        if recovery_code is not None:
            artifact_identity = None
        checkpoints: dict[str, Any] = {}
        if trajectory.label == "alpha_session_01":
            checkpoints["stale_action.execution_count"] = self._execution_count(
                state=state
            )
        elif trajectory.label == "alpha_session_04":
            approval_coverage = self._confirmation_coverage(
                state=state,
                confirmation_alias=alias,
            )
            job = self._job_for_confirmation(
                state=state,
                confirmation_alias=alias,
            )
            completion = self._complete_effective_window_job(job=job)
            job = self._job_for_confirmation(
                state=state,
                confirmation_alias=alias,
            )
            checkpoints["effective_window.execution_matches_approval"] = (
                self._provider_adjusted_window(approval_coverage)
                and self._same_coverage(
                    approval_coverage,
                    self._job_coverage(job),
                )
            )
            checkpoints["effective_window.completed_result_matches_approval"] = (
                completion.get("status") == "succeeded"
                and self._completed_result_matches_approval(
                    state=state,
                    confirmation_alias=alias,
                )
            )
            checkpoints["effective_window.result_surfaces_complete"] = (
                self._completed_result_surfaces_are_canonical(
                    state=state,
                    confirmation_alias=alias,
                )
            )
        elif trajectory.label == "alpha_session_05":
            if is_retry:
                checkpoints.update(
                    {
                        "by_action.replay_count": state.replay_count,
                        "admission.execution_count": self._execution_count(state=state),
                    }
                )
        elif trajectory.label == "alpha_session_06":
            checkpoints["admission.allowance_count"] = self._allowance_count()
            if is_retry:
                checkpoints["admission.execution_count"] = self._execution_count(
                    state=state
                )
        return self._stream_observation(
            result=result,
            state=state,
            artifact_identity=artifact_identity,
            action_identity=alias,
            recovery_code=recovery_code,
            checkpoints=checkpoints,
            stale_action_executions=self._execution_count(state=state)
            if recovery_code == "confirmation_action_stale_card"
            else 0,
        )

    def _retry_draft(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
    ) -> StepObservation:
        state = self._state(trajectory)
        result = self._submit_stream(
            trajectory=trajectory,
            step=step,
            body={
                "conversation_id": state.conversation_id,
                "language": trajectory.locale,
                "message": "Reintentar",
            },
        )
        artifact_identity, _ = self._observe_artifact(
            trajectory=trajectory,
            state=state,
            final=result.final,
        )
        return self._stream_observation(
            result=result,
            state=state,
            artifact_identity=artifact_identity,
            checkpoints={"terminal.retry_target": artifact_identity},
        )

    def _retry_abandoned_turn(
        self,
        *,
        trajectory: AlphaTrajectory,
        step: TrajectoryStep,
    ) -> StepObservation:
        state = self._state(trajectory)
        action = step.request.get("action")
        payload = action.get("payload") if isinstance(action, dict) else None
        requested_alias = (
            payload.get("request_message_id") if isinstance(payload, dict) else None
        )
        expected_alias = f"{trajectory.label}:turn:1"
        if (
            not isinstance(action, dict)
            or action.get("type") != "retry_last_turn"
            or requested_alias != expected_alias
        ):
            raise AssertionError("projected retry authority does not match fixture")
        raw_turn_id = state.raw_artifact_ids[expected_alias]
        request_message = next(
            (
                message
                for message in api_state.store.messages[state.conversation_id]
                if message.id == raw_turn_id and message.role == "user"
            ),
            None,
        )
        if request_message is None:
            raise AssertionError("abandoned turn has no persisted request message")
        projected = self._projected_retry_authority(
            state=state,
            raw_turn_id=raw_turn_id,
        )
        projected_message = projected.get("message")
        if (
            projected.get("request_message_id") != raw_turn_id
            or not isinstance(projected_message, str)
            or projected_message != request_message.content
        ):
            raise AssertionError("projected retry authority is not canonical")
        before_retry_count = self._matching_retry_attempt_count(state=state)
        result = self._submit_stream(
            trajectory=trajectory,
            step=step,
            body={
                "conversation_id": state.conversation_id,
                "language": trajectory.locale,
                "message": projected_message,
            },
        )
        streamed_artifact_identity, _ = self._observe_artifact(
            trajectory=trajectory,
            state=state,
            final=result.final,
        )
        artifact_identity, action_identity = self._persisted_artifact_identity(
            state=state
        )
        if artifact_identity is None or streamed_artifact_identity != artifact_identity:
            raise AssertionError("retry terminal artifact is not durably persisted")
        retry_count = self._matching_retry_attempt_count(state=state)
        if retry_count <= before_retry_count:
            raise AssertionError("retry did not create a lifecycle attempt")
        return self._stream_observation(
            result=result,
            state=state,
            artifact_identity=artifact_identity,
            action_identity=action_identity,
            checkpoints={
                "retry_last_turn.request_message_id": expected_alias,
                "orphan_turn.duplicate_turn_count": max(0, retry_count - 1),
                "terminal.artifact_identity": artifact_identity,
            },
        )

    def _age_disconnected_turn_for_reconciliation(
        self,
        *,
        state: _TrajectoryState,
    ) -> None:
        from argus.domain import chat_turn_lifecycle

        if state.disconnected_turn_id is None:
            raise AssertionError("disconnect did not accept a turn")
        future = utcnow() + timedelta(minutes=16)
        self._monkeypatch.setattr(chat_turn_lifecycle, "utcnow", lambda: future)

    def _observe_abandoned_reload(
        self,
        *,
        state: _TrajectoryState,
        messages: list[dict[str, Any]],
    ) -> StepObservation:
        alias = next(
            alias for alias in state.raw_artifact_ids if alias.endswith(":turn:1")
        )
        raw_turn_id = state.raw_artifact_ids[alias]
        projected = next(
            message
            for message in messages
            if isinstance(message.get("metadata"), dict)
            and message["metadata"].get("recovery", {}).get("code") == "turn_abandoned"
        )
        metadata = projected["metadata"]
        runtime_turn = metadata["agent_runtime_turn"]
        retry = metadata["retry_last_turn"]
        lifecycle = self._disconnected_lifecycle(state=state)
        accepted_orphans = sum(
            row["status"] in {"accepted", "running"}
            for row in api_state.store.chat_turn_lifecycles.values()
            if row["conversation_id"] == state.conversation_id
        )
        return StepObservation(
            artifact_identity=alias,
            reload_state=str(lifecycle["status"]),
            recovery_code=str(metadata["recovery"]["code"]),
            typed_terminal=bool(runtime_turn["terminal"]),
            fingerprint=raw_turn_id,
            checkpoints={
                "agent_runtime_turn.turn_id": alias,
                "agent_runtime_turn.request_id": (
                    state.disconnected_request_id
                    if runtime_turn["request_id"] == state.disconnected_raw_request_id
                    else runtime_turn["request_id"]
                ),
                "agent_runtime_turn.status": runtime_turn["status"],
                "agent_runtime_turn.terminal": runtime_turn["terminal"],
                "agent_runtime_turn.reconciled_outcome": runtime_turn.get(
                    "reconciled_outcome"
                ),
                "agent_runtime_turn.failure_code": runtime_turn["failure_code"],
                "agent_runtime_turn.retryable": runtime_turn["retryable"],
                "recovery.code": metadata["recovery"]["code"],
                "recovery.retryable": metadata["recovery"]["retryable"],
                "retry_last_turn.request_message_id": (
                    alias
                    if retry["request_message_id"] == raw_turn_id
                    else retry["request_message_id"]
                ),
                "retry_last_turn.message": retry["message"],
                "orphan_turn.after_window_count": accepted_orphans,
            },
            accepted_orphan_turns_after_window=accepted_orphans,
        )

    @staticmethod
    def _disconnected_lifecycle(*, state: _TrajectoryState) -> dict[str, Any]:
        if state.disconnected_turn_id is None:
            raise AssertionError("trajectory has no disconnected turn")
        return api_state.store.chat_turn_lifecycles[state.disconnected_turn_id]

    @staticmethod
    def _execution_count(*, state: _TrajectoryState) -> int:
        return sum(
            job.get("conversation_id") == state.conversation_id
            for job in api_state.store.backtest_jobs.values()
        )

    @staticmethod
    def _execution_count_for_action(
        *,
        state: _TrajectoryState,
        action_alias: str,
    ) -> int:
        raw_action_id = state.raw_artifact_ids.get(action_alias)
        if not isinstance(raw_action_id, str) or not raw_action_id:
            raise AssertionError("trajectory action identity is not persisted")
        return sum(
            job.get("conversation_id") == state.conversation_id
            and job.get("idempotency_key") == raw_action_id
            for job in api_state.store.backtest_jobs.values()
        )

    def _repeated_terminal_fingerprint_count(
        self,
        *,
        state: _TrajectoryState,
    ) -> int:
        evidence = self._persisted_route_evidence.get(state.conversation_id)
        if not evidence:
            raise AssertionError("trajectory has no persisted execution summaries")
        fingerprints: list[str] = []
        for item in evidence:
            summary = item.get("turn_execution")
            if not isinstance(summary, dict) or summary.get("terminal") is None:
                raise AssertionError("persisted terminal execution summary is missing")
            fingerprints.append(self._persisted_fingerprint(summary))
        return len(fingerprints) - len(set(fingerprints))

    @staticmethod
    def _matching_lifecycle_rows(
        *,
        state: _TrajectoryState,
    ) -> list[dict[str, Any]]:
        if state.disconnected_turn_id is None:
            raise AssertionError("trajectory has no disconnected turn")
        request_message = next(
            (
                message
                for message in api_state.store.messages.get(
                    state.conversation_id,
                    [],
                )
                if message.id == state.disconnected_turn_id and message.role == "user"
            ),
            None,
        )
        if request_message is None:
            raise AssertionError("disconnected request message is not persisted")
        messages_by_id = {
            message.id: message
            for message in api_state.store.messages.get(state.conversation_id, [])
        }
        rows: list[dict[str, Any]] = []
        for row in api_state.store.chat_turn_lifecycles.values():
            if row.get("conversation_id") != state.conversation_id:
                continue
            turn_id = row.get("turn_id")
            message = messages_by_id.get(turn_id)
            if (
                message is not None
                and message.role == "user"
                and message.content == request_message.content
            ):
                rows.append(row)
        return rows

    @classmethod
    def _matching_lifecycle_identity_count(
        cls,
        *,
        state: _TrajectoryState,
    ) -> int:
        return len(cls._matching_lifecycle_rows(state=state))

    @classmethod
    def _matching_retry_attempt_count(
        cls,
        *,
        state: _TrajectoryState,
    ) -> int:
        rows = cls._matching_lifecycle_rows(state=state)
        if not any(row.get("turn_id") == state.disconnected_turn_id for row in rows):
            raise AssertionError("disconnected lifecycle identity is missing")
        return sum(row.get("turn_id") != state.disconnected_turn_id for row in rows)

    def _projected_retry_authority(
        self,
        *,
        state: _TrajectoryState,
        raw_turn_id: str,
    ) -> dict[str, Any]:
        response = self._http.get(
            f"/api/v1/conversations/{state.conversation_id}/messages"
        )
        response.raise_for_status()
        projected = next(
            (
                message
                for message in response.json()["items"]
                if message.get("id") == raw_turn_id
                and isinstance(message.get("metadata"), dict)
            ),
            None,
        )
        retry = (
            projected["metadata"].get("retry_last_turn")
            if projected is not None
            else None
        )
        if not isinstance(retry, dict):
            raise AssertionError("projected retry authority is missing")
        return retry

    @staticmethod
    def _allowance_count() -> int:
        counts = [
            int(row.get("used_count", 0))
            for row in api_state.store.usage_counters.values()
        ]
        return max(counts, default=0)

    def _observe_artifact(
        self,
        *,
        trajectory: AlphaTrajectory,
        state: _TrajectoryState,
        final: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        confirmation = final.get("confirmation")
        if isinstance(confirmation, dict) and isinstance(
            confirmation.get("confirmation_id"), str
        ):
            raw_id = str(confirmation["confirmation_id"])
            existing = state.artifact_aliases.get(raw_id)
            if existing is None:
                count = sum(
                    alias.startswith(f"{trajectory.label}:confirmation:")
                    for alias in state.artifact_aliases.values()
                )
                existing = f"{trajectory.label}:confirmation:{count + 1}"
            state.artifact_aliases[raw_id] = existing
            state.raw_artifact_ids[existing] = raw_id
            return existing, existing
        pending = final.get("pending_strategy")
        if isinstance(pending, dict):
            alias = f"{trajectory.label}:draft:1"
            raw_id = final.get("message_id")
            if not isinstance(raw_id, str) or not raw_id:
                raise AssertionError("pending strategy has no persisted message identity")
            state.artifact_aliases[raw_id] = alias
            state.raw_artifact_ids[alias] = raw_id
            return alias, None
        return None, None

    @staticmethod
    def _visible_category(final: dict[str, Any]) -> str | None:
        if isinstance(final.get("recovery"), dict):
            return "typed_recovery"
        if isinstance(final.get("confirmation"), dict):
            confirmation = final["confirmation"]
            adjustment = confirmation.get("period_adjustment")
            if isinstance(adjustment, dict):
                requested = adjustment.get("requested_date_range")
                effective = adjustment.get("effective_date_range")
                if (
                    isinstance(requested, dict)
                    and isinstance(effective, dict)
                    and requested.get("start") != effective.get("start")
                ):
                    return "confirmation_with_correction"
            return "confirmation"
        if isinstance(final.get("backtest_job"), dict):
            return "job_accepted"
        if isinstance(final.get("pending_strategy"), dict):
            return "clarification"
        return None

    @staticmethod
    def _observed_stage_outcome(final: dict[str, Any]) -> str | None:
        outcome = final.get("stage_outcome")
        if outcome == "await_approval":
            return "ready_for_confirmation"
        if outcome == "await_user_reply":
            return "needs_clarification"
        return str(outcome) if outcome else None

    def _stream_checkpoints(
        self,
        *,
        trajectory: AlphaTrajectory,
        state: _TrajectoryState,
        final: dict[str, Any],
        artifact_identity: str | None,
    ) -> dict[str, Any]:
        if trajectory.label == "alpha_session_04":
            confirmation = final.get("confirmation")
            coverage = self._confirmation_coverage(
                state=state,
                confirmation_alias=artifact_identity,
            )
            requested = self._coverage_range(coverage, "requested_date_range")
            return {
                "effective_window.requested_start": (
                    requested.get("start") if requested is not None else None
                ),
                "effective_window.source": (
                    "provider_supported_common_window"
                    if self._provider_adjusted_window(coverage)
                    else None
                ),
                "effective_window.visible_before_approval": (
                    self._provider_adjusted_window(coverage)
                    and self._visible_period_adjustment_matches_coverage(
                        confirmation=confirmation,
                        coverage=coverage,
                    )
                ),
            }
        if trajectory.label == "alpha_session_01" and artifact_identity:
            return {"stale_action.active_artifact": artifact_identity}
        if trajectory.label == "alpha_session_02":
            return {"terminal.response_language": trajectory.locale}
        if trajectory.label == "alpha_session_03":
            latest_evidence = self._persisted_route_evidence.get(
                state.conversation_id, []
            )
            receipt_count = (
                len(latest_evidence[-1]["receipts"]) if latest_evidence else None
            )
            confirmation_metadata = self._confirmation_metadata(
                state=state,
                confirmation_alias=artifact_identity,
            )
            confirmation_payload = (
                confirmation_metadata.get("confirmation_payload")
                if isinstance(confirmation_metadata, dict)
                else None
            )
            strategy = (
                confirmation_payload.get("strategy")
                if isinstance(confirmation_payload, dict)
                else None
            )
            return {
                "discovery.route_receipt_count": receipt_count,
                "discovery.known_symbol_confirmation": bool(
                    isinstance(strategy, dict)
                    and strategy.get("strategy_type") == "indicator_threshold"
                    and strategy.get("asset_universe") == ["AAPL"]
                    and strategy.get("extra_parameters", {}).get("indicator") == "rsi"
                ),
            }
        return {}

    @staticmethod
    def _confirmation_alias(*, state: _TrajectoryState) -> str | None:
        return next(
            (alias for alias in state.raw_artifact_ids if ":confirmation:" in alias),
            None,
        )

    @staticmethod
    def _confirmation_metadata(
        *,
        state: _TrajectoryState,
        confirmation_alias: str | None,
    ) -> dict[str, Any] | None:
        raw_confirmation_id = state.raw_artifact_ids.get(confirmation_alias or "")
        if not isinstance(raw_confirmation_id, str):
            return None
        message = next(
            (
                message
                for message in api_state.store.messages.get(state.conversation_id, [])
                if message.role == "assistant"
                and message.metadata.get("confirmation_card", {}).get("confirmation_id")
                == raw_confirmation_id
            ),
            None,
        )
        return message.metadata if message is not None else None

    @classmethod
    def _confirmation_coverage(
        cls,
        *,
        state: _TrajectoryState,
        confirmation_alias: str | None,
    ) -> dict[str, Any] | None:
        return cls._coverage_from_metadata(
            cls._confirmation_metadata(
                state=state,
                confirmation_alias=confirmation_alias,
            )
        )

    @staticmethod
    def _coverage_from_metadata(
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(metadata, dict):
            return None
        payload = metadata.get("confirmation_payload")
        if not isinstance(payload, dict):
            return None
        launch_payload = payload.get("launch_payload")
        if not isinstance(launch_payload, dict):
            return None
        coverage = launch_payload.get("coverage_preflight")
        return coverage if isinstance(coverage, dict) else None

    @staticmethod
    def _coverage_range(
        coverage: dict[str, Any] | None,
        key: str,
    ) -> dict[str, Any] | None:
        if not isinstance(coverage, dict):
            return None
        date_range = coverage.get(key)
        if not isinstance(date_range, dict):
            return None
        start = date_range.get("start")
        end = date_range.get("end")
        if not (isinstance(start, str) and isinstance(end, str)):
            return None
        return date_range

    @classmethod
    def _provider_adjusted_window(cls, coverage: dict[str, Any] | None) -> bool:
        requested = cls._coverage_range(coverage, "requested_date_range")
        effective = cls._coverage_range(coverage, "effective_date_range")
        return bool(
            requested is not None
            and effective is not None
            and requested != effective
            and coverage is not None
            and coverage.get("outcome") == "adjusted_coverage"
            and coverage.get("adjustment_reason") == "provider_coverage_adjustment"
        )

    @classmethod
    def _same_coverage(
        cls,
        left: dict[str, Any] | None,
        right: dict[str, Any] | None,
    ) -> bool:
        if not (
            cls._provider_adjusted_window(left)
            and cls._provider_adjusted_window(right)
            and left is not None
            and right is not None
            and isinstance(left.get("preflight_id"), str)
            and left["preflight_id"]
            and isinstance(right.get("preflight_id"), str)
            and right["preflight_id"]
        ):
            return False
        return all(
            left.get(key) == right.get(key)
            for key in (
                "requested_date_range",
                "effective_date_range",
                "outcome",
                "adjustment_reason",
                "preflight_id",
            )
        )

    @classmethod
    def _visible_period_adjustment_matches_coverage(
        cls,
        *,
        confirmation: object,
        coverage: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(confirmation, dict):
            return False
        adjustment = confirmation.get("period_adjustment")
        if not isinstance(adjustment, dict):
            return False
        return cls._coverage_range(coverage, "requested_date_range") == adjustment.get(
            "requested_date_range"
        ) and cls._coverage_range(coverage, "effective_date_range") == adjustment.get(
            "effective_date_range"
        )

    @staticmethod
    def _job_for_confirmation(
        *,
        state: _TrajectoryState,
        confirmation_alias: str | None,
    ) -> dict[str, Any] | None:
        raw_confirmation_id = state.raw_artifact_ids.get(confirmation_alias or "")
        if not isinstance(raw_confirmation_id, str):
            return None
        return next(
            (
                job
                for job in api_state.store.backtest_jobs.values()
                if job.get("conversation_id") == state.conversation_id
                and job.get("idempotency_key") == raw_confirmation_id
            ),
            None,
        )

    @staticmethod
    def _job_coverage(job: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(job, dict):
            return None
        launch_payload = job.get("launch_payload")
        if not isinstance(launch_payload, dict):
            return None
        request = launch_payload.get("request")
        if not isinstance(request, dict):
            return None
        coverage = request.get("coverage_preflight")
        return coverage if isinstance(coverage, dict) else None

    def _complete_effective_window_job(
        self,
        *,
        job: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw_job_id = job.get("id") if isinstance(job, dict) else None
        if not isinstance(raw_job_id, str) or not raw_job_id:
            return {}
        from workflows.backtest_job import run_backtest_job

        with self._monkeypatch.context() as completion_env:
            completion_env.setenv("OPENROUTER_API_KEY", "")
            result = run_backtest_job(
                self._backtest_gateway,
                job_id=raw_job_id,
                backtest_tool=RealBacktestTool(),
            )
        return result

    @classmethod
    def _completed_result_matches_approval(
        cls,
        *,
        state: _TrajectoryState,
        confirmation_alias: str | None,
    ) -> bool:
        approval_coverage = cls._confirmation_coverage(
            state=state,
            confirmation_alias=confirmation_alias,
        )
        job = cls._job_for_confirmation(
            state=state,
            confirmation_alias=confirmation_alias,
        )
        run = cls._run_for_job(job)
        return bool(
            isinstance(job, dict)
            and job.get("status") == "succeeded"
            and isinstance(job.get("result_run_id"), str)
            and cls._run_value(run, "id") == job.get("result_run_id")
            and cls._same_executed_coverage(
                approval_coverage,
                cls._run_coverage(run),
            )
        )

    @classmethod
    def _completed_result_surfaces_are_canonical(
        cls,
        *,
        state: _TrajectoryState,
        confirmation_alias: str | None,
    ) -> bool:
        job = cls._job_for_confirmation(
            state=state,
            confirmation_alias=confirmation_alias,
        )
        run = cls._run_for_job(job)
        run_id = cls._run_value(run, "id")
        evidence = [
            artifact
            for artifact in api_state.store.evidence_artifacts.values()
            if artifact.source_run_id == run_id
        ]
        return bool(
            cls._completed_result_matches_approval(
                state=state,
                confirmation_alias=confirmation_alias,
            )
            and cls._has_result_surfaces(run)
            and cls._has_deterministic_result_readout(job)
            and isinstance(run_id, str)
            and len(evidence) == 1
            and cls._evidence_matches_run(evidence[0], run=run)
        )

    @staticmethod
    def _run_for_job(job: dict[str, Any] | None) -> object | None:
        raw_run_id = job.get("result_run_id") if isinstance(job, dict) else None
        return (
            api_state.store.backtest_runs.get(raw_run_id)
            if isinstance(raw_run_id, str)
            else None
        )

    @staticmethod
    def _run_value(run: object | None, field: str) -> Any:
        if isinstance(run, dict):
            return run.get(field)
        return getattr(run, field, None)

    @classmethod
    def _run_coverage(cls, run: object | None) -> dict[str, Any] | None:
        config = cls._run_value(run, "config_snapshot")
        coverage = config.get("data_coverage") if isinstance(config, dict) else None
        return coverage if isinstance(coverage, dict) else None

    @classmethod
    def _same_executed_coverage(
        cls,
        approval: dict[str, Any] | None,
        executed: dict[str, Any] | None,
    ) -> bool:
        preflight_id = (
            approval.get("preflight_id") if isinstance(approval, dict) else None
        )
        dataset_id = executed.get("dataset_id") if isinstance(executed, dict) else None
        return bool(
            isinstance(preflight_id, str)
            and preflight_id
            and isinstance(dataset_id, str)
            and dataset_id
            and cls._provider_adjusted_window(approval)
            and cls._provider_adjusted_window(executed)
            and preflight_id == dataset_id
            and all(
                approval.get(key) == executed.get(key)
                for key in (
                    "requested_date_range",
                    "effective_date_range",
                    "outcome",
                    "adjustment_reason",
                )
            )
        )

    @classmethod
    def _has_result_surfaces(cls, run: object | None) -> bool:
        metrics = cls._run_value(run, "metrics")
        chart = cls._run_value(run, "chart")
        card = cls._run_value(run, "conversation_result_card")
        return bool(
            cls._run_value(run, "status") == "completed"
            and isinstance(metrics, dict)
            and isinstance(metrics.get("aggregate"), dict)
            and isinstance(chart, dict)
            and isinstance(chart.get("series"), list)
            and chart["series"]
            and isinstance(card, dict)
            and isinstance(card.get("title"), str)
            and card["title"].strip()
            and isinstance(card.get("status_label"), str)
            and card["status_label"].strip()
            and isinstance(card.get("rows"), list)
            and card["rows"]
        )

    @staticmethod
    def _has_deterministic_result_readout(job: dict[str, Any] | None) -> bool:
        metadata = job.get("execution_metadata") if isinstance(job, dict) else None
        workflow = (
            metadata.get("workflow_backtest") if isinstance(metadata, dict) else None
        )
        result_readout = (
            workflow.get("result_readout") if isinstance(workflow, dict) else None
        )
        return bool(
            isinstance(result_readout, str)
            and result_readout.strip()
            and workflow.get("result_readout_source") == "deterministic_fallback"
            and workflow.get("result_readout_fallback_used") is True
        )

    @classmethod
    def _evidence_matches_run(cls, evidence: object, *, run: object | None) -> bool:
        payload = getattr(evidence, "payload", None)
        card = cls._run_value(run, "conversation_result_card")
        chart = cls._run_value(run, "chart")
        run_id = cls._run_value(run, "id")
        if not (
            getattr(evidence, "source_run_id", None) == run_id
            and isinstance(payload, dict)
            and isinstance(card, dict)
            and isinstance(chart, dict)
            and isinstance(payload.get("result_card"), dict)
            and isinstance(payload.get("chart_summary"), dict)
        ):
            return False
        return (
            payload.get("metrics") == cls._run_value(run, "metrics")
            and payload["result_card"].get("title") == card.get("title")
            and payload["chart_summary"].get("points") == len(chart.get("series") or [])
        )

    @classmethod
    def _projected_confirmation_coverage(
        cls,
        *,
        state: _TrajectoryState,
        confirmation_alias: str | None,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        raw_confirmation_id = state.raw_artifact_ids.get(confirmation_alias or "")
        if not isinstance(raw_confirmation_id, str):
            return None
        metadata = next(
            (
                message.get("metadata")
                for message in messages
                if isinstance(message.get("metadata"), dict)
                and message["metadata"]
                .get("confirmation_card", {})
                .get("confirmation_id")
                == raw_confirmation_id
            ),
            None,
        )
        return cls._coverage_from_metadata(metadata)

    @staticmethod
    def _persisted_fingerprint(execution_summary: dict[str, Any]) -> str:
        value = execution_summary.get("output_fingerprint") or execution_summary.get(
            "input_fingerprint"
        )
        if not (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        ):
            raise AssertionError("persisted route execution fingerprint is missing")
        return value

    @classmethod
    def _contains_transport_cut(cls, exc: BaseException) -> bool:
        if isinstance(exc, _TransportCut):
            return True
        nested = getattr(exc, "exceptions", ())
        return isinstance(nested, tuple) and any(
            cls._contains_transport_cut(item)
            for item in nested
            if isinstance(item, BaseException)
        )

    @staticmethod
    def _latest_projected_artifact_alias(
        *,
        state: _TrajectoryState,
        messages: list[dict[str, Any]],
    ) -> str | None:
        for message in reversed(messages):
            metadata = message.get("metadata")
            if not isinstance(metadata, dict):
                continue
            confirmation = metadata.get("confirmation_card")
            if isinstance(confirmation, dict):
                raw_id = confirmation.get("confirmation_id")
                if isinstance(raw_id, str) and raw_id in state.artifact_aliases:
                    return state.artifact_aliases[raw_id]
            if isinstance(metadata.get("pending_strategy"), dict):
                raw_id = message.get("id")
                if isinstance(raw_id, str):
                    return state.artifact_aliases.get(raw_id)
            job = metadata.get("backtest_job")
            if isinstance(job, dict):
                raw_id = job.get("id")
                if isinstance(raw_id, str):
                    return state.artifact_aliases.get(raw_id)
        return None

    def _persisted_artifact_identity(
        self,
        *,
        state: _TrajectoryState,
    ) -> tuple[str | None, str | None]:
        response = self._http.get(
            f"/api/v1/conversations/{state.conversation_id}/messages"
        )
        response.raise_for_status()
        artifact_alias = self._latest_projected_artifact_alias(
            state=state,
            messages=response.json()["items"],
        )
        durable_job_alias = self._latest_durable_job_alias(state=state)
        if durable_job_alias is not None:
            artifact_alias = durable_job_alias
        return (
            artifact_alias,
            self._persisted_action_alias(
                state=state,
                artifact_alias=artifact_alias,
            ),
        )

    @staticmethod
    def _latest_durable_job_alias(*, state: _TrajectoryState) -> str | None:
        user_id = api_state.store.get_or_create_dev_user().id
        candidates = sorted(
            (
                job
                for job in api_state.store.backtest_jobs.values()
                if job.get("conversation_id") == state.conversation_id
            ),
            key=lambda job: str(job.get("created_at") or ""),
            reverse=True,
        )
        for job in candidates:
            raw_job_id = job.get("id")
            action_id = job.get("idempotency_key")
            confirmation_message_id = job.get("confirmation_message_id")
            if not all(
                isinstance(value, str) and value
                for value in (raw_job_id, action_id, confirmation_message_id)
            ):
                continue
            reservation = (
                user_id,
                backtest_admission.CHAT_RUN_SCOPE,
                action_id,
            )
            if api_state.store.backtest_job_reservations.get(reservation) != raw_job_id:
                continue
            confirmation = next(
                (
                    message
                    for message in api_state.store.messages[state.conversation_id]
                    if message.id == confirmation_message_id
                    and message.role == "assistant"
                    and message.metadata.get("confirmation_card", {}).get(
                        "confirmation_id"
                    )
                    == action_id
                ),
                None,
            )
            if confirmation is None:
                continue
            alias = state.artifact_aliases.get(raw_job_id)
            if alias is not None:
                return alias
        return None

    @staticmethod
    def _persisted_action_alias(
        *,
        state: _TrajectoryState,
        artifact_alias: str | None,
    ) -> str | None:
        if artifact_alias is None:
            return None
        if ":confirmation:" in artifact_alias:
            return artifact_alias
        raw_job_id = state.raw_artifact_ids.get(artifact_alias)
        job = api_state.store.backtest_jobs.get(raw_job_id or "")
        if not isinstance(job, dict):
            return None
        raw_action_id = job.get("idempotency_key")
        return (
            state.artifact_aliases.get(raw_action_id)
            if isinstance(raw_action_id, str)
            else None
        )

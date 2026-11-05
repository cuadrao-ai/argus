from __future__ import annotations

import time
import traceback
from collections.abc import Callable, Mapping
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from math import isfinite
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID, uuid4

from argus.api.schemas import BacktestRun, EvidenceArtifact, Idea, IdeaVersion
from argus.domain.backtest_admission import admission_limits
from argus.domain.backtest_finalization import (
    BacktestFinalizationError,
    BacktestFinalizationInput,
    FinalizedBacktest,
    PreparedBacktestFinalization,
    finalize_backtest_completion,
    stable_backtest_run_id,
)
from argus.domain.backtest_job_lifecycle import RESULT_CLEANUP_PENDING_KEY
from argus.domain.evidence import CapturedEvidence
from argus.llm.openrouter_key_policy import (
    OpenRouterTrafficClass,
    openrouter_traffic_class,
)
from argus.log_sink import configure_logging
from argus.observability.cost_ledger import (
    normalize_cost_ledger_entry,
    persist_openrouter_cost_ledger_entries,
)
from loguru import logger

configure_logging()

if TYPE_CHECKING:
    from argus.agent_runtime.result_readout import ResultReadout
    from argus.llm.openrouter import OpenRouterRouteReceipt

try:
    from workflows.proof import require_database_url, utcnow_iso
except ModuleNotFoundError:  # pragma: no cover - supports `python workflows/main.py`
    from proof import require_database_url, utcnow_iso

REAL_BACKTEST_JOB_KIND = "run_backtest_job"
WORKFLOW_METADATA_KEY = "workflow_backtest"
CAPACITY_LOAD_SOURCE = "public_alpha_capacity_load"
CAPACITY_LOAD_AUTHORITY = "service_role"
CAPACITY_PROBE_MODES = {
    "invalid_envelope",
    "upstream_transient_once",
}
CAPACITY_PROBE_MAX_ATTEMPTS = 2
DEFAULT_WORKFLOW_CAPACITY_WAIT_SECONDS = 240.0
DEFAULT_WORKFLOW_CAPACITY_POLL_SECONDS = 0.25


class WorkflowBacktestJobError(RuntimeError):
    """Raised when a real backtest job cannot be executed safely."""


class WorkflowCapacityTimeout(WorkflowBacktestJobError):
    """Raised when a queued workflow cannot claim a bounded running slot."""


class WithheldCleanupError(WorkflowBacktestJobError):
    """A refused link's tuple removal failed after the durable pending
    marker was written. The task run fails so the Render retry re-enters
    the entry reconciler; the job's standing terminal state is never
    overwritten on the way out."""


class BacktestJobGateway(Protocol):
    def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        """Return one backtest job row by id."""

    def mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
        started_at: str | None = None,
    ) -> dict[str, Any]:
        """Claim a queued or retryable-finalization job for one worker."""

    def finalize_backtest_completion(
        self,
        *,
        finalization: PreparedBacktestFinalization,
    ) -> FinalizedBacktest:
        """Commit or replay one complete backtest evidence tuple."""

    def link_backtest_job_result(
        self,
        *,
        user_id: str,
        job_id: str,
        result_run_id: str,
        execution_metadata: dict[str, Any] | None = None,
        mark_succeeded: bool = False,
    ) -> dict[str, Any]:
        """Link a successful job to its canonical run."""

    def delete_withheld_backtest_result(self, *, user_id: str, run_id: str) -> bool:
        """Remove a run row whose publication the link write refused."""

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
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        """Persist a structured workflow failure."""

    def merge_backtest_job_execution_metadata(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge non-lifecycle execution metadata onto an existing job."""

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
        """Persist LLM route telemetry produced during workflow execution."""

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        """Append provider/runtime spend produced during workflow execution."""


class BacktestTool(Protocol):
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the Argus launch backtest payload."""


def result_readout_with_metadata_from_backtest_payload(
    *args: Any,
    **kwargs: Any,
) -> "ResultReadout":
    from argus.agent_runtime.result_readout import (
        result_readout_with_metadata_from_backtest_payload as _result_readout,
    )

    return _result_readout(*args, **kwargs)


def run_backtest_job(
    gateway: BacktestJobGateway,
    *,
    job_id: str,
    backtest_tool: BacktestTool | None = None,
    workflow_run_id: str | None = None,
    run_id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    timings = _WorkflowTimingRecorder()
    phase_started = time.perf_counter()
    row = gateway.fetch_job(job_id)
    timings.record_elapsed("job_fetch", phase_started)
    if row is None:
        raise WorkflowBacktestJobError(f"Backtest job {job_id} was not found.")

    # Before any startability assertion: the retry of a task that failed
    # its withheld-tuple removal carries a terminal job (often canceled),
    # and its only remaining work is finishing that removal.
    pending_cleanup = _job_metadata(row).get(RESULT_CLEANUP_PENDING_KEY)
    if (
        isinstance(pending_cleanup, dict)
        and pending_cleanup.get("run_id")
        and not pending_cleanup.get("completed_at")
    ):
        return _reconcile_withheld_cleanup(
            gateway,
            row=row,
            job_id=job_id,
            pending=pending_cleanup,
            workflow_run_id=workflow_run_id,
        )
    _assert_real_job(row)

    if row.get("status") == "succeeded" and row.get("result_run_id"):
        return _already_succeeded_result(
            row,
            job_id=job_id,
            workflow_run_id=workflow_run_id,
        )

    user_id = _required_str(row, "user_id")
    try:
        traffic_class = _openrouter_traffic_class_from_job(row)
    except WorkflowBacktestJobError:
        return _mark_failed(
            gateway,
            row=row,
            job_id=job_id,
            user_id=user_id,
            failure_code="invalid_job_contract",
            failure_detail="execution_failed",
            retryable=False,
            workflow_run_id=workflow_run_id,
            failure_category="invalid_job_contract",
            timings=timings,
        )
    conversation_id = _required_str(row, "conversation_id")
    request = _request_payload(row)
    running_metadata = _merge_workflow_metadata(
        row,
        {
            "kind": REAL_BACKTEST_JOB_KIND,
            "workflow_run_id": workflow_run_id,
        },
    )
    phase_started = time.perf_counter()
    try:
        running = gateway.mark_backtest_job_running(
            user_id=user_id,
            job_id=job_id,
            execution_metadata=running_metadata,
        )
    except WorkflowCapacityTimeout:
        timings.record_elapsed("mark_running", phase_started)
        finalization_retry = (
            row.get("status") == "failed"
            and row.get("failure_code") == "finalization_failed"
            and bool(row.get("retryable"))
        )
        return _mark_failed(
            gateway,
            row=row,
            job_id=job_id,
            user_id=user_id,
            failure_code=(
                "finalization_failed" if finalization_retry else "capacity_timeout"
            ),
            failure_detail="execution_failed",
            retryable=finalization_retry,
            workflow_run_id=workflow_run_id,
            failure_category="capacity_timeout",
            timings=timings,
            expected_status=str(row.get("status") or "queued"),
        )
    timings.record_elapsed("mark_running", phase_started)
    started_at = _required_str(running, "started_at")
    attempt = int(running.get("attempts") or 0)
    probe_mode = capacity_probe_mode(running)
    if probe_mode == "invalid_envelope":
        return _mark_failed(
            gateway,
            row=running,
            job_id=job_id,
            user_id=user_id,
            failure_code="invalid_job_contract",
            failure_detail="execution_failed",
            retryable=attempt < CAPACITY_PROBE_MAX_ATTEMPTS,
            workflow_run_id=workflow_run_id,
            failure_category="invalid_job_contract",
            timings=timings,
        )
    if probe_mode == "upstream_transient_once" and attempt == 1:
        return _mark_failed(
            gateway,
            row=running,
            job_id=job_id,
            user_id=user_id,
            failure_code="failed_upstream",
            failure_detail="execution_failed",
            retryable=True,
            workflow_run_id=workflow_run_id,
            failure_category="failed_upstream",
            timings=timings,
        )

    if backtest_tool is None:
        phase_started = time.perf_counter()
        tool = _default_backtest_tool()
        timings.record_elapsed("dependency_or_tool_load", phase_started)
    else:
        tool = backtest_tool
    finalization_committed = False
    result_run_id: str | None = None
    try:
        phase_started = time.perf_counter()
        result = tool.run(request)
        timings.record_elapsed("backtest_tool_run_total", phase_started)
        timings.merge(_tool_timings_ms(result))
        if not bool(result.get("success")):
            return _mark_failed_from_tool_result(
                gateway,
                row=running,
                job_id=job_id,
                user_id=user_id,
                result=result,
                workflow_run_id=workflow_run_id,
                timings=timings,
            )

        payload = result.get("payload")
        if not isinstance(payload, dict):
            return _mark_failed(
                gateway,
                row=running,
                job_id=job_id,
                user_id=user_id,
                failure_code="invalid_tool_result",
                failure_detail="execution_failed",
                retryable=False,
                workflow_run_id=workflow_run_id,
                timings=timings,
            )
        envelope = payload.get("envelope")
        result_card = payload.get("result_card")
        if not isinstance(envelope, dict) or not isinstance(result_card, dict):
            return _mark_failed(
                gateway,
                row=running,
                job_id=job_id,
                user_id=user_id,
                failure_code="invalid_tool_result",
                failure_detail="execution_failed",
                retryable=False,
                workflow_run_id=workflow_run_id,
                timings=timings,
            )
        explanation_context = payload.get("explanation_context")
        explanation_context_dict = (
            dict(explanation_context) if isinstance(explanation_context, dict) else {}
        )
        phase_started = time.perf_counter()
        with openrouter_traffic_class(traffic_class):
            result_readout, result_readout_receipts = _safe_result_readout_with_receipts(
                request=request,
                envelope=envelope,
                result_card=result_card,
                explanation_context=explanation_context_dict,
            )
        timings.record_elapsed("result_readout_total", phase_started)

        from argus.domain.result_readout_content import readout_metadata

        result_card = {
            **result_card,
            **readout_metadata(
                surface="quick_take",
                text=result_readout.text,
                language=str(request.get("language") or "en"),
                source=result_readout.source,
                fallback_used=result_readout.fallback_used,
                failure_mode=result_readout.failure_mode,
            ),
        }

        from argus.domain.backtest_run_builder import build_backtest_run_from_result

        binding = _request_tool_binding(running)
        if binding is not None:
            from argus.agent_runtime.tools.registered_backtest import (
                backtest_execution_result,
            )
            from argus.domain.tool_contracts import ToolOutcome
            from argus.domain.tool_job_binding import tool_card_for_job_completion

            completed_card = tool_card_for_job_completion(
                binding,
                ToolOutcome(
                    status="succeeded",
                    result=backtest_execution_result(
                        {"result": envelope, "result_card": result_card}
                    ).model_dump(mode="json"),
                ),
            )
            result_card = {
                **result_card,
                "tool_result_cards": [completed_card.model_dump(mode="json")],
            }
        run = build_backtest_run_from_result(
            conversation_id=conversation_id,
            result_card=result_card,
            envelope=envelope,
            run_id_factory=(
                run_id_factory
                or (
                    lambda: stable_backtest_run_id(
                        user_id,
                        f"backtest_job:{job_id}",
                    )
                )
            ),
        )
        if run is None:
            return _mark_failed(
                gateway,
                row=running,
                job_id=job_id,
                user_id=user_id,
                failure_code="invalid_run_snapshot",
                failure_detail="execution_failed",
                retryable=False,
                workflow_run_id=workflow_run_id,
                timings=timings,
            )

        phase_started = time.perf_counter()
        try:
            finalized = finalize_backtest_completion(
                gateway,
                BacktestFinalizationInput(
                    user_id=user_id,
                    execution_identity=f"backtest_job:{job_id}",
                    run=run,
                    result_card=dict(run.conversation_result_card),
                    idea_id=str(uuid4()),
                    idea_version_id=str(uuid4()),
                    evidence_artifact_id=str(uuid4()),
                    finalized_at=datetime.now(timezone.utc),
                ),
            )
        except BacktestFinalizationError as exc:
            timings.record_elapsed("backtest_finalization", phase_started)
            return _mark_failed(
                gateway,
                row=running,
                job_id=job_id,
                user_id=user_id,
                failure_code="finalization_failed",
                failure_detail="execution_failed",
                retryable=True,
                workflow_run_id=workflow_run_id,
                source_error=exc,
                timings=timings,
            )
        timings.record_elapsed("backtest_finalization", phase_started)
        finalization_committed = True
        result_run_id = finalized.identity.run_id
        phase_started = time.perf_counter()
        _persist_result_readout_route_receipts(
            gateway,
            receipts=result_readout_receipts,
            user_id=user_id,
            conversation_id=conversation_id,
            result_run_id=result_run_id,
            job_id=job_id,
            workflow_run_id=workflow_run_id,
        )
        timings.record_elapsed("result_readout_receipts_persist", phase_started)
        finished_at = utcnow_iso()
        succeeded_metadata = _merge_workflow_metadata(
            running,
            {
                "kind": REAL_BACKTEST_JOB_KIND,
                "workflow_run_id": workflow_run_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "result_run_id": result_run_id,
                "timings_ms": timings.snapshot(),
                **_result_readout_metadata(result_readout),
            },
        )
        phase_started = time.perf_counter()
        succeeded = gateway.link_backtest_job_result(
            user_id=user_id,
            job_id=job_id,
            result_run_id=result_run_id,
            execution_metadata=succeeded_metadata,
            mark_succeeded=True,
        )
        timings.record_elapsed("link_result", phase_started)
        link_refused = str(succeeded.get("result_run_id") or "") != result_run_id
        if link_refused:
            # The lifecycle statement refused the attach: the job's terminal
            # state stands and its card may already be restored. Completed
            # run rows are product-readable regardless of link state, so
            # the just-committed tuple leaves the result tables. A removal
            # failure persists a durable pending marker and fails the task
            # run: the Render retry re-enters the entry reconciler, and the
            # generic failure handler, which would overwrite the job's
            # standing terminal state, is bypassed.
            if not _delete_withheld_run(gateway, user_id=user_id, run_id=result_run_id):
                _persist_cleanup_pending_marker(
                    gateway,
                    row=succeeded,
                    user_id=user_id,
                    job_id=job_id,
                    run_id=result_run_id,
                )
                raise WithheldCleanupError(
                    f"Withheld-result cleanup failed for job {job_id}; "
                    "re-running the task reconciles it."
                )
            # The task return is ephemeral; the job row carries the
            # contract's durable refusal record so hydration and operators
            # can tell a cleaned withheld result from a plain cancellation.
            succeeded = _persist_refusal_audit_record(
                gateway,
                row=succeeded,
                user_id=user_id,
                job_id=job_id,
                run_id=result_run_id,
            )
        succeeded = _persist_final_workflow_timings(
            gateway,
            user_id=user_id,
            job_id=job_id,
            row=succeeded,
            timings=timings,
        )
        return {
            "job_id": str(succeeded.get("id") or job_id),
            "status": succeeded.get("status") or "succeeded",
            "result_run_id": None if link_refused else result_run_id,
            **({"result_link_refused": True} if link_refused else {}),
            "workflow_run_id": workflow_run_id,
            **({"result_readout": result_readout.text} if result_readout.text else {}),
            "result_readout_source": result_readout.source,
            "result_readout_fallback_used": result_readout.fallback_used,
            **(
                {"result_readout_failure_mode": result_readout.failure_mode}
                if result_readout.failure_mode
                else {}
            ),
            "execution_metadata": _json_safe(
                succeeded.get("execution_metadata") or succeeded_metadata
            ),
        }
    except WithheldCleanupError:
        # The pending marker is already durable; failing the task run is
        # the retry mechanism, and the job's standing terminal state must
        # not be overwritten with a re-claimable failure.
        raise
    except Exception as exc:
        latest = gateway.fetch_job(job_id) or running
        if (
            finalization_committed
            and result_run_id is not None
            and latest.get("status") == "succeeded"
            and latest.get("result_run_id") == result_run_id
        ):
            return _already_succeeded_result(
                latest,
                job_id=job_id,
                workflow_run_id=workflow_run_id,
            )
        failure_code = (
            "finalization_failed" if finalization_committed else "failed_internal"
        )
        return _mark_failed(
            gateway,
            row=latest,
            job_id=job_id,
            user_id=user_id,
            failure_code=failure_code,
            failure_detail="execution_failed",
            retryable=finalization_committed,
            workflow_run_id=workflow_run_id,
            source_error=exc,
            timings=timings,
        )


def _request_tool_binding(row: Mapping[str, Any]) -> dict[str, Any] | None:
    launch = row.get("launch_payload")
    if not isinstance(launch, dict):
        return None
    binding = launch.get("tool_binding")
    return binding if isinstance(binding, dict) else None


def _delete_withheld_run(gateway: Any, *, user_id: str, run_id: str) -> bool:
    """Returns whether the tuple is gone. The caller turns a failure into
    the durable pending marker plus a failed task run, whose retry is the
    reconciliation mechanism."""
    delete_run = getattr(gateway, "delete_withheld_backtest_result", None)
    if delete_run is None:
        return True
    try:
        delete_run(user_id=user_id, run_id=run_id)
        return True
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning(
            "Withheld result tuple could not be removed",
            user_id=user_id,
            run_id=run_id,
        )
        return False


def _persist_cleanup_pending_marker(
    gateway: Any,
    *,
    row: Mapping[str, Any],
    user_id: str,
    job_id: str,
    run_id: str,
) -> None:
    """Durable record of the leak, written with bounded retries because
    the entry reconciler keys on it: even if the task retry never lands,
    the marker is queryable on the job row and names the exact tuple an
    operator must remove. This gateway's metadata write replaces the
    whole object, so the marker is merged onto the standing row's
    metadata rather than sent alone."""
    metadata = _job_metadata(row)
    metadata[RESULT_CLEANUP_PENDING_KEY] = {
        "run_id": run_id,
        "failed_at": utcnow_iso(),
    }
    for attempt in (1, 2, 3):
        try:
            gateway.merge_backtest_job_execution_metadata(
                user_id=user_id,
                job_id=job_id,
                execution_metadata=metadata,
            )
            return
        except Exception:  # noqa: BLE001
            if attempt == 3:
                logger.opt(exception=True).warning(
                    "Withheld-cleanup pending marker could not be persisted "
                    "after retries; the leak is visible only in logs until "
                    "an operator intervenes",
                    user_id=user_id,
                    job_id=job_id,
                    run_id=run_id,
                )
                return
            time.sleep(0.2 * attempt)


def _persist_refusal_audit_record(
    gateway: Any,
    *,
    row: Mapping[str, Any],
    user_id: str,
    job_id: str,
    run_id: str,
) -> dict[str, Any]:
    """The contract's durable refusal record for a cleaned withheld
    result, merged onto the standing metadata because this gateway's
    write replaces the whole object. Best effort: the refusal is also in
    the task output and logs, so a failed audit write degrades loudly
    without failing the task."""
    metadata = _job_metadata(row)
    metadata["result_link_refused"] = {
        "run_id": run_id,
        "cleaned_at": utcnow_iso(),
    }
    try:
        updated = gateway.merge_backtest_job_execution_metadata(
            user_id=user_id,
            job_id=job_id,
            execution_metadata=metadata,
        )
        return dict(updated) if isinstance(updated, dict) else dict(row)
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning(
            "Refused-link audit record could not be persisted",
            user_id=user_id,
            job_id=job_id,
            run_id=run_id,
        )
        return dict(row)


def _reconcile_withheld_cleanup(
    gateway: Any,
    *,
    row: Mapping[str, Any],
    job_id: str,
    pending: dict[str, Any],
    workflow_run_id: str | None,
) -> dict[str, Any]:
    """Finish a previously failed withheld-tuple removal before anything
    else runs: the retry of the failed task run lands here, and a job
    carrying the marker must not be treated as startable work."""
    user_id = _required_str(row, "user_id")
    run_id = str(pending.get("run_id") or "")
    if not _delete_withheld_run(gateway, user_id=user_id, run_id=run_id):
        raise WithheldCleanupError(
            f"Withheld-result cleanup is still failing for job {job_id}."
        )
    # This gateway's metadata write replaces the whole object, so the
    # completed marker and the contract's refusal record are merged onto
    # the standing row's metadata.
    completed_metadata = _job_metadata(row)
    completed_metadata[RESULT_CLEANUP_PENDING_KEY] = {
        **pending,
        "completed_at": utcnow_iso(),
    }
    completed_metadata.setdefault(
        "result_link_refused",
        {"run_id": run_id, "cleaned_at": utcnow_iso()},
    )
    metadata = gateway.merge_backtest_job_execution_metadata(
        user_id=user_id,
        job_id=job_id,
        execution_metadata=completed_metadata,
    )
    return {
        "job_id": job_id,
        "status": str(row.get("status") or ""),
        "result_run_id": None,
        "result_link_refused": True,
        "result_cleanup_reconciled": True,
        "workflow_run_id": workflow_run_id,
        "execution_metadata": _json_safe(
            metadata.get("execution_metadata")
            if isinstance(metadata, dict)
            else completed_metadata
        ),
    }


def _already_succeeded_result(
    row: Mapping[str, Any],
    *,
    job_id: str,
    workflow_run_id: str | None,
) -> dict[str, Any]:
    metadata = _job_metadata(row)
    workflow_metadata = metadata.get(WORKFLOW_METADATA_KEY)
    workflow_metadata = (
        dict(workflow_metadata) if isinstance(workflow_metadata, dict) else {}
    )
    result_readout = workflow_metadata.get("result_readout")
    return {
        "job_id": str(row.get("id") or job_id),
        "status": "succeeded",
        "result_run_id": str(row["result_run_id"]),
        "workflow_run_id": workflow_run_id,
        **(
            {"result_readout": result_readout}
            if isinstance(result_readout, str) and result_readout.strip()
            else {}
        ),
        "result_readout_source": workflow_metadata.get("result_readout_source"),
        "result_readout_fallback_used": bool(
            workflow_metadata.get("result_readout_fallback_used")
        ),
        **(
            {
                "result_readout_failure_mode": workflow_metadata[
                    "result_readout_failure_mode"
                ]
            }
            if workflow_metadata.get("result_readout_failure_mode")
            else {}
        ),
        "execution_metadata": _json_safe(metadata),
    }


def _default_backtest_tool() -> BacktestTool:
    from argus.agent_runtime.tools.real_backtest import RealBacktestTool

    return RealBacktestTool()


def _safe_result_readout(
    *,
    request: dict[str, Any],
    envelope: dict[str, Any],
    result_card: dict[str, Any],
    explanation_context: dict[str, Any],
) -> "ResultReadout":
    from argus.agent_runtime.result_readout import unavailable_result_readout

    try:
        return result_readout_with_metadata_from_backtest_payload(
            request=request,
            envelope=envelope,
            result_card=result_card,
            explanation_context=explanation_context,
            language=_optional_str(request.get("language")),
        )
    except Exception:
        return unavailable_result_readout()


def _safe_result_readout_with_receipts(
    *,
    request: dict[str, Any],
    envelope: dict[str, Any],
    result_card: dict[str, Any],
    explanation_context: dict[str, Any],
) -> tuple["ResultReadout", list["OpenRouterRouteReceipt"]]:
    from argus.llm.openrouter import (
        begin_openrouter_route_receipt_capture,
        end_openrouter_route_receipt_capture,
    )

    token = begin_openrouter_route_receipt_capture()
    try:
        result_readout = _safe_result_readout(
            request=request,
            envelope=envelope,
            result_card=result_card,
            explanation_context=explanation_context,
        )
    finally:
        receipts = end_openrouter_route_receipt_capture(token)
    return result_readout, receipts


def _persist_result_readout_route_receipts(
    gateway: BacktestJobGateway,
    *,
    receipts: list["OpenRouterRouteReceipt"],
    user_id: str,
    conversation_id: str,
    result_run_id: str,
    job_id: str,
    workflow_run_id: str | None,
) -> None:
    if not receipts:
        return
    metadata = {
        "job_id": job_id,
        "workflow_run_id": workflow_run_id,
        "source": "render_workflow",
    }
    for receipt in receipts:
        try:
            created = gateway.create_route_receipt(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=result_run_id,
                metadata=metadata,
                receipt=receipt.as_dict(),
            )
            persist_openrouter_cost_ledger_entries(
                gateway=gateway,
                receipts=[receipt],
                source="render_workflow",
                feature_area="result_readout",
                user_id=user_id,
                conversation_id=conversation_id,
                backtest_run_id=result_run_id,
                backtest_job_id=job_id,
                route_receipt_rows=[created],
                correlation_id=":".join(
                    part
                    for part in (
                        "workflow",
                        workflow_run_id,
                        job_id,
                        result_run_id,
                    )
                    if part
                ),
                metadata=metadata,
            )
        except Exception as exc:
            logger.warning(
                "Backtest workflow route receipt persistence failed",
                error=str(exc),
                job_id=job_id,
                workflow_run_id=workflow_run_id,
                llm_task=receipt.task,
            )


def _result_readout_metadata(result_readout: "ResultReadout") -> dict[str, Any]:
    metadata = {
        "result_readout_source": result_readout.source,
        "result_readout_fallback_used": result_readout.fallback_used,
        **(
            {"next_experiments": result_readout.next_experiments}
            if result_readout.next_experiments
            else {}
        ),
    }
    if result_readout.text:
        metadata["result_readout"] = result_readout.text
    if result_readout.failure_mode:
        metadata["result_readout_failure_mode"] = result_readout.failure_mode
    return metadata


def _assert_real_job(row: Mapping[str, Any]) -> None:
    status = row.get("status")
    retryable_finalization_failure = (
        status == "failed"
        and row.get("failure_code") == "finalization_failed"
        and bool(row.get("retryable"))
    )
    retryable_capacity_probe = (
        status == "failed"
        and bool(row.get("retryable"))
        and int(row.get("attempts") or 0) < CAPACITY_PROBE_MAX_ATTEMPTS
        and capacity_probe_mode(row) in CAPACITY_PROBE_MODES
    )
    if status not in {"queued", "running", "succeeded"} and not (
        retryable_finalization_failure or retryable_capacity_probe
    ):
        raise WorkflowBacktestJobError(
            f"run_backtest_job cannot execute job in status {status!r}."
        )
    payload = _launch_payload(row)
    if payload.get("kind") != REAL_BACKTEST_JOB_KIND:
        raise WorkflowBacktestJobError(
            "run_backtest_job can only execute launch_payload.kind="
            f"{REAL_BACKTEST_JOB_KIND!r} jobs."
        )
    if (
        not isinstance(payload.get("request"), dict)
        and capacity_probe_mode(row) != "invalid_envelope"
    ):
        raise WorkflowBacktestJobError(
            "run_backtest_job requires a JSON object launch_payload.request."
        )


def _request_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    request = _launch_payload(row).get("request")
    return dict(request) if isinstance(request, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _launch_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("launch_payload") or {}
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def _job_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("execution_metadata") or {}
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def capacity_probe_mode(row: Mapping[str, Any]) -> str | None:
    """Return a controlled probe mode only from service-role ops metadata."""

    metadata = _job_metadata(row)
    if metadata.get("source") != CAPACITY_LOAD_SOURCE:
        return None
    if metadata.get("ops_authority") != CAPACITY_LOAD_AUTHORITY:
        return None
    probe = metadata.get("capacity_probe")
    if not isinstance(probe, dict):
        return None
    mode = probe.get("mode")
    return str(mode) if mode in CAPACITY_PROBE_MODES else None


def capacity_probe_should_raise(result: Mapping[str, Any]) -> bool:
    """Tell the Render task wrapper when a controlled probe needs task failure."""

    return (
        result.get("status") == "failed"
        and capacity_probe_mode(result) in CAPACITY_PROBE_MODES
    )


def _openrouter_traffic_class_from_job(
    row: Mapping[str, Any],
) -> OpenRouterTrafficClass:
    traffic_class = _job_metadata(row).get("openrouter_traffic_class")
    if traffic_class not in {"guest", "registered"}:
        raise WorkflowBacktestJobError(
            "run_backtest_job requires execution_metadata.openrouter_traffic_class."
        )
    return cast(OpenRouterTrafficClass, traffic_class)


def _merge_workflow_metadata(
    row: Mapping[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    metadata = _job_metadata(row)
    workflow_metadata = dict(metadata.get(WORKFLOW_METADATA_KEY) or {})
    workflow_metadata.update(patch)
    metadata[WORKFLOW_METADATA_KEY] = workflow_metadata
    return metadata


class _WorkflowTimingRecorder:
    def __init__(self) -> None:
        self._task_started = time.perf_counter()
        self._timings_ms: dict[str, float] = {}

    def record_elapsed(self, name: str, started: float) -> None:
        self.add(name, (time.perf_counter() - started) * 1000.0)

    def add(self, name: str, elapsed_ms: Any) -> None:
        if isinstance(elapsed_ms, bool):
            return
        try:
            numeric = float(elapsed_ms)
        except (TypeError, ValueError):
            return
        if not isfinite(numeric) or numeric < 0.0:
            return
        self._timings_ms[name] = self._timings_ms.get(name, 0.0) + numeric

    def merge(self, timings_ms: Mapping[str, Any]) -> None:
        for name, elapsed_ms in timings_ms.items():
            self.add(str(name), elapsed_ms)

    def record_workflow_total(self) -> None:
        self._timings_ms["workflow_task_total"] = (
            time.perf_counter() - self._task_started
        ) * 1000.0

    def snapshot(self) -> dict[str, float]:
        return {
            name: round(elapsed_ms, 3)
            for name, elapsed_ms in sorted(self._timings_ms.items())
        }


def _tool_timings_ms(result: Mapping[str, Any]) -> dict[str, float]:
    metadata = result.get("execution_metadata")
    if not isinstance(metadata, dict):
        return {}
    raw_timings = metadata.get("timings_ms")
    if not isinstance(raw_timings, dict):
        return {}
    timings: dict[str, float] = {}
    for name, elapsed_ms in raw_timings.items():
        if not isinstance(name, str) or isinstance(elapsed_ms, bool):
            continue
        try:
            numeric = float(elapsed_ms)
        except (TypeError, ValueError):
            continue
        if isfinite(numeric) and numeric >= 0.0:
            timings[name] = numeric
    return timings


def _persist_final_workflow_timings(
    gateway: BacktestJobGateway,
    *,
    user_id: str,
    job_id: str,
    row: Mapping[str, Any],
    timings: _WorkflowTimingRecorder,
) -> dict[str, Any]:
    timings.record_workflow_total()
    metadata = _merge_workflow_metadata(row, {"timings_ms": timings.snapshot()})
    try:
        updated = gateway.merge_backtest_job_execution_metadata(
            user_id=user_id,
            job_id=job_id,
            execution_metadata=metadata,
        )
    except Exception as exc:
        logger.warning(
            "Backtest workflow timing metadata merge failed",
            error=str(exc),
            job_id=job_id,
        )
        updated = dict(row)
        updated["execution_metadata"] = metadata
    return updated


def _mark_failed_from_tool_result(
    gateway: BacktestJobGateway,
    *,
    row: Mapping[str, Any],
    job_id: str,
    user_id: str,
    result: dict[str, Any],
    workflow_run_id: str | None,
    timings: _WorkflowTimingRecorder,
) -> dict[str, Any]:
    failure_category = str(result.get("error_type") or "failed_internal")
    failure_code = failure_category
    capability_context = result.get("capability_context")
    failure_detail = None
    if isinstance(capability_context, dict):
        from argus.domain.engine_launch.results import (
            is_user_safe_failure_code,
            is_user_safe_failure_detail,
        )

        raw_failure_code = capability_context.get("failure_code")
        if isinstance(raw_failure_code, str) and is_user_safe_failure_code(
            raw_failure_code
        ):
            failure_code = raw_failure_code.strip()
        raw_failure_detail = capability_context.get("failure_detail")
        if isinstance(raw_failure_detail, str) and is_user_safe_failure_detail(
            raw_failure_detail
        ):
            failure_detail = raw_failure_detail.strip()
    from argus.domain.engine_launch.results import user_safe_failure_detail

    failure_detail = failure_detail or user_safe_failure_detail(
        failure_reason=failure_code,
        failure_category=failure_code,
    )
    return _mark_failed(
        gateway,
        row=row,
        job_id=job_id,
        user_id=user_id,
        failure_code=failure_code,
        failure_detail=failure_detail,
        retryable=bool(result.get("retryable")),
        workflow_run_id=workflow_run_id,
        failure_category=failure_category,
        timings=timings,
    )


def _mark_failed(
    gateway: BacktestJobGateway,
    *,
    row: Mapping[str, Any],
    job_id: str,
    user_id: str,
    failure_code: str,
    failure_detail: str,
    retryable: bool,
    workflow_run_id: str | None,
    failure_category: str | None = None,
    source_error: Exception | None = None,
    timings: _WorkflowTimingRecorder | None = None,
    expected_status: str | None = None,
) -> dict[str, Any]:
    finished_at = utcnow_iso()
    failure_patch: dict[str, Any] = {
        "kind": REAL_BACKTEST_JOB_KIND,
        "workflow_run_id": workflow_run_id,
        "finished_at": finished_at,
        "failure_category": failure_category or failure_code,
        "failure_detail": failure_detail,
        "retryable": retryable,
    }
    if timings is not None:
        failure_patch["timings_ms"] = timings.snapshot()
    if source_error is not None:
        failure_patch["source_error_type"] = type(source_error).__name__
        failure_patch["source_traceback"] = traceback.format_exception_only(
            type(source_error),
            source_error,
        )[-1].strip()
    metadata = _merge_workflow_metadata(row, failure_patch)
    if expected_status is None:
        failed = gateway.mark_backtest_job_failed(
            user_id=user_id,
            job_id=job_id,
            failure_code=failure_code,
            failure_detail=failure_detail,
            retryable=retryable,
            execution_metadata=metadata,
            finished_at=finished_at,
        )
    else:
        failed = gateway.mark_backtest_job_failed(
            user_id=user_id,
            job_id=job_id,
            failure_code=failure_code,
            failure_detail=failure_detail,
            retryable=retryable,
            execution_metadata=metadata,
            finished_at=finished_at,
            expected_status=expected_status,
        )
    if failed:
        from argus.api.chat.confirmation import restore_pending_card_for_failed_job

        restore_pending_card_for_failed_job(
            gateway,
            user_id=user_id,
            job={**(row if isinstance(row, dict) else {}), **dict(failed)},
        )
    if timings is not None:
        failed = _persist_final_workflow_timings(
            gateway,
            user_id=user_id,
            job_id=job_id,
            row=failed,
            timings=timings,
        )
    return {
        "job_id": str(failed.get("id") or job_id),
        "status": failed.get("status") or "failed",
        "failure_code": failure_code,
        "failure_detail": failure_detail,
        "retryable": retryable,
        "workflow_run_id": workflow_run_id,
        "execution_metadata": _json_safe(failed.get("execution_metadata") or metadata),
    }


def _required_str(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowBacktestJobError(f"Backtest job is missing required {key}.")
    return value


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _workflow_start_candidate(row: Any) -> bool:
    if not isinstance(row, Mapping):
        return False
    if row.get("status") == "queued":
        return True
    if row.get("status") != "failed" or not bool(row.get("retryable")):
        return False
    if row.get("failure_code") == "finalization_failed":
        return True
    return (
        int(row.get("attempts") or 0) < CAPACITY_PROBE_MAX_ATTEMPTS
        and capacity_probe_mode(row) in CAPACITY_PROBE_MODES
    )


class PostgresBacktestJobGateway:
    def __init__(
        self,
        database_url: str,
        *,
        capacity_wait_seconds: float = DEFAULT_WORKFLOW_CAPACITY_WAIT_SECONDS,
        capacity_poll_seconds: float = DEFAULT_WORKFLOW_CAPACITY_POLL_SECONDS,
    ) -> None:
        self.database_url = database_url
        self.capacity_wait_seconds = max(0.0, capacity_wait_seconds)
        self.capacity_poll_seconds = max(0.01, capacity_poll_seconds)
        self._conn: Any | None = None
        self._exit_stack: ExitStack | None = None

    @classmethod
    def from_env(cls) -> PostgresBacktestJobGateway:
        return cls(require_database_url())

    def __enter__(self) -> PostgresBacktestJobGateway:
        if self._exit_stack is not None:
            return self
        exit_stack = ExitStack()
        self._conn = exit_stack.enter_context(self._connect())
        self._exit_stack = exit_stack
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._exit_stack is not None:
            self._exit_stack.__exit__(*exc_info)
        self._conn = None
        self._exit_stack = None

    def _connect(self) -> Any:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self.database_url,
            autocommit=True,
            prepare_threshold=None,
            row_factory=dict_row,
        )

    @contextmanager
    def _connection(self) -> Any:
        if self._conn is not None:
            yield self._conn
            return
        with self._connect() as conn:
            yield conn

    def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select *
                    from public.backtest_jobs
                    where id = %s
                    limit 1
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
        return _json_safe(row) if row else None

    def mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
        started_at: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.capacity_wait_seconds
        waiting_logged = False
        while True:
            row = self._try_mark_backtest_job_running(
                user_id=user_id,
                job_id=job_id,
                execution_metadata=execution_metadata,
                started_at=started_at,
            )
            if row is not None:
                return row
            if time.monotonic() >= deadline:
                raise WorkflowCapacityTimeout(
                    f"Backtest job {job_id} timed out waiting for a running slot."
                )
            if not waiting_logged:
                logger.info(
                    "Backtest workflow waiting for a running slot",
                    job_id=job_id,
                )
                waiting_logged = True
            time.sleep(self.capacity_poll_seconds)

    def _try_mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
        started_at: str | None = None,
    ) -> dict[str, Any] | None:
        from psycopg.types.json import Jsonb

        with self._connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "select pg_advisory_xact_lock(hashtext('backtest_admission'))"
                    )
                    cur.execute(
                        """
                        select status, failure_code, retryable, attempts,
                               execution_metadata
                        from public.backtest_jobs
                        where id = %(job_id)s
                          and user_id = %(user_id)s
                        for update
                        """,
                        {"job_id": job_id, "user_id": user_id},
                    )
                    candidate = cur.fetchone()
                    if not _workflow_start_candidate(candidate):
                        raise WorkflowBacktestJobError(
                            f"Backtest job {job_id} cannot be started or retried."
                        )
                    limits = admission_limits()
                    cur.execute(
                        """
                        select
                          count(*) filter (
                            where user_id = %(user_id)s
                          )::integer as user_running,
                          count(*)::integer as global_running
                        from public.backtest_jobs
                        where status = 'running'
                        """,
                        {"user_id": user_id},
                    )
                    counts = cur.fetchone() or {}
                    if (
                        int(counts.get("user_running") or 0) >= limits.user_running
                        or int(counts.get("global_running") or 0) >= limits.global_running
                    ):
                        return None
                    claim_started_at = started_at or utcnow_iso()
                    claimed_metadata = dict(execution_metadata)
                    workflow_metadata = claimed_metadata.get(WORKFLOW_METADATA_KEY)
                    claimed_workflow_metadata = (
                        dict(workflow_metadata)
                        if isinstance(workflow_metadata, Mapping)
                        else {}
                    )
                    claimed_workflow_metadata["started_at"] = claim_started_at
                    claimed_metadata[WORKFLOW_METADATA_KEY] = claimed_workflow_metadata
                    cur.execute(
                        """
                        update public.backtest_jobs
                        set status = 'running',
                            started_at = coalesce(started_at, %(started_at)s),
                            attempts = attempts + 1,
                            result_run_id = null,
                            finished_at = null,
                            failure_code = null,
                            failure_detail = null,
                            retryable = false,
                            execution_metadata = %(execution_metadata)s,
                            updated_at = %(updated_at)s
                        where id = %(job_id)s
                          and user_id = %(user_id)s
                        returning *
                        """,
                        {
                            "job_id": job_id,
                            "user_id": user_id,
                            "started_at": claim_started_at,
                            "execution_metadata": Jsonb(claimed_metadata),
                            "updated_at": utcnow_iso(),
                        },
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise WorkflowBacktestJobError(
                            f"Backtest job {job_id} cannot be started or retried."
                        )
        return _json_safe(row)

    def merge_backtest_job_execution_metadata(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update public.backtest_jobs
                    set execution_metadata = %(execution_metadata)s,
                        updated_at = %(updated_at)s
                    where id = %(job_id)s
                      and user_id = %(user_id)s
                    returning *
                    """,
                    {
                        "job_id": job_id,
                        "user_id": user_id,
                        "execution_metadata": Jsonb(execution_metadata),
                        "updated_at": utcnow_iso(),
                    },
                )
                row = cur.fetchone()
                if row is None:
                    raise WorkflowBacktestJobError(f"Backtest job {job_id} not found.")
        return _json_safe(row)

    def finalize_backtest_completion(
        self,
        *,
        finalization: PreparedBacktestFinalization,
    ) -> FinalizedBacktest:
        from psycopg.types.json import Jsonb

        captured = finalization.captured
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select *
                    from public.finalize_backtest_completion(
                      %(user_id)s::uuid,
                      %(execution_identity)s::text,
                      %(run)s::jsonb,
                      %(idea)s::jsonb,
                      %(idea_version)s::jsonb,
                      %(evidence_artifact)s::jsonb
                    )
                    """,
                    {
                        "user_id": finalization.user_id,
                        "execution_identity": finalization.execution_identity,
                        "run": Jsonb(finalization.run.model_dump(mode="json")),
                        "idea": Jsonb(captured.idea.model_dump(mode="json")),
                        "idea_version": Jsonb(
                            captured.idea_version.model_dump(mode="json")
                        ),
                        "evidence_artifact": Jsonb(
                            captured.evidence_artifact.model_dump(mode="json")
                        ),
                    },
                )
                row = cur.fetchone()
        if row is None:
            raise WorkflowBacktestJobError(
                "Backtest finalization did not return durable artifact state."
            )
        return FinalizedBacktest(
            run=BacktestRun.model_validate(row["run"]),
            captured=CapturedEvidence(
                idea=Idea.model_validate(row["idea"]),
                idea_version=IdeaVersion.model_validate(row["idea_version"]),
                evidence_artifact=EvidenceArtifact.model_validate(
                    row["evidence_artifact"]
                ),
            ),
        )

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
        from psycopg.types.json import Jsonb

        context_packet_ids = [
            str(packet_id)
            for packet_id in receipt.get("context_packet_ids") or []
            if str(packet_id or "").strip()
        ]
        token_usage = receipt.get("token_usage")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.route_receipts (
                      user_id,
                      conversation_id,
                      run_id,
                      message_id,
                      task,
                      tier,
                      model,
                      fallback_model,
                      mode,
                      schema_name,
                      latency_ms,
                      outcome,
                      failure_mode,
                      fallback_used,
                      token_usage,
                      context_packet_ids,
                      metadata,
                      created_at
                    )
                    values (
                      %(user_id)s,
                      %(conversation_id)s,
                      %(run_id)s,
                      %(message_id)s,
                      %(task)s,
                      %(tier)s,
                      %(model)s,
                      %(fallback_model)s,
                      %(mode)s,
                      %(schema_name)s,
                      %(latency_ms)s,
                      %(outcome)s,
                      %(failure_mode)s,
                      %(fallback_used)s,
                      %(token_usage)s,
                      %(context_packet_ids)s,
                      %(metadata)s,
                      %(created_at)s
                    )
                    returning *
                    """,
                    {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "run_id": run_id,
                        "message_id": message_id,
                        "task": receipt["task"],
                        "tier": receipt["tier"],
                        "model": receipt.get("model"),
                        "fallback_model": receipt.get("fallback_model"),
                        "mode": receipt["mode"],
                        "schema_name": receipt.get("schema_name"),
                        "latency_ms": int(receipt.get("latency_ms") or 0),
                        "outcome": receipt["outcome"],
                        "failure_mode": receipt.get("failure_mode"),
                        "fallback_used": bool(receipt.get("fallback_used")),
                        "token_usage": Jsonb(token_usage)
                        if token_usage is not None
                        else None,
                        "context_packet_ids": context_packet_ids,
                        "metadata": Jsonb(metadata or {}),
                        "created_at": receipt.get("created_at") or utcnow_iso(),
                    },
                )
                row = cur.fetchone()
        return _json_safe(row)

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        params = normalize_cost_ledger_entry(entry)
        params["usage_metadata"] = Jsonb(params["usage_metadata"])
        params["metadata"] = Jsonb(params["metadata"])
        params["occurred_at"] = params["occurred_at"] or utcnow_iso()
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.cost_ledger_entries (
                      source,
                      service,
                      provider,
                      model,
                      feature_area,
                      task,
                      user_id,
                      conversation_id,
                      message_id,
                      backtest_run_id,
                      backtest_job_id,
                      route_receipt_id,
                      request_id,
                      correlation_id,
                      provider_request_id,
                      upstream_id,
                      usage_metadata,
                      input_tokens,
                      output_tokens,
                      total_tokens,
                      billable_unit,
                      billable_quantity,
                      cost_amount,
                      cost_currency,
                      cost_source,
                      latency_ms,
                      status,
                      metadata,
                      occurred_at
                    )
                    values (
                      %(source)s,
                      %(service)s,
                      %(provider)s,
                      %(model)s,
                      %(feature_area)s,
                      %(task)s,
                      %(user_id)s,
                      %(conversation_id)s,
                      %(message_id)s,
                      %(backtest_run_id)s,
                      %(backtest_job_id)s,
                      %(route_receipt_id)s,
                      %(request_id)s,
                      %(correlation_id)s,
                      %(provider_request_id)s,
                      %(upstream_id)s,
                      %(usage_metadata)s,
                      %(input_tokens)s,
                      %(output_tokens)s,
                      %(total_tokens)s,
                      %(billable_unit)s,
                      %(billable_quantity)s,
                      %(cost_amount)s,
                      %(cost_currency)s,
                      %(cost_source)s,
                      %(latency_ms)s,
                      %(status)s,
                      %(metadata)s,
                      %(occurred_at)s
                    )
                    returning *
                    """,
                    params,
                )
                row = cur.fetchone()
        return _json_safe(row)

    def link_backtest_job_result(
        self,
        *,
        user_id: str,
        job_id: str,
        result_run_id: str,
        execution_metadata: dict[str, Any] | None = None,
        mark_succeeded: bool = False,
    ) -> dict[str, Any]:
        from argus.domain.backtest_job_lifecycle import (
            job_result_attach_sql_predicate,
            job_success_write_sql_predicate,
        )
        from psycopg.types.json import Jsonb

        status = "succeeded" if mark_succeeded else None
        finished_at = utcnow_iso() if mark_succeeded else None
        # Every result attach passes the lifecycle statement, and success
        # may only follow a state a worker legitimately holds. Both
        # predicates are generated beside the card-restore classification
        # so the sides of the consumption design cannot drift: a state the
        # card was restored from can never gain a result, whether or not
        # the write also converts status.
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    update public.backtest_jobs
                    set result_run_id = coalesce(result_run_id, %(result_run_id)s),
                        status = coalesce(%(status)s, status),
                        finished_at = coalesce(%(finished_at)s, finished_at),
                        failure_code = case
                          when %(status)s = 'succeeded' then null
                          else failure_code
                        end,
                        failure_detail = case
                          when %(status)s = 'succeeded' then null
                          else failure_detail
                        end,
                        retryable = case
                          when %(status)s = 'succeeded' then false
                          else retryable
                        end,
                        execution_metadata = %(execution_metadata)s,
                        updated_at = %(updated_at)s
                    where id = %(job_id)s
                      and user_id = %(user_id)s
                      and {job_result_attach_sql_predicate()}
                      and (
                        %(status)s is distinct from 'succeeded'
                        or {job_success_write_sql_predicate()}
                      )
                    returning *
                    """,
                    {
                        "job_id": job_id,
                        "user_id": user_id,
                        "result_run_id": result_run_id,
                        "status": status,
                        "finished_at": finished_at,
                        "execution_metadata": Jsonb(execution_metadata or {}),
                        "updated_at": utcnow_iso(),
                    },
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        """
                        select * from public.backtest_jobs
                        where id = %(job_id)s and user_id = %(user_id)s
                        """,
                        {"job_id": job_id, "user_id": user_id},
                    )
                    standing = cur.fetchone()
                    if standing is None:
                        raise WorkflowBacktestJobError(
                            f"Backtest job {job_id} not found."
                        )
                    # The attach was refused: the job reached a state no
                    # future write may turn into a result, its card may
                    # already be restored, and that terminal state stands.
                    # The caller removes the computed finalized tuple,
                    # because every part of it is product-readable.
                    logger.warning(
                        "Result link refused; the job's terminal state "
                        "stands and its card consequence is owned by the "
                        "writer that won it",
                        job_id=job_id,
                        standing_status=str(standing.get("status") or ""),
                        mark_succeeded=mark_succeeded,
                    )
                    return _json_safe(standing)
        return _json_safe(row)

    def delete_withheld_backtest_result(self, *, user_id: str, run_id: str) -> bool:
        """Remove the full finalized tuple of a withheld run atomically.

        The database function is the one owner of the removal (children
        first, run row last, ideas with earlier versions repointed), so
        this gateway and the API gateway cannot drift apart and product
        reads can never observe a partial tuple."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select public.delete_withheld_backtest_result("
                    "%(user_id)s, %(run_id)s) as deleted",
                    {"run_id": run_id, "user_id": user_id},
                )
                row = cur.fetchone()
        return bool(row and row.get("deleted"))

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
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update public.backtest_jobs
                    set status = 'failed',
                        result_run_id = null,
                        finished_at = coalesce(%(finished_at)s, finished_at),
                        failure_code = %(failure_code)s,
                        failure_detail = %(failure_detail)s,
                        retryable = %(retryable)s,
                        execution_metadata = %(execution_metadata)s,
                        updated_at = %(updated_at)s
                    where id = %(job_id)s
                      and user_id = %(user_id)s
                      and (
                        %(expected_status)s::text is null
                        or status = %(expected_status)s
                      )
                    returning *
                    """,
                    {
                        "job_id": job_id,
                        "user_id": user_id,
                        "failure_code": failure_code,
                        "failure_detail": failure_detail,
                        "retryable": retryable,
                        "expected_status": expected_status,
                        "finished_at": finished_at or utcnow_iso(),
                        "execution_metadata": Jsonb(execution_metadata or {}),
                        "updated_at": utcnow_iso(),
                    },
                )
                row = cur.fetchone()
                if row is None:
                    raise WorkflowBacktestJobError(f"Backtest job {job_id} not found.")
        return _json_safe(row)

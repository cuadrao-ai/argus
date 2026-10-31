"""Backtest admission identity and allowance charging (#229/#247).

Identity uses one canonical JSON serializer and full ``sha256:`` hex hashes;
the reservation key is ``(user_id, operation_scope, idempotency_key)``. One
admission decision resolves replay/collision, then allowance, then capacity,
and only then inserts the job and charges both windows. The memory backend is
the single-process twin of the database function in migration
``20260722000002_atomic_backtest_admission.sql``.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from argus.domain.backtest_job_scopes import CHAT_RUN_SCOPE, DIRECT_RUN_SCOPE
from argus.domain.backtesting.config import normalize_timeframe
from argus.domain.idempotency import CanonicalJSONError as CanonicalJSONError
from argus.domain.idempotency import KeyState as KeyState
from argus.domain.idempotency import canonical_hash as canonical_hash
from argus.domain.idempotency import canonical_json as canonical_json
from argus.domain.idempotency import validate_idempotency_key as validate_idempotency_key
from argus.domain.usage_limits import (
    SIMULATION_USAGE_RESOURCE,
    AllowanceWindowInput,
    normalize_allowance_windows,
    read_memory_usage,
    settle_memory_usage,
)

STALE_DIRECT_JOB_MINUTES = 15
STALE_DIRECT_JOB_BATCH = 20
STALE_DIRECT_FAILURE_CODE = "direct_execution_abandoned"
STALE_DIRECT_FAILURE_DETAIL = "execution_interrupted"

DEFAULT_USER_RUNNING_LIMIT = 1
DEFAULT_USER_QUEUED_LIMIT = 2
DEFAULT_GLOBAL_RUNNING_LIMIT = 5
DEFAULT_GLOBAL_QUEUED_LIMIT = 10


def _limit(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class AdmissionLimits:
    user_running: int
    user_queued: int
    global_running: int
    global_queued: int


def admission_limits() -> AdmissionLimits:
    return AdmissionLimits(
        user_running=_limit(
            "ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT", DEFAULT_USER_RUNNING_LIMIT
        ),
        user_queued=_limit(
            "ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT", DEFAULT_USER_QUEUED_LIMIT
        ),
        global_running=_limit(
            "ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT", DEFAULT_GLOBAL_RUNNING_LIMIT
        ),
        global_queued=_limit(
            "ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT", DEFAULT_GLOBAL_QUEUED_LIMIT
        ),
    )


def chat_run_identity_hash(
    *,
    conversation_id: str | None,
    confirmation_id: str | None,
    launch_payload_hash: str,
) -> str:
    return canonical_hash(
        {
            "conversation_id": conversation_id,
            "confirmation_id": confirmation_id,
            "launch_payload_hash": launch_payload_hash,
        }
    )


def direct_run_identity_hash(
    *,
    conversation_id: str | None,
    strategy_id: str | None,
    normalized_payload: dict[str, Any],
) -> str:
    return canonical_hash(
        {
            "conversation_id": conversation_id,
            "strategy_id": strategy_id,
            "normalized_payload": normalized_payload,
        }
    )


_DIRECT_PAYLOAD_FIELDS = (
    "template",
    "asset_class",
    "symbols",
    "benchmark_symbol",
    "start_date",
    "end_date",
    "timeframe",
    "side",
    "starting_capital",
    "allocation_method",
    "parameters",
    "conversation_id",
    "strategy_id",
)


def normalize_direct_launch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Materialize the direct-run request: declared fields, executor defaults,
    trimmed/uppercased/de-duplicated symbols preserving first occurrence."""

    normalized: dict[str, Any] = {}
    for field in _DIRECT_PAYLOAD_FIELDS:
        normalized[field] = payload.get(field, None)

    symbols: list[str] = []
    seen: set[str] = set()
    for raw_symbol in payload.get("symbols") or []:
        symbol = str(raw_symbol).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    normalized["symbols"] = symbols

    benchmark = payload.get("benchmark_symbol")
    if isinstance(benchmark, str):
        normalized["benchmark_symbol"] = benchmark.strip().upper() or None

    # Omitted fields and spelled-out executor defaults are one identity;
    # values the executor rejects stay as-is and are never admitted.
    normalized["template"] = normalized["template"] or "rsi_mean_reversion"
    normalized["side"] = normalized["side"] or "long"
    normalized["allocation_method"] = normalized["allocation_method"] or "equal_weight"
    capital = normalized["starting_capital"]
    if capital is None:
        capital = 1000
    if isinstance(capital, (int, float)) and not isinstance(capital, bool):
        capital = float(capital)
    normalized["starting_capital"] = capital
    timeframe = normalized["timeframe"]
    if timeframe is None or isinstance(timeframe, str):
        try:
            normalized["timeframe"] = normalize_timeframe(timeframe)
        except ValueError:
            pass

    # The durable launch payload travels as wire JSON; typed dates
    # canonicalize to ISO day strings, matching identity hashing.
    for field in ("start_date", "end_date"):
        value = normalized[field]
        if isinstance(value, datetime):
            normalized[field] = value.date().isoformat()
        elif isinstance(value, date):
            normalized[field] = value.isoformat()
    return normalized


DecisionKind = Literal[
    "admitted",
    "replay",
    "conflict",
    "allowance_exhausted",
    "conversion_required",
    "per_user_capacity",
    "global_capacity",
]


@dataclass(frozen=True)
class AdmissionOutcome:
    kind: DecisionKind
    job: dict[str, Any] | None = None
    retry_after_seconds: int | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _job_started_at(job: dict[str, Any]) -> datetime | None:
    raw = job.get("started_at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def reconcile_stale_direct_jobs_memory(
    store: Any,
    *,
    now: datetime | None = None,
    only_job_id: str | None = None,
) -> int:
    """Bounded stale direct-job pass: running ``backtests.run`` jobs whose
    ``started_at`` is at least 15 minutes old become durable retryable
    failures, oldest first, at most 20 per pass."""

    moment = now or _utcnow()
    cutoff = moment - timedelta(minutes=STALE_DIRECT_JOB_MINUTES)
    candidates = []
    for job in store.backtest_jobs.values():
        if only_job_id is not None and job.get("id") != only_job_id:
            continue
        if job.get("operation_scope") != DIRECT_RUN_SCOPE:
            continue
        if job.get("status") != "running":
            continue
        started_at = _job_started_at(job)
        if started_at is None or started_at > cutoff:
            continue
        candidates.append(job)
    candidates.sort(key=lambda job: (_job_started_at(job) or moment, str(job["id"])))

    reconciled = 0
    for job in candidates[:STALE_DIRECT_JOB_BATCH]:
        job["status"] = "failed"
        job["failure_code"] = STALE_DIRECT_FAILURE_CODE
        job["failure_detail"] = STALE_DIRECT_FAILURE_DETAIL
        job["retryable"] = True
        job["finished_at"] = _iso(moment)
        job["updated_at"] = _iso(moment)
        reconciled += 1
    return reconciled


def _memory_counts(store: Any, *, user_id: str) -> dict[str, int]:
    counts = {
        "user_running": 0,
        "user_queued": 0,
        "global_running": 0,
        "global_queued": 0,
    }
    for job in store.backtest_jobs.values():
        status = job.get("status")
        if status == "running":
            counts["global_running"] += 1
            if job.get("user_id") == user_id:
                counts["user_running"] += 1
        elif status == "queued":
            counts["global_queued"] += 1
            if job.get("user_id") == user_id:
                counts["user_queued"] += 1
    return counts


def admit_backtest_job_memory(
    store: Any,
    *,
    user_id: str,
    operation_scope: str,
    idempotency_key: str,
    identity_hash: str,
    payload_hash: str,
    launch_payload: dict[str, Any],
    initial_status: Literal["queued", "running"],
    conversation_id: str | None = None,
    request_message_id: str | None = None,
    confirmation_message_id: str | None = None,
    execution_metadata: dict[str, Any] | None = None,
    allowance_limits: list[AllowanceWindowInput] | None = None,
    limits: AdmissionLimits | None = None,
    now: datetime | None = None,
) -> AdmissionOutcome:
    """The deterministic in-process twin of the database admission operation."""

    if operation_scope not in (CHAT_RUN_SCOPE, DIRECT_RUN_SCOPE):
        raise ValueError(f"unsupported operation scope: {operation_scope!r}")

    resolved_limits = limits or admission_limits()
    moment = now or _utcnow()
    reservation = (user_id, operation_scope, idempotency_key)

    with store.backtest_admission_lock:
        existing_job_id = store.backtest_job_reservations.get(reservation)
        if existing_job_id is not None:
            job = store.backtest_jobs.get(existing_job_id)
            if job is not None:
                if job.get("identity_hash") == identity_hash:
                    if operation_scope == DIRECT_RUN_SCOPE:
                        reconcile_stale_direct_jobs_memory(
                            store, now=moment, only_job_id=existing_job_id
                        )
                    return AdmissionOutcome(kind="replay", job=dict(job))
                return AdmissionOutcome(kind="conflict")

        allowance_windows = normalize_allowance_windows(
            allowance_limits or [],
            at=moment,
        )
        for window in allowance_windows:
            row = read_memory_usage(
                store.usage_counters,
                user_id=user_id,
                resource=SIMULATION_USAGE_RESOURCE,
                period=window.period,
                at=moment,
                period_start=window.period_start,
            )
            if row is not None and int(row.get("used_count", 0)) >= window.limit:
                return AdmissionOutcome(
                    kind=(
                        "conversion_required"
                        if window.period == "guest_session"
                        else "allowance_exhausted"
                    )
                )

        if operation_scope == DIRECT_RUN_SCOPE:
            reconcile_stale_direct_jobs_memory(store, now=moment)

        counts = _memory_counts(store, user_id=user_id)
        # Direct admissions occupy a running slot immediately, so they must
        # clear the queued and running ceilings at both scopes.
        if operation_scope == DIRECT_RUN_SCOPE:
            user_checks = ("user_running", "user_queued")
            global_checks = ("global_running", "global_queued")
        elif initial_status == "queued":
            user_checks = ("user_queued",)
            global_checks = ("global_queued",)
        else:
            user_checks = ("user_running",)
            global_checks = ("global_running",)

        for boundary in user_checks:
            if counts[boundary] >= getattr(resolved_limits, boundary):
                return AdmissionOutcome(kind="per_user_capacity", retry_after_seconds=15)
        for boundary in global_checks:
            if counts[boundary] >= getattr(resolved_limits, boundary):
                return AdmissionOutcome(kind="global_capacity", retry_after_seconds=15)

        job_id = str(uuid.uuid4())
        job: dict[str, Any] = {
            "id": job_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "request_message_id": request_message_id,
            "confirmation_message_id": confirmation_message_id,
            "operation_scope": operation_scope,
            "idempotency_key": idempotency_key,
            "identity_hash": identity_hash,
            "payload_hash": payload_hash,
            "launch_payload": launch_payload,
            "status": initial_status,
            "priority": "normal",
            "attempts": 0,
            "max_attempts": 1,
            "result_run_id": None,
            "failure_code": None,
            "failure_detail": None,
            "retryable": False,
            "queued_at": _iso(moment),
            "started_at": _iso(moment) if initial_status == "running" else None,
            "finished_at": None,
            "created_at": _iso(moment),
            "updated_at": _iso(moment),
            "execution_metadata": execution_metadata or {},
        }
        store.backtest_jobs[job_id] = job
        store.backtest_job_reservations[reservation] = job_id
        if allowance_windows:
            settle_memory_usage(
                store.usage_counters,
                user_id=user_id,
                resource=SIMULATION_USAGE_RESOURCE,
                limits=allowance_windows,
                at=moment,
            )
        return AdmissionOutcome(kind="admitted", job=dict(job))


def finalize_direct_job_memory(
    store: Any,
    *,
    job_id: str,
    status: Literal["succeeded", "failed"],
    result_run_id: str | None = None,
    failure_code: str | None = None,
    failure_detail: str | None = None,
    retryable: bool = False,
) -> dict[str, Any] | None:
    moment = _utcnow()
    with store.backtest_admission_lock:
        job = store.backtest_jobs.get(job_id)
        if job is None or job.get("status") != "running":
            return None
        job["status"] = status
        job["result_run_id"] = result_run_id
        job["failure_code"] = failure_code
        job["failure_detail"] = failure_detail
        job["retryable"] = retryable
        job["finished_at"] = _iso(moment)
        job["updated_at"] = _iso(moment)
        return dict(job)

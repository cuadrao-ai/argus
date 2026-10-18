from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from loguru import logger

from argus.api import state as api_state
from argus.api.chat.backtest_jobs import (
    fail_job_without_task_run,
    should_fail_stale_job_without_task_run,
)
from argus.api.chat.confirmation import public_confirmation_projection
from argus.api.chat.research_jobs import RESEARCH_OPERATION_SCOPE
from argus.api.conversation_surface import (
    refuse_business_under_grant,
    refuse_closed_chat,
)
from argus.api.dependencies import current_user, problem
from argus.api.guest_access import account_context, client_identity
from argus.api.memory_ownership import memory_object_visible
from argus.api.message_store import owned_conversation_message
from argus.api.schemas import (
    BacktestJob,
    BacktestJobResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    Message,
    User,
)
from argus.domain import backtest_admission
from argus.domain.backtest_admission import CHAT_RUN_SCOPE, chat_run_identity_hash
from argus.domain.backtest_finalization import (
    BacktestFinalizationError,
    stable_backtest_run_id,
)
from argus.domain.supabase_gateway import QuotaExceededError
from argus.domain.usage_limits import (
    GUEST_SIMULATION_VISITOR_LIMITS,
    SIMULATION_ALLOWANCE_LIMITS,
    SIMULATION_USAGE_RESOURCE,
    allowance_windows,
)
from argus.domain.visitor_usage import (
    settle_visitor_usage,
    visitor_key_for,
    visitor_within_limits,
)

router = APIRouter(prefix="/api/v1", tags=["backtests"])


def _reconcile_stale_owner_job(
    *,
    gateway: Any,
    user_id: str,
    job: dict[str, Any],
) -> dict[str, Any]:
    if not should_fail_stale_job_without_task_run(job):
        return job
    return fail_job_without_task_run(gateway=gateway, user_id=user_id, job=job)


@router.post("/backtests/run", response_model=BacktestRunResponse)
def run_backtest(
    payload: BacktestRunRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),  # noqa: B008
) -> BacktestRunResponse:
    # Chat is the owner's: a chosen client grant is refused on a Business conversation.
    refuse_business_under_grant(
        request, user_id=user.id, conversation_id=payload.conversation_id
    )
    endpoint = "/api/v1/backtests/run"
    clean_idempotency_key = _clean_required_idempotency_key(
        request=request,
        idempotency_key=idempotency_key,
    )

    if payload.conversation_id:
        conversation = None
        if api_state.supabase_gateway is not None:
            conversation = api_state.supabase_gateway.get_conversation(
                user_id=user.id,
                conversation_id=payload.conversation_id,
            )
        else:
            owner_id = api_state.store.conversation_owners.get(payload.conversation_id)
            if owner_id in {None, user.id}:
                conversation = api_state.store.conversations.get(payload.conversation_id)
        if conversation is None:
            raise problem(
                request,
                status_code=404,
                code="not_found",
                title="Not Found",
                detail="Conversation not found.",
            )
        refuse_closed_chat(request, conversation.surface)

    data = payload.model_dump(exclude_none=True)
    if payload.strategy_id:
        strategy = None
        if api_state.supabase_gateway is not None:
            strategy = api_state.supabase_gateway.get_strategy(
                user_id=user.id,
                strategy_id=payload.strategy_id,
            )
        else:
            if memory_object_visible(
                owner_map=api_state.store.strategy_owners,
                object_id=payload.strategy_id,
                user_id=user.id,
            ):
                strategy = api_state.store.strategies.get(payload.strategy_id)

        if not strategy:
            raise problem(
                request,
                status_code=404,
                code="not_found",
                title="Not Found",
                detail="Strategy not found.",
            )
        strategy_data = strategy.model_dump()
        data = {
            **strategy_data,
            **data,
            "template": strategy.template,
            "asset_class": strategy.asset_class,
            "symbols": data.get("symbols") or strategy.symbols,
            "parameters": strategy.parameters,
            "benchmark_symbol": strategy.benchmark_symbol,
        }
    if not data.get("template"):
        data["template"] = "rsi_mean_reversion"
    from argus.api.backtest_service import (
        create_run_from_payload,
        prepare_run_from_payload,
    )
    from argus.api.chat.evidence import finalize_completed_direct_backtest

    _validate_direct_payload_shape(data, request)
    normalized_payload = backtest_admission.normalize_direct_launch_payload(data)
    identity_hash = backtest_admission.direct_run_identity_hash(
        conversation_id=payload.conversation_id,
        strategy_id=payload.strategy_id,
        normalized_payload=normalized_payload,
    )
    launch_payload_digest = backtest_admission.canonical_hash(normalized_payload)

    # The pre-read only routes around preflight; atomic admission stays the
    # authority for replay/collision races.
    if _direct_reservation_exists(user=user, idempotency_key=clean_idempotency_key):
        decision, job = _admit_direct_run(
            request,
            user=user,
            idempotency_key=clean_idempotency_key,
            identity_hash=identity_hash,
            payload_hash=launch_payload_digest,
            launch_payload=normalized_payload,
            conversation_id=payload.conversation_id,
        )
        if decision == "replay":
            return _replay_direct_job(request, user=user, job=job or {})

    if api_state.supabase_gateway is not None:
        account = account_context(request)
        try:
            if account.kind == "guest":
                # Visitor-keyed: a renewed workspace grants no fresh run.
                if not visitor_within_limits(
                    api_state.supabase_gateway.client,
                    visitor_key=visitor_key_for(client_identity(request)),
                    resource=SIMULATION_USAGE_RESOURCE,
                    limits=list(GUEST_SIMULATION_VISITOR_LIMITS),
                    now=datetime.now(timezone.utc),
                ):
                    raise QuotaExceededError("Quota exceeded for backtest_runs (day)")
            else:
                api_state.supabase_gateway.check_usage_limits(
                    user_id=user.id,
                    resource=SIMULATION_USAGE_RESOURCE,
                    limits=SIMULATION_ALLOWANCE_LIMITS,
                )
        except QuotaExceededError as exc:
            # A duplicate racing the admission that filled the window must
            # still resolve replay/collision first.
            if _direct_reservation_exists(
                user=user, idempotency_key=clean_idempotency_key
            ):
                decision, job = _admit_direct_run(
                    request,
                    user=user,
                    idempotency_key=clean_idempotency_key,
                    identity_hash=identity_hash,
                    payload_hash=launch_payload_digest,
                    launch_payload=normalized_payload,
                    conversation_id=payload.conversation_id,
                )
                if decision == "replay":
                    return _replay_direct_job(request, user=user, job=job or {})
            if account.kind == "guest":
                raise problem(
                    request,
                    status_code=403,
                    code="account_conversion_required",
                    title="Account Required",
                    detail="Sign in before running another simulation.",
                ) from exc
            raise problem(
                request,
                status_code=429,
                code="too_many_requests",
                title="Quota Exceeded",
                detail=str(exc),
                headers={"Retry-After": "60"},
            ) from exc

    prepared_execution = prepare_run_from_payload(data, request)

    decision, job = _admit_direct_run(
        request,
        user=user,
        idempotency_key=clean_idempotency_key,
        identity_hash=identity_hash,
        payload_hash=launch_payload_digest,
        launch_payload=normalized_payload,
        conversation_id=payload.conversation_id,
    )
    if decision == "replay":
        return _replay_direct_job(request, user=user, job=job or {})

    job_id = str((job or {}).get("id") or "").strip()
    execution_identity = f"{endpoint}:{clean_idempotency_key}"
    try:
        run = create_run_from_payload(
            data,
            request,
            user=user,
            user_id=user.id,
            persist_in_memory=False,
            language=user.language,
            run_id=stable_backtest_run_id(user.id, execution_identity),
            prepared_execution=prepared_execution,
        )
        finalized = finalize_completed_direct_backtest(
            user_id=user.id,
            conversation_id=run.conversation_id,
            run=run,
            execution_identity=execution_identity,
            job_id=job_id,
        )
    except BacktestFinalizationError as exc:
        _finalize_direct_job(
            user=user,
            job_id=job_id,
            status="failed",
            failure_code="finalization_failed",
            failure_detail="finalization_failed",
            retryable=True,
            failure_status=503,
        )
        raise problem(
            request,
            status_code=503,
            code="finalization_failed",
            title="Backtest Finalization Failed",
            detail="The backtest finished, but its result could not be saved safely.",
            context={"retryable": True},
            headers={"Retry-After": "1"},
        ) from exc
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        _finalize_direct_job(
            user=user,
            job_id=job_id,
            status="failed",
            failure_code=str(detail.get("code") or "execution_failed"),
            failure_detail=str(detail.get("detail") or "execution_failed"),
            retryable=False,
            failure_status=exc.status_code,
        )
        raise
    except Exception:
        _finalize_direct_job(
            user=user,
            job_id=job_id,
            status="failed",
            failure_code="execution_failed",
            failure_detail="unexpected_error",
            retryable=False,
            failure_status=500,
        )
        raise

    if finalized is None:
        # A reconciled terminal outcome is final; a late success is discarded.
        raise problem(
            request,
            status_code=503,
            code="direct_execution_abandoned",
            title="Backtest Execution Abandoned",
            detail=(
                "This execution ran past the staleness boundary and was "
                "reconciled as abandoned. Start it again with a new "
                "Idempotency-Key."
            ),
            context={"backtest_job_id": job_id, "retryable": True},
        )
    return BacktestRunResponse(run=finalized.run)


def _clean_required_idempotency_key(
    *,
    request: Request,
    idempotency_key: str | None,
) -> str:
    state, key = backtest_admission.validate_idempotency_key(idempotency_key)
    if state == "ok" and key is not None:
        return key
    if state == "invalid":
        raise problem(
            request,
            status_code=422,
            code="validation_error",
            title="Validation Error",
            detail=(
                "Idempotency-Key must be 1-128 visible ASCII characters "
                "with no whitespace."
            ),
        )
    raise problem(
        request,
        status_code=400,
        code="idempotency_key_required",
        title="Idempotency Key Required",
        detail="POST /backtests/run requires an Idempotency-Key header.",
    )


def _validate_direct_payload_shape(data: dict[str, Any], request: Request) -> None:
    """The #229 contract validates and materializes the launch request before
    hashing; invalid shapes reject before admission and consume nothing."""

    from argus.api.backtest_service import (
        ensure_same_asset_or_raise,
        raise_backtest_problem,
    )

    symbols = data.get("symbols") or []
    if not symbols:
        raise problem(
            request,
            status_code=400,
            code="validation_error",
            title="Validation Error",
            detail="Symbol is required.",
        )
    inferred_asset_class, classified_symbols = ensure_same_asset_or_raise(
        symbols, request
    )
    requested_asset_class = data.get("asset_class")
    if requested_asset_class and requested_asset_class != inferred_asset_class:
        raise_backtest_problem(
            request,
            "asset_class_conflict",
            context={
                "requested_asset_class": requested_asset_class,
                "inferred_asset_class": inferred_asset_class,
                "symbols": [entry.symbol for entry in classified_symbols],
            },
        )


def _direct_reservation_exists(*, user: User, idempotency_key: str) -> bool:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        return (
            gateway.get_backtest_job_reservation(
                user_id=user.id,
                operation_scope=backtest_admission.DIRECT_RUN_SCOPE,
                idempotency_key=idempotency_key,
            )
            is not None
        )
    with api_state.store.backtest_admission_lock:
        return (
            user.id,
            backtest_admission.DIRECT_RUN_SCOPE,
            idempotency_key,
        ) in api_state.store.backtest_job_reservations


def _admit_direct_run(
    request: Request,
    *,
    user: User,
    idempotency_key: str,
    identity_hash: str,
    payload_hash: str,
    launch_payload: dict[str, Any],
    conversation_id: str | None,
) -> tuple[str, dict[str, Any] | None]:
    gateway = api_state.supabase_gateway
    account = account_context(request)
    if gateway is not None:
        outcome = gateway.admit_backtest_job(
            user_id=user.id,
            operation_scope=backtest_admission.DIRECT_RUN_SCOPE,
            idempotency_key=idempotency_key,
            identity_hash=identity_hash,
            payload_hash=payload_hash,
            launch_payload=launch_payload,
            initial_status="running",
            conversation_id=conversation_id,
            execution_metadata={
                "source": "api_direct",
                "openrouter_traffic_class": account.kind,
            },
            allowance_limits=allowance_windows(
                account,
                SIMULATION_USAGE_RESOURCE,
            ),
        )
        decision = str(outcome.get("decision") or "")
        job = outcome.get("job") if isinstance(outcome.get("job"), dict) else None
        if account.kind == "guest" and decision == "admitted":
            # Workspace reservation owns replay identity; the visitor row
            # is the cross-renewal bound (best-effort past admission).
            try:
                settle_visitor_usage(
                    gateway.client,
                    visitor_key=visitor_key_for(client_identity(request)),
                    resource=SIMULATION_USAGE_RESOURCE,
                    limits=list(GUEST_SIMULATION_VISITOR_LIMITS),
                )
            except Exception as exc:
                logger.warning(
                    "Visitor simulation settlement failed",
                    error=str(exc),
                    failure_classification="telemetry_only",
                )
    else:
        memory_outcome = backtest_admission.admit_backtest_job_memory(
            api_state.store,
            user_id=user.id,
            operation_scope=backtest_admission.DIRECT_RUN_SCOPE,
            idempotency_key=idempotency_key,
            identity_hash=identity_hash,
            payload_hash=payload_hash,
            launch_payload=launch_payload,
            initial_status="running",
            conversation_id=conversation_id,
            execution_metadata={
                "source": "api_direct",
                "openrouter_traffic_class": account.kind,
            },
            allowance_limits=allowance_windows(
                account,
                SIMULATION_USAGE_RESOURCE,
            ),
        )
        decision = memory_outcome.kind
        job = memory_outcome.job

    if decision in ("admitted", "replay"):
        return decision, job
    if decision == "conflict":
        raise problem(
            request,
            status_code=409,
            code="idempotency_conflict",
            title="Idempotency Conflict",
            detail=(
                "This Idempotency-Key is already reserved for a different "
                "request. Use a new key for a new execution."
            ),
        )
    if decision == "allowance_exhausted":
        raise problem(
            request,
            status_code=429,
            code="too_many_requests",
            title="Quota Exceeded",
            detail="Simulation allowance exhausted for the current window.",
            headers={"Retry-After": "60"},
        )
    if decision == "conversion_required":
        raise problem(
            request,
            status_code=403,
            code="account_conversion_required",
            title="Account Required",
            detail="Sign in before running another simulation.",
        )
    if decision == "per_user_capacity":
        raise problem(
            request,
            status_code=429,
            code="backtest_capacity_exceeded",
            title="Backtest Capacity Exceeded",
            detail="Your other simulations are still in progress. Retry shortly.",
            headers={"Retry-After": "15"},
        )
    if decision == "global_capacity":
        raise problem(
            request,
            status_code=503,
            code="backtest_capacity_exceeded",
            title="Backtest Capacity Exceeded",
            detail="Simulation capacity is briefly saturated. Retry shortly.",
            headers={"Retry-After": "15"},
        )
    raise problem(
        request,
        status_code=500,
        code="internal_error",
        title="Internal Error",
        detail="Backtest admission returned an unknown decision.",
    )


def _replay_direct_job(
    request: Request, *, user: User, job: dict[str, Any]
) -> BacktestRunResponse:
    status = str(job.get("status") or "").strip().lower()
    job_id = str(job.get("id") or "").strip()
    if status == "succeeded":
        run_id = str(job.get("result_run_id") or "").strip()
        run = (
            api_state.supabase_gateway.get_backtest_run(user_id=user.id, run_id=run_id)
            if api_state.supabase_gateway is not None
            else api_state.store.backtest_runs.get(run_id)
        )
        if run is not None:
            return BacktestRunResponse(run=run)
        raise problem(
            request,
            status_code=500,
            code="internal_error",
            title="Internal Error",
            detail="Admitted job is succeeded but its Run is unavailable.",
        )
    if status in ("queued", "running"):
        raise problem(
            request,
            status_code=409,
            code="idempotency_in_progress",
            title="Idempotency In Progress",
            detail="This execution is still in progress. Retry shortly.",
            context={"backtest_job_id": job_id},
            headers={"Retry-After": "1"},
        )
    metadata = job.get("execution_metadata")
    failure_status = 503
    if isinstance(metadata, dict):
        recorded = metadata.get("failure_status")
        if isinstance(recorded, int) and 400 <= recorded <= 599:
            failure_status = recorded
    raise problem(
        request,
        status_code=failure_status,
        code=str(job.get("failure_code") or "execution_failed"),
        title="Backtest Execution Failed",
        detail=str(job.get("failure_detail") or "execution_failed"),
        context={"retryable": bool(job.get("retryable"))},
        headers={"Retry-After": "1"} if job.get("retryable") else None,
    )


def _finalize_direct_job(
    *,
    user: User,
    job_id: str,
    status: str,
    result_run_id: str | None = None,
    failure_code: str | None = None,
    failure_detail: str | None = None,
    retryable: bool = False,
    failure_status: int | None = None,
) -> dict[str, Any] | None:
    if not job_id:
        return None
    gateway = api_state.supabase_gateway
    if gateway is not None:
        metadata: dict[str, Any] | None = None
        if failure_status is not None:
            job = gateway.get_backtest_job(user_id=user.id, job_id=job_id) or {}
            metadata = dict(job.get("execution_metadata") or {})
            metadata["failure_status"] = failure_status
        return gateway.finalize_direct_backtest_job(
            user_id=user.id,
            job_id=job_id,
            status=status,
            result_run_id=result_run_id,
            failure_code=failure_code,
            failure_detail=failure_detail,
            retryable=retryable,
            execution_metadata=metadata,
        )
    with api_state.store.backtest_admission_lock:
        job = api_state.store.backtest_jobs.get(job_id)
        if job is not None and failure_status is not None:
            metadata = dict(job.get("execution_metadata") or {})
            metadata["failure_status"] = failure_status
            job["execution_metadata"] = metadata
    return backtest_admission.finalize_direct_job_memory(
        api_state.store,
        job_id=job_id,
        status=status,  # type: ignore[arg-type]
        result_run_id=result_run_id,
        failure_code=failure_code,
        failure_detail=failure_detail,
        retryable=retryable,
    )


@router.get(
    "/backtest-jobs/by-action/{confirmation_id}",
    response_model=BacktestJobResponse,
)
def get_backtest_job_by_action(
    confirmation_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> BacktestJobResponse:
    gateway = api_state.supabase_gateway
    if gateway is None:
        raise _by_action_internal_error(request)

    try:
        job = gateway.get_backtest_job_reservation(
            user_id=user.id,
            operation_scope=CHAT_RUN_SCOPE,
            idempotency_key=confirmation_id,
        )
    except Exception:
        raise _by_action_internal_error(request) from None
    if not job:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="Backtest job not found.",
        )

    launch_payload_hash = _linked_confirmation_launch_hash(
        request=request,
        gateway=gateway,
        user_id=user.id,
        confirmation_id=confirmation_id,
        job=job,
    )
    expected_identity_hash = chat_run_identity_hash(
        conversation_id=str(job.get("conversation_id") or ""),
        confirmation_id=confirmation_id,
        launch_payload_hash=launch_payload_hash,
    )
    if (
        job.get("identity_hash") != expected_identity_hash
        or job.get("payload_hash") != launch_payload_hash
    ):
        raise problem(
            request,
            status_code=409,
            code="idempotency_conflict",
            title="Idempotency Conflict",
            detail="This action identity is already linked to different inputs.",
        )

    job = _reconcile_stale_owner_job(
        gateway=gateway,
        user_id=user.id,
        job=job,
    )
    return _backtest_job_response(
        request=request,
        gateway=gateway,
        user_id=user.id,
        job=job,
        require_succeeded_run=True,
    )


@router.get("/backtest-jobs/{job_id}", response_model=BacktestJobResponse)
def get_backtest_job(
    job_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> BacktestJobResponse:
    if api_state.supabase_gateway is None:
        raise problem(
            request,
            status_code=500,
            code="internal_error",
            title="Internal Error",
            detail="Supabase persistence is required for backtest job status.",
        )

    job = api_state.supabase_gateway.get_backtest_job(user_id=user.id, job_id=job_id)
    if not job:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="Backtest job not found.",
        )
    job = _reconcile_stale_owner_job(
        gateway=api_state.supabase_gateway,
        user_id=user.id,
        job=job,
    )
    return _backtest_job_response(
        request=request,
        gateway=api_state.supabase_gateway,
        user_id=user.id,
        job=job,
        require_succeeded_run=False,
    )


@router.get("/backtests/{run_id}", response_model=BacktestRunResponse)
def get_backtest(
    run_id: str,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> BacktestRunResponse:
    run = (
        api_state.supabase_gateway.get_backtest_run(user_id=user.id, run_id=run_id)
        if api_state.supabase_gateway is not None
        else api_state.store.backtest_runs.get(run_id)
    )
    if not run:
        raise problem(
            request,
            status_code=404,
            code="not_found",
            title="Not Found",
            detail="Backtest run not found.",
        )
    # Chat is the owner's: a run of a Business conversation is refused under a chosen grant.
    refuse_business_under_grant(
        request, user_id=user.id, conversation_id=run.conversation_id
    )
    return BacktestRunResponse(run=run)


def _result_readout_from_job(job: dict[str, object]) -> str | None:
    execution_metadata = job.get("execution_metadata")
    if not isinstance(execution_metadata, dict):
        return None
    workflow_metadata = execution_metadata.get("workflow_backtest")
    if not isinstance(workflow_metadata, dict):
        return None
    result_readout = workflow_metadata.get("result_readout")
    if not isinstance(result_readout, str):
        return None
    normalized = result_readout.strip()
    return normalized or None


def _result_readout_metadata_from_job(job: dict[str, object]) -> dict[str, Any]:
    execution_metadata = job.get("execution_metadata")
    if not isinstance(execution_metadata, dict):
        return {}
    workflow_metadata = execution_metadata.get("workflow_backtest")
    if not isinstance(workflow_metadata, dict):
        return {}
    metadata: dict[str, Any] = {}
    source = workflow_metadata.get("result_readout_source")
    if isinstance(source, str) and source.strip():
        metadata["result_readout_source"] = source.strip()
    fallback_used = workflow_metadata.get("result_readout_fallback_used")
    if isinstance(fallback_used, bool):
        metadata["result_readout_fallback_used"] = fallback_used
    failure_mode = workflow_metadata.get("result_readout_failure_mode")
    if isinstance(failure_mode, str) and failure_mode.strip():
        metadata["result_readout_failure_mode"] = failure_mode.strip()
    next_experiments = workflow_metadata.get("next_experiments")
    if isinstance(next_experiments, dict):
        metadata["next_experiments"] = next_experiments
    return metadata


def _linked_confirmation_launch_hash(
    *,
    request: Request,
    gateway: Any,
    user_id: str,
    confirmation_id: str,
    job: dict[str, object],
) -> str:
    conversation_id = job.get("conversation_id")
    confirmation_message_id = job.get("confirmation_message_id")
    if (
        job.get("operation_scope") != CHAT_RUN_SCOPE
        or job.get("idempotency_key") != confirmation_id
        or not isinstance(conversation_id, str)
        or not conversation_id
        or not isinstance(confirmation_message_id, str)
        or not confirmation_message_id
    ):
        raise _by_action_internal_error(request)

    try:
        message = gateway.get_message(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=confirmation_message_id,
        )
    except Exception:
        raise _by_action_internal_error(request) from None
    if (
        message is None
        or message.id != confirmation_message_id
        or message.conversation_id != conversation_id
        or message.role != "assistant"
        or not isinstance(message.metadata, dict)
    ):
        raise _by_action_internal_error(request)

    card = message.metadata.get("confirmation_card")
    if not isinstance(card, dict) or card.get("confirmation_id") != confirmation_id:
        raise _by_action_internal_error(request)

    launch_payload_hash = card.get("canonical_launch_payload_hash")
    if not _is_full_payload_hash(launch_payload_hash):
        raise _by_action_internal_error(request)
    active_reference = message.metadata.get("active_confirmation_reference")
    if not isinstance(active_reference, dict):
        raise _by_action_internal_error(request)
    reference_metadata = active_reference.get("metadata")
    if (
        active_reference.get("artifact_kind") != "confirmation"
        or active_reference.get("artifact_id") != confirmation_id
        or not isinstance(reference_metadata, dict)
        or reference_metadata.get("canonical_launch_payload_hash") != launch_payload_hash
    ):
        raise _by_action_internal_error(request)
    return str(launch_payload_hash)


def _is_full_payload_hash(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _backtest_job_response(
    *,
    request: Request,
    gateway: Any,
    user_id: str,
    job: dict[str, object],
    require_succeeded_run: bool,
) -> BacktestJobResponse:
    run = None
    result_run_id = job.get("result_run_id")
    if (
        job.get("status") == "succeeded"
        and isinstance(result_run_id, str)
        and result_run_id
    ):
        try:
            run = gateway.get_backtest_run(
                user_id=user_id,
                run_id=result_run_id,
            )
        except Exception:
            if require_succeeded_run:
                raise _by_action_internal_error(request) from None
            raise
    if job.get("status") == "succeeded" and require_succeeded_run:
        if (
            run is None
            or run.id != result_run_id
            or run.conversation_id != job.get("conversation_id")
        ):
            raise _by_action_internal_error(request)
    readout = _result_readout_from_job(job) if run is not None else None
    readout_metadata = _result_readout_metadata_from_job(job) if run is not None else {}
    if run is not None:
        from argus.domain.result_readout_content import stored_readout_metadata

        readout_metadata.update(stored_readout_metadata(run.conversation_result_card))
    # A decoration on the status report, never a precondition for it: a
    # transient messages read failure must not turn a finished job into a 500.
    result_message = _research_result_message(user_id=user_id, job=job)
    try:
        return BacktestJobResponse(
            job=BacktestJob.model_validate(job),
            run=run,
            result_message=result_message,
            result_readout=readout,
            **readout_metadata,
        )
    except Exception:
        if require_succeeded_run:
            raise _by_action_internal_error(request) from None
        raise


_TERMINAL_RESEARCH_STATUSES = frozenset({"succeeded", "failed", "canceled", "expired"})


def _research_result_message(
    *,
    user_id: str,
    job: Mapping[str, object],
) -> Message | None:
    """The message a terminal research job produced (answer or failure note).

    Projected like every transcript message, so the in-place paint and the
    reloaded transcript carry the same shape and the same redactions.
    """
    if (
        job.get("operation_scope") != RESEARCH_OPERATION_SCOPE
        or job.get("status") not in _TERMINAL_RESEARCH_STATUSES
    ):
        return None
    conversation_id = job.get("conversation_id")
    metadata = job.get("execution_metadata")
    message_id = (
        metadata.get("research_result_message_id")
        if isinstance(metadata, Mapping)
        else None
    )
    if not isinstance(conversation_id, str) or not isinstance(message_id, str):
        return None
    try:
        message = owned_conversation_message(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Research result message read failed; job status served without it",
            job_id=job.get("id"),
            error=str(exc),
        )
        return None
    if message is None:
        return None
    return message.model_copy(
        update={"metadata": public_confirmation_projection(message.metadata)}
    )


def _by_action_internal_error(request: Request) -> HTTPException:
    return problem(
        request,
        status_code=500,
        code="internal_error",
        title="Internal Error",
        detail="Backtest job state is inconsistent.",
    )

"""Thorough research through the existing job lifecycle.

Chat never hangs on a thorough run: the turn ends with a queued job envelope,
the provider works in background mode, and an in-process poller finalizes by
persisting the answer as an ordinary assistant message and marking the job
succeeded. The job row is the same ``backtest_jobs`` lifecycle that serves
backtests, under ``operation_scope = 'chat.research'``; no second progress
mechanism exists. A process loss leaves the row for the existing stale-job
scan, which fails it honestly.

Dev memory persistence has no job endpoint, so the thorough shape degrades to
a synchronous call there; production always takes the background path.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Coroutine
from typing import Any

from loguru import logger

from argus.api import state as api_state
from argus.api.chat.backtest_job_envelopes import public_backtest_job_payload
from argus.api.chat.research_evidence import record_research_turn_evidence
from argus.api.chat.research_tool_results import (
    research_tool_card_for_completion,
    with_research_tool_binding,
)
from argus.domain.answer_dossiers import ANSWER_REQUEST_MESSAGE_KEY

# Re-exported: the scope literal is owned by the settlement rule the SQL is
# rendered from.
from argus.domain.job_settlement import RESEARCH_OPERATION_SCOPE
from argus.domain.research.admission import (
    ResearchCapacityExhausted,
    admitted_provider_work,
    claim_current_research_attempt,
)
from argus.domain.research.config import (
    BACKGROUND_POLL_INTERVAL_SECONDS,
    background_deadline_seconds,
)
from argus.domain.research.contracts import (
    ResearchPacket,
    ResearchUnavailableError,
    ResearchUsage,
)
from argus.domain.research.credentials import perplexity_api_key
from argus.domain.research.perplexity_agent import PerplexityAgentClient
from argus.domain.tool_job_binding import ToolJobBinding

# Keep strong references so in-flight pollers never get garbage collected.
_POLLER_TASKS: set[asyncio.Task[Any]] = set()


def retain_research_work(
    work: Coroutine[Any, Any, Any], *, name: str
) -> asyncio.Task[Any]:
    """Research completion outlives the request that admitted it."""
    task = asyncio.create_task(work, name=name)
    _POLLER_TASKS.add(task)
    task.add_done_callback(_POLLER_TASKS.discard)
    return task


def _client() -> PerplexityAgentClient | None:
    api_key = perplexity_api_key()
    if not api_key:
        return None
    return PerplexityAgentClient(api_key)


def apply_research_job_request(
    runtime_result: dict[str, Any],
    *,
    user_id: str,
    conversation_id: str,
    request_message_id: str | None,
    request_id: str | None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    tool_artifact_id: str | None = None,
    tool_arguments: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Consume a typed research job request from the runtime result.

    Returns the public job payload for the background path. The synchronous
    dev fallback, a lookup that failed and the failure note mutate
    ``runtime_result`` in place so the stream and metadata carry the finalized
    artifacts, and return None.
    """
    from argus.agent_runtime.research_answer import (
        compose_completed_research,
        research_capacity_exhausted_for_job,
        research_failure_note,
        store_research_packet_for_job,
    )
    from argus.agent_runtime.research_grounded import research_lookup_failure_for_job

    job_request = runtime_result.pop("research_job_request", None)
    if not isinstance(job_request, dict):
        return None
    job_request = with_research_tool_binding(
        job_request,
        call_id=tool_call_id,
        tool_name=tool_name,
        artifact_id=tool_artifact_id,
        arguments=tool_arguments,
    )
    try:
        job, sync_packet = start_research_job(
            job_request=job_request,
            user_id=user_id,
            conversation_id=conversation_id,
            request_message_id=request_message_id,
            request_id=request_id,
        )
    except ResearchCapacityExhausted as exc:
        composed = research_capacity_exhausted_for_job(
            job_request,
            guest_allowance_exhausted=exc.admission.guest_exhausted,
            registered_allowance_exhausted=exc.admission.registered_exhausted,
        )
        runtime_result["assistant_response"] = composed["answer"]
        runtime_result["research"] = composed["research"]
        _attach_completed_tool_card(runtime_result, job_request)
        return None
    except ResearchUnavailableError as exc:
        # No job was started here: the turn ends on the lookup recovery the
        # inline path takes, retryable when the failure is. A submission whose
        # answer was lost may already have started a billing run, so the client
        # marks it not retryable and records the attempt as unpriced.
        runtime_result.update(research_lookup_failure_for_job(job_request, failure=exc))
        _attach_completed_tool_card(
            runtime_result, job_request, failure_code="research_failed"
        )
        return None
    if job is not None:
        return job
    if sync_packet is not None:
        composed = compose_completed_research(job_request=job_request, packet=sync_packet)
        store_research_packet_for_job(job_request, sync_packet, composed)
        runtime_result["assistant_response"] = composed["answer"]
        runtime_result["research"] = composed["research"]
        for key in ("next_experiments", "next_steps", "calculation_offer"):
            if composed.get(key) is not None:
                runtime_result[key] = composed[key]
        _attach_completed_tool_card(runtime_result, job_request)
        _attach_computed_answer(runtime_result, composed.get("computed"))
        _attach_pending_question(runtime_result, composed.get("question"))
        return None
    runtime_result["assistant_response"] = research_failure_note(
        str(job_request.get("language") or "en")
    )
    _attach_completed_tool_card(
        runtime_result, job_request, failure_code="research_failed"
    )
    return None


def _attach_completed_tool_card(
    patch: dict[str, Any], job_request: dict[str, Any], *, failure_code: str | None = None
) -> None:
    card = research_tool_card_for_completion(
        job_request, patch, failure_code=failure_code
    )
    if card is not None:
        patch["tool_result_cards"] = [card]


def _attach_computed_answer(patch: dict[str, Any], computed: Any) -> None:
    """A thorough answer's computed calculation joins its research card, with
    the prose template a recompute re-renders."""
    from argus.agent_runtime.answer_calculation import (
        ANSWER_ASSUMPTIONS_KEY,
        ANSWER_TEMPLATE_KEY,
    )
    from argus.api.chat.tool_results import computation_marker

    if not isinstance(computed, dict):
        return
    payload = computed.get("final_response_payload") or {}
    cards = list(payload.get("tool_result_cards") or [])
    if not cards:
        return
    patch["tool_result_cards"] = [*(patch.get("tool_result_cards") or []), *cards]
    marker = computation_marker(patch["tool_result_cards"])
    if marker:
        patch["computation"] = marker
    if computed.get(ANSWER_TEMPLATE_KEY) is not None:
        patch[ANSWER_TEMPLATE_KEY] = computed[ANSWER_TEMPLATE_KEY]
    if computed.get(ANSWER_ASSUMPTIONS_KEY):
        patch[ANSWER_ASSUMPTIONS_KEY] = computed[ANSWER_ASSUMPTIONS_KEY]


def _attach_pending_question(patch: dict[str, Any], question: Any) -> None:
    """A thorough answer that asks for a figure only the user knows waits for
    the reply that completes its calculation."""
    if not isinstance(question, dict):
        return
    for key in ("requested_field", "clarification"):
        if question.get(key) is not None:
            patch[key] = question[key]
    patch["last_stage_outcome"] = "await_user_reply"


def start_research_job(
    *,
    job_request: dict[str, Any],
    user_id: str,
    conversation_id: str,
    request_message_id: str | None,
    request_id: str | None,
) -> tuple[dict[str, Any] | None, ResearchPacket | None]:
    """Submit the background run and create the queued job row.

    Returns ``(public_job_payload, None)`` on the background path,
    ``(None, packet)`` for the synchronous dev fallback, and ``(None, None)``
    when the job row could not be written. A provider that cannot take the run
    raises ``ResearchUnavailableError``.
    """
    from argus.agent_runtime.research_answer import (
        research_prompt_for_job,
        retrieval_spec_for_job,
    )

    client = _client()
    if client is None:
        raise ResearchUnavailableError("not_configured")
    spec = retrieval_spec_for_job(job_request)
    prompt = research_prompt_for_job(job_request)
    if api_state.supabase_gateway is None:
        # Dev memory persistence has no durable job surface; run the same
        # documented configuration synchronously instead of inventing one.
        admission = claim_current_research_attempt()
        if not admission.available:
            raise ResearchCapacityExhausted(admission)
        try:
            sync_spec = spec.model_copy(update={"timeout_seconds": 110.0})
            with admitted_provider_work():
                packet = client.run_research(prompt, sync_spec)
        except ResearchUnavailableError as exc:
            logger.warning(
                "Synchronous thorough research failed"
                f" reason={exc.reason} status={exc.status} detail={exc.detail or ''}"
            )
            raise
        return None, packet
    idempotency_key = _research_job_identity(job_request, request_message_id)
    replay = _replayed_research_job(
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    if replay is not None:
        # The same request message already admitted a research job. Its row is
        # the answer whatever its status: a live row has its own poller, a
        # terminal row already names its message. Spawning a second poller
        # would finalize a second answer nobody links to, and submitting
        # first would spend provider budget on a run that could not land.
        return public_backtest_job_payload(replay), None
    admission = claim_current_research_attempt()
    if not admission.available:
        raise ResearchCapacityExhausted(admission)
    try:
        with admitted_provider_work():
            background_id = client.submit_background(prompt, spec)
    except ResearchUnavailableError as exc:
        logger.warning(
            "Research background submission failed"
            f" reason={exc.reason} status={exc.status} detail={exc.detail or ''}"
        )
        raise
    launch_payload = {
        "schema_version": "research_job_launch/v1",
        "research_request": job_request,
        "perplexity_background_id": background_id,
    }
    payload_hash = (
        "sha256:"
        + hashlib.sha256(json.dumps(launch_payload, sort_keys=True).encode()).hexdigest()
    )
    try:
        job = api_state.supabase_gateway.create_backtest_job(
            user_id=user_id,
            conversation_id=conversation_id,
            payload_hash=payload_hash,
            launch_payload=launch_payload,
            request_message_id=request_message_id,
            idempotency_key=idempotency_key,
            execution_metadata={
                "capability_class": job_request.get("capability_class"),
                "perplexity_background_id": background_id,
            },
            operation_scope=RESEARCH_OPERATION_SCOPE,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Research job row creation failed", error=str(exc))
        return None, None
    _spawn_poller(
        job_id=str(job.get("id")),
        background_id=background_id,
        job_request=job_request,
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        request_message_id=request_message_id,
    )
    return public_backtest_job_payload(job), None


def _replayed_research_job(
    *,
    user_id: str,
    idempotency_key: str | None,
) -> dict[str, Any] | None:
    gateway = api_state.supabase_gateway
    if gateway is None or not idempotency_key:
        return None
    try:
        return gateway.find_backtest_job_by_idempotency_key(
            user_id=user_id,
            operation_scope=RESEARCH_OPERATION_SCOPE,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Research job replay lookup failed", error=str(exc))
        return None


def _research_job_identity(
    job_request: dict[str, Any], request_message_id: str | None
) -> str | None:
    binding = job_request.get("tool_binding")
    if not isinstance(binding, dict):
        return request_message_id
    if not request_message_id:
        raise ValueError("A registered research job requires a durable request message")
    material = json.dumps([request_message_id, binding["call"]["call_id"]])
    return "research-tool:" + hashlib.sha256(material.encode()).hexdigest()


def _spawn_poller(
    *,
    job_id: str,
    background_id: str,
    job_request: dict[str, Any],
    user_id: str,
    conversation_id: str,
    request_id: str | None,
    request_message_id: str | None = None,
) -> None:
    retain_research_work(
        _poll_and_finalize(
            job_id=job_id,
            background_id=background_id,
            job_request=job_request,
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=request_id,
            request_message_id=request_message_id,
        ),
        name=f"research-job-{job_id}",
    )


async def _poll_and_finalize(
    *,
    job_id: str,
    background_id: str,
    job_request: dict[str, Any],
    user_id: str,
    conversation_id: str,
    request_id: str | None,
    request_message_id: str | None = None,
) -> None:
    from argus.agent_runtime.research_answer import retrieval_spec_for_job

    client = _client()
    if client is None:
        _fail_job(job_id=job_id, user_id=user_id, detail="provider key missing")
        return
    spec = retrieval_spec_for_job(job_request)
    deadline = time.monotonic() + background_deadline_seconds()
    marked_running = False
    try:
        while True:
            await asyncio.sleep(BACKGROUND_POLL_INTERVAL_SECONDS)
            try:
                poll = await asyncio.to_thread(
                    client.poll_background, background_id, spec=spec
                )
            except ResearchUnavailableError as exc:
                # No reason class is provably deterministic from one poll: a
                # 401/403 can be an edge or WAF in front of the provider and a
                # malformed body can be a 200 interstitial, so every reason
                # earns the rest of the deadline and the deadline alone owns
                # giving up.
                if time.monotonic() > deadline:
                    _fail_job(
                        job_id=job_id,
                        user_id=user_id,
                        detail=f"poll: {exc.reason}: {exc.detail or ''}",
                        post_note=True,
                        job_request=job_request,
                        conversation_id=conversation_id,
                    )
                    return
                continue
            if not marked_running and poll.status == "in_progress":
                marked_running = True
                _mark_running(job_id=job_id, user_id=user_id)
            if poll.terminal:
                if poll.status == "completed" and poll.packet is not None:
                    await _finalize_success(
                        job_id=job_id,
                        job_request=job_request,
                        packet=poll.packet,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        request_id=request_id,
                        request_message_id=request_message_id,
                    )
                else:
                    _fail_job(
                        job_id=job_id,
                        user_id=user_id,
                        detail=poll.failure_detail or poll.status,
                        post_note=True,
                        job_request=job_request,
                        conversation_id=conversation_id,
                        request_id=request_id,
                        billed_reason=poll.failure_reason,
                        billed_usage=poll.usage,
                    )
                return
            if time.monotonic() > deadline:
                _fail_job(
                    job_id=job_id,
                    user_id=user_id,
                    detail="background deadline exceeded",
                    post_note=True,
                    job_request=job_request,
                    conversation_id=conversation_id,
                )
                return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Research job poller crashed", job_id=job_id, error=str(exc))
        _fail_job(job_id=job_id, user_id=user_id, detail="poller crash")


def _mark_running(*, job_id: str, user_id: str) -> None:
    gateway = api_state.supabase_gateway
    if gateway is None:
        return
    try:
        gateway.mark_backtest_job_running(user_id=user_id, job_id=job_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Research job running mark skipped", error=str(exc))


# The completion mark is the row's only way out of running once the answer is
# persisted; no scheduled janitor revisits a research row. Retry it, and if it
# still fails, fail the row with the answer linked so the conversation settles
# and the answer still paints.
COMPLETION_MARK_ATTEMPTS = 3
COMPLETION_MARK_RETRY_SECONDS = 2.0


async def _finalize_success(
    *,
    job_id: str,
    job_request: dict[str, Any],
    packet: ResearchPacket,
    user_id: str,
    conversation_id: str,
    request_id: str | None,
    request_message_id: str | None = None,
) -> None:
    from argus.agent_runtime.research_answer import (
        compose_completed_research,
        store_research_packet_for_job,
    )

    composed = compose_completed_research(job_request=job_request, packet=packet)
    store_research_packet_for_job(job_request, packet, composed)
    metadata: dict[str, Any] = {
        "conversation_mode": "guide",
        "research": composed["research"],
    }
    card = research_tool_card_for_completion(
        job_request,
        {"assistant_response": composed["answer"], "research": composed["research"]},
    )
    if card is not None:
        metadata["tool_result_cards"] = [card]
    _attach_computed_answer(metadata, composed.get("computed"))
    _attach_pending_question(metadata, composed.get("question"))
    for key in ("next_experiments", "next_steps", "calculation_offer"):
        if composed.get(key) is not None:
            metadata[key] = composed[key]
    if request_message_id:
        # The answer can land after later turns, so it names the message that
        # asked instead of leaving readers to infer it from time.
        metadata[ANSWER_REQUEST_MESSAGE_KEY] = request_message_id
    message = await persist_research_job_answer(
        job_id=job_id,
        user_id=user_id,
        conversation_id=conversation_id,
        content=composed["answer"],
        metadata=metadata,
    )
    if message is None:
        return
    record_research_turn_evidence(
        research=composed["research"],
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message.id,
        request_id=request_id,
        tool_call_id=card["call_id"] if card is not None else None,
    )


async def persist_research_job_answer(
    *,
    job_id: str,
    user_id: str,
    conversation_id: str,
    content: str,
    metadata: dict[str, Any],
) -> Any:
    """Persist the complete answer before the shared job settlement can succeed."""
    from argus.api.message_store import create_message

    try:
        message = create_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata=metadata,
            settle_usage=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Research result message persistence failed",
            job_id=job_id,
            error=str(exc),
        )
        _fail_job(job_id=job_id, user_id=user_id, detail="result persistence failed")
        return None
    await _mark_completed(job_id=job_id, user_id=user_id, message_id=message.id)
    return message


async def _mark_completed(*, job_id: str, user_id: str, message_id: str) -> None:
    gateway = api_state.supabase_gateway
    if gateway is None:
        return
    for attempt in range(1, COMPLETION_MARK_ATTEMPTS + 1):
        try:
            gateway.complete_research_job(
                user_id=user_id,
                job_id=job_id,
                execution_metadata={"research_result_message_id": message_id},
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Research job completion mark failed",
                job_id=job_id,
                attempt=attempt,
                error=str(exc),
            )
            if attempt < COMPLETION_MARK_ATTEMPTS:
                await asyncio.sleep(COMPLETION_MARK_RETRY_SECONDS)
    _fail_job(
        job_id=job_id,
        user_id=user_id,
        detail="completion mark failed",
        result_message_id=message_id,
    )


def _fail_job(
    *,
    job_id: str,
    user_id: str,
    detail: str,
    post_note: bool = False,
    job_request: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    result_message_id: str | None = None,
    request_id: str | None = None,
    billed_reason: str | None = None,
    billed_usage: ResearchUsage | None = None,
) -> None:
    # The note is persisted first so the failed row can name it: a terminal
    # research row's message, answer or note, is served as the job's
    # result_message and painted in place.
    message_id = result_message_id
    if post_note and conversation_id and job_request is not None:
        message_id = _persist_failure_note(
            job_id=job_id,
            user_id=user_id,
            conversation_id=conversation_id,
            job_request=job_request,
        )
    if billed_usage is not None and job_request is not None:
        # A completed run whose answer could not be read was still billed.
        # The note carries no sidecar, so the ledger is told directly rather
        # than through a turn that has none.
        from argus.agent_runtime.research_answer import (
            research_billed_failure_evidence,
        )

        binding = job_request.get("tool_binding")
        record_research_turn_evidence(
            research=research_billed_failure_evidence(
                job_request,
                reason=billed_reason or "malformed_response",
                usage=billed_usage,
            ),
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_id=request_id,
            tool_call_id=(
                ToolJobBinding.model_validate(binding).call.call_id
                if binding is not None
                else None
            ),
        )
    gateway = api_state.supabase_gateway
    if gateway is None:
        return
    try:
        gateway.mark_backtest_job_failed(
            user_id=user_id,
            job_id=job_id,
            failure_code="research_failed",
            failure_detail=detail[:500],
            retryable=False,
            execution_metadata=(
                {"research_result_message_id": message_id} if message_id else None
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Research job failure mark failed; the row stays active until an"
            " operator settles it",
            job_id=job_id,
            error=str(exc),
        )


def _persist_failure_note(
    *,
    job_id: str,
    user_id: str,
    conversation_id: str,
    job_request: dict[str, Any],
) -> str | None:
    from argus.agent_runtime.research_answer import research_failure_note
    from argus.api.message_store import create_message

    card = research_tool_card_for_completion(
        job_request, {}, failure_code="research_failed"
    )
    metadata: dict[str, Any] = {"conversation_mode": "guide"}
    if card is not None:
        metadata["tool_result_cards"] = [card]
    try:
        note = create_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=research_failure_note(str(job_request.get("language") or "en")),
            metadata=metadata,
            settle_usage=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Research failure note persistence failed",
            job_id=job_id,
            error=str(exc),
        )
        return None
    return note.id

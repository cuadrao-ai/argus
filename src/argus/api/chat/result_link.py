"""Linking an in-process run to its job, and obeying what the write did.

The consumption guard's publication leg lives here: the link write is
gated by the lifecycle statement inside the gateways, this module reads
what actually landed, and the publisher derives from the outcome instead
of assuming success. A refused link withholds the result so a restored,
editable card can never sit beside a published one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from argus.agent_runtime.recovery_messages import recovery_message, recovery_state
from argus.api.artifact_presentation import reader_run
from argus.api.chat.backtest_jobs import (
    REAL_BACKTEST_JOB_KIND,
    _utcnow_iso,
    backtest_workflow_execution_enabled,
    current_backtest_job_shadow_context,
)
from argus.domain.backtest_message_projection import result_fact_bank

RESULT_PUBLICATION_KEYS = (
    "result_card",
    "latest_run_id",
    "result_run_id",
    "result_strategy_id",
    "result_conversation_id",
    "result_fact_bank",
    "context_packets",
    "next_experiments",
    "run",
    "final_response_payload",
)


@dataclass(frozen=True)
class ResultLinkOutcome:
    """What the result-link write actually did, for the publisher to obey.

    Publication of an in-process run derives from this outcome: a link the
    lifecycle statement refused must not become a visible result, because
    the job it belongs to is dead and its card may already be restored.
    ``job`` carries the standing row when the gateway returned one.
    """

    publishable: bool
    reason: str
    job: dict[str, Any] | None = None


def link_shadow_backtest_job_result(
    *,
    user_id: str,
    run_id: str,
    gateway: Any | None,
    dev_memory_fallback_enabled: bool,
) -> ResultLinkOutcome:
    context = current_backtest_job_shadow_context()
    if context is None or context.created_job_id is None:
        return ResultLinkOutcome(publishable=True, reason="no_job")
    if gateway is None:
        if dev_memory_fallback_enabled:
            return ResultLinkOutcome(publishable=True, reason="no_gateway")
        raise RuntimeError("Supabase persistence is required to link backtest jobs.")

    mark_succeeded = not context.workflow_dispatch_started
    linked_at = _utcnow_iso()
    metadata: dict[str, Any] = {
        "api_in_process_result": {
            "result_run_id": run_id,
            "linked_at": linked_at,
            "marked_succeeded": mark_succeeded,
        }
    }
    if context.workflow_task_run_id:
        metadata["workflow_dispatch"] = {
            "task_run_id": context.workflow_task_run_id,
            "result_linked_at": linked_at,
        }
    if context.workflow_dispatch_error:
        metadata["workflow_dispatch_error"] = context.workflow_dispatch_error

    try:
        if context.workflow_dispatch_started and backtest_workflow_execution_enabled():
            metadata["api_in_process_result"]["job_result_column_owned_by"] = (
                REAL_BACKTEST_JOB_KIND
            )
            gateway.merge_backtest_job_execution_metadata(
                user_id=user_id,
                job_id=context.created_job_id,
                execution_metadata=metadata,
            )
            return ResultLinkOutcome(publishable=True, reason="metadata_only")
        linked = gateway.link_backtest_job_result(
            user_id=user_id,
            job_id=context.created_job_id,
            result_run_id=run_id,
            execution_metadata=metadata,
            mark_succeeded=mark_succeeded,
        )
        attached = str(linked.get("result_run_id") or "").strip() == str(run_id)
        if attached:
            if mark_succeeded and str(linked.get("status") or "") != "succeeded":
                logger.warning(
                    "Success finalization refused; the job's terminal state "
                    "stands and its card consequence is owned by the writer "
                    "that won it",
                    job_id=context.created_job_id,
                    standing_status=str(linked.get("status") or ""),
                )
            return ResultLinkOutcome(publishable=True, reason="linked", job=dict(linked))
        logger.warning(
            "Result link refused; publication is withheld so a restored "
            "card can never sit beside a result",
            job_id=context.created_job_id,
            standing_status=str(linked.get("status") or ""),
            run_id=run_id,
        )
        return ResultLinkOutcome(
            publishable=False,
            reason="refused",
            job=dict(linked) if linked else None,
        )
    except Exception as exc:
        if not dev_memory_fallback_enabled:
            raise
        logger.warning(
            "Shadow backtest job result link failed; result run remains persisted",
            error=str(exc),
            user_id=user_id,
            job_id=context.created_job_id,
            run_id=run_id,
        )
        return ResultLinkOutcome(publishable=True, reason="link_error")


@dataclass(frozen=True)
class ResultPublication:
    """The turn-facing consequence of the link outcome."""

    publishable: bool
    result_card: dict[str, Any] | None = None
    assistant_text: str | None = None


def apply_result_link_outcome(
    *,
    run: Any,
    metadata: dict[str, Any],
    runtime_result: dict[str, Any],
    gateway: Any | None,
    user_id: str,
    language: str | None,
    dev_memory_fallback_enabled: bool,
) -> ResultPublication:
    """Link the run to its job, then publish or withhold accordingly.

    An accepted link stamps the result keys onto the turn's metadata and
    final payload. A refused link publishes nothing: every result key is
    stripped, the just-persisted finalized tuple is removed so it cannot
    surface through durable result reads or the Omnisearch leaves, card
    restoration is re-attempted only after that removal succeeds (the
    finalizer that won the terminal state may not have completed it, and
    failing toward consumed is the guard's bias), and the turn settles on
    the ``run_result_withheld`` recovery, recording the refusal as
    ``result_link_refused``.
    """
    link_outcome = link_shadow_backtest_job_result(
        user_id=user_id,
        run_id=run.id,
        gateway=gateway,
        dev_memory_fallback_enabled=dev_memory_fallback_enabled,
    )
    if not link_outcome.publishable:
        # The declared card is another projection of this same withheld run.
        # Other calls on this turn keep their own independent results.
        bound = getattr(run, "conversation_result_card", {}).get("tool_result_cards", [])
        call_ids = {
            card["call_id"]
            for card in bound
            if isinstance(card, dict) and "call_id" in card
        }
        for document in (metadata, runtime_result):
            cards = document.get("tool_result_cards")
            if isinstance(cards, list):
                document["tool_result_cards"] = [
                    card for card in cards if card.get("call_id") not in call_ids
                ]
        return ResultPublication(
            publishable=False,
            assistant_text=_withhold_refused_result_publication(
                link_outcome=link_outcome,
                run_id=run.id,
                metadata=metadata,
                runtime_result=runtime_result,
                gateway=gateway,
                user_id=user_id,
                language=language,
            ),
        )
    result_card = run.conversation_result_card
    metadata["result_card"] = result_card
    runtime_result["result_card"] = result_card
    final_response_payload = runtime_result.get("final_response_payload")
    if isinstance(final_response_payload, dict):
        final_response_payload["result_card"] = result_card
    metadata["latest_run_id"] = run.id
    metadata["result_run_id"] = run.id
    metadata["result_strategy_id"] = run.strategy_id
    metadata["result_conversation_id"] = run.conversation_id
    metadata["result_fact_bank"] = result_fact_bank(run)
    context_packets = result_card.get("context_packets")
    if isinstance(context_packets, list):
        metadata["context_packets"] = context_packets
    runtime_result["run"] = reader_run(run).model_dump(mode="json")
    return ResultPublication(publishable=True, result_card=result_card)


def _withhold_refused_result_publication(
    *,
    link_outcome: ResultLinkOutcome,
    run_id: str,
    metadata: dict[str, Any],
    runtime_result: dict[str, Any],
    gateway: Any | None,
    user_id: str,
    language: str | None,
) -> str:
    from argus.api.chat.confirmation import restore_pending_card_for_failed_job

    # Removal first, restoration second: if the cleanup fails, the raise
    # skips the restore re-attempt, so this path never itself hands back
    # an editable card while the tuple is still readable. Failing toward
    # consumed is the guard's stated bias; the finalizer that won the
    # terminal state ran its own restore either way. Before the raise, a
    # durable pending marker lands on the job row so the leaked tuple is
    # queryable rather than known only to a log line.
    try:
        _remove_withheld_result_tuple(gateway, user_id=user_id, run_id=run_id)
    except Exception:
        _persist_cleanup_pending_marker(
            gateway,
            user_id=user_id,
            job_id=str((link_outcome.job or {}).get("id") or ""),
            run_id=run_id,
        )
        raise
    _evict_withheld_from_process_cache(user_id=user_id, run_id=run_id)
    _persist_refusal_audit_record(
        gateway,
        user_id=user_id,
        job_id=str((link_outcome.job or {}).get("id") or ""),
        run_id=run_id,
    )
    restore_pending_card_for_failed_job(
        gateway,
        user_id=user_id,
        job=link_outcome.job,
    )
    for stale_key in RESULT_PUBLICATION_KEYS:
        metadata.pop(stale_key, None)
        runtime_result.pop(stale_key, None)
    assistant_text = recovery_message("run_result_withheld", language=language)
    withheld_recovery = recovery_state(
        "run_result_withheld",
        language=language,
        retryable=False,
    )
    metadata["conversation_mode"] = "confirm"
    metadata["recovery"] = withheld_recovery
    metadata["result_link_refused"] = {
        "job_id": (link_outcome.job or {}).get("id"),
        "job_status": (link_outcome.job or {}).get("status"),
        "unpublished_run_id": run_id,
    }
    runtime_result["recovery"] = withheld_recovery
    runtime_result["assistant_response"] = assistant_text
    return assistant_text


def _evict_withheld_from_process_cache(*, user_id: str, run_id: str) -> None:
    """The finalization also cached the tuple in this process's memory
    store, and fallback readers scan that cache after an authoritative
    empty read, so the withheld claim requires the cache eviction too. A
    failure here propagates like the authoritative removal: the turn must
    not claim there is no result while this process would still serve
    one."""
    from argus.api import state as api_state
    from argus.domain.backtest_finalization import evict_cached_backtest_result

    evict_cached_backtest_result(
        api_state.store,
        user_id=user_id,
        run_id=run_id,
    )


def _persist_refusal_audit_record(
    gateway: Any | None,
    *,
    user_id: str,
    job_id: str,
    run_id: str,
) -> None:
    """The contract's durable refusal record on the job row: without it,
    the row cannot distinguish a successfully cleaned withheld result
    from an ordinary cancellation once the turn is stored. Best effort,
    matching the worker path: the message metadata and logs still carry
    the refusal if this write fails. This gateway's merge
    read-modify-writes internally, so the record is sent alone."""
    merge = getattr(gateway, "merge_backtest_job_execution_metadata", None)
    if merge is None or not job_id:
        return
    try:
        merge(
            user_id=user_id,
            job_id=job_id,
            execution_metadata={
                "result_link_refused": {
                    "run_id": run_id,
                    "cleaned_at": _utcnow_iso(),
                }
            },
        )
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).warning(
            "Refused-link audit record could not be persisted",
            user_id=user_id,
            job_id=job_id,
            run_id=run_id,
        )


def _persist_cleanup_pending_marker(
    gateway: Any | None,
    *,
    user_id: str,
    job_id: str,
    run_id: str,
) -> None:
    """Best-effort durable record of the leaked tuple on the job row,
    under the shared RESULT_CLEANUP_PENDING_KEY vocabulary; the worker's
    entry reconciler and operators query the same marker."""
    from argus.domain.backtest_job_lifecycle import RESULT_CLEANUP_PENDING_KEY

    merge = getattr(gateway, "merge_backtest_job_execution_metadata", None)
    if merge is None or not job_id:
        return
    for attempt in (1, 2, 3):
        try:
            merge(
                user_id=user_id,
                job_id=job_id,
                execution_metadata={
                    RESULT_CLEANUP_PENDING_KEY: {
                        "run_id": run_id,
                        "failed_at": _utcnow_iso(),
                    }
                },
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


def _remove_withheld_result_tuple(
    gateway: Any | None, *, user_id: str, run_id: str
) -> None:
    """Every part of a finalized tuple is product-readable without a link
    check (History's run leaf, the latest-completed read, the Omnisearch
    idea and evidence leaves), so the withheld terminal may only be
    composed after the tuple has left those tables. A removal failure
    propagates and the turn fails as an ordinary runtime error instead:
    the transcript must never claim there is no result to show while one
    remains readable, and no reconciler exists to finish the job later. A
    gateway without the remover holds no durable tuple to remove; a False
    return means the row was already gone, which a replay of a refused
    turn legitimately produces."""
    delete_run = getattr(gateway, "delete_withheld_backtest_result", None)
    if delete_run is None:
        return
    try:
        delete_run(user_id=user_id, run_id=run_id)
    except Exception:
        logger.opt(exception=True).warning(
            "Withheld result tuple could not be removed; failing the turn "
            "rather than claiming the result does not exist",
            user_id=user_id,
            run_id=run_id,
        )
        raise

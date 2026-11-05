"""The link outcome the publisher obeys.

``link_shadow_backtest_job_result`` reports what the gated write actually
did; these tests pin the outcome semantics: a standing row without the
requested result is a refusal the publisher must withhold, and the
tolerant paths stay publishable only where nothing durable was guarded.
"""

from __future__ import annotations

import pytest
from argus.api.chat.backtest_jobs import (
    BacktestJobShadowContext,
    backtest_job_shadow_context,
)
from argus.api.chat.result_link import link_shadow_backtest_job_result


class _LinkGateway:
    def __init__(
        self,
        *,
        link_result: dict[str, object] | None = None,
        should_raise: bool = False,
    ) -> None:
        self.link_result = link_result
        self.should_raise = should_raise
        self.result_links: list[dict[str, object]] = []

    def link_backtest_job_result(self, **payload: object) -> dict[str, object]:
        if self.should_raise:
            raise RuntimeError("link failed")
        self.result_links.append(payload)
        if self.link_result is not None:
            return dict(self.link_result)
        return {"id": payload["job_id"], **payload}


def _context() -> BacktestJobShadowContext:
    return BacktestJobShadowContext(
        user_id="user-1",
        conversation_id="conversation-1",
        account_kind="registered",
    )


def test_link_outcome_refused_when_the_lifecycle_statement_won() -> None:
    """A standing row without the requested result means the attach was
    refused; the publisher must withhold the result so a restored card can
    never sit beside one."""
    gateway = _LinkGateway(
        link_result={"id": "job-1", "status": "canceled", "result_run_id": None},
    )
    context = _context()
    context.created_job_id = "job-1"
    context.workflow_dispatch_started = True

    with backtest_job_shadow_context(context):
        outcome = link_shadow_backtest_job_result(
            user_id="user-1",
            run_id="run-1",
            gateway=gateway,
            dev_memory_fallback_enabled=True,
        )

    assert len(gateway.result_links) == 1
    assert outcome.publishable is False
    assert outcome.reason == "refused"
    assert outcome.job == {"id": "job-1", "status": "canceled", "result_run_id": None}


def test_link_outcome_refused_when_the_job_owns_a_different_result() -> None:
    """A job already linked to another run must not publish this one; the
    first link owns the card's consequence."""
    gateway = _LinkGateway(
        link_result={"id": "job-1", "status": "succeeded", "result_run_id": "run-0"},
    )
    context = _context()
    context.created_job_id = "job-1"
    context.workflow_dispatch_started = True

    with backtest_job_shadow_context(context):
        outcome = link_shadow_backtest_job_result(
            user_id="user-1",
            run_id="run-1",
            gateway=gateway,
            dev_memory_fallback_enabled=True,
        )

    assert outcome.publishable is False
    assert outcome.reason == "refused"


def test_link_outcome_publishable_without_a_job_context() -> None:
    with backtest_job_shadow_context(None):
        outcome = link_shadow_backtest_job_result(
            user_id="user-1",
            run_id="run-1",
            gateway=None,
            dev_memory_fallback_enabled=False,
        )
    assert outcome.publishable is True
    assert outcome.reason == "no_job"


def test_refused_publication_removes_the_run_row_and_strips_the_turn(
    monkeypatch,
) -> None:
    """The withheld terminal leaves nothing readable: result keys leave the
    turn, the just-persisted run row is deleted (History and latest-result
    reads carry no link check), and restoration is re-attempted."""
    from argus.api.chat import confirmation as chat_confirmation
    from argus.api.chat.result_link import apply_result_link_outcome

    class _Run:
        id = "run-1"

    order: list[str] = []

    class _RefusingGateway(_LinkGateway):
        def __init__(self) -> None:
            super().__init__(
                link_result={
                    "id": "job-1",
                    "status": "canceled",
                    "result_run_id": None,
                }
            )
            self.deleted_runs: list[str] = []
            self.metadata_merges: list[dict[str, object]] = []

        def delete_withheld_backtest_result(self, *, user_id: str, run_id: str) -> bool:
            order.append("cleanup")
            self.deleted_runs.append(run_id)
            return True

        def merge_backtest_job_execution_metadata(
            self, **payload: object
        ) -> dict[str, object]:
            self.metadata_merges.append(payload)
            return {"id": payload["job_id"]}

    restore_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        chat_confirmation,
        "restore_pending_card_for_failed_job",
        lambda gateway, *, user_id, job: (
            order.append("restore"),
            restore_calls.append({"user_id": user_id, "job": job}),
        ),
    )

    from argus.api import state as api_state
    from argus.api.chat import evidence as chat_evidence
    from argus.domain.store import AlphaStore

    store = AlphaStore()
    store.backtest_runs["run-1"] = object()
    store.backtest_run_owners["run-1"] = "user-1"
    monkeypatch.setattr(api_state, "store", store)
    product_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        chat_evidence,
        "capture_product_event",
        lambda kind, **kwargs: product_events.append((kind, kwargs)),
    )

    gateway = _RefusingGateway()
    context = _context()
    context.created_job_id = "job-1"
    context.workflow_dispatch_started = True
    metadata = {"result_card": {"title": "x"}, "latest_run_id": "run-1"}
    runtime_result = {"result_card": {"title": "x"}, "run": {"id": "run-1"}}

    with backtest_job_shadow_context(context):
        publication = apply_result_link_outcome(
            run=_Run(),
            metadata=metadata,
            runtime_result=runtime_result,
            gateway=gateway,
            user_id="user-1",
            language="en",
            dev_memory_fallback_enabled=True,
        )

    assert publication.publishable is False
    assert publication.assistant_text
    assert gateway.deleted_runs == ["run-1"]
    assert order == ["cleanup", "restore"], (
        "restoration may only follow a successful removal, so this path "
        "can never hand back an editable card beside a readable tuple"
    )
    assert restore_calls and restore_calls[0]["job"]["status"] == "canceled"
    assert "run-1" not in store.backtest_runs, (
        "the process cache must be evicted too, or fallback readers "
        "resurrect the withheld result after the authoritative empty read"
    )
    audit = gateway.metadata_merges[-1]["execution_metadata"]
    assert audit["result_link_refused"]["run_id"] == "run-1", (
        "the job row carries the contract's durable refusal record, or it "
        "cannot distinguish a cleaned withheld result from a cancellation"
    )
    # evidence_capture was retired by SPEC 0 package 0C-1, so there is no
    # completion to withdraw.
    assert [kind for kind, _ in product_events] == []
    assert "result_card" not in metadata and "latest_run_id" not in metadata
    assert "result_card" not in runtime_result and "run" not in runtime_result
    assert metadata["recovery"]["code"] == "run_result_withheld"
    assert metadata["result_link_refused"]["unpublished_run_id"] == "run-1"


def test_failed_tuple_removal_fails_the_turn_instead_of_claiming_withheld(
    monkeypatch,
) -> None:
    """The withheld terminal may only be composed after the tuple left the
    result tables: a removal failure propagates so the turn fails as an
    ordinary runtime error, never persisting a claim that no result exists
    while one remains readable. The restore re-attempt is also skipped, so
    this path cannot itself hand back an editable card beside the still
    readable tuple."""
    from argus.api.chat import confirmation as chat_confirmation
    from argus.api.chat.result_link import apply_result_link_outcome

    class _Run:
        id = "run-1"

    class _BrokenCleanupGateway(_LinkGateway):
        def __init__(self) -> None:
            super().__init__(
                link_result={
                    "id": "job-1",
                    "status": "canceled",
                    "result_run_id": None,
                }
            )
            self.metadata_merges: list[dict[str, object]] = []

        def delete_withheld_backtest_result(self, *, user_id: str, run_id: str) -> bool:
            raise RuntimeError("cleanup unavailable")

        def merge_backtest_job_execution_metadata(
            self, **payload: object
        ) -> dict[str, object]:
            self.metadata_merges.append(payload)
            return {"id": payload["job_id"]}

    restore_calls: list[str] = []
    monkeypatch.setattr(
        chat_confirmation,
        "restore_pending_card_for_failed_job",
        lambda gateway, *, user_id, job: restore_calls.append(user_id),
    )
    context = _context()
    context.created_job_id = "job-1"
    context.workflow_dispatch_started = True
    metadata: dict[str, object] = {"result_card": {"title": "x"}}
    runtime_result: dict[str, object] = {"result_card": {"title": "x"}}

    gateway = _BrokenCleanupGateway()
    with backtest_job_shadow_context(context):
        with pytest.raises(RuntimeError, match="cleanup unavailable"):
            apply_result_link_outcome(
                run=_Run(),
                metadata=metadata,
                runtime_result=runtime_result,
                gateway=gateway,
                user_id="user-1",
                language="en",
                dev_memory_fallback_enabled=True,
            )

    assert restore_calls == []
    assert "recovery" not in metadata
    assert "result_link_refused" not in metadata
    marker = gateway.metadata_merges[-1]["execution_metadata"]
    assert marker["result_cleanup_pending"]["run_id"] == "run-1"


def test_link_outcome_tolerates_gateway_errors_only_in_dev_fallback() -> None:
    context = _context()
    context.created_job_id = "job-1"

    with backtest_job_shadow_context(context):
        outcome = link_shadow_backtest_job_result(
            user_id="user-1",
            run_id="run-1",
            gateway=_LinkGateway(should_raise=True),
            dev_memory_fallback_enabled=True,
        )
    assert outcome.publishable is True
    assert outcome.reason == "link_error"

    with backtest_job_shadow_context(context):
        with pytest.raises(RuntimeError):
            link_shadow_backtest_job_result(
                user_id="user-1",
                run_id="run-1",
                gateway=_LinkGateway(should_raise=True),
                dev_memory_fallback_enabled=False,
            )

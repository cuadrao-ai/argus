from __future__ import annotations

from threading import Event, Thread

from argus.api import state as api_state
from argus.api.schemas import BacktestRun, Conversation, DecisionNoteCreate, User
from argus.domain.backtest_finalization import (
    BacktestFinalizationInput,
    MemoryBacktestFinalizationGateway,
    PreparedBacktestFinalization,
    finalize_backtest_completion,
)
from argus.domain.evidence import (
    build_backtest_evidence_capture,
    evidence_preview_from_artifact,
)
from argus.domain.store import AlphaStore, utcnow


def _user() -> User:
    return User(
        id="user-1",
        email="user@example.com",
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        created_at=utcnow(),
        updated_at=utcnow(),
    )


def _conversation() -> Conversation:
    return Conversation(
        id="conv-1",
        title="AAPL MSFT TSLA idea",
        title_source="system_default",
        created_at=utcnow(),
        updated_at=utcnow(),
        last_message_preview="AAPL MSFT TSLA buy and hold",
    )


def _run() -> BacktestRun:
    return BacktestRun(
        id="run-1",
        conversation_id="conv-1",
        strategy_id=None,
        status="completed",
        asset_class="equity",
        symbols=["AAPL", "MSFT", "TSLA"],
        allocation_method="equal_weight",
        benchmark_symbol="SPY",
        metrics={
            "aggregate": {"performance": {"total_return_pct": 12.3}},
            "by_symbol": {},
        },
        config_snapshot={
            "template": "buy_and_hold",
            "symbols": ["AAPL", "MSFT", "TSLA"],
            "benchmark_symbol": "SPY",
            "date_range": {"start": "2023-01-01", "end": "2026-06-19"},
        },
        conversation_result_card={
            "title": "AAPL, MSFT, TSLA Buy and Hold",
            "status_label": "Simulation Complete",
            "rows": [
                {
                    "key": "total_return_pct",
                    "label": "Total Return",
                    "value": "+12.3%",
                }
            ],
            "assumptions": ["**Benchmark:** SPY", "- No fees"],
            "quick_take": (
                "**Quick take**\n\n"
                "AAPL, MSFT, and TSLA beat SPY in this window.\n\n"
                "- This is evidence, not advice."
            ),
            "breakdown": {
                "summary": "**The equal-weight basket led the benchmark.**",
                "sections": ["Setup", "Benchmark comparison"],
            },
            "context_packets": [{"provider": "internal", "raw": "not preview-safe"}],
            "actions": [],
        },
        created_at=utcnow(),
        chart=None,
        trades=[],
    )


def test_completed_backtest_auto_captures_idea_version_and_evidence() -> None:
    from argus.api.chat.evidence import auto_capture_completed_backtest

    api_state.store.reset()
    user = _user()
    conversation = _conversation()
    run = _run()
    api_state.store.users[user.id] = user
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user.id
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user.id

    captured = auto_capture_completed_backtest(
        user=user,
        conversation=conversation,
        run=run,
    )

    assert captured.idea.lifecycle == "captured"
    assert captured.idea_version.idea_id == captured.idea.id
    assert captured.evidence_artifact.idea_version_id == captured.idea_version.id
    assert captured.evidence_artifact.artifact_type == "backtest"
    assert captured.evidence_artifact.source_run_id == run.id
    assert captured.evidence_artifact.digest
    assert (
        captured.evidence_artifact.digest
        == "Quick take AAPL, MSFT, and TSLA beat SPY in this window. "
        "This is evidence, not advice."
    )
    assert captured.idea.summary == captured.evidence_artifact.digest
    assert captured.idea_version.summary == captured.evidence_artifact.digest
    assert (
        captured.evidence_artifact.payload["quick_take"]
        == "Quick take AAPL, MSFT, and TSLA beat SPY in this window. "
        "This is evidence, not advice."
    )
    assert captured.evidence_artifact.payload["breakdown"] == {
        "summary": "The equal-weight basket led the benchmark.",
        "sections": ["Setup", "Benchmark comparison"],
    }
    assert captured.evidence_artifact.payload["assumptions"] == [
        "Benchmark: SPY",
        "No fees",
    ]
    assert captured.evidence_artifact.payload["metrics"] == run.metrics
    assert "context_packets" not in captured.evidence_artifact.payload["result_card"]
    assert "actions" not in captured.evidence_artifact.payload["result_card"]
    preview = evidence_preview_from_artifact(captured.evidence_artifact)
    assert (
        preview["quick_take"]
        == "Quick take AAPL, MSFT, and TSLA beat SPY in this window. "
        "This is evidence, not advice."
    )
    assert "**" not in preview["quick_take"]
    assert preview["breakdown"] == {
        "summary": "The equal-weight basket led the benchmark.",
        "sections": ["Setup", "Benchmark comparison"],
    }
    assert preview["assumptions"] == ["Benchmark: SPY", "No fees"]
    assert preview["metrics_summary"] == {"total_return_pct": 12.3}
    assert preview["symbols"] == ["AAPL", "MSFT", "TSLA"]
    assert preview["benchmark_symbol"] == "SPY"
    assert not any(key.endswith("_id") for key in preview)
    assert (
        run.conversation_result_card["evidence_artifact_id"]
        == captured.evidence_artifact.id
    )
    assert run.conversation_result_card["idea_id"] == captured.idea.id
    assert run.conversation_result_card["idea_version_id"] == captured.idea_version.id


def test_evidence_provenance_preserves_requested_and_effective_data_windows() -> None:
    run = _run().model_copy(
        update={
            "config_snapshot": {
                **_run().config_snapshot,
                "requested_date_range": {
                    "start": "2023-01-01",
                    "end": "2026-06-19",
                },
                "effective_date_range": {
                    "start": "2023-03-15",
                    "end": "2026-06-18",
                },
                "data_coverage": {
                    "schema_version": "market_data_coverage_v1",
                    "dataset_id": "sha256:fixture",
                },
            }
        }
    )

    captured = build_backtest_evidence_capture(
        run=run,
        idea_id="idea-window",
        idea_version_id="version-window",
        evidence_artifact_id="evidence-window",
        now=utcnow(),
    )

    assert captured.evidence_artifact.payload["provenance"]["data_window"] == {
        "requested": {"start": "2023-01-01", "end": "2026-06-19"},
        "effective": {"start": "2023-03-15", "end": "2026-06-18"},
        "dataset_id": "sha256:fixture",
    }


def test_memory_search_waits_for_complete_backtest_finalization(monkeypatch) -> None:
    from argus.api.search_assembly import scored_memory_search_items

    artifact_published = Event()
    release_finalizer = Event()

    class PausingArtifactDict(dict):
        def __setitem__(self, key, value) -> None:
            super().__setitem__(key, value)
            artifact_published.set()
            assert release_finalizer.wait(timeout=2)

    store = AlphaStore()
    store.evidence_artifacts = PausingArtifactDict()
    conversation = _conversation()
    store.conversations[conversation.id] = conversation
    store.conversation_owners[conversation.id] = _user().id
    monkeypatch.setattr(api_state, "store", store)
    run = _run()
    finalization = BacktestFinalizationInput(
        user_id="user-1",
        execution_identity="backtest_job:job-1",
        run=run,
        result_card=dict(run.conversation_result_card),
        idea_id="idea-1",
        idea_version_id="version-1",
        evidence_artifact_id="artifact-1",
        finalized_at=utcnow(),
    )
    finalization_errors: list[BaseException] = []
    search_results: list[tuple[int, object]] = []
    search_finished = Event()

    def finalize() -> None:
        try:
            finalize_backtest_completion(
                MemoryBacktestFinalizationGateway(store),
                finalization,
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            finalization_errors.append(exc)

    def search() -> None:
        search_results.extend(scored_memory_search_items(user=_user(), query="aapl"))
        search_finished.set()

    finalizer_thread = Thread(target=finalize)
    search_thread = Thread(target=search)
    finalizer_thread.start()
    assert artifact_published.wait(timeout=1)
    search_thread.start()

    try:
        assert not search_finished.wait(timeout=0.1)
    finally:
        release_finalizer.set()
        finalizer_thread.join(timeout=2)
        search_thread.join(timeout=2)

    assert not finalization_errors
    assert search_finished.is_set()
    assert len(search_results) == 1
    item = search_results[0][1]
    assert item.type == "conversation"
    assert item.id == conversation.id
    assert item.total_runs == 1
    assert item.decided_runs == 0
    assert item.dossier is not None
    assert item.dossier.run_id == run.id


def test_completed_backtest_capture_sends_no_evidence_capture_event(monkeypatch) -> None:
    """evidence_capture was retired by SPEC 0 package 0C-1."""
    from argus.api.chat.evidence import auto_capture_completed_backtest

    observed: list[str] = []
    monkeypatch.setattr(
        "argus.api.chat.evidence.capture_product_event",
        lambda kind, **kwargs: observed.append(kind),
    )
    api_state.store.reset()

    auto_capture_completed_backtest(
        user=_user(),
        conversation=_conversation(),
        run=_run(),
    )

    assert observed == []


def test_decision_capture_emits_product_event(monkeypatch) -> None:
    from argus.api.chat.evidence import (
        auto_capture_completed_backtest,
        create_decision_for_evidence_artifact,
    )

    observed: list[dict[str, object]] = []

    def fake_capture(kind: str, **kwargs: object) -> None:
        observed.append({"kind": kind, **kwargs})

    monkeypatch.setattr(
        "argus.api.chat.evidence.capture_product_event",
        fake_capture,
        raising=False,
    )
    api_state.store.reset()
    user = _user()
    conversation = _conversation()
    run = _run()
    captured = auto_capture_completed_backtest(
        user=user,
        conversation=conversation,
        run=run,
    )
    observed.clear()

    create_decision_for_evidence_artifact(
        user=user,
        artifact_id=captured.evidence_artifact.id,
        payload=DecisionNoteCreate(decision_state="promising", note="Keep watching."),
    )

    assert observed == [
        {
            "kind": "decision_capture",
            "user_id": user.id,
            "conversation_id": conversation.id,
            "backtest_run_id": run.id,
            "status": "promising",
            "attributes": {
                "decision_state": "promising",
                "artifact_lifecycle": "decided",
                "note_present": True,
            },
        }
    ]


def test_completed_backtest_capture_is_idempotent_by_run_id() -> None:
    from argus.api.chat.evidence import auto_capture_completed_backtest

    api_state.store.reset()
    user = _user()
    conversation = _conversation()
    run = _run()
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user.id
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user.id

    first = auto_capture_completed_backtest(
        user=user,
        conversation=conversation,
        run=run,
    )
    second = auto_capture_completed_backtest(
        user=user,
        conversation=conversation,
        run=run,
    )

    assert second.idea.id == first.idea.id
    assert second.idea_version.id == first.idea_version.id
    assert second.evidence_artifact.id == first.evidence_artifact.id
    assert len(api_state.store.evidence_artifacts) == 1


def test_completed_backtest_capture_reuses_durable_sidecar_after_restart(
    monkeypatch,
) -> None:
    from argus.api.chat.evidence import auto_capture_completed_backtest

    class _Gateway:
        def __init__(self, existing, run: BacktestRun):  # noqa: ANN001
            self.store = AlphaStore()
            self.finalization_calls = 0
            self.store.backtest_runs[run.id] = run
            self.store.backtest_run_owners[run.id] = "user-1"
            self.store.ideas[existing.idea.id] = existing.idea
            self.store.idea_owners[existing.idea.id] = "user-1"
            self.store.idea_versions[existing.idea_version.id] = existing.idea_version
            self.store.idea_version_owners[existing.idea_version.id] = "user-1"
            artifact = existing.evidence_artifact
            self.store.evidence_artifacts[artifact.id] = artifact
            self.store.evidence_artifact_owners[artifact.id] = "user-1"

        def finalize_backtest_completion(
            self,
            *,
            finalization: PreparedBacktestFinalization,
        ):
            self.finalization_calls += 1
            return MemoryBacktestFinalizationGateway(
                self.store
            ).finalize_backtest_completion(finalization=finalization)

    api_state.store.reset()
    user = _user()
    conversation = _conversation()
    run = _run()
    existing = build_backtest_evidence_capture(
        run=run,
        idea_id="00000000-0000-0000-0000-000000000101",
        idea_version_id="00000000-0000-0000-0000-000000000102",
        evidence_artifact_id="00000000-0000-0000-0000-000000000103",
        now=utcnow(),
    )
    gateway = _Gateway(existing, run)
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    captured = auto_capture_completed_backtest(
        user=user,
        conversation=conversation,
        run=run,
    )

    assert captured.evidence_artifact.id == existing.evidence_artifact.id
    assert gateway.finalization_calls == 1
    assert (
        run.conversation_result_card["evidence_artifact_id"]
        == existing.evidence_artifact.id
    )
    assert len(api_state.store.evidence_artifacts) == 1


def test_evicting_a_withheld_run_removes_the_cached_tuple() -> None:
    """The eviction mirrors cache_finalized_backtest exactly: run, minted
    version, evidence, and a versionless idea leave together, so fallback
    readers cannot resurrect a result the turn reported as withheld."""
    from argus.domain.backtest_finalization import (
        FinalizedBacktest,
        cache_finalized_backtest,
        evict_cached_backtest_result,
    )

    store = AlphaStore()
    run = _run()
    captured = build_backtest_evidence_capture(
        run=run,
        idea_id="idea-evict",
        idea_version_id="version-evict",
        evidence_artifact_id="evidence-evict",
        now=utcnow(),
    )
    cache_finalized_backtest(
        store,
        user_id="user-1",
        finalized=FinalizedBacktest(run=run, captured=captured),
    )
    assert store.backtest_runs and store.ideas and store.evidence_artifacts

    evict_cached_backtest_result(store, user_id="user-1", run_id=run.id)

    assert store.backtest_runs == {}
    assert store.backtest_run_owners == {}
    assert store.idea_versions == {}
    assert store.idea_version_owners == {}
    assert store.evidence_artifacts == {}
    assert store.evidence_artifact_owners == {}
    assert store.ideas == {}
    assert store.idea_owners == {}


def test_evicting_a_withheld_run_repoints_an_idea_with_earlier_versions() -> None:
    """An idea holding a previously published version survives the
    eviction and its active pointer moves to the latest remaining
    version, matching the authoritative removal function."""
    from argus.domain.backtest_finalization import (
        FinalizedBacktest,
        cache_finalized_backtest,
        evict_cached_backtest_result,
    )

    store = AlphaStore()
    published_run = _run()
    published = build_backtest_evidence_capture(
        run=published_run,
        idea_id="idea-shared",
        idea_version_id="version-published",
        evidence_artifact_id="evidence-published",
        now=utcnow(),
    )
    cache_finalized_backtest(
        store,
        user_id="user-1",
        finalized=FinalizedBacktest(run=published_run, captured=published),
    )

    withheld_run = _run().model_copy(update={"id": "run-withheld"})
    withheld_version = published.idea_version.model_copy(
        update={
            "id": "version-withheld",
            "source_run_id": "run-withheld",
            "created_at": utcnow(),
        }
    )
    withheld_evidence = published.evidence_artifact.model_copy(
        update={
            "id": "evidence-withheld",
            "idea_version_id": "version-withheld",
            "source_run_id": "run-withheld",
        }
    )
    store.backtest_runs[withheld_run.id] = withheld_run
    store.backtest_run_owners[withheld_run.id] = "user-1"
    store.idea_versions[withheld_version.id] = withheld_version
    store.idea_version_owners[withheld_version.id] = "user-1"
    store.evidence_artifacts[withheld_evidence.id] = withheld_evidence
    store.evidence_artifact_owners[withheld_evidence.id] = "user-1"
    store.ideas["idea-shared"] = store.ideas["idea-shared"].model_copy(
        update={"active_version_id": withheld_version.id}
    )

    evict_cached_backtest_result(store, user_id="user-1", run_id="run-withheld")

    assert "run-withheld" not in store.backtest_runs
    assert "version-withheld" not in store.idea_versions
    assert "evidence-withheld" not in store.evidence_artifacts
    assert "idea-shared" in store.ideas
    assert store.ideas["idea-shared"].active_version_id == "version-published"

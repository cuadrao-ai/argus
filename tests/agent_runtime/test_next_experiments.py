"""Stage-0 Try next selection (issue #249, `next_experiments` in
docs/API_CONTRACT.md): deterministic, result-aware,
capped, typed — and attached to the completed-result stage patch."""

from __future__ import annotations

from argus.agent_runtime.next_experiments import (
    NEXT_EXPERIMENT_ACTION_LABELS,
    NEXT_EXPERIMENTS_ROW_CAP,
    NEXT_EXPERIMENTS_VERSION,
    next_experiments_sidecar,
)
from argus.agent_runtime.stages.explain import explain_stage
from argus.agent_runtime.state.models import ResponseProfile, RunState

_BUY_AND_HOLD_FACTS = {
    "config_snapshot": {"template": "buy_and_hold"},
    "symbols": ["AAPL"],
}


def test_sidecar_caps_rows_and_carries_typed_identity() -> None:
    sidecar = next_experiments_sidecar(_BUY_AND_HOLD_FACTS)

    assert sidecar is not None
    assert sidecar["version"] == NEXT_EXPERIMENTS_VERSION
    assert 1 <= len(sidecar["rows"]) <= NEXT_EXPERIMENTS_ROW_CAP
    for row in sidecar["rows"]:
        assert row["kind"]
        assert row["label"]
        assert row["label_key"] == f"chat.next_experiments.labels.{row['kind']}"


def test_sidecar_names_its_run_only_when_told() -> None:
    # A card-bearing message owns its run id; a card-less one (a what-next
    # follow-up, #590) gets it from the sidecar so continuity rows keep their
    # typed action.
    assert "source_run_id" not in next_experiments_sidecar(_BUY_AND_HOLD_FACTS)
    anchored = next_experiments_sidecar(_BUY_AND_HOLD_FACTS, source_run_id="run-1")
    assert anchored is not None
    assert anchored["source_run_id"] == "run-1"
    assert (
        next_experiments_sidecar(_BUY_AND_HOLD_FACTS, source_run_id="").get(
            "source_run_id"
        )
        is None
    )


def test_losing_run_leads_with_refinement_and_says_why() -> None:
    sidecar = next_experiments_sidecar(
        _BUY_AND_HOLD_FACTS,
        benchmark_delta=-7.5,
    )

    assert sidecar is not None
    first = sidecar["rows"][0]
    assert first["kind"] in {
        "recurring_monthly_buys",
        "supported_ma_crossover",
        "compare_buy_and_hold",
    }
    assert first["why"] == {
        "code": "lost_to_benchmark",
        "params": {"points": 7.5},
    }


def test_winning_run_leads_with_exploration() -> None:
    sidecar = next_experiments_sidecar(
        _BUY_AND_HOLD_FACTS,
        benchmark_delta=12.0,
    )

    assert sidecar is not None
    first = sidecar["rows"][0]
    assert first["kind"] in {"change_date_range", "same_setup_peer_asset"}
    assert first["why"]["code"] == "beat_benchmark"


def test_reason_carries_the_engine_gap_as_a_display_figure() -> None:
    # Rounded once here, from the engine gap, never rebuilt from two rounded
    # returns; the client prints the digits it receives.
    sidecar = next_experiments_sidecar(_BUY_AND_HOLD_FACTS, benchmark_delta=46.35)

    assert sidecar is not None
    assert sidecar["rows"][0]["why"] == {
        "code": "beat_benchmark",
        "params": {"points": 46.4},
    }


def test_a_gap_that_rounds_to_nothing_is_no_reason_and_no_loss() -> None:
    sidecar = next_experiments_sidecar(_BUY_AND_HOLD_FACTS, benchmark_delta=-0.03)

    assert sidecar is not None
    assert all("why" not in row for row in sidecar["rows"])
    assert sidecar["rows"][0]["kind"] in {"change_date_range", "same_setup_peer_asset"}


def test_deep_drawdown_outranks_the_benchmark_story() -> None:
    sidecar = next_experiments_sidecar(
        _BUY_AND_HOLD_FACTS,
        benchmark_delta=12.0,
        max_drawdown=-22.4,
    )

    assert sidecar is not None
    assert sidecar["rows"][0]["kind"] in {
        "recurring_monthly_buys",
        "supported_ma_crossover",
        "compare_buy_and_hold",
    }
    assert sidecar["rows"][0]["why"] == {
        "code": "deep_drawdown",
        "params": {"drawdown": -22.4},
    }


def test_every_offered_kind_has_labels_in_both_languages() -> None:
    for family in (
        {"config_snapshot": {"template": "buy_and_hold"}},
        {"config_snapshot": {"template": "indicator_threshold"}},
        {"config_snapshot": {"template": "signal_strategy"}},
        {"config_snapshot": {"template": "dca_accumulation"}},
        {"config_snapshot": {}},
    ):
        sidecar = next_experiments_sidecar(family)
        assert sidecar is not None
        for row in sidecar["rows"]:
            for language in ("en", "es-419"):
                assert row["label_key"] in NEXT_EXPERIMENT_ACTION_LABELS[language]


def test_explain_stage_attaches_the_sidecar_to_the_result_patch() -> None:
    state = RunState.new(current_user_message="why", recent_thread_history=[])
    state.effective_response_profile = ResponseProfile(
        effective_tone="concise",
        effective_verbosity="low",
        effective_expertise_mode="advanced",
    )
    state.confirmation_payload = {
        "strategy": {"strategy_thesis": "Buy Tesla on pullbacks"},
        "optional_parameters": {},
    }
    state.final_response_payload = {
        "result": {"total_return": 0.14, "benchmark_return": 0.09}
    }

    result = explain_stage(state=state)

    sidecar = result.patch["next_experiments"]
    assert sidecar["version"] == NEXT_EXPERIMENTS_VERSION
    assert 1 <= len(sidecar["rows"]) <= NEXT_EXPERIMENTS_ROW_CAP


def test_rows_never_reoffer_what_the_conversation_already_asked() -> None:
    sidecar = next_experiments_sidecar(
        _BUY_AND_HOLD_FACTS,
        recent_user_messages=[
            "Test AAPL for all of 2023 with $1000.",
            "Test a different date range",
            "  probar el mismo enfoque en un activo similar  ",
        ],
    )

    assert sidecar is not None
    kinds = [row["kind"] for row in sidecar["rows"]]
    assert "change_date_range" not in kinds
    assert "same_setup_peer_asset" not in kinds
    assert kinds


def test_previously_offered_kinds_are_spent_even_if_ignored() -> None:
    sidecar = next_experiments_sidecar(
        _BUY_AND_HOLD_FACTS,
        previously_offered_kinds=["change_date_range", "supported_rsi_threshold"],
    )

    assert sidecar is not None
    kinds = [row["kind"] for row in sidecar["rows"]]
    assert "change_date_range" not in kinds
    assert "supported_rsi_threshold" not in kinds
    assert kinds


def test_acceptance_detection_matches_offered_labels_in_both_languages() -> None:
    from argus.agent_runtime.next_experiments import (
        detect_next_experiment_acceptance,
        offered_kinds_from_thread_metadata,
    )

    thread_metadata = {
        "next_experiments_offered_kinds": [
            "same_setup_peer_asset",
            "change_date_range",
        ]
    }
    assert offered_kinds_from_thread_metadata(thread_metadata) == [
        "same_setup_peer_asset",
        "change_date_range",
    ]
    assert detect_next_experiment_acceptance(
        "  Test a different date range ", thread_metadata
    ) == {"kind": "change_date_range", "position": 1}
    assert detect_next_experiment_acceptance(
        "Probar el mismo enfoque en un activo similar", thread_metadata
    ) == {"kind": "same_setup_peer_asset", "position": 0}
    # A label that was never offered is not an acceptance.
    assert (
        detect_next_experiment_acceptance("Compare with buy and hold", thread_metadata)
        is None
    )
    assert detect_next_experiment_acceptance("Test AAPL", thread_metadata) is None
    assert detect_next_experiment_acceptance("Test a different date range", None) is None


def test_thread_metadata_carries_the_offered_kinds() -> None:
    from argus.agent_runtime.graph.workflow import (
        WorkflowStageOutcome,
        _build_thread_metadata,
    )

    state = RunState.new(current_user_message="run it", recent_thread_history=[])
    metadata = _build_thread_metadata(
        workflow_state={
            "run_state": state,
            "next_experiments": {
                "version": NEXT_EXPERIMENTS_VERSION,
                "rows": [
                    {"kind": "change_date_range", "label": "x", "label_key": "k"},
                    {"kind": "compare_buy_and_hold", "label": "y", "label_key": "k2"},
                ],
            },
        },
        run_state=state,
        stage_outcome=WorkflowStageOutcome.END_RUN,
    )

    assert metadata["next_experiments_offered_kinds"] == [
        "change_date_range",
        "compare_buy_and_hold",
    ]


def test_deep_drawdown_reads_the_canonical_nested_metrics() -> None:
    state = RunState.new(current_user_message="why", recent_thread_history=[])
    state.effective_response_profile = ResponseProfile(
        effective_tone="concise",
        effective_verbosity="low",
        effective_expertise_mode="advanced",
    )
    state.confirmation_payload = {
        "strategy": {"strategy_thesis": "Buy Tesla on pullbacks"},
        "optional_parameters": {},
    }
    state.final_response_payload = {
        "result": {
            "total_return": 0.30,
            "benchmark_return": 0.10,
            "metrics": {"aggregate": {"performance": {"max_drawdown_pct": -24.5}}},
        }
    }

    result = explain_stage(state=state)

    sidecar = result.patch["next_experiments"]
    assert sidecar["rows"][0]["why"] == {
        "code": "deep_drawdown",
        "params": {"drawdown": -24.5},
    }


def test_prebaked_peer_row_carries_suffix_and_full_ask() -> None:
    facts = {
        "config_snapshot": {
            "template": "buy_and_hold",
            "symbols": ["AAPL"],
            "date_range": {"start": "2023-01-03", "end": "2023-12-29"},
            "initial_capital": 1000,
            "asset_class": "equity",
        },
    }
    sidecar = next_experiments_sidecar(
        facts,
        language="en",
        prebake_probe=lambda peer: peer == "MSFT",
    )

    assert sidecar is not None
    peer_row = next(
        row for row in sidecar["rows"] if row["kind"] == "same_setup_peer_asset"
    )
    assert peer_row["detail"] == "MSFT"
    assert peer_row["send_text"] == (
        "Test the same buy and hold setup on MSFT from 2023-01-03 to "
        "2023-12-29 with $1000."
    )
    dca_row = next(
        row for row in sidecar["rows"] if row["kind"] == "recurring_monthly_buys"
    )
    assert dca_row["send_text"] == (
        "Try monthly recurring buys of AAPL from 2023-01-03 to 2023-12-29 "
        "with $1000 each month."
    )


def test_prebake_stays_off_when_the_peer_fails_grounding() -> None:
    facts = {
        "config_snapshot": {
            "template": "buy_and_hold",
            "symbols": ["AAPL"],
            "date_range": {"start": "2023-01-03", "end": "2023-12-29"},
            "initial_capital": 1000,
            "asset_class": "equity",
        },
    }
    sidecar = next_experiments_sidecar(
        facts,
        language="en",
        prebake_probe=lambda peer: False,
    )

    assert sidecar is not None
    peer_row = next(
        row for row in sidecar["rows"] if row["kind"] == "same_setup_peer_asset"
    )
    assert "detail" not in peer_row
    assert "send_text" not in peer_row


def test_prebaked_spanish_ask_reads_in_spanish() -> None:
    facts = {
        "config_snapshot": {
            "template": "buy_and_hold",
            "symbols": ["NVDA"],
            "date_range": {"start": "2023-01-03", "end": "2023-12-29"},
            "initial_capital": 1500,
            "asset_class": "equity",
        },
    }
    sidecar = next_experiments_sidecar(
        facts,
        language="es-419",
        prebake_probe=lambda peer: True,
    )

    assert sidecar is not None
    peer_row = next(
        row for row in sidecar["rows"] if row["kind"] == "same_setup_peer_asset"
    )
    assert peer_row["detail"] == "AMD"
    assert "Probar el mismo enfoque" in peer_row["send_text"]
    assert "AMD" in peer_row["send_text"]


def test_acceptance_matches_the_offered_send_text() -> None:
    from argus.agent_runtime.next_experiments import detect_next_experiment_acceptance

    thread_metadata = {
        "next_experiments_offered_kinds": ["same_setup_peer_asset"],
        "next_experiments_offered_texts": {
            "same_setup_peer_asset": (
                "Test the same buy and hold setup on MSFT from 2023-01-03 to "
                "2023-12-29 with $1000."
            )
        },
    }
    assert detect_next_experiment_acceptance(
        "Test the same buy and hold setup on MSFT from 2023-01-03 to "
        "2023-12-29 with $1000.",
        thread_metadata,
    ) == {"kind": "same_setup_peer_asset", "position": 0}


def test_slow_peer_grounding_degrades_to_the_generic_row(
    monkeypatch,
) -> None:
    import time

    from argus.agent_runtime import next_experiments as module

    monkeypatch.setattr(module, "_PREBAKE_PROBE_BUDGET_SECONDS", 0.2)

    def slow_probe(peer: str) -> bool:
        time.sleep(1.0)
        return True

    facts = {
        "config_snapshot": {
            "template": "buy_and_hold",
            "symbols": ["AAPL"],
            "date_range": {"start": "2023-01-03", "end": "2023-12-29"},
            "initial_capital": 1000,
            "asset_class": "equity",
        },
    }
    started = time.monotonic()
    sidecar = next_experiments_sidecar(facts, language="en", prebake_probe=slow_probe)
    elapsed = time.monotonic() - started

    assert sidecar is not None
    peer_row = next(
        row for row in sidecar["rows"] if row["kind"] == "same_setup_peer_asset"
    )
    assert peer_row.get("detail") is None
    assert peer_row.get("send_text") is None
    assert elapsed < 0.8


def test_offered_kinds_survive_an_intervening_turn_without_a_result() -> None:
    from argus.agent_runtime.graph.workflow import _build_thread_metadata
    from argus.agent_runtime.state.models import RunState

    run_state = RunState.new(
        current_user_message="a follow-up question", recent_thread_history=[]
    )
    prior = {
        "next_experiments_offered_kinds": ["change_date_range"],
        "next_experiments_offered_texts": {"change_date_range": "Test 2024 instead."},
    }
    metadata = _build_thread_metadata(
        workflow_state={"selected_thread_metadata": prior},
        run_state=run_state,
        stage_outcome="ready_to_respond",
    )
    assert metadata["next_experiments_offered_kinds"] == ["change_date_range"]
    assert metadata["next_experiments_offered_texts"] == {
        "change_date_range": "Test 2024 instead."
    }

    fresh_offer = {
        "version": "argus_next_experiments/v1",
        "rows": [{"kind": "same_setup_peer_asset", "label": "x", "label_key": "k"}],
    }
    replaced = _build_thread_metadata(
        workflow_state={
            "selected_thread_metadata": prior,
            "next_experiments": fresh_offer,
        },
        run_state=run_state,
        stage_outcome="ready_to_respond",
    )
    assert replaced["next_experiments_offered_kinds"] == ["same_setup_peer_asset"]
    assert "next_experiments_offered_texts" not in replaced

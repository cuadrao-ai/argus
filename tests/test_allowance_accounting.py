"""Retained direct-run identity and terminal finalization contracts."""

from argus.domain.store import AlphaStore

USER_ID = "00000000-0000-0000-0000-000000000001"


def test_direct_identity_covers_every_execution_field():
    from argus.domain.backtest_admission import (
        direct_run_identity_hash,
        normalize_direct_launch_payload,
    )

    base = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": "2024-01-02",
        "end_date": "2024-06-28",
    }

    def identity(payload):
        return direct_run_identity_hash(
            conversation_id=None,
            strategy_id=None,
            normalized_payload=normalize_direct_launch_payload(payload),
        )

    baseline = identity(base)
    for field, changed in (
        ("starting_capital", 250_000),
        ("side", "short"),
        ("allocation_method", "risk_parity"),
    ):
        assert identity({**base, field: changed}) != baseline, (
            f"{field} must participate in the direct-run identity; reusing a "
            "key with a changed execution field is a collision, not a replay."
        )


def test_direct_identity_stable_across_typed_and_string_dates():
    from datetime import date

    from argus.domain.backtest_admission import (
        direct_run_identity_hash,
        normalize_direct_launch_payload,
    )

    def identity(payload):
        return direct_run_identity_hash(
            conversation_id=None,
            strategy_id=None,
            normalized_payload=normalize_direct_launch_payload(payload),
        )

    typed = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": date(2024, 1, 2),
        "end_date": date(2024, 6, 28),
    }
    stringly = {
        **typed,
        "start_date": "2024-01-02",
        "end_date": "2024-06-28",
    }
    assert identity(typed) == identity(stringly)


def test_direct_identity_treats_explicit_defaults_as_the_same_execution():
    from argus.domain.backtest_admission import (
        direct_run_identity_hash,
        normalize_direct_launch_payload,
    )

    base = {
        "template": "buy_and_hold",
        "asset_class": "equity",
        "symbols": ["AAPL"],
        "start_date": "2024-01-02",
        "end_date": "2024-06-28",
    }

    def identity(payload):
        return direct_run_identity_hash(
            conversation_id=None,
            strategy_id=None,
            normalized_payload=normalize_direct_launch_payload(payload),
        )

    baseline = identity(base)
    for field, explicit_default in (
        ("side", "long"),
        ("starting_capital", 1000),
        ("starting_capital", 1000.0),
        ("allocation_method", "equal_weight"),
        ("timeframe", "1D"),
        ("timeframe", "1d"),
    ):
        assert identity({**base, field: explicit_default}) == baseline, (
            f"Spelling out the executor default for {field} does not change "
            "what runs, so it must not mint a second chargeable identity."
        )
    assert identity({**base, "starting_capital": 2500}) == identity(
        {**base, "starting_capital": 2500.0}
    )


def test_memory_direct_finalization_requires_a_running_job():
    from argus.domain import backtest_admission

    store = AlphaStore()
    outcome = backtest_admission.admit_backtest_job_memory(
        store,
        user_id=USER_ID,
        operation_scope="backtests.run",
        idempotency_key="race-key",
        identity_hash=f"sha256:{'e' * 64}",
        payload_hash=f"sha256:{'f' * 64}",
        launch_payload={"kind": "proof"},
        initial_status="running",
        allowance_limits=[("hour", 10), ("day", 50)],
    )
    job_id = outcome.job["id"]
    store.backtest_jobs[job_id]["status"] = "failed"
    store.backtest_jobs[job_id]["failure_code"] = "direct_execution_abandoned"

    result = backtest_admission.finalize_direct_job_memory(
        store,
        job_id=job_id,
        status="succeeded",
        result_run_id="run-1",
    )

    assert result is None
    assert store.backtest_jobs[job_id]["status"] == "failed"
    assert store.backtest_jobs[job_id]["failure_code"] == "direct_execution_abandoned"

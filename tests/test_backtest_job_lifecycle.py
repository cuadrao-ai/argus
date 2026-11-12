"""The two sides of the consumption design cannot disagree.

One module states when a job may still succeed; the card-restore filter
and both success-write guards derive from it. These tests walk every job
state the database allows, plus shapes it does not, and assert the
derivations never diverge: no state may both give the card back and later
convert into a result.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from argus.domain.backtest_job_lifecycle import (
    JOB_DEAD,
    JOB_HAS_RESULT,
    JOB_MAY_SUCCEED,
    classify_job_for_card,
    job_result_attach_postgrest_filter,
    job_result_attach_sql_predicate,
    job_success_write_postgrest_filter,
    job_success_write_sql_predicate,
)

KNOWN_STATUSES = ("queued", "running", "succeeded", "failed", "canceled", "expired")
STRANGE_STATUSES = ("", None, "paused", "FAILED ", "Running")
RETRYABLE_VALUES = (True, False, None)


def _python_reading_of_sql_predicate(status: object, retryable: object) -> bool:
    """The SQL fragment's semantics, restated for the exhaustive walk; the
    Postgres test evaluates the real fragment against real rows."""
    normalized = str(status or "").strip().casefold()
    if normalized in ("queued", "running"):
        return True
    return normalized == "failed" and bool(retryable)


def _python_reading_of_attach_predicate(status: object, retryable: object) -> bool:
    """The attach fragment's semantics, restated for the exhaustive walk."""
    normalized = str(status or "").strip().casefold()
    if normalized in ("queued", "running", "succeeded"):
        return True
    return normalized == "failed" and bool(retryable)


def test_no_state_can_both_restore_the_card_and_still_succeed() -> None:
    for status, retryable in itertools.product(
        KNOWN_STATUSES + STRANGE_STATUSES, RETRYABLE_VALUES
    ):
        classification = classify_job_for_card(status=status, retryable=retryable)
        restore_would_fire = classification == JOB_DEAD
        success_allowed = _python_reading_of_sql_predicate(status, retryable)
        assert success_allowed == (
            classification == JOB_MAY_SUCCEED
        ), f"success guard and classifier disagree for {status!r}/{retryable!r}"
        assert not (restore_would_fire and success_allowed), (
            f"state {status!r}/{retryable!r} could restore the card and " "later succeed"
        )


def test_no_state_can_both_restore_the_card_and_still_attach_a_result() -> None:
    """The round-7 statement: the attach guard covers every result link,
    not only the success transition, and it agrees with the classifier on
    every state, so a state the card was restored from can never gain a
    result through a plain link either."""
    for status, retryable in itertools.product(
        KNOWN_STATUSES + STRANGE_STATUSES, RETRYABLE_VALUES
    ):
        classification = classify_job_for_card(status=status, retryable=retryable)
        restore_would_fire = classification == JOB_DEAD
        attach_allowed = _python_reading_of_attach_predicate(status, retryable)
        assert attach_allowed == (
            classification in (JOB_MAY_SUCCEED, JOB_HAS_RESULT)
        ), f"attach guard and classifier disagree for {status!r}/{retryable!r}"
        assert not (restore_would_fire and attach_allowed), (
            f"state {status!r}/{retryable!r} could restore the card and "
            "later attach a result"
        )


def test_unknown_states_fail_closed_on_both_sides() -> None:
    for status in STRANGE_STATUSES:
        if str(status or "").strip().casefold() in KNOWN_STATUSES:
            continue
        for retryable in RETRYABLE_VALUES:
            classification = classify_job_for_card(status=status, retryable=retryable)
            assert classification not in (JOB_DEAD, JOB_MAY_SUCCEED), (
                f"unknown state {status!r} must neither restore the card "
                "nor be allowed to succeed"
            )
            assert not _python_reading_of_sql_predicate(status, retryable)
            assert not _python_reading_of_attach_predicate(status, retryable)


def test_every_lifecycle_writer_embeds_the_generated_predicates() -> None:
    """Source contract: the worker, the API gateway, and the proof task
    build their lifecycle guards from the generators, never from
    hand-typed copies. The attach guard must sit on both link writes with
    no way for a caller to opt out."""
    root = Path(__file__).resolve().parents[1]
    gateway = (root / "src/argus/domain/supabase_gateway.py").read_text()
    assert "job_success_write_postgrest_filter" in gateway
    assert (
        "job_result_attach_postgrest_filter" in gateway
    ), "the API gateway's link write must apply the generated attach filter"
    proof = (root / "workflows" / "proof.py").read_text()
    assert (
        "{job_success_write_sql_predicate()}" in proof
    ), "the proof task's status writes must interpolate the generated fragment"


def test_the_generated_encodings_state_the_same_sets() -> None:
    sql = job_success_write_sql_predicate()
    postgrest = job_success_write_postgrest_filter()
    for status in ("queued", "running"):
        assert f"'{status}'" in sql
        assert status in postgrest
    assert "failed" in sql and "retryable" in sql
    assert "failed" in postgrest and "retryable" in postgrest
    attach_sql = job_result_attach_sql_predicate()
    attach_postgrest = job_result_attach_postgrest_filter()
    for status in ("queued", "running", "succeeded"):
        assert f"'{status}'" in attach_sql
        assert status in attach_postgrest
    assert "failed" in attach_sql and "retryable" in attach_sql
    assert "failed" in attach_postgrest and "retryable" in attach_postgrest

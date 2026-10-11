from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict

from tests.evals.business_eval import load_cases
from tests.evals.business_runtime_capture import _local_dsn, _plan_references
from tests.evals.business_scripted_plans import (
    SCRIPTED_INTERPRETATIONS,
    scripted_interpretation,
)


def test_every_new_owner_turn_has_an_independent_semantic_interpretation() -> None:
    cases = load_cases()
    owner_turns = {
        (case["id"], index)
        for case in cases
        for index, step in enumerate(case["steps"])
        if step["actor"] == "owner_a" and not step.get("replay")
    }
    assert owner_turns == set(SCRIPTED_INTERPRETATIONS)
    assert len(owner_turns) == 12
    assert all(
        0 < len(interpretation["records"]) <= 8
        for key, interpretation in SCRIPTED_INTERPRETATIONS.items()
        if key != ("es_cross_client_approval_injection", 0)
    )
    assert SCRIPTED_INTERPRETATIONS[("es_cross_client_approval_injection", 0)] == {
        "records": []
    }
    forbidden = {
        "actions",
        "source_ids",
        "answers_question_id",
        "from_action",
        "base_version",
        "version",
    }

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert all(
        not forbidden.intersection(keys(interpretation))
        for interpretation in SCRIPTED_INTERPRETATIONS.values()
    )


def test_scripted_interpretation_binds_only_selected_record_and_account() -> None:
    interpretation = scripted_interpretation(
        "es_owner_funds_no_receipt",
        1,
        {"draft_a": "actual-draft-id"},
    )
    assert interpretation["records"][0]["target_draft_id"] == "actual-draft-id"
    assert interpretation["records"][0]["question"]["field"] == "occurred_on"
    assert not any(
        forbidden in str(interpretation)
        for forbidden in (
            "source_ids",
            "answers_question_id",
            "from_action",
            "base_version",
            "version",
        )
    )
    with pytest.raises(KeyError, match="draft_a"):
        scripted_interpretation(
            "es_owner_funds_no_receipt",
            1,
            {},
        )
    assert scripted_interpretation("es_cross_client_approval_injection", 0, {}) == {
        "records": []
    }


def test_funding_answer_scripts_one_date_question_then_preserves_it() -> None:
    bindings = {"draft_b": "actual-draft-id", "shop_cash": "actual-account-id"}
    answered = scripted_interpretation("en_funding_correction", 1, bindings)
    corrected = scripted_interpretation("en_funding_correction", 2, bindings)
    expected = next(
        case for case in load_cases() if case["id"] == "en_funding_correction"
    )["steps"]
    assert answered["records"][0]["question"]["field"] == "occurred_on"
    assert answered["records"][0]["question"]["asked_of"] == "owner"
    assert "question" not in corrected["records"][0]
    assert (
        expected[1]["expect"]["questions"][-1]
        == expected[2]["expect"]["questions"][-1]
        == {"field": "occurred_on", "asked_of": "owner", "state": "open"}
    )
    assert [action["name"] for action in expected[1]["expect"]["actions"]] == [
        "business_propose_activity",
        "business_ask",
    ]
    assert [action["name"] for action in expected[2]["expect"]["actions"]] == [
        "business_propose_activity"
    ]


def test_bound_draft_projection_uses_actual_prior_receipts() -> None:
    reference = {"draft_id": "actual-draft-id", "base_version": 1}
    plan = {
        "actions": [
            {"action": "business_propose_activity", "draft": reference},
            {"action": "business_ask", "draft": reference},
        ]
    }
    outcomes = [
        {"outcome": "applied", "draft_id": "actual-draft-id", "version": 2},
        {"outcome": "applied", "draft_id": "actual-draft-id", "version": 2},
    ]
    assert _plan_references(plan, outcomes, {"actual-draft-id": "draft_a"}) == [
        {"action_index": 0, "existing_draft": "draft_a", "version": 1},
        {"action_index": 1, "existing_draft": "draft_a", "version": 2},
    ]
    outcomes[0]["outcome"] = "stale_version"
    with pytest.raises(ValueError, match="applied receipt"):
        _plan_references(plan, outcomes, {"actual-draft-id": "draft_a"})


def test_capture_dsn_must_be_explicit_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PGHOSTADDR", raising=False)
    monkeypatch.delenv("PGSERVICE", raising=False)
    dsn = "postgresql://user@127.0.0.1:5432/postgres"
    assert conninfo_to_dict(_local_dsn(dsn))["hostaddr"] == "127.0.0.1"
    with pytest.raises(ValueError, match="loopback"):
        _local_dsn("postgresql://user@db.example.test/postgres")
    with pytest.raises(ValueError, match="loopback"):
        _local_dsn("postgresql://user@127.0.0.1/postgres?hostaddr=198.51.100.1")
    with pytest.raises(ValueError, match="loopback"):
        _local_dsn("")
    monkeypatch.setenv("PGHOSTADDR", "198.51.100.1")
    with pytest.raises(ValueError, match="redirects"):
        _local_dsn(dsn)
    monkeypatch.delenv("PGHOSTADDR")
    monkeypatch.setenv("PGSERVICE", "remote")
    with pytest.raises(ValueError, match="redirects"):
        _local_dsn(dsn)

from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict

from tests.evals.business_eval import load_cases
from tests.evals.business_runtime_capture import _local_dsn
from tests.evals.business_scripted_plans import SCRIPTED_PLANS, scripted_plan


def test_every_new_owner_turn_has_an_independent_declared_plan() -> None:
    cases = load_cases()
    owner_turns = {
        (case["id"], index)
        for case in cases
        for index, step in enumerate(case["steps"])
        if step["actor"] == "owner_a" and not step.get("replay")
    }
    assert owner_turns == set(SCRIPTED_PLANS)
    assert len(owner_turns) == 12
    assert all(
        0 < len(actions) <= 8
        and all(action["action"].startswith("business_") for action in actions)
        for actions in SCRIPTED_PLANS.values()
    )


def test_scripted_plan_binds_only_supplied_runtime_ids() -> None:
    plan = scripted_plan(
        "es_owner_funds_no_receipt",
        1,
        {
            "draft_a": "actual-draft-id",
            "question_funding": "actual-question-id",
            "source": "actual-source-id",
        },
    )
    assert plan["actions"][0]["draft"] == {
        "draft_id": "actual-draft-id",
        "version": 1,
    }
    assert plan["actions"][0]["answers_question_id"] == "actual-question-id"
    assert plan["actions"][0]["source_ids"] == ["actual-source-id"]
    assert plan["actions"][1]["draft"]["version"] == 2
    with pytest.raises(KeyError, match="question_funding"):
        scripted_plan(
            "es_owner_funds_no_receipt",
            1,
            {"draft_a": "actual-draft-id", "source": "actual-source-id"},
        )


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

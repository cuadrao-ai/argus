from __future__ import annotations

import os

import pytest

from tests.evals.business_eval import check_case, load_cases
from tests.evals.business_runtime_capture import capture_case, scripted_interpreter

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
async def test_real_graph_executor_and_postgres_match_business_corpus(case: dict) -> None:
    if not DSN:
        pytest.skip("ARGUS_DISPOSABLE_DATABASE_URL is required for real Business capture")
    capture = await capture_case(case, dsn=DSN, interpreter_factory=scripted_interpreter)
    assert len(capture.observed_steps) == len(case["steps"])
    assert capture.step_route_receipts == [[] for _ in case["steps"]]
    assert len(capture.graph_run_ids) == sum(
        step["actor"] == "owner_a" for step in case["steps"]
    )
    assert all(capture.graph_run_ids)
    assert all(
        state["space_id"] == capture.db_namespace for state in capture.saved_states
    )
    if case["id"] == "en_replay_stale_and_current_grant":
        assert capture.replies[0] == capture.replies[1]
    assert check_case(case, capture.observed_steps) == []

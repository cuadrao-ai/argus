from __future__ import annotations

import os
from uuid import UUID

import pytest
from argus.domain.business.contracts.actions import ExplainStatus

from tests import test_business_actions_postgres as action_pg
from tests.evals.business_eval import check_case, load_cases
from tests.evals.business_runtime_capture import capture_case, scripted_interpreter
from tests.test_business_spaces_migration_postgres import event, space

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
actions = action_pg.actions
users = action_pg.users


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


def test_actual_foreign_target_read_is_denied_without_foreign_mutation(
    actions, users
) -> None:
    service, context, _ = actions
    with service.authority.pool.connection() as db:
        foreign_space = space(db, users["guest"])
        foreign_draft = event(db, users["guest"], foreign_space)
        before = db.execute(
            "select to_jsonb(item) from public.financial_import_events item where id=%s",
            (UUID(foreign_draft),),
        ).fetchone()[0]
    key, lease = action_pg.prepare(
        service, context, [ExplainStatus(draft_id=UUID(foreign_draft))]
    )
    outcome = service.execute(context, key, 0, lease=lease)
    assert outcome.outcome == "not_found"
    assert outcome.code == "business_record_not_found"
    with service.authority.pool.connection() as db:
        after = db.execute(
            "select to_jsonb(item) from public.financial_import_events item where id=%s",
            (UUID(foreign_draft),),
        ).fetchone()[0]
        receipt = db.execute(
            "select command,outcome from public.business_action_receipts"
            " where turn_key=%s",
            (key,),
        ).fetchone()
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where space_id=%s",
                (UUID(foreign_space),),
            ).fetchone()[0]
            == 0
        )
    assert after == before
    assert receipt[0]["draft_id"] == foreign_draft
    assert receipt[1] == {
        "outcome": "not_found",
        "code": "business_record_not_found",
    }

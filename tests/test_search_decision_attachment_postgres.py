"""Disposable-Postgres proof that the durable decision index holds every decision.

A computed-answer decision has no evidence lineage: it attaches to the
assistant message that carried the answer. The executed search SQL must find it
by its note, by its state, and by the answer's text, count it in the ledger and
the decision-state filter, and carry its state on the conversation. Each case
runs the real reader against the real schema, so a reader that still requires
evidence lineage fails here rather than in production.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from argus.api.decision_contract import DecisionComputation
from argus.domain.owner_scope import PERSONAL
from faker import Faker
from psycopg.types.json import Jsonb
from test_search_postgres import (
    _connect,
    _insert_conversation,
    _insert_message,
    _ranked,
    _reader,
    search_identities,  # noqa: F401 - fixture reused by name
)

fake = Faker()
pytestmark = pytest.mark.skipif(
    not os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip(),
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

ANSWER = "Nine months of 5,000 a month reaches the tablet in December."
NOTE = "Commit to the savings plan."
ONE_PLAN = {"kind": "savings_projection", "inputs": {"monthly_amount": 5000, "months": 9}}
TWO_PLANS = {
    "calculations": [
        ONE_PLAN,
        {"kind": "savings_projection", "inputs": {"monthly_amount": 4000, "months": 12}},
    ]
}


def _insert_computed_answer_decision(
    cursor: Any,
    *,
    user_id: UUID,
    conversation_id: UUID,
    timestamp: datetime,
    decision_state: str = "promising",
    computation: dict[str, Any] | None = None,
) -> dict[str, UUID]:
    stored = computation or ONE_PLAN
    message_id = _insert_message(
        cursor,
        user_id=user_id,
        conversation_id=conversation_id,
        timestamp=timestamp,
        role="assistant",
        content=ANSWER,
        metadata={"computation": stored},
    )
    decision_id = uuid4()
    cursor.execute(
        """
        insert into public.decision_notes (
            id, user_id, source_conversation_id, source_message_id, computation,
            decision_state, note, created_at, updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            decision_id,
            user_id,
            conversation_id,
            message_id,
            Jsonb(stored),
            decision_state,
            NOTE,
            timestamp,
            timestamp,
        ),
    )
    return {"message": message_id, "decision": decision_id}


@pytest.mark.parametrize(
    "query",
    ["savings plan", "tablet in december", "promising"],
    ids=["by_note", "by_answer_text", "by_state"],
)
def test_search_finds_a_computed_answer_decision_through_its_attachment(
    search_identities,  # noqa: F811 - pytest fixture
    query: str,
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title=fake.sentence(nb_words=3),
        )
        _insert_computed_answer_decision(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now,
        )

    reader, _pool = _reader()
    result = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query=query,
        source_limit=4,
        include_ledger_groups=True,
    )
    ranked = _ranked(result.rows, query)

    assert [item.id for _, item in ranked] == [str(conversation_id)]
    item = ranked[0][1]
    assert item.match.layer == "decision"
    assert item.decision_states == ("promising",)
    assert item.dossier is None
    assert item.total_runs == 0
    assert result.ledger_counts == {
        "promising": 1,
        "watching": 0,
        "rejected": 0,
        "revisit_later": 0,
    }


def test_decision_state_filter_and_recall_carry_a_computed_answer_decision(
    search_identities,  # noqa: F811 - pytest fixture
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=now,
            title="Tablet savings",
        )
        rows = _insert_computed_answer_decision(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now,
            decision_state="watching",
        )

    reader, _pool = _reader()
    kept = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="tablet",
        source_limit=4,
        decision_state="watching",
    )
    dropped = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="tablet",
        source_limit=4,
        decision_state="rejected",
    )
    recalled = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="",
        source_limit=4,
        conversation_ids=[str(conversation_id)],
    )

    assert [item.id for _, item in _ranked(kept.rows, "tablet")] == [str(conversation_id)]
    assert _ranked(dropped.rows, "tablet") == []
    recalled_decisions = recalled.rows["decisions"]
    assert [row["id"] for row in recalled_decisions] == [str(rows["decision"])]
    assert recalled_decisions[0]["source_message_id"] == str(rows["message"])
    assert recalled_decisions[0]["computation"]["kind"] == "savings_projection"
    assert recalled_decisions[0]["evidence_artifact_id"] is None
    assert ANSWER in str(recalled_decisions[0].get("attachment_text"))


def test_one_decision_over_every_option_an_answer_weighed_is_found_and_recalled(
    search_identities,  # noqa: F811 - pytest fixture
) -> None:
    owner_id = search_identities["owner"]
    now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    with _connect() as connection, connection.cursor() as cursor:
        conversation_id = _insert_conversation(
            cursor, user_id=owner_id, timestamp=now, title="Two savings plans"
        )
        rows = _insert_computed_answer_decision(
            cursor,
            user_id=owner_id,
            conversation_id=conversation_id,
            timestamp=now,
            computation=TWO_PLANS,
        )

    reader, _pool = _reader()
    found = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="savings plan",
        source_limit=4,
        include_ledger_groups=True,
    )
    assert [item.id for _, item in _ranked(found.rows, "savings plan")] == [
        str(conversation_id)
    ]
    recalled = reader.search_rows(
        scope=PERSONAL,
        user_id=str(owner_id),
        query="",
        source_limit=4,
        conversation_ids=[str(conversation_id)],
    )
    decisions = recalled.rows["decisions"]
    assert [row["id"] for row in decisions] == [str(rows["decision"])]
    assert decisions[0]["computation"] == TWO_PLANS
    stored = DecisionComputation.model_validate(decisions[0]["computation"])
    assert stored.kinds == ["savings_projection", "savings_projection"]

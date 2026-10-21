"""Real-Postgres proof of the computed-answer reads Search and comparisons use.

Every read runs through the real ``SupabaseGateway`` over PostgREST against the
disposable local stack the guest-release-gates job resets (the
``tests/test_*_postgres.py`` glob carries this file without a workflow edit).
Rows are seeded with psycopg under the ``search_identities`` owner and
stranger, and each computed answer stores the real calculation card and the
marker derived from it, so the JSON paths PostgREST filters on are the ones
production writes. A computed answer in a soft-deleted conversation does not
count under its asset.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` plus ``ARGUS_LOCAL_SUPABASE_URL`` and
``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY`` to run locally.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from argus.api import state as api_state
from argus.api.decision_contract import DecisionComputation
from argus.api.schemas import User
from argus.api.search_computed import with_computed_results
from argus.domain.answer_dossiers import computed_answer_cards
from argus.domain.computation_marker import (
    computation_from_tool_card,
    computation_from_tool_cards,
)
from argus.domain.owner_scope import PERSONAL
from argus.domain.tool_contracts import ToolResultCard
from psycopg.types.json import Jsonb
from test_search_postgres import (
    _connect,
    _insert_conversation,
    _insert_message,
    search_identities,  # noqa: F401 - fixture reused by name
)

from tests.domain.calculations import WORKED_ARGUMENTS
from tests.domain.calculations.support import run_calculation

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
LOCAL_URL = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip()
LOCAL_SERVICE_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip()

pytestmark = pytest.mark.skipif(
    not (DSN and LOCAL_URL and LOCAL_SERVICE_KEY),
    reason="disposable local Supabase is not configured",
)

NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
MESSAGE_COLUMNS = {"id", "conversation_id", "role", "content", "metadata", "created_at"}


def _gateway():
    from argus.domain.supabase_gateway import SupabaseGateway

    from supabase import create_client

    return SupabaseGateway(client=create_client(LOCAL_URL, LOCAL_SERVICE_KEY))


def _computed_answer(kind: str, **changes: Any) -> dict[str, Any]:
    """The metadata a computed answer stores: its card and the marker derived from it."""
    card = run_calculation(kind, {**WORKED_ARGUMENTS[kind], **changes}).model_copy(
        update={"artifact_id": str(uuid4())}
    )
    computation = computation_from_tool_card(card)
    assert computation is not None, kind
    return {
        "tool_result_cards": [card.model_dump(mode="json")],
        "computation": computation.model_dump(mode="json"),
    }


def _message(
    cursor: Any,
    user_id: UUID,
    conversation_id: UUID,
    minutes_ago: int,
    metadata: dict[str, Any],
    *,
    role: str = "assistant",
    content: str = "Apple trades at 25 times earnings.",
) -> UUID:
    return _insert_message(
        cursor,
        user_id=user_id,
        conversation_id=conversation_id,
        timestamp=NOW - timedelta(minutes=minutes_ago),
        role=role,
        content=content,
        metadata=metadata,
    )


def _insert_answer_decision(
    cursor: Any,
    *,
    user_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    computation: dict[str, Any],
    decision_state: str,
    timestamp: datetime,
) -> None:
    cursor.execute(
        """
        insert into public.decision_notes (
            id, user_id, source_conversation_id, source_message_id, computation,
            decision_state, created_at, updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid4(),
            user_id,
            conversation_id,
            message_id,
            Jsonb(computation),
            decision_state,
            timestamp,
            timestamp,
        ),
    )


def _user(user_id: UUID) -> User:
    return User(id=str(user_id), email=None, created_at=NOW, updated_at=NOW)


def test_symbol_rows_are_the_owners_live_asset_answers_and_the_asset_row_counts_them(
    search_identities,  # noqa: F811 - pytest fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    apple = _computed_answer("price_multiple")
    loan = _computed_answer("time_value")
    assert apple["computation"]["symbols"] == ["AAPL"]
    assert "symbols" not in loan["computation"], "an asset-less marker omits symbols"
    with _connect() as connection, connection.cursor() as cursor:
        older = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=NOW - timedelta(days=2),
            title="Apple multiple",
        )
        newer = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=NOW - timedelta(days=1),
            title="Apple again",
        )
        deleted = _insert_conversation(
            cursor,
            user_id=owner_id,
            timestamp=NOW - timedelta(days=1),
            title="Deleted Apple",
            deleted=True,
        )
        foreign = _insert_conversation(
            cursor, user_id=other_id, timestamp=NOW, title="Foreign Apple"
        )
        oldest_answer = _message(cursor, owner_id, older, 180, apple)
        newest_answer = _message(cursor, owner_id, newer, 60, apple)
        _message(cursor, owner_id, newer, 10, loan, content="The loan costs 1,199.")
        _message(cursor, owner_id, newer, 5, apple, role="user")
        _message(cursor, owner_id, older, 5, {}, content="No computation here.")
        deleted_answer = _message(cursor, owner_id, deleted, 1, apple)
        _message(cursor, other_id, foreign, 1, apple)
        _insert_answer_decision(
            cursor,
            user_id=owner_id,
            conversation_id=newer,
            message_id=newest_answer,
            computation=apple["computation"],
            decision_state="watching",
            timestamp=NOW - timedelta(minutes=30),
        )
        _insert_answer_decision(
            cursor,
            user_id=owner_id,
            conversation_id=deleted,
            message_id=deleted_answer,
            computation=apple["computation"],
            decision_state="rejected",
            timestamp=NOW,
        )

    gateway = _gateway()
    rows = gateway.computed_answer_rows_for_symbols(scope=PERSONAL, user_id=str(owner_id))
    assert [row["id"] for row in rows] == [str(newest_answer), str(oldest_answer)]
    assert all(set(row) == MESSAGE_COLUMNS for row in rows)
    assert all(row["metadata"]["computation"]["symbols"] == ["AAPL"] for row in rows)
    scoped = gateway.computed_answer_rows_for_symbols(
        scope=PERSONAL, user_id=str(owner_id), conversation_id=str(older)
    )
    assert [row["id"] for row in scoped] == [str(oldest_answer)]
    assert (
        gateway.computed_answer_rows_for_symbols(
            scope=PERSONAL, user_id=str(owner_id), conversation_id=str(deleted)
        )
        == []
    ), "a soft-deleted conversation's answer is not an asset result"

    monkeypatch.setattr(api_state, "supabase_gateway", gateway)
    owner = _user(owner_id)
    rollup = with_computed_results(
        None, scope=PERSONAL, user=owner, query="AAPL", guest_conversation_id=None
    )
    assert rollup is not None
    assert rollup.model_dump() == {
        "type": "asset_rollup",
        "symbol": "AAPL",
        "run_count": 0,
        "result_count": 2,
        "decision_counts": {
            "promising": 0,
            "watching": 1,
            "rejected": 0,
            "revisit_later": 0,
        },
        "last_touched_at": NOW - timedelta(minutes=30),
    }
    guest = with_computed_results(
        None, scope=PERSONAL, user=owner, query="aapl", guest_conversation_id=str(older)
    )
    assert guest is not None
    assert (guest.result_count, guest.decision_counts.watching) == (1, 0)
    assert guest.last_touched_at == NOW - timedelta(minutes=180)


def test_latest_computed_answer_per_owned_conversation_and_the_question_before_it(
    search_identities,  # noqa: F811 - pytest fixture
) -> None:
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    at_150 = _computed_answer("price_multiple")
    at_180 = _computed_answer("price_multiple", price=180)
    with _connect() as connection, connection.cursor() as cursor:
        asked = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="Apple twice"
        )
        plain = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="Plain chat"
        )
        foreign = _insert_conversation(
            cursor, user_id=other_id, timestamp=NOW, title="Foreign Apple"
        )
        first_question = _message(
            cursor, owner_id, asked, 60, {}, role="user", content="Is Apple expensive?"
        )
        _message(cursor, owner_id, asked, 59, at_150)
        second_question = _message(
            cursor, owner_id, asked, 40, {}, role="user", content="And at 180?"
        )
        second_answer = _message(cursor, owner_id, asked, 39, at_180)
        _message(cursor, owner_id, asked, 20, {}, role="user", content="And Microsoft?")
        _message(cursor, owner_id, asked, 19, {}, content="A plain reply afterwards.")
        _message(cursor, owner_id, plain, 10, {}, content="No computation here.")
        _message(cursor, other_id, foreign, 5, at_180)

    gateway = _gateway()
    latest = gateway.latest_computed_answers(
        user_id=str(owner_id),
        conversation_ids=[str(asked), str(plain), str(foreign)],
    )
    assert list(latest) == [str(asked)]
    answer = latest[str(asked)]
    assert answer["id"] == str(second_answer)
    assert answer["metadata"]["computation"]["inputs"]["price"] == 180
    assert (
        gateway.latest_computed_answers(
            user_id=str(other_id), conversation_ids=[str(asked)]
        )
        == {}
    )
    assert (
        gateway.latest_computed_answers(user_id=str(owner_id), conversation_ids=[]) == {}
    )

    question = gateway.question_before_message(
        user_id=str(owner_id),
        conversation_id=str(asked),
        created_at=answer["created_at"],
    )
    assert question is not None
    assert (question["id"], question["content"]) == (str(second_question), "And at 180?")
    earlier = gateway.question_before_message(
        user_id=str(owner_id),
        conversation_id=str(asked),
        created_at=(NOW - timedelta(minutes=59)).isoformat(),
    )
    assert earlier is not None and earlier["id"] == str(first_question)
    assert (
        gateway.question_before_message(
            user_id=str(other_id),
            conversation_id=str(asked),
            created_at=answer["created_at"],
        )
        is None
    )


def test_answers_of_one_kind_are_the_owners_newest_in_live_conversations(
    search_identities,  # noqa: F811 - pytest fixture
) -> None:
    owner_id = search_identities["owner"]
    other_id = search_identities["other"]
    apple = _computed_answer("price_multiple")
    loan = _computed_answer("time_value")
    with _connect() as connection, connection.cursor() as cursor:
        first = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="First valuation"
        )
        second = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="Second valuation"
        )
        deleted = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="Deleted", deleted=True
        )
        foreign = _insert_conversation(
            cursor, user_id=other_id, timestamp=NOW, title="Foreign valuation"
        )
        oldest = _message(cursor, owner_id, first, 50, apple)
        _message(cursor, owner_id, deleted, 40, apple)
        middle = _message(cursor, owner_id, second, 30, apple)
        newest = _message(cursor, owner_id, first, 20, apple)
        loan_answer = _message(cursor, owner_id, second, 10, loan)
        _message(cursor, owner_id, first, 5, apple, role="user")
        _message(cursor, other_id, foreign, 1, apple)

    gateway = _gateway()
    listed = gateway.computed_answers_of_kind(
        scope=PERSONAL, user_id=str(owner_id), kind="price_multiple", limit=10
    )
    assert [row["id"] for row in listed] == [str(newest), str(middle), str(oldest)]
    assert {row["metadata"]["computation"]["kind"] for row in listed} == {
        "price_multiple"
    }
    bounded = gateway.computed_answers_of_kind(
        scope=PERSONAL, user_id=str(owner_id), kind="price_multiple", limit=2
    )
    assert [row["id"] for row in bounded] == [str(newest), str(middle)]
    loans = gateway.computed_answers_of_kind(
        scope=PERSONAL, user_id=str(owner_id), kind="time_value", limit=10
    )
    assert [row["id"] for row in loans] == [str(loan_answer)]


def _weighing(*answers: dict[str, Any]) -> dict[str, Any]:
    """The metadata an answer weighing options stores: every card and one marker."""
    cards = [
        ToolResultCard.model_validate(card).model_copy(update={"call_id": str(uuid4())})
        for answer in answers
        for card in answer["tool_result_cards"]
    ]
    computation = computation_from_tool_cards(cards)
    assert computation is not None
    return {
        "tool_result_cards": [card.model_dump(mode="json") for card in cards],
        "computation": computation.model_dump(mode="json"),
    }


def test_an_answer_weighing_options_reads_back_whole_and_is_not_one_kind(
    search_identities,  # noqa: F811 - pytest fixture
) -> None:
    owner_id = search_identities["owner"]
    options = _weighing(
        _computed_answer("price_multiple"),
        _computed_answer("price_multiple", symbol="MSFT", price=410),
    )
    single = _computed_answer("price_multiple")
    assert set(options["computation"]) == {"calculations", "symbols"}
    assert options["computation"]["symbols"] == ["AAPL", "MSFT"]
    with _connect() as connection, connection.cursor() as cursor:
        weighed = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="Apple or Microsoft"
        )
        alone = _insert_conversation(
            cursor, user_id=owner_id, timestamp=NOW, title="Apple alone"
        )
        options_answer = _message(cursor, owner_id, weighed, 30, options)
        single_answer = _message(cursor, owner_id, alone, 20, single)
        _insert_answer_decision(
            cursor,
            user_id=owner_id,
            conversation_id=weighed,
            message_id=options_answer,
            computation=options["computation"],
            decision_state="promising",
            timestamp=NOW - timedelta(minutes=10),
        )

    gateway = _gateway()
    latest = gateway.latest_computed_answers(
        user_id=str(owner_id), conversation_ids=[str(weighed)]
    )
    row = latest[str(weighed)]
    assert row["id"] == str(options_answer)
    cards = computed_answer_cards(row)
    assert cards is not None and len(cards) == 2
    marker = DecisionComputation.model_validate(row["metadata"]["computation"])
    assert marker.kinds == ["price_multiple", "price_multiple"]
    symbol_rows = gateway.computed_answer_rows_for_symbols(
        scope=PERSONAL, user_id=str(owner_id), conversation_id=str(weighed)
    )
    assert [symbol_row["id"] for symbol_row in symbol_rows] == [str(options_answer)]
    listed = gateway.computed_answers_of_kind(
        scope=PERSONAL, user_id=str(owner_id), kind="price_multiple", limit=10
    )
    assert [listed_row["id"] for listed_row in listed] == [
        str(single_answer)
    ], "an answer weighing options is not a result of one kind"
    decisions = gateway.current_decisions_for_attachments(
        user_id=str(owner_id), artifact_ids=[], message_ids=[str(options_answer)]
    )
    stored = decisions[str(options_answer)].computation
    assert stored is not None and stored == marker

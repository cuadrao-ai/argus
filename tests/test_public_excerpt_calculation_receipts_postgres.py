"""Real-Postgres proof that a computed answer is a receipt kind of its own.

``20260912190000_share_calculation_receipts.sql`` replaces the inline kind
check from ``20260909183646_share_answer_receipt_selections.sql`` with one that
also admits ``calculation``. The guarantees around it are the database's, so
they are proven here: a calculation receipt passes every snapshot trigger, an
unknown kind is refused, one check guards the column, the kind stays frozen,
and deleting the answer revokes the receipt. Every case rolls back.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with every checked-in migration applied; never point it at shared or
production data.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from argus.api.decision_contract import DecisionComputation
from argus.api.public_excerpt_schemas import PublicExcerptCalculationTurn
from argus.domain.computation_marker import (
    computation_from_tool_card,
    computation_from_tool_cards,
)
from argus.domain.public_excerpt_turns import _public_calculation

from tests.domain.calculations import WORKED_ARGUMENTS
from tests.domain.calculations.support import run_calculation
from tests.test_public_excerpt_snapshots_postgres import _public_id

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

psycopg = pytest.importorskip("psycopg")

DIGEST = "a" * 64
KIND_CHECK = "public_excerpt_snapshots_kind_check"


def _computed_answer_metadata() -> dict[str, Any]:
    """The metadata a computed answer stores: its card and the marker derived from it."""
    card = run_calculation("price_multiple", WORKED_ARGUMENTS["price_multiple"])
    computation = computation_from_tool_card(card)
    assert computation is not None
    return {
        "tool_result_cards": [card.model_dump(mode="json")],
        "computation": computation.model_dump(mode="json"),
    }


class _ComputedAnswer:
    """One owner with a live conversation whose assistant turn is a computed answer."""

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor
        self.owner_id = uuid4()
        self.conversation_id = uuid4()
        self.message_id = uuid4()

    def seed(self, metadata: dict[str, Any] | None = None) -> _ComputedAnswer:
        from psycopg.types.json import Jsonb

        email = f"calculation-receipt-{self.owner_id}@example.test"
        self.cursor.execute(
            "insert into auth.users (id, email) values (%s, %s)",
            (self.owner_id, email),
        )
        self.cursor.execute(
            "insert into public.profiles (id, email) values (%s, %s)",
            (self.owner_id, email),
        )
        self.cursor.execute(
            "insert into public.conversations (id, user_id, title) values (%s, %s, %s)",
            (self.conversation_id, self.owner_id, "Apple valuation"),
        )
        self.cursor.execute(
            "insert into public.messages"
            " (id, user_id, conversation_id, role, content, metadata)"
            " values (%s, %s, %s, 'assistant', %s, %s)",
            (
                self.message_id,
                self.owner_id,
                self.conversation_id,
                "Apple trades at 25 times earnings.",
                Jsonb(metadata or _computed_answer_metadata()),
            ),
        )
        return self

    def insert_receipt(self, *, kind: str, payload: dict[str, Any] | None = None) -> UUID:
        from psycopg.types.json import Jsonb

        message_ids = [self.message_id]
        selection_key = hashlib.sha256(
            json.dumps(
                sorted(str(value) for value in message_ids), separators=(",", ":")
            ).encode()
        ).hexdigest()
        self.cursor.execute(
            "insert into public.public_excerpt_snapshots"
            " (public_id, owner_id, source_conversation_id, source_message_ids,"
            "  selection_key, kind, title, payload, payload_digest)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " returning id",
            (
                _public_id(),
                self.owner_id,
                self.conversation_id,
                message_ids,
                selection_key,
                kind,
                "Is Apple expensive at this P/E?",
                Jsonb(payload or {}),
                DIGEST,
            ),
        )
        return self.cursor.fetchone()[0]


def test_a_calculation_receipt_is_created_for_an_owned_computed_answer() -> None:
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                answer = _ComputedAnswer(cursor).seed()
                cursor.execute("set local role service_role")
                receipt_id = answer.insert_receipt(kind="calculation")
                cursor.execute(
                    "select kind, source_conversation_id, source_message_ids,"
                    " revoked_at from public.public_excerpt_snapshots where id = %s",
                    (receipt_id,),
                )
                assert cursor.fetchone() == (
                    "calculation",
                    answer.conversation_id,
                    [answer.message_id],
                    None,
                )
        finally:
            connection.rollback()


def test_an_unknown_receipt_kind_is_refused_by_the_kind_check() -> None:
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                answer = _ComputedAnswer(cursor).seed()
                with pytest.raises(psycopg.errors.CheckViolation) as failure:
                    answer.insert_receipt(kind="bogus")
                assert failure.value.diag.constraint_name == KIND_CHECK
        finally:
            connection.rollback()


def test_exactly_one_check_guards_the_kind_and_it_admits_calculation() -> None:
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select checked.conname, pg_get_constraintdef(checked.oid)
                      from pg_constraint as checked
                      join pg_attribute as attribute
                        on attribute.attrelid = checked.conrelid
                       and attribute.attnum = any(checked.conkey)
                     where checked.conrelid
                           = 'public.public_excerpt_snapshots'::regclass
                       and checked.contype = 'c'
                       and attribute.attname = 'kind'
                    """
                )
                checks = cursor.fetchall()
                assert len(checks) == 1, checks
                name, definition = checks[0]
                assert name == KIND_CHECK
                for kind in ("backtest", "research_answer", "calculation", "mixed"):
                    assert f"'{kind}'" in definition, definition
        finally:
            connection.rollback()


def test_a_calculation_receipt_cannot_be_rewritten_as_mixed() -> None:
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                answer = _ComputedAnswer(cursor).seed()
                receipt_id = answer.insert_receipt(kind="calculation")
                with pytest.raises(psycopg.errors.CheckViolation) as failure:
                    with connection.transaction():
                        cursor.execute(
                            "update public.public_excerpt_snapshots"
                            " set kind = 'mixed' where id = %s",
                            (receipt_id,),
                        )
                assert (
                    "public_excerpt_snapshots immutable fields cannot be updated"
                    in str(failure.value)
                )
                cursor.execute(
                    "select kind from public.public_excerpt_snapshots where id = %s",
                    (receipt_id,),
                )
                assert cursor.fetchone()[0] == "calculation"
        finally:
            connection.rollback()


def test_deleting_the_computed_answer_revokes_its_calculation_receipt() -> None:
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                answer = _ComputedAnswer(cursor).seed()
                receipt_id = answer.insert_receipt(kind="calculation")
                cursor.execute(
                    "delete from public.messages where id = %s", (answer.message_id,)
                )
                cursor.execute(
                    "select revoked_at, revocation_reason, source_message_ids"
                    " from public.public_excerpt_snapshots where id = %s",
                    (receipt_id,),
                )
                revoked_at, reason, message_ids = cursor.fetchone()
                assert revoked_at is not None
                assert reason == "source_deleted"
                assert message_ids == [
                    answer.message_id
                ], "provenance outlives the source"
        finally:
            connection.rollback()


def test_a_receipt_freezes_every_calculation_of_an_answer_weighing_options() -> None:
    cards = [
        run_calculation(
            "price_multiple", {**WORKED_ARGUMENTS["price_multiple"], **changes}
        ).model_copy(update={"artifact_id": str(uuid4()), "call_id": str(uuid4())})
        for changes in ({}, {"symbol": "MSFT", "price": 410})
    ]
    computation = computation_from_tool_cards(cards)
    assert computation is not None
    turn = PublicExcerptCalculationTurn(
        question="Apple or Microsoft at these multiples?",
        calculations=[_public_calculation(card) for card in cards],
        computed_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                answer = _ComputedAnswer(cursor).seed(
                    metadata={
                        "tool_result_cards": [
                            card.model_dump(mode="json") for card in cards
                        ],
                        "computation": computation.model_dump(mode="json"),
                    }
                )
                cursor.execute(
                    "select metadata from public.messages where id = %s",
                    (answer.message_id,),
                )
                marker = DecisionComputation.model_validate(
                    cursor.fetchone()[0]["computation"]
                )
                assert marker.kinds == ["price_multiple", "price_multiple"]
                cursor.execute("set local role service_role")
                receipt_id = answer.insert_receipt(
                    kind="calculation", payload=turn.model_dump(mode="json")
                )
                cursor.execute(
                    "select payload from public.public_excerpt_snapshots where id = %s",
                    (receipt_id,),
                )
                frozen = PublicExcerptCalculationTurn.model_validate(cursor.fetchone()[0])
                assert len(frozen.calculations) == 2
                assert frozen == turn
        finally:
            connection.rollback()

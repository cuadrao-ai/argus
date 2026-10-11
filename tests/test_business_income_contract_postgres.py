from __future__ import annotations

import pytest
from argus.domain.business.contracts.actions import (
    ApproveIncome,
    IncomeApprovalCommand,
    canonical_input_hash,
)
from faker import Faker
from psycopg import Connection, errors, sql
from psycopg.types.json import Jsonb

from tests import test_business_contracts_postgres as shared

fake = Faker()
users = shared.users
db = shared.db
client = shared.client
pytestmark = shared.pytestmark


def income_command(client: dict[str, str]) -> IncomeApprovalCommand:
    return IncomeApprovalCommand(
        draft_id=client["draft"],
        request=ApproveIncome(action="record_income", version=1),
    )


def insert_receipt(
    db: Connection,
    client: dict[str, str],
    command: dict,
    *,
    actor: dict[str, str] | None = None,
    turn: str | None = None,
    index: int | None = None,
) -> str:
    key = fake.sha256()
    db.execute(
        "insert into public.business_action_receipts"
        " (space_id,actor_id,actor,idempotency_key,input_hash,command,turn_key,action_index)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            client["id"],
            client["owner"],
            Jsonb(actor if actor is not None else shared.actor_provenance(client)),
            key,
            canonical_input_hash(income_command(client)),
            Jsonb(command),
            turn,
            index,
        ),
    )
    return key


def test_income_receipt_settles_once_with_original_human_and_request(db, client):
    command = income_command(client)
    db.execute("set local role service_role")
    key = insert_receipt(db, client, command.model_dump(mode="json"))
    unknown = {"outcome": "outcome_unknown", "code": "business_recording_unsettled"}
    result = {"outcome": "applied", "draft_id": client["draft"], "version": 1}
    for outcome in (unknown, result):
        db.execute(
            "update public.business_action_receipts set outcome=%s where idempotency_key=%s",
            (Jsonb(outcome), key),
        )
    assert db.execute(
        "select command,input_hash,actor,turn_key,action_index,outcome"
        " from public.business_action_receipts where idempotency_key=%s",
        (key,),
    ).fetchone() == (
        command.model_dump(mode="json"),
        canonical_input_hash(command),
        shared.actor_provenance(client),
        None,
        None,
        result,
    )
    with pytest.raises(errors.UniqueViolation), db.transaction():
        db.execute(
            "insert into public.business_action_receipts"
            " select * from public.business_action_receipts where idempotency_key=%s",
            (key,),
        )
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "update public.business_action_receipts set outcome=%s where idempotency_key=%s",
            (Jsonb(unknown), key),
        )


@pytest.mark.parametrize("kind", ["owner_via_agent", "extractor"])
def test_income_receipt_requires_actual_human(db, client, kind):
    actor = {**shared.actor_provenance(client), "actor_kind": kind}
    db.execute("set local role service_role")
    with (
        pytest.raises(
            errors.CheckViolation, match="business_action_receipts_income_human"
        ),
        db.transaction(),
    ):
        insert_receipt(
            db, client, income_command(client).model_dump(mode="json"), actor=actor
        )


def test_income_cannot_be_inserted_as_a_matching_model_plan_action(db, client):
    command = income_command(client).model_dump(mode="json")
    turn = shared.add_turn(db, client, [command])
    db.execute("set local role service_role")
    with (
        pytest.raises(
            errors.CheckViolation, match="business_action_receipts_income_human"
        ),
        db.transaction(),
    ):
        insert_receipt(db, client, command, turn=turn, index=0)


@pytest.mark.parametrize(
    "change", ["grant_id", "issuer_id", "actor_id", "version", "draft_id", "input_hash"]
)
def test_income_receipt_identity_cannot_change_during_recovery(db, client, change):
    command = income_command(client).model_dump(mode="json")
    key = insert_receipt(db, client, command)
    if change in {"version", "draft_id"}:
        column = "command"
        value = (
            {**command, "draft_id": fake.uuid4()}
            if change == "draft_id"
            else {**command, "request": {"action": "record_income", "version": 2}}
        )
        value = Jsonb(value)
    elif change == "input_hash":
        column, value = "input_hash", fake.sha256()
    else:
        column, value = (
            "actor",
            Jsonb({**shared.actor_provenance(client), change: fake.uuid4()}),
        )
    db.execute("set local role service_role")
    with (
        pytest.raises(errors.CheckViolation, match="identity_immutable"),
        db.transaction(),
    ):
        db.execute(
            sql.SQL(
                "update public.business_action_receipts set {}=%s where idempotency_key=%s"
            ).format(sql.Identifier(column)),
            (value, key),
        )


@pytest.mark.parametrize("action", ["review_draft", "approve_expense", "capture_note"])
def test_income_extension_keeps_existing_human_receipts(db, client, action):
    request = {
        "review_draft": {"version": 1, "facts": {"amount": {"state": "unknown"}}},
        "approve_expense": {"version": 1, "action": "record_expense"},
        "capture_note": {"text": fake.sentence()},
    }[action]
    db.execute("set local role service_role")
    insert_receipt(
        db, client, {"action": action, "draft_id": client["draft"], "request": request}
    )


@pytest.mark.parametrize(
    "command", [{}, {"action": "unknown"}, {"action": "business_read_context"}]
)
def test_income_extension_keeps_unplanned_agent_commands_blocked(db, client, command):
    db.execute("set local role service_role")
    with pytest.raises(errors.CheckViolation), db.transaction():
        insert_receipt(db, client, command)


def test_income_extension_preserves_turn_pairing_constraint(db, client):
    db.execute("set local role service_role")
    with (
        pytest.raises(errors.CheckViolation, match="business_action_receipts_check1"),
        db.transaction(),
    ):
        insert_receipt(db, client, {"action": "review_draft"}, index=0)


def test_income_receipt_rejects_foreign_actual_actor(db, client, users):
    db.execute("set local role service_role")
    with pytest.raises(errors.CheckViolation), db.transaction():
        insert_receipt(
            db,
            client,
            income_command(client).model_dump(mode="json"),
            actor={**shared.actor_provenance(client), "actor_id": users["other"]},
        )

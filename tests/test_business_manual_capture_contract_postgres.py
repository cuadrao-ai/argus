from __future__ import annotations

import pytest
from argus.domain.business.contracts.actions import (
    CaptureCommand,
    CaptureNote,
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


def capture_command() -> CaptureCommand:
    return CaptureCommand(request=CaptureNote(text=f" \t{fake.sentence()}\n"))


def insert_receipt(
    db: Connection,
    client: dict[str, str],
    command: dict,
    *,
    actor: dict[str, str] | None = None,
    turn: str | None = None,
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
            canonical_input_hash(CaptureCommand.model_validate(command))
            if command.get("action") == "capture_note"
            else fake.sha256(),
            Jsonb(command),
            turn,
            0 if turn is not None else None,
        ),
    )
    return key


def test_human_capture_receipt_preserves_original_command_without_a_turn(
    db: Connection, client: dict[str, str]
) -> None:
    command = capture_command()
    payload = command.model_dump(mode="json", exclude_none=True)
    db.execute("set local role service_role")
    key = insert_receipt(db, client, payload)
    result = {"outcome": "applied", "draft_id": client["draft"], "version": 1}
    db.execute(
        "update public.business_action_receipts set outcome=%s where idempotency_key=%s",
        (Jsonb(result), key),
    )
    assert db.execute(
        "select command,input_hash,actor,turn_key,action_index,outcome"
        " from public.business_action_receipts where idempotency_key=%s",
        (key,),
    ).fetchone() == (
        payload,
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


@pytest.mark.parametrize("actor_kind", ["owner_via_agent", "extractor"])
def test_capture_without_turn_rejects_nonhuman_actor(
    db: Connection, client: dict[str, str], actor_kind: str
) -> None:
    actor = {**shared.actor_provenance(client), "actor_kind": actor_kind}
    db.execute("set local role service_role")
    with (
        pytest.raises(
            errors.CheckViolation, match="business_action_receipts_capture_human"
        ),
        db.transaction(),
    ):
        insert_receipt(db, client, capture_command().model_dump(mode="json"), actor=actor)


def test_capture_cannot_be_smuggled_through_matching_raw_plan(
    db: Connection, client: dict[str, str]
) -> None:
    command = capture_command().model_dump(mode="json")
    turn = shared.add_turn(db, client, [command])
    db.execute("set local role service_role")
    with (
        pytest.raises(
            errors.CheckViolation, match="business_action_receipts_capture_human"
        ),
        db.transaction(),
    ):
        insert_receipt(db, client, command, turn=turn)


@pytest.mark.parametrize(
    "change", ["grant_id", "issuer_id", "actor_id", "text", "input_hash"]
)
def test_capture_receipt_provenance_and_input_remain_immutable(
    db: Connection, client: dict[str, str], change: str
) -> None:
    command = capture_command().model_dump(mode="json")
    actor = shared.actor_provenance(client)
    key = insert_receipt(db, client, command)
    if change == "text":
        column = "command"
        value = Jsonb({**command, "request": {"text": fake.sentence()}})
    elif change == "input_hash":
        column, value = "input_hash", fake.sha256()
    else:
        column, value = "actor", Jsonb({**actor, change: fake.uuid4()})
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


@pytest.mark.parametrize(
    "command", [{}, {"action": "unknown"}, {"action": "business_read_context"}]
)
def test_capture_extension_keeps_other_unplanned_actions_blocked(
    db: Connection, client: dict[str, str], command: dict
) -> None:
    db.execute("set local role service_role")
    with pytest.raises(errors.CheckViolation), db.transaction():
        insert_receipt(db, client, command)


@pytest.mark.parametrize("action", ["review_draft", "approve_expense"])
def test_existing_human_receipts_remain_valid(
    db: Connection, client: dict[str, str], action: str
) -> None:
    request = (
        {"version": 1, "facts": {"amount": {"state": "unknown"}}}
        if action == "review_draft"
        else {"version": 1, "action": "record_expense"}
    )
    db.execute("set local role service_role")
    insert_receipt(
        db, client, {"action": action, "draft_id": client["draft"], "request": request}
    )


def test_capture_receipt_rejects_another_actual_actor(
    db: Connection, client: dict[str, str], users: dict[str, str]
) -> None:
    actor = {**shared.actor_provenance(client), "actor_id": users["other"]}
    db.execute("set local role service_role")
    with pytest.raises(errors.CheckViolation), db.transaction():
        insert_receipt(db, client, capture_command().model_dump(mode="json"), actor=actor)

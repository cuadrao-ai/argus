from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.transactions import transaction
from psycopg.errors import CheckViolation
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared

actions = shared.actions
users = shared.users
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


@pytest.mark.parametrize(
    "command",
    [
        "capture_note",
        "delete_document",
        "reopen_draft",
        "restore_document",
        "review_draft",
        "unknown_document_command",
    ],
)
def test_document_actions_join_existing_human_commands(actions, command):
    service, context, _ = actions
    with transaction(service.authority, context) as tx:
        sql = (
            "insert into public.business_action_receipts"
            " (space_id,actor_id,actor,idempotency_key,input_hash,command)"
            " values (%s,%s,%s,%s,%s,%s)"
        )
        params = (
            context.actor.space_id,
            context.actor.actor_id,
            Jsonb(tx.authorization.provenance.model_dump(mode="json")),
            str(uuid4()),
            "a" * 64,
            Jsonb({"action": command}),
        )
        if command == "unknown_document_command":
            with pytest.raises(CheckViolation) as error, tx.connection.transaction():
                tx.connection.execute(sql, params)
            assert error.value.diag.constraint_name == (
                "business_action_receipts_unplanned_command"
            )
        else:
            tx.connection.execute(sql, params)


@pytest.mark.parametrize("command", ["delete_document", "restore_document"])
@pytest.mark.parametrize("actor_kind", ["owner_via_agent", "extractor"])
def test_document_actions_refuse_nonhuman_actors(actions, command, actor_kind):
    service, context, _ = actions
    with transaction(service.authority, context) as tx:
        actor = tx.authorization.provenance.model_dump(mode="json")
        actor["actor_kind"] = actor_kind
        with pytest.raises(CheckViolation) as error, tx.connection.transaction():
            tx.connection.execute(
                "insert into public.business_action_receipts"
                " (space_id,actor_id,actor,idempotency_key,input_hash,command)"
                " values (%s,%s,%s,%s,%s,%s)",
                (
                    context.actor.space_id,
                    context.actor.actor_id,
                    Jsonb(actor),
                    str(uuid4()),
                    "a" * 64,
                    Jsonb({"action": command}),
                ),
            )
        assert error.value.diag.constraint_name == "business_document_delete_human_commands"


@pytest.mark.parametrize("command", ["delete_document", "restore_document"])
def test_document_actions_refuse_even_a_matching_persisted_turn(actions, command):
    service, context, _ = actions
    with transaction(service.authority, context) as tx:
        actor = tx.authorization.provenance.model_dump(mode="json")
        turn = str(uuid4())
        action = {"action": command}
        tx.connection.execute(
            "insert into public.business_turns"
            " (turn_key,space_id,sender_hash,actor_id,lease_fence,model_state,plan,plan_actor)"
            " values (%s,%s,%s,%s,1,'completed',%s,%s)",
            (
                turn,
                context.actor.space_id,
                "a" * 64,
                context.actor.actor_id,
                Jsonb({"schema_version": 1, "actions": [action]}),
                Jsonb(actor),
            ),
        )
        with pytest.raises(CheckViolation) as error, tx.connection.transaction():
            tx.connection.execute(
                "insert into public.business_action_receipts"
                " (space_id,actor_id,actor,idempotency_key,input_hash,command,turn_key,action_index)"
                " values (%s,%s,%s,%s,%s,%s,%s,0)",
                (
                    context.actor.space_id,
                    context.actor.actor_id,
                    Jsonb(actor),
                    str(uuid4()),
                    "a" * 64,
                    Jsonb(action),
                    turn,
                ),
            )
        assert error.value.diag.constraint_name == "business_document_delete_human_commands"

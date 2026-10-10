from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.interpretation import BusinessInterpretation
from argus.agent_runtime.business.runner import BusinessTurnRunner
from argus.domain.business.authority import authorize
from argus.domain.business.contracts.actions import (
    Ask,
    ExistingDraft,
    ProposeActivity,
    ProposeAllocation,
    TurnPlan,
)
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.contracts.recovery import DurableTurn, SenderLease
from argus.domain.business.transactions import check_lease

from tests import test_business_actions_postgres as action_pg

users = action_pg.users
actions = action_pg.actions
pytestmark = action_pg.pytestmark


class InjectedInterpreter:
    def __init__(self, build_plan):
        self.build_plan = build_plan
        self.interpret_count = 0
        self.reply_count = 0

    async def ainterpret_business(self, payload):
        self.interpret_count += 1
        return BusinessInterpretation(plan=self.build_plan(payload))

    async def acompose_business(self, payload):
        self.reply_count += 1
        return "El borrador está guardado para revisión."


def claimed_context(service, member):
    actor = TrustedActor(
        actor_id=UUID(member.owner_id),
        actor_kind="owner_via_agent",
        space_id=member.actor.space_id,
    )
    with service.authority.pool.connection() as db:
        grant_id = db.execute(
            "insert into public.business_client_grants"
            "(space_id,grantee_id,issuer_id,capabilities)"
            " values(%s,%s,%s,ARRAY['read','prepare']) returning id",
            (actor.space_id, actor.actor_id, actor.actor_id),
        ).fetchone()[0]
    authorized = service.resolve_actor(actor, grant_id=grant_id)
    now = datetime.now(timezone.utc)
    lease = SenderLease(
        space_id=actor.space_id,
        sender_hash=uuid4().hex + uuid4().hex,
        holder=uuid4(),
        fence=1,
        lease_until=now + timedelta(minutes=3),
    )
    key = str(uuid4())
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_sender_leases"
            "(space_id,sender_hash,holder,fence,lease_until) values(%s,%s,%s,1,%s)",
            (lease.space_id, lease.sender_hash, lease.holder, lease.lease_until),
        )
        db.execute(
            "insert into public.business_turns"
            "(turn_key,space_id,sender_hash,actor_id,lease_fence,phase,model_state)"
            " values(%s,%s,%s,%s,1,'turn_running','running')",
            (key, lease.space_id, lease.sender_hash, actor.actor_id),
        )

    def begin_reply():
        with service.authority.pool.connection() as db:
            check_lease(db, authorized, lease)
            authorize(db, actor, authorized.grant_id).require("read")
            row = db.execute(
                "select reply_text from public.business_turns where turn_key=%s for update",
                (key,),
            ).fetchone()
            return row[0]

    context = AuthorizedBusinessContext(
        actions=service,
        authorization=authorized,
        turn_key=key,
        lease=lease,
        message_id=uuid4(),
        received_at=now,
        channel="whatsapp",
        begin_reply=begin_reply,
    )
    turn = DurableTurn(
        space_id=actor.space_id,
        actor_id=actor.actor_id,
        sender_hash=lease.sender_hash,
        turn_key=key,
        arrival_sequence=1,
        phase="turn_running",
        model_state="running",
        lease_fence=lease.fence,
    )
    return turn, context


def activity_plan(payload):
    source_id = payload["source_id"]
    return TurnPlan(
        actions=(
            ProposeActivity(
                facts=BusinessFactPatch(
                    amount={"state": "known", "value": "850"},
                    kind={"state": "known", "value": "expense"},
                ),
                source_ids=(source_id,),
            ),
            ProposeAllocation(
                draft={"from_action": 0},
                funding={"state": "known", "value": {"kind": "owner_funds"}},
                business_share={"state": "known", "value": {"kind": "all"}},
                source_ids=(source_id,),
            ),
            Ask(
                draft={"from_action": 0},
                field="occurred_on",
                asked_of="owner",
                prompt="¿Qué día compraste los materiales?",
            ),
        )
    )


@pytest.mark.asyncio
async def test_real_database_runner_persists_provenance_and_replays_one_draft(actions):
    service, member, _ = actions
    turn, context = claimed_context(service, member)
    interpreter = InjectedInterpreter(activity_plan)
    runner = BusinessTurnRunner(interpreter=interpreter)
    message = "Pagué  850 por materiales con mi dinero."
    first = await runner.run(context=context, turn=turn, message=message)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_turns set reply_text=%s,phase='reply_sent' where turn_key=%s",
            (first.reply_text, turn.turn_key),
        )
    replay = await runner.run(context=context, turn=turn, message=message)
    assert interpreter.interpret_count == interpreter.reply_count == 1
    assert len(first.tool_records) == len(replay.tool_records) == 3
    dossier = first.saved_state["dossiers"][0]
    assert dossier["version"] == 2
    assert dossier["facts"]["amount"]["value"] == "850"
    assert dossier["facts"]["funding"]["value"] == {"kind": "owner_funds"}
    assert dossier["facts"]["occurred_on"]["state"] == "unknown"
    assert dossier["sources"][0]["text"] == message
    assert len(dossier["history"]) == 2
    assert all(
        row["actor"]["actor_kind"] == "owner_via_agent" for row in dossier["history"]
    )
    assert replay.saved_state == first.saved_state
    with service.authority.pool.connection() as db:
        row = db.execute(
            "select plan,plan_actor,model_state from public.business_turns where turn_key=%s",
            (turn.turn_key,),
        ).fetchone()
        assert TurnPlan.model_validate(row[0]) == TurnPlan.model_validate(first.plan)
        assert row[1]["grant_id"] == str(context.authorization.grant_id)
        assert row[2] == "completed"
        receipts = db.execute(
            "select actor,outcome from public.business_action_receipts"
            " where turn_key=%s order by action_index",
            (turn.turn_key,),
        ).fetchall()
        assert len(receipts) == 3
        assert all(receipt[0] == row[1] for receipt in receipts)
        assert (
            db.execute(
                "select count(*) from public.financial_import_events where owner_space_id=%s",
                (context.authorization.actor.space_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "select count(*) from public.financial_records where user_id=%s",
                (context.authorization.owner_id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.asyncio
async def test_real_database_runner_missing_draft_is_not_found_and_stops_actions(actions):
    service, member, _ = actions
    turn, context = claimed_context(service, member)
    interpreter = InjectedInterpreter(
        lambda payload: TurnPlan(
            actions=(
                ProposeActivity(
                    draft=ExistingDraft(draft_id=uuid4(), version=1),
                    facts=BusinessFactPatch(amount={"state": "known", "value": "850"}),
                    source_ids=(payload["source_id"],),
                ),
                ProposeActivity(
                    facts=BusinessFactPatch(amount={"state": "known", "value": "900"}),
                    source_ids=(payload["source_id"],),
                ),
            )
        )
    )
    result = await BusinessTurnRunner(interpreter=interpreter).run(
        context=context, turn=turn, message="Corrige ese registro a 850."
    )
    assert len(result.tool_records) == 1
    assert (
        result.tool_records[0]["tool_outcome"]["failure"]["code"]
        == "business_record_not_found"
    )
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select outcome from public.business_action_receipts where turn_key=%s",
            (turn.turn_key,),
        ).fetchall() == [({"outcome": "not_found", "code": "business_record_not_found"},)]
        assert (
            db.execute(
                "select count(*) from public.financial_import_events where owner_space_id=%s",
                (context.authorization.actor.space_id,),
            ).fetchone()[0]
            == 0
        )

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.interpretation import (
    BusinessInterpretation,
    BusinessRecordIntent,
    business_reply_prompt,
)
from argus.agent_runtime.business.runner import BusinessTurnRunner
from argus.domain.business.authority import authorize
from argus.domain.business.contracts.actions import (
    ReviewDraft,
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
    def __init__(self, build_interpretation):
        self.build_interpretation = build_interpretation
        self.interpret_count = 0
        self.reply_count = 0

    async def ainterpret_business(self, payload):
        self.interpret_count += 1
        return self.build_interpretation(payload)

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

    def check_access():
        with service.authority.pool.connection() as db:
            check_lease(db, authorized, lease)
            authorize(db, actor, authorized.grant_id).require("read")

    context = AuthorizedBusinessContext(
        actions=service,
        authorization=authorized,
        turn_key=key,
        lease=lease,
        message_id=uuid4(),
        received_at=now,
        channel="whatsapp",
        begin_reply=begin_reply,
        require_access=check_access,
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


def activity_proposal(payload):
    return BusinessInterpretation(
        records=(
            BusinessRecordIntent(
                facts=BusinessFactPatch(
                    amount={"state": "known", "value": "850"},
                    kind={"state": "known", "value": "expense"},
                ),
                allocation={
                    "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                    "business_share": {"state": "known", "value": {"kind": "all"}},
                },
                question={
                    "field": "occurred_on",
                    "asked_of": "owner",
                    "prompt": "¿Qué día compraste los materiales?",
                },
            ),
        )
    )


@pytest.mark.asyncio
async def test_real_database_runner_persists_provenance_and_replays_one_draft(actions):
    service, member, _ = actions
    turn, context = claimed_context(service, member)
    interpreter = InjectedInterpreter(activity_proposal)
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
    assert "due_on" not in dossier
    assert all("after_due_on" not in row for row in dossier["history"])
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


class CapturingInterpreter(InjectedInterpreter):
    def __init__(self, build_interpretation):
        super().__init__(build_interpretation)
        self.reply_payloads = []

    async def acompose_business(self, payload):
        self.reply_payloads.append(payload)
        return await super().acompose_business(payload)


_IDS_AND_CLOCKS = re.compile(
    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    r"|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?"
)


def _without_ids_and_clocks(value) -> str:
    seen: dict[str, str] = {}
    return _IDS_AND_CLOCKS.sub(
        lambda found: seen.setdefault(found.group(0), f"<{len(seen)}>"),
        json.dumps(value, ensure_ascii=False),
    )


@pytest.mark.asyncio
async def test_a_due_date_never_reaches_the_reply_model_on_explain_status(actions):
    service, member, _ = actions

    async def explained_after_review(due_on: dict | None):
        turn, context = claimed_context(service, member)
        created = await BusinessTurnRunner(
            interpreter=InjectedInterpreter(
                lambda payload: BusinessInterpretation(
                    records=(
                        activity_proposal(payload)
                        .records[0]
                        .model_copy(update={"question": None}),
                    )
                )
            )
        ).run(
            context=context, turn=turn, message="Pagué 850 por materiales con mi dinero."
        )
        draft_id = UUID(created.saved_state["dossiers"][0]["draft_id"])
        review = {"version": 2, "document_type": "recibo"}
        if due_on is not None:
            review["due_on"] = due_on
        service.review(member, draft_id, ReviewDraft.model_validate(review), str(uuid4()))
        turn, context = claimed_context(service, member)
        interpreter = CapturingInterpreter(
            lambda payload: BusinessInterpretation(
                records=(
                    BusinessRecordIntent(target_draft_id=draft_id, explain_status=True),
                )
            )
        )
        await BusinessTurnRunner(interpreter=interpreter).run(
            context=context, turn=turn, message="¿Cómo va ese registro?"
        )
        (payload,) = interpreter.reply_payloads
        return service.dossier(member, draft_id), payload

    undated, undated_input = await explained_after_review(None)
    dated, dated_input = await explained_after_review(
        {"state": "known", "value": "2026-11-30"}
    )
    assert (undated.due_on, dated.due_on) == (None, date(2026, 11, 30))
    for payload in (undated_input, dated_input):
        sent = json.dumps(business_reply_prompt(payload), ensure_ascii=False)
        assert "due_on" not in sent
        assert "2026-11-30" not in sent

    def dossier_views(payload) -> str:
        (explained,) = (
            record["tool_outcome"]["result"]["data"]
            for record in payload["tool_records"]
            if record["tool_name"] == "business_explain_status"
        )
        return _without_ids_and_clocks([explained, payload["saved_state"]["dossiers"]])

    assert dossier_views(dated_input) == dossier_views(undated_input)


@pytest.mark.asyncio
async def test_real_database_runner_foreign_read_is_not_found_and_stops_actions(actions):
    service, member, _ = actions
    turn, context = claimed_context(service, member)
    interpreter = InjectedInterpreter(
        lambda payload: BusinessInterpretation(
            records=(
                BusinessRecordIntent(target_draft_id=uuid4(), explain_status=True),
                BusinessRecordIntent(
                    facts=BusinessFactPatch(amount={"state": "known", "value": "900"}),
                ),
            )
        )
    )
    result = await BusinessTurnRunner(interpreter=interpreter).run(
        context=context,
        turn=turn,
        message="Busca ese registro y prepara un gasto de 900.",
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


@pytest.mark.asyncio
async def test_existing_record_update_allocation_question_and_replay_use_receipts(
    actions,
):
    service, member, _ = actions
    draft_id, version = action_pg.create(service, member)
    turn, context = claimed_context(service, member)
    interpreter = InjectedInterpreter(
        lambda payload: BusinessInterpretation(
            records=(
                BusinessRecordIntent(
                    target_draft_id=draft_id,
                    facts={"occurred_on": {"state": "known", "value": "2026-10-09"}},
                    allocation={
                        "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                        "business_share": {"state": "known", "value": {"kind": "all"}},
                    },
                    question={
                        "field": "counterparty",
                        "asked_of": "owner",
                        "prompt": "Which supplier?",
                    },
                ),
            )
        )
    )
    runner = BusinessTurnRunner(interpreter=interpreter)
    message = "Friday, paid personally; all for the business."
    first = await runner.run(context=context, turn=turn, message=message)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_turns set reply_text=%s,phase='reply_sent' where turn_key=%s",
            (first.reply_text, turn.turn_key),
        )
    replay = await runner.run(context=context, turn=turn, message=message)
    assert interpreter.interpret_count == interpreter.reply_count == 1
    assert replay.saved_state == first.saved_state
    assert all(
        item["draft"] == {"draft_id": str(draft_id), "base_version": version}
        for item in first.plan["actions"]
    )
    with service.authority.pool.connection() as db:
        receipts = db.execute(
            "select outcome,actor,command from public.business_action_receipts where turn_key=%s order by action_index",
            (turn.turn_key,),
        ).fetchall()
    assert [item[0]["version"] for item in receipts] == [
        version + 1,
        version + 2,
        version + 2,
    ]
    assert all(
        item[1]["grant_id"] == str(context.authorization.grant_id) for item in receipts
    )
    assert all(item[2]["draft"] == first.plan["actions"][0]["draft"] for item in receipts)
    dossier = service.dossier(member, draft_id)
    assert len(dossier.history) == 3
    assert len(dossier.questions) == 1
    assert str(dossier.facts.occurred_on.value) == "2026-10-09"
    assert dossier.facts.funding.value.kind == "owner_funds"
    assert dossier.questions[0].draft_id == draft_id
    assert len(dossier.sources) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("interleave_after_first", [False, True])
async def test_server_binding_does_not_absorb_external_revision(
    actions, monkeypatch, interleave_after_first
):
    from argus.domain.business.contracts.actions import ReviewDraft

    service, member, _ = actions
    draft_id, version = action_pg.create(service, member)
    turn, context = claimed_context(service, member)

    def revise(expected):
        result = service.review(
            member,
            draft_id,
            ReviewDraft(
                version=expected,
                facts=BusinessFactPatch(
                    counterparty={"state": "known", "value": "Human supplier"}
                ),
            ),
            str(uuid4()),
        )
        assert result.outcome == "applied"

    def proposal(payload):
        if not interleave_after_first:
            revise(version)
        return BusinessInterpretation(
            records=(
                BusinessRecordIntent(
                    target_draft_id=draft_id,
                    facts={"amount": {"state": "known", "value": "83"}},
                    question={
                        "field": "funding",
                        "asked_of": "owner",
                        "prompt": "How paid?",
                    },
                ),
            )
        )

    original_execute = service.execute

    def execute(context, key, index, *, lease):
        result = original_execute(context, key, index, lease=lease)
        if interleave_after_first and index == 0:
            revise(result.version)
        return result

    monkeypatch.setattr(service, "execute", execute)
    result = await BusinessTurnRunner(interpreter=InjectedInterpreter(proposal)).run(
        context=context, turn=turn, message="Correct amount to 83; how was it paid?"
    )
    assert result.tool_records[-1]["tool_outcome"]["failure"] is not None
    with service.authority.pool.connection() as db:
        refused = db.execute(
            "select outcome from public.business_action_receipts where turn_key=%s order by action_index desc limit 1",
            (turn.turn_key,),
        ).fetchone()[0]
    assert refused["outcome"] == "stale_version"
    assert len(result.tool_records) == (2 if interleave_after_first else 1)
    dossier = service.dossier(member, draft_id)
    assert not dossier.questions
    assert dossier.facts.counterparty.value == "Human supplier"
    assert dossier.facts.amount.value == ("83" if interleave_after_first else "850")
    assert dossier.version == version + (2 if interleave_after_first else 1)


@pytest.mark.asyncio
async def test_unknown_mutable_target_cannot_persist_executable_plan(actions):
    from argus.agent_runtime.business.binding import BusinessBindingError

    service, member, _ = actions
    turn, context = claimed_context(service, member)
    interpreter = InjectedInterpreter(
        lambda payload: BusinessInterpretation(
            records=(
                BusinessRecordIntent(
                    target_draft_id=uuid4(),
                    facts={"amount": {"state": "known", "value": "31"}},
                ),
            )
        )
    )
    with pytest.raises(BusinessBindingError, match="target_not_in_context"):
        await BusinessTurnRunner(interpreter=interpreter).run(
            context=context,
            turn=turn,
            message="Change a record absent from this context.",
        )
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select plan,plan_actor from public.business_turns where turn_key=%s",
            (turn.turn_key,),
        ).fetchone() == (None, None)
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where turn_key=%s",
                (turn.turn_key,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from public.financial_import_events where owner_space_id=%s",
                (context.authorization.actor.space_id,),
            ).fetchone()[0]
            == 0
        )
    assert interpreter.reply_count == 0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.interpretation import BusinessInterpretation
from argus.agent_runtime.business.runner import BusinessTurnRunner
from argus.domain.business.contracts.actions import (
    Applied,
    Ask,
    PlannedDraft,
    ProposeActivity,
    ReadContext,
    Refused,
    TurnPlan,
)
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import BusinessFactPatch, KnownInput
from argus.domain.business.contracts.recovery import DurableTurn, SenderLease
from argus.domain.capability_registry import get_tool_catalog


class Actions:
    def __init__(self):
        self.plan = None
        self.sources = {}
        self.receipts = {}
        self.drafts = {}
        self.calls = []
        self.refusal = None
        self.composition_started = False
        self.reply_text = None

    def begin_reply(self):
        if self.reply_text is not None:
            return self.reply_text
        if self.composition_started:
            raise RuntimeError("business_reply_outcome_unknown")
        self.composition_started = True
        return None

    def save_reply(self, text):
        self.reply_text = text

    def plan_for_turn(self, context, key, *, lease):
        self.calls.append("read_plan")
        return self.plan

    def read_context(self, context):
        return {"drafts": list(self.drafts.values()), "questions": [], "accounts": []}

    def record_source(self, context, key, evidence):
        if key in self.sources and self.sources[key].text != evidence.text:
            raise ValueError("source_identity_conflict")
        self.sources.setdefault(key, evidence)
        return self.sources[key].id

    def persist_plan(self, context, key, plan, *, lease):
        self.calls.append("persist_plan")
        self.plan = plan
        return plan

    def dossier(self, context, draft_id):
        return SimpleNamespace(model_dump=lambda **kwargs: self.drafts[str(draft_id)])

    def execute(self, context, key, index, *, lease):
        assert self.plan is not None
        self.calls.append(f"execute:{index}")
        if self.refusal is not None:
            return self.refusal
        if index in self.receipts:
            return self.receipts[index]
        action = self.plan.actions[index]
        draft_id = uuid4() if isinstance(action, ProposeActivity) else None
        outcome = Applied(
            outcome="applied", draft_id=draft_id, version=1 if draft_id else None
        )
        if draft_id:
            self.drafts[str(draft_id)] = {"id": str(draft_id), "version": 1}
        self.receipts[index] = outcome
        return outcome


class Interpreter:
    def __init__(self, make_plan):
        self.make_plan = make_plan
        self.interpret_count = 0
        self.compose_count = 0
        self.payload = None

    async def ainterpret_business(self, payload):
        self.interpret_count += 1
        self.payload = payload
        return BusinessInterpretation(plan=self.make_plan(payload))

    async def acompose_business(self, payload):
        self.compose_count += 1
        assert "saved_state" in payload
        return "El borrador está pendiente de revisión."


@pytest.fixture
def turn_context():
    now = datetime.now(timezone.utc)
    actor = TrustedActor(actor_id=uuid4(), actor_kind="owner_via_agent", space_id=uuid4())
    lease = SenderLease(
        space_id=actor.space_id,
        sender_hash="test-sender",
        holder=uuid4(),
        fence=1,
        lease_until=now + timedelta(minutes=5),
    )
    turn = DurableTurn(
        space_id=actor.space_id,
        actor_id=actor.actor_id,
        sender_hash=lease.sender_hash,
        turn_key=f"test:{uuid4()}",
        arrival_sequence=1,
        phase="turn_running",
        model_state="running",
        lease_fence=lease.fence,
    )
    actions = Actions()
    context = AuthorizedBusinessContext(
        actions=actions,
        authorization=SimpleNamespace(actor=actor, grant_id=uuid4()),
        turn_key=turn.turn_key,
        lease=lease,
        message_id=uuid4(),
        received_at=now,
        channel="whatsapp",
        begin_reply=actions.begin_reply,
    )
    return turn, context, actions


def proposal(payload):
    return TurnPlan(
        actions=(
            ProposeActivity(
                facts=BusinessFactPatch(amount=KnownInput(value="850")),
                source_ids=(payload["source_id"],),
            ),
        )
    )


@pytest.mark.asyncio
async def test_graph_persists_plan_before_executor_and_replay_does_not_reinterpret(
    turn_context,
):
    turn, context, actions = turn_context
    interpreter = Interpreter(proposal)
    runner = BusinessTurnRunner(interpreter=interpreter)
    message = "Pagué  850\npor materiales"
    result = await runner.run(context=context, turn=turn, message=message)
    actions.save_reply(result.reply_text)
    replay = await runner.run(context=context, turn=turn, message=message)
    assert interpreter.interpret_count == interpreter.compose_count == 1
    assert actions.calls.index("persist_plan") < actions.calls.index("execute:0")
    assert len(actions.drafts) == len(actions.receipts) == len(actions.sources) == 1
    assert next(iter(actions.sources.values())).text == message
    assert result.saved_state == replay.saved_state
    assert result.tool_records[0]["outcome"] == "succeeded"
    assert interpreter.payload["source_id"] == str(context.message_id)


@pytest.mark.asyncio
async def test_refused_action_stops_dependent_tools_and_reply_sees_refusal(turn_context):
    turn, context, actions = turn_context
    actions.refusal = Refused(outcome="not_found", code="business_record_not_found")
    interpreter = Interpreter(
        lambda payload: TurnPlan(actions=(ReadContext(), ReadContext()))
    )
    result = await BusinessTurnRunner(interpreter=interpreter).run(
        context=context, turn=turn, message="Busca ese registro"
    )
    assert len(result.tool_records) == 1
    assert (
        result.tool_records[0]["tool_outcome"]["failure"]["code"]
        == "business_record_not_found"
    )
    assert "execute:1" not in actions.calls
    assert not actions.drafts


@pytest.mark.asyncio
async def test_context_fence_mismatch_prevents_interpreter_and_execution(turn_context):
    turn, context, actions = turn_context
    interpreter = Interpreter(proposal)
    turn = turn.model_copy(update={"lease_fence": 2})
    with pytest.raises(ValueError, match="claimed durable turn"):
        await BusinessTurnRunner(interpreter=interpreter).run(
            context=context, turn=turn, message="Pagué 850"
        )
    assert not actions.calls
    assert interpreter.interpret_count == 0


@pytest.mark.asyncio
async def test_approval_language_reaches_interpreter_but_has_no_approval_tool(
    turn_context,
):
    turn, context, actions = turn_context
    interpreter = Interpreter(lambda payload: TurnPlan(actions=()))
    result = await BusinessTurnRunner(interpreter=interpreter).run(
        context=context, turn=turn, message="aprueba todo"
    )
    assert interpreter.payload["message"] == "aprueba todo"
    assert result.plan["actions"] == []
    assert not actions.receipts
    assert not actions.drafts


def test_business_catalogue_excludes_personal_tools_and_approval():
    business = get_tool_catalog(surface="business")
    personal = get_tool_catalog()
    assert len(business.declarations) == 7
    assert all(
        declaration.surfaces == {"business"} for declaration in business.declarations
    )
    assert not {d.name for d in business.declarations} & {
        d.name for d in personal.declarations
    }
    assert all("approv" not in d.name for d in business.declarations)


def test_plan_schema_bounds_actions_and_prior_draft_references():
    with pytest.raises(ValueError):
        TurnPlan(actions=(ReadContext(),) * 9)
    with pytest.raises(ValueError, match="earlier action"):
        TurnPlan(
            actions=(
                Ask(
                    draft=PlannedDraft(from_action=0),
                    field="funding",
                    asked_of="owner",
                    prompt="¿Con qué pagaste?",
                ),
            )
        )
    with pytest.raises(ValueError):
        TurnPlan.model_validate({"actions": [{"action": "approve_expense"}]})


@pytest.mark.asyncio
async def test_replay_cannot_bind_a_changed_message_to_existing_plan(turn_context):
    turn, context, actions = turn_context
    interpreter = Interpreter(proposal)
    runner = BusinessTurnRunner(interpreter=interpreter)
    await runner.run(context=context, turn=turn, message="Pagué 850")
    prior_call_count = len(actions.calls)
    with pytest.raises(ValueError, match="source_identity_conflict"):
        await runner.run(context=context, turn=turn, message="Pagué 950")
    assert len(actions.calls) == prior_call_count + 1
    assert len(actions.receipts) == 1
    assert interpreter.interpret_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message", ["Pagué 850 por materiales", "I spent 850 on supplies"]
)
async def test_existing_openrouter_interpreter_business_methods_run_through_real_graph(
    turn_context, monkeypatch, message
):
    import json

    from argus.agent_runtime.business import interpretation
    from argus.agent_runtime.business.interpretation import BusinessReply

    turn, context, actions = turn_context
    requests = []

    async def invoke_schema(**kwargs):
        requests.append(kwargs)
        payload = json.loads(kwargs["messages"][1]["content"])
        if kwargs["schema_name"] == "BusinessInterpretation":
            assert payload["message"] == message
            return BusinessInterpretation(plan=proposal(payload))
        assert len(payload["saved_state"]["dossiers"]) == 1
        return BusinessReply(reply="El borrador está pendiente de revisión.")

    monkeypatch.setattr(interpretation, "invoke_openrouter_json_schema", invoke_schema)
    result = await BusinessTurnRunner().run(context=context, turn=turn, message=message)
    assert len(requests) == 2
    assert all(
        request["model_name"] == interpretation.BUSINESS_MODEL_CANDIDATES[0]
        for request in requests
    )
    assert result.graph_run_id
    assert len(actions.receipts) == 1


def test_business_tool_arguments_cannot_supply_authority_or_approval():
    catalog = get_tool_catalog(surface="business")
    declaration = catalog.get("business_read_context")
    for field in ("actor_id", "space_id", "grant_id", "approve"):
        with pytest.raises(ValueError):
            declaration.validate_arguments({field: str(uuid4())})


@pytest.mark.asyncio
async def test_interrupted_reply_composition_never_blindly_repeats_provider_call(
    turn_context,
):
    turn, context, actions = turn_context
    interpreter = Interpreter(proposal)

    async def failed_composer(payload):
        interpreter.compose_count += 1
        raise RuntimeError("simulated_provider_interruption")

    interpreter.acompose_business = failed_composer
    runner = BusinessTurnRunner(interpreter=interpreter)
    with pytest.raises(RuntimeError, match="simulated_provider_interruption"):
        await runner.run(context=context, turn=turn, message="Pagué 850")
    with pytest.raises(RuntimeError, match="business_reply_outcome_unknown"):
        await runner.run(context=context, turn=turn, message="Pagué 850")
    assert interpreter.interpret_count == interpreter.compose_count == 1
    assert len(actions.drafts) == len(actions.receipts) == 1

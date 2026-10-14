from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.agent_runtime.business.context import AuthorizedBusinessContext
from argus.agent_runtime.business.interpretation import (
    BusinessInterpretation,
    BusinessRecordIntent,
)
from argus.agent_runtime.business.runner import BusinessTurnRunner
from argus.domain.business.actions.facts import patched_facts
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
    def __init__(self, make_interpretation):
        self.make_interpretation = make_interpretation
        self.interpret_count = 0
        self.compose_count = 0
        self.payload = None

    async def ainterpret_business(self, payload):
        self.interpret_count += 1
        self.payload = payload
        return self.make_interpretation(payload)

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
        require_access=lambda: None,
    )
    return turn, context, actions


def proposal(payload):
    return BusinessInterpretation(
        records=(
            BusinessRecordIntent(
                facts=BusinessFactPatch(amount=KnownInput(value="850")),
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
    assert "source_id" not in interpreter.payload
    assert result.plan["actions"][0]["source_ids"] == [str(context.message_id)]


@pytest.mark.asyncio
async def test_refused_action_stops_dependent_tools_and_reply_sees_refusal(turn_context):
    turn, context, actions = turn_context
    actions.refusal = Refused(outcome="not_found", code="business_record_not_found")
    interpreter = Interpreter(
        lambda payload: BusinessInterpretation(
            read_context=True,
            records=(BusinessRecordIntent(target_draft_id=uuid4(), explain_status=True),),
        )
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
    interpreter = Interpreter(lambda payload: BusinessInterpretation())
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
            return proposal(payload)
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


@pytest.mark.asyncio
async def test_unknown_mutable_target_fails_before_persist_or_execute(turn_context):
    from argus.agent_runtime.business.binding import BusinessBindingError

    turn, context, actions = turn_context
    interpreter = Interpreter(
        lambda payload: BusinessInterpretation(
            records=(
                BusinessRecordIntent(
                    target_draft_id=uuid4(),
                    facts={"amount": {"state": "known", "value": "27"}},
                ),
            )
        )
    )
    with pytest.raises(BusinessBindingError, match="target_not_in_context"):
        await BusinessTurnRunner(interpreter=interpreter).run(
            context=context, turn=turn, message="Change that record to 27."
        )
    assert actions.plan is None
    assert not actions.receipts
    assert not actions.drafts
    assert "persist_plan" not in actions.calls
    assert interpreter.compose_count == 0


@pytest.mark.asyncio
async def test_model_cannot_replace_the_captured_server_revision(turn_context):
    turn, context, actions = turn_context
    draft_id = uuid4()
    actions.drafts[str(draft_id)] = {"id": str(draft_id), "version": 2}

    def change_during_interpretation(payload):
        assert "version" not in payload["business"]["drafts"][0]
        actions.drafts[str(draft_id)]["version"] = 30
        return BusinessInterpretation(
            records=(
                BusinessRecordIntent(
                    target_draft_id=draft_id,
                    facts={"occurred_on": {"state": "known", "value": "2026-10-09"}},
                    question={
                        "field": "counterparty",
                        "asked_of": "owner",
                        "prompt": "Which supplier?",
                    },
                ),
            )
        )

    await BusinessTurnRunner(interpreter=Interpreter(change_during_interpretation)).run(
        context=context, turn=turn, message="It was Friday; which supplier is missing?"
    )
    assert all(action.draft.base_version == 2 for action in actions.plan.actions)
    assert actions.calls.index("persist_plan") < actions.calls.index("execute:0")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "account_currency,expected", [("USD", []), ("DOP", ["import_currency_mismatch"])]
)
async def test_graph_projects_income_account_context_without_rebinding_facts(
    turn_context, account_currency, expected
):
    turn, context, actions = turn_context
    draft_id, account_id, original_source = uuid4(), uuid4(), uuid4()
    facts = patched_facts(
        None,
        BusinessFactPatch.model_validate(
            {
                "kind": {"state": "known", "value": "income"},
                "amount": {"state": "known", "value": "125"},
                "currency": {"state": "known", "value": "USD"},
                "occurred_on": {"state": "known", "value": "2026-10-09"},
                "funding": {
                    "state": "known",
                    "value": {"kind": "business_account", "account_id": str(account_id)},
                },
                "business_share": {"state": "known", "value": {"kind": "all"}},
            }
        ),
        (original_source,),
        origin="owner_stated",
    )
    raw = {
        "accounts": [
            {
                "id": str(account_id),
                "nickname": "Cash",
                "type": "cash",
                "currency": account_currency,
            }
        ],
        "drafts": [
            {"id": str(draft_id), "version": 3, "facts": facts.model_dump(mode="json")}
        ],
        "questions": [],
    }
    actions.read_context = lambda _: raw
    interpreter = Interpreter(lambda _: BusinessInterpretation(read_context=True))
    result = await BusinessTurnRunner(interpreter=interpreter).run(
        context=context, turn=turn, message="Show the income record."
    )
    projected = interpreter.payload["business"]
    assert [item["code"] for item in projected["drafts"][0]["blockers"]] == expected
    assert projected["accounts"] == raw["accounts"]
    assert projected["drafts"][0]["facts"]["currency"]["value"] == "USD"
    assert "version" not in projected["drafts"][0]
    assert "source_ids" not in projected["drafts"][0]["facts"]["funding"]
    assert result.plan["actions"] == [{"action": "business_read_context"}]
    assert raw["drafts"][0]["version"] == 3
    assert raw["drafts"][0]["facts"] == facts.model_dump(mode="json")
    assert len(actions.sources) == len(actions.receipts) == 1
    assert not actions.drafts


@pytest.mark.asyncio
@pytest.mark.parametrize("supplied_callback", [False, True])
async def test_whatsapp_denial_precedes_provider_construction_and_state_access(
    turn_context, monkeypatch, supplied_callback
):
    from argus.agent_runtime import llm_interpreter

    turn, context, actions = turn_context
    constructed = []

    def construct(**kwargs):
        constructed.append(kwargs)
        raise AssertionError("denied job constructed provider interpreter")

    def denied():
        raise PermissionError("captured_consent_revoked")

    monkeypatch.setattr(llm_interpreter, "OpenRouterStructuredInterpreter", construct)
    context = replace(context, require_access=denied if supplied_callback else None)
    runner = BusinessTurnRunner()
    with pytest.raises(PermissionError):
        await runner.run(context=context, turn=turn, message="Pagué 850")
    assert constructed == actions.calls == []
    assert actions.sources == actions.receipts == {}


@pytest.mark.asyncio
async def test_web_turn_does_not_require_whatsapp_consent(turn_context):
    turn, context, actions = turn_context
    context = replace(context, channel="web", require_access=None)
    interpreter = Interpreter(proposal)
    interpreter.model_name = "web/injected-offline-model"
    await BusinessTurnRunner(interpreter=interpreter).run(
        context=context, turn=turn, message="Pagué 850"
    )
    assert interpreter.interpret_count == interpreter.compose_count == 1
    assert len(actions.receipts) == 1


@pytest.mark.asyncio
async def test_revocation_between_interpretation_and_composition_blocks_reply(
    turn_context,
):
    turn, context, actions = turn_context
    access = {"live": True}

    def require_access():
        if not access["live"]:
            raise PermissionError("captured_consent_revoked")

    original_execute = actions.execute

    def execute(*args, **kwargs):
        outcome = original_execute(*args, **kwargs)
        access["live"] = False
        return outcome

    actions.execute = execute
    context = replace(context, require_access=require_access)
    interpreter = Interpreter(proposal)
    with pytest.raises(PermissionError, match="captured_consent_revoked"):
        await BusinessTurnRunner(interpreter=interpreter).run(
            context=context, turn=turn, message="Pagué 850"
        )
    assert interpreter.interpret_count == 1
    assert interpreter.compose_count == 0
    assert not actions.composition_started
    assert len(actions.receipts) == 1


@pytest.mark.parametrize(
    "model", [None, "openai/gpt-6-luna-pro", "deepseek/deepseek-v4.1-flash"]
)
def test_business_disclosure_derives_actual_interpretation_and_reply_payloads(model):
    from argus.agent_runtime.business.interpretation import (
        BUSINESS_MODEL_CANDIDATES,
        BusinessReply,
    )
    from argus.agent_runtime.business.runner import business_provider_route
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import openrouter_payload_route

    route = business_provider_route(model)
    selected = model or BUSINESS_MODEL_CANDIDATES[0]
    assert route["gateway"] == "openrouter"
    for role, schema in (
        ("interpretation", BusinessInterpretation),
        ("reply", BusinessReply),
    ):
        payload = openrouter._json_schema_payload(
            model=selected,
            messages=[],
            schema_model=schema,
            schema_name=schema.__name__,
            profile=openrouter.openrouter_profile_for_task("interpretation"),
        )
        assert route[role] == [openrouter_payload_route(payload)]
    assert route["interpretation"][0]["model"] == selected
    assert route["interpretation"][0]["provider"] == (
        None if selected.startswith("anthropic/") else {"require_parameters": True}
    )


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize("guard_order", ["observer_outer", "observer_inner"])
@pytest.mark.parametrize("failure", [None, "revoked", "route_drift"])
@pytest.mark.asyncio
async def test_actual_post_keeps_nested_diagnostic_then_access_guards(
    async_path, guard_order, failure
):
    import httpx
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import (
        openrouter_payload_route,
        validate_openrouter_route,
    )

    events = []
    payload = {"model": "test/model", "provider": {"allow_fallbacks": False}}
    routes = [openrouter_payload_route(payload)]

    def observer(task, actual):
        events.append("observer")
        if failure == "route_drift":
            actual = {**actual, "provider": {"allow_fallbacks": True}}
        return actual

    def access(task, actual):
        validate_openrouter_route(actual, routes)
        events.append("access")
        if failure == "revoked":
            raise PermissionError("captured_consent_revoked")
        return actual

    def post(url, **kwargs):
        events.append("post")
        assert kwargs["json"] == payload
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def apost(url, **kwargs):
        return post(url, **kwargs)

    client = SimpleNamespace(post=apost if async_path else post)
    first, second = ((observer, False), (access, True))
    if guard_order == "observer_inner":
        first, second = second, first
    with openrouter.openrouter_request_guard(first[0], final=first[1]):
        with openrouter.openrouter_request_guard(second[0], final=second[1]):
            kwargs = dict(
                client=client,
                api_key="offline-placeholder",
                payload=payload,
                retry_attempt=(
                    "interpretation",
                    2.0,
                    "test/model",
                    "json_schema",
                    "Test",
                    None,
                ),
            )
            call = (
                openrouter._post_openrouter_json_schema
                if async_path
                else openrouter._post_openrouter_json_schema_sync
            )
            if failure:
                with pytest.raises(PermissionError):
                    if async_path:
                        await call(**kwargs)
                    else:
                        call(**kwargs)
            elif async_path:
                await call(**kwargs)
            else:
                call(**kwargs)
    assert events == (
        ["observer", "access", "post"]
        if not failure
        else ["observer", "access"]
        if failure == "revoked"
        else ["observer"]
    )
    assert openrouter._guard_request("interpretation", payload) is payload


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize("revoke", [False, True])
@pytest.mark.asyncio
async def test_internal_reasoning_retry_rechecks_live_access_before_each_post(
    async_path, revoke, monkeypatch
):
    import httpx
    from argus.llm import openrouter

    payload = {"model": "test/model", "reasoning": {"effort": "medium"}}
    events = []
    live = {"value": True}

    def access(task, actual):
        events.append("access")
        if not live["value"]:
            raise PermissionError("captured_consent_revoked")
        return actual

    def post(url, **kwargs):
        events.append("post")
        if events.count("post") == 1:
            live["value"] = not revoke
            return httpx.Response(400, request=httpx.Request("POST", url))
        assert "reasoning" not in kwargs["json"]
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def apost(url, **kwargs):
        return post(url, **kwargs)

    monkeypatch.setattr(
        openrouter,
        "_reserve_openrouter_attempt",
        lambda *args: SimpleNamespace(timeout_seconds=2.0),
    )
    kwargs = dict(
        client=SimpleNamespace(post=apost if async_path else post),
        api_key="offline-placeholder",
        payload=payload,
        retry_attempt=("interpretation", 2.0, "test/model", "json_schema", "Test", None),
    )
    call = (
        openrouter._post_openrouter_json_schema
        if async_path
        else openrouter._post_openrouter_json_schema_sync
    )
    with openrouter.openrouter_request_guard(access, final=True):
        if revoke:
            with pytest.raises(PermissionError, match="captured_consent_revoked"):
                if async_path:
                    await call(**kwargs)
                else:
                    call(**kwargs)
        elif async_path:
            await call(**kwargs)
        else:
            call(**kwargs)
    assert events == (
        ["access", "post", "access"] if revoke else ["access", "post", "access", "post"]
    )


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize("denial", ["revoked", "undisclosed_fallback"])
@pytest.mark.asyncio
async def test_candidate_fallback_cannot_dispatch_after_access_or_route_denial(
    async_path, denial, monkeypatch
):
    import httpx
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import validate_openrouter_route
    from pydantic import BaseModel

    class Result(BaseModel):
        ok: bool

    posts = []
    live = {"value": True}
    routes = [
        {"model": "test/primary", "provider": {"require_parameters": True}},
        {"model": "test/fallback", "provider": {"require_parameters": True}},
    ]

    def access(task, payload):
        validate_openrouter_route(payload, routes if denial == "revoked" else routes[:1])
        if not live["value"]:
            raise PermissionError("captured_consent_revoked")
        return payload

    def post(url, **kwargs):
        posts.append(kwargs["json"])
        live["value"] = denial != "revoked"
        return httpx.Response(503, request=httpx.Request("POST", url))

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return post(url, **kwargs)

    class AsyncClient(Client):
        async def post(self, url, **kwargs):
            return post(url, **kwargs)

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", AsyncClient)
    monkeypatch.setattr(openrouter.httpx, "Client", Client)
    monkeypatch.setattr(
        openrouter, "resolve_openrouter_api_key", lambda: "offline-placeholder"
    )
    monkeypatch.setattr(
        openrouter,
        "openrouter_structured_model_candidates",
        lambda *args, **kwargs: ["test/primary", "test/fallback"],
    )
    call = (
        openrouter.invoke_openrouter_json_schema
        if async_path
        else openrouter.invoke_openrouter_json_schema_sync
    )
    with openrouter.openrouter_request_guard(access, final=True):
        with pytest.raises(PermissionError):
            kwargs = dict(
                task="interpretation",
                messages=[],
                schema_model=Result,
                schema_name="Result",
            )
            if async_path:
                await call(**kwargs)
            else:
                call(**kwargs)
    assert len(posts) == 1
    assert posts[0]["model"] == "test/primary"


@pytest.mark.parametrize("stop", [None, "before_composer", "route_drift"])
@pytest.mark.asyncio
async def test_local_business_graph_dispatch_checks_consent_with_intercepted_http(
    turn_context, monkeypatch, stop
):
    import json

    import httpx
    from argus.llm import openrouter

    turn, context, actions = turn_context
    live = {"value": True}
    checks = []
    posts = []

    def require_access():
        checks.append(True)
        if not live["value"]:
            raise PermissionError("captured_consent_revoked")

    context = replace(context, require_access=require_access)
    if stop == "before_composer":
        original_execute = actions.execute

        def execute(*args, **kwargs):
            outcome = original_execute(*args, **kwargs)
            live["value"] = False
            return outcome

        actions.execute = execute

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            posts.append(kwargs["json"])
            content = (
                proposal({}).model_dump(mode="json")
                if len(posts) == 1
                else {"reply": "Pendiente de revisión."}
            )
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "choices": [{"message": {"content": json.dumps(content)}}],
                },
            )

    def observer(task, payload):
        return (
            {**payload, "model": "undisclosed/model"}
            if stop == "route_drift"
            else payload
        )

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", Client)
    monkeypatch.setattr(
        openrouter, "resolve_openrouter_api_key", lambda: "offline-placeholder"
    )
    with openrouter.openrouter_request_guard(observer):
        runner = BusinessTurnRunner()
        if stop:
            with pytest.raises(PermissionError):
                await runner.run(context=context, turn=turn, message="Pagué 850")
        else:
            result = await runner.run(context=context, turn=turn, message="Pagué 850")
            assert result.reply_text == "Pendiente de revisión."
    assert len(posts) == (0 if stop == "route_drift" else 1 if stop else 2)
    assert len(checks) == 3 if stop == "route_drift" else len(checks) >= 4
    assert len(actions.receipts) == (0 if stop == "route_drift" else 1)


@pytest.mark.parametrize("extra", ["models", "route", "plugins", "provider"])
def test_disclosure_rejects_undisclosed_routing_or_recipient_overrides(extra):
    from argus.llm.openrouter_request_policy import validate_openrouter_route

    original = {"model": "test/model", "provider": None}
    changed = {**original, extra: {"override": True}}
    with pytest.raises(PermissionError, match="openrouter_consent_route_changed"):
        validate_openrouter_route(changed, [original])


@pytest.mark.asyncio
async def test_saved_plan_and_reply_do_not_revive_revoked_capture(turn_context):
    import json

    turn, context, actions = turn_context
    live = {"value": True}

    def require_access():
        if not live["value"]:
            raise PermissionError("original_captured_consent_revoked")

    context = replace(context, require_access=require_access)
    interpreter = Interpreter(proposal)
    runner = BusinessTurnRunner(interpreter=interpreter)
    result = await runner.run(context=context, turn=turn, message="Pagué 850")
    actions.save_reply(result.reply_text)
    assert "require_access" not in json.dumps(result.model_dump(mode="json"))
    calls = tuple(actions.calls)
    live["value"] = False
    with pytest.raises(PermissionError, match="original_captured_consent_revoked"):
        await runner.run(context=context, turn=turn, message="Pagué 850")
    assert tuple(actions.calls) == calls
    assert interpreter.interpret_count == interpreter.compose_count == 1
    assert context.require_access is require_access


@pytest.mark.asyncio
async def test_actual_post_access_guards_are_isolated_between_concurrent_tasks():
    import asyncio

    import httpx
    from argus.llm import openrouter

    posts = []

    async def run(model, admitted):
        def access(task, payload):
            assert payload["model"] == model
            if not admitted:
                raise PermissionError("captured_consent_revoked")
            return payload

        async def post(url, **kwargs):
            posts.append(kwargs["json"]["model"])
            return httpx.Response(200, request=httpx.Request("POST", url))

        with openrouter.openrouter_request_guard(access, final=True):
            await asyncio.sleep(0)
            return await openrouter._post_openrouter_json_schema(
                client=SimpleNamespace(post=post),
                api_key="offline-placeholder",
                payload={"model": model},
                retry_attempt=("interpretation", 2.0, model, "json_schema", "Test", None),
            )

    results = await asyncio.gather(
        run("test/allowed", True), run("test/denied", False), return_exceptions=True
    )
    assert isinstance(results[0], httpx.Response)
    assert isinstance(results[1], PermissionError)
    assert posts == ["test/allowed"]


@pytest.mark.asyncio
async def test_real_memory_saver_characterizes_business_transient_reset_gap(turn_context):
    from argus.agent_runtime.business.stages import BusinessStages
    from argus.agent_runtime.graph.workflow import build_workflow
    from argus.agent_runtime.runtime import build_workflow_input
    from argus.agent_runtime.state.models import UserState
    from langgraph.checkpoint.memory import MemorySaver

    turn, context, actions = turn_context
    interpreter = Interpreter(proposal)
    workflow = build_workflow(
        business_runtime=BusinessStages(context, interpreter, "Pagué 850"),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "offline-business-reset-characterization"}}
    poison = {"unowned_prior_confirmation": True}
    await workflow.aupdate_state(
        config,
        {
            "business_plan": {"actions": [{"action": "unowned_prior_plan"}]},
            "confirmation_payload": poison,
            "assistant_response": "Prior turn text",
        },
    )
    state = await workflow.ainvoke(
        build_workflow_input(
            user=UserState(user_id=str(turn.actor_id)),
            message="Pagué 850",
        ),
        config=config,
    )
    assert state["business_plan"] == actions.plan.model_dump(mode="json")
    assert state["run_state"].current_user_message == "Pagué 850"
    assert len(state["run_state"].tool_call_records) == 1
    assert state["confirmation_payload"] == poison
    assert state["assistant_response"] == "Prior turn text"
    assert interpreter.interpret_count == 1


@pytest.mark.asyncio
async def test_revocation_during_interpretation_blocks_plan_persistence(turn_context):
    turn, context, actions = turn_context
    live = {"value": True}

    def require_access():
        if not live["value"]:
            raise PermissionError("captured_consent_revoked")

    def interpreted(payload):
        live["value"] = False
        return proposal(payload)

    interpreter = Interpreter(interpreted)
    with pytest.raises(PermissionError, match="captured_consent_revoked"):
        await BusinessTurnRunner(interpreter=interpreter).run(
            context=replace(context, require_access=require_access),
            turn=turn,
            message="Pagué 850",
        )
    assert actions.plan is None
    assert actions.receipts == {}
    assert interpreter.interpret_count == 1
    assert interpreter.compose_count == 0


@pytest.mark.parametrize("async_path", [False, True])
@pytest.mark.parametrize(
    "mutation", ["replacement", "model", "provider", "nested_provider"]
)
@pytest.mark.asyncio
async def test_nested_final_guard_cannot_change_intercepted_post_after_access(
    async_path, mutation
):
    import asyncio

    import httpx
    from argus.llm import openrouter
    from argus.llm.openrouter_request_policy import (
        openrouter_payload_route,
        validate_openrouter_route,
    )

    payload = {
        "model": "approved",
        "provider": {"order": ["disclosed"], "allow_fallbacks": False},
    }
    routes = [openrouter_payload_route(payload)]
    posts = []

    def access(task, actual):
        validate_openrouter_route(actual, routes)
        return actual

    def nested_final(task, actual):
        if mutation == "replacement":
            return {**actual, "model": "undisclosed"}
        if mutation == "model":
            actual["model"] = "undisclosed"
        elif mutation == "provider":
            actual["provider"] = {"allow_fallbacks": True}
        else:
            actual["provider"]["order"].append("undisclosed")
        return actual

    def post(url, **kwargs):
        posts.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def apost(url, **kwargs):
        return post(url, **kwargs)

    with openrouter.openrouter_request_guard(access, final=True):
        await asyncio.sleep(0)
        with openrouter.openrouter_request_guard(nested_final, final=True):
            kwargs = dict(
                client=SimpleNamespace(post=apost if async_path else post),
                api_key="offline-placeholder",
                payload=payload,
                retry_attempt=(
                    "interpretation",
                    2.0,
                    "approved",
                    "json_schema",
                    "Test",
                    None,
                ),
            )
            with pytest.raises(PermissionError):
                if async_path:
                    await openrouter._post_openrouter_json_schema(**kwargs)
                else:
                    openrouter._post_openrouter_json_schema_sync(**kwargs)
    assert posts == []


@pytest.mark.asyncio
async def test_final_validator_captured_alias_cannot_change_intercepted_http_after_await():
    import asyncio

    import httpx
    from argus.llm import openrouter

    captured = []
    dispatched = []
    events = []
    payload = {"model": "approved", "provider": {"order": ["disclosed"]}}

    def access(task, actual):
        events.append("access")
        assert actual == payload
        return actual

    def inner_validator(task, actual):
        events.append("validator")
        captured.append(actual)
        return actual

    async def post(url, **kwargs):
        await asyncio.sleep(0)
        captured[0]["model"] = "undisclosed"
        captured[0]["provider"]["order"].append("undisclosed")
        dispatched.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url))

    with openrouter.openrouter_request_guard(access, final=True):
        await asyncio.sleep(0)
        with openrouter.openrouter_request_guard(inner_validator, final=True):
            await openrouter._post_openrouter_json_schema(
                client=SimpleNamespace(post=post),
                api_key="offline-placeholder",
                payload=payload,
                retry_attempt=(
                    "interpretation",
                    2.0,
                    "approved",
                    "json_schema",
                    "Test",
                    None,
                ),
            )
    assert events == ["validator", "access"]
    assert dispatched == [{"model": "approved", "provider": {"order": ["disclosed"]}}]
    assert dispatched[0] is not captured[0]


@pytest.mark.asyncio
async def test_an_invalid_model_answer_is_typed_not_a_generic_failure(monkeypatch) -> None:
    from argus.agent_runtime.business import interpretation
    from argus.domain.business.contracts.recovery import BusinessModelOutputInvalid

    async def invalid(**_: object) -> dict:
        return {"records": "not a list"}

    monkeypatch.setattr(interpretation, "invoke_openrouter_json_schema", invalid)
    with pytest.raises(BusinessModelOutputInvalid):
        await interpretation.interpret_business_turn({})

    async def unavailable(**_: object) -> None:
        return None

    monkeypatch.setattr(interpretation, "invoke_openrouter_json_schema", unavailable)
    with pytest.raises(RuntimeError, match="business_interpreter_unavailable"):
        await interpretation.interpret_business_turn({})

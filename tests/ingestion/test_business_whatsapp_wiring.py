import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from argus.api.whatsapp_worker import start_worker, stop_worker
from argus.domain.ingestion.whatsapp.payload import Delivery, TextMessage

from tests.ingestion.test_whatsapp_intake import _world
from tests.ingestion.whatsapp_support import ALICE_PHONE


@pytest.mark.asyncio
async def test_factory_binds_canonical_actions_without_creating_consent(monkeypatch):
    import httpx
    from argus.agent_runtime.business.runner import business_provider_route
    from argus.api.whatsapp import build_whatsapp
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

    from tests.ingestion.whatsapp_support import ENV

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    sink = ReconciliationService(object(), object(), lambda: None)
    pool = object()
    documents = SimpleNamespace(
        hub=SimpleNamespace(
            sink=sink, box=SecretBox(bytes(range(32))), clock=lambda: None
        )
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected HTTP"))
    )
    runtime = build_whatsapp(
        load_whatsapp_settings(),
        documents=documents,
        spaces=object(),
        store=object(),
        client=client,
        pool=pool,
    )
    assert runtime.worker.actions.imports is sink
    assert runtime.worker.actions.authority.pool is pool
    assert runtime.worker.consent is runtime.consent is runtime.worker.captures.consent
    assert not runtime.worker.has_consent(None, None)
    assert runtime.worker.execute_turn is not None
    assert runtime.consent.route() == business_provider_route()
    assert runtime.consent.route()["interpretation"]
    assert runtime.consent.route()["reply"]
    await client.aclose()


@pytest.mark.parametrize("mode", ["allowed", "retry", "revoked_retry", "no_consent"])
@pytest.mark.asyncio
async def test_adapter_runs_real_graph_with_capture_guard_at_each_http_attempt(
    monkeypatch, mode
):
    import json
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    import httpx
    from argus.agent_runtime.business.runner import BusinessTurnRunner
    from argus.api.whatsapp_worker import build_worker
    from argus.domain.business.authority import ActionContext
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.business.contracts.recovery import DurableTurn, SenderLease
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.business_capture import CapturedText
    from argus.domain.ingestion.whatsapp.business_envelope import TextEnvelope
    from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
    from argus.llm import openrouter

    from tests.agent_runtime.test_business_runtime import Actions, proposal

    now = datetime.now(timezone.utc)
    actor = TrustedActor(actor_id=uuid4(), actor_kind="owner_via_agent", space_id=uuid4())
    authorization = ActionContext(
        actor, uuid4(), str(actor.actor_id), "Synthetic Business"
    )
    keys = WhatsAppKeys("synthetic-key")
    message = TextMessage("wamid.synthetic-assembled", ALICE_PHONE, now, "Original  text")
    captured = CapturedText(
        id=uuid4(),
        message_key=keys.message(message.id),
        sender_hash=keys.sender(message.sender),
        space_id=actor.space_id,
        owner_id=actor.actor_id,
        link_id=uuid4(),
        arrival_sequence=1,
        received_at=now,
        language="es-419",
        composition_state="not_started",
        envelope=TextEnvelope.from_message(message),
        ai_consent_id=uuid4(),
    )
    lease = SenderLease(
        space_id=actor.space_id,
        sender_hash=captured.sender_hash.hex(),
        holder=uuid4(),
        fence=1,
        lease_until=now + timedelta(minutes=5),
    )
    turn = DurableTurn(
        space_id=actor.space_id,
        actor_id=actor.actor_id,
        sender_hash=lease.sender_hash,
        turn_key=captured.turn_key,
        arrival_sequence=1,
        phase="turn_running",
        model_state="running",
        lease_fence=1,
    )
    events, posts = [], []
    live = True
    actions = Actions()

    def require_access(actual_capture, actual_authorization, *, lease):
        assert actual_capture is captured and actual_authorization is authorization
        assert (
            lease.space_id == captured.space_id
            and lease.sender_hash == captured.sender_hash.hex()
        )
        events.append("access")
        if not live:
            raise PermissionError("captured_consent_revoked")

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            nonlocal live
            assert events[-1] == "access"
            events.append("post")
            posts.append(kwargs["json"])
            request = httpx.Request("POST", url)
            if len(posts) == 1 and mode in {"retry", "revoked_retry"}:
                assert "reasoning" in kwargs["json"]
                live = mode != "revoked_retry"
                return httpx.Response(400, request=request)
            content = (
                proposal({}).model_dump(mode="json")
                if actions.plan is None
                else {"reply": "Pendiente de revisión."}
            )
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"content": json.dumps(content)}}]},
            )

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", Client)
    monkeypatch.setattr(
        openrouter, "resolve_openrouter_api_key", lambda: "offline-placeholder"
    )
    worker = build_worker(
        object(),
        box=SecretBox(bytes(range(32))),
        keys=keys,
        transport=None,
        enabled=lambda: True,
        send_enabled=lambda: False,
        actions=actions,
        runner=BusinessTurnRunner(),
        consent=None
        if mode == "no_consent"
        else SimpleNamespace(require_access=require_access),
    )
    call = worker.execute_turn(
        captured=captured,
        turn=turn,
        lease=lease,
        authorization=authorization,
        begin_reply=actions.begin_reply,
        history=(),
    )
    if mode in {"revoked_retry", "no_consent"}:
        with pytest.raises(PermissionError):
            await call
        assert not actions.receipts
    else:
        assert await call == "Pendiente de revisión."
        assert len(actions.receipts) == 1
        assert next(iter(actions.sources.values())).text == message.body
    assert (
        len(posts)
        == {"allowed": 2, "retry": 3, "revoked_retry": 1, "no_consent": 0}[mode]
    )
    if mode == "no_consent":
        assert not events and not actions.calls


@pytest.mark.asyncio
async def test_intake_defers_durable_text_reply_to_worker():
    world = _world()
    await world.link(world.alice, ALICE_PHONE)
    before = len(world.transport.sent)
    captured = []

    def capture(message):
        captured.append(message)
        return True

    world.intake.capture_text = capture
    message = TextMessage(
        "wamid.synthetic-durable", ALICE_PHONE, world.clock.now, "Compré materiales"
    )
    await world.intake.handle(Delivery((message,), 0, 0, 0))
    assert captured == [message]
    assert world.record(message.id) is None
    assert len(world.transport.sent) == before


@pytest.mark.asyncio
async def test_worker_lifecycle_has_one_owned_task_and_awaits_shutdown(monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()

    class Worker:
        async def run(self):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

    monkeypatch.setattr(
        "argus.api.whatsapp.whatsapp_runtime", lambda: SimpleNamespace(worker=Worker())
    )
    app = SimpleNamespace(state=SimpleNamespace())
    start_worker(app)
    original = app.state.business_whatsapp_worker
    start_worker(app)
    assert app.state.business_whatsapp_worker is original
    await asyncio.wait_for(started.wait(), timeout=1)
    await stop_worker(app)
    assert stopped.is_set() and original.done()
    assert app.state.business_whatsapp_worker is None
    await stop_worker(app)


@pytest.mark.asyncio
async def test_with_the_agent_off_text_never_reaches_it_even_with_the_pilot_on(
    monkeypatch,
):
    import httpx
    from argus.api.whatsapp import build_whatsapp
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

    from tests.ingestion.whatsapp_support import ENV

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ARGUS_WHATSAPP_AGENT_ENABLED", "false")
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_BUSINESS_PILOT_ENABLED", "true")
    touched = []

    class Pool:
        def connection(self):
            touched.append(1)
            raise RuntimeError("the pool must not be used")

    documents = SimpleNamespace(
        hub=SimpleNamespace(
            sink=ReconciliationService(object(), object(), lambda: None),
            box=SecretBox(bytes(range(32))),
            clock=lambda: None,
        )
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None))
    runtime = build_whatsapp(
        load_whatsapp_settings(),
        documents=documents,
        spaces=object(),
        store=object(),
        client=client,
        pool=Pool(),
    )
    message = TextMessage("wamid.Y", ALICE_PHONE, datetime.now(timezone.utc), "hola")
    assert runtime.intake.capture_text(message) is False
    assert touched == []
    assert runtime.worker.enabled() is False
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("pilot", ["false", "true"])
async def test_text_reaches_the_agent_only_while_the_worker_is_enabled(
    monkeypatch, pilot
):
    import httpx
    from argus.api.whatsapp import build_whatsapp
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.secrets import SecretBox
    from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings

    from tests.ingestion.whatsapp_support import ENV

    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", pilot)
    monkeypatch.setenv("CUADRAO_BUSINESS_PILOT_ENABLED", pilot)
    captured = []

    class Pool:
        def connection(self):
            captured.append("touched")
            raise RuntimeError("the pool must not be used while disabled")

    documents = SimpleNamespace(
        hub=SimpleNamespace(
            sink=ReconciliationService(object(), object(), lambda: None),
            box=SecretBox(bytes(range(32))),
            clock=lambda: None,
        )
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None))
    runtime = build_whatsapp(
        load_whatsapp_settings(),
        documents=documents,
        spaces=object(),
        store=object(),
        client=client,
        pool=Pool(),
    )
    message = TextMessage("wamid.X", ALICE_PHONE, datetime.now(timezone.utc), "hola")
    if pilot == "false":
        assert runtime.intake.capture_text(message) is False
        assert captured == []
    else:
        with pytest.raises(RuntimeError):
            runtime.intake.capture_text(message)
        assert captured == ["touched"]
    await client.aclose()

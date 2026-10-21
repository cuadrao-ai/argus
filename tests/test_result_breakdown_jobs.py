"""A paid Breakdown is owned by completion work, not its browser stream."""

import asyncio
import importlib
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.chat import breakdown, research_jobs
from argus.api.schemas import Message
from argus.domain.owner_scope import PERSONAL
from argus.domain.research.contracts import ResearchSource, ResearchUsage
from argus.domain.result_readout_research import RESULT_RESEARCH_MODEL
from argus.domain.store import utcnow

from tests.research.test_research_jobs import _JobGateway
from tests.test_backtest_message_projection import _completed_run


def dispatch():
    try:
        return importlib.import_module(
            "argus.api.chat.breakdown_jobs"
        ).dispatch_result_breakdown
    except ModuleNotFoundError:
        pytest.fail("Breakdown has no completion owner outside the browser stream")


@pytest.mark.asyncio
async def test_closing_stream_at_first_progress_cannot_cancel_dispatch(monkeypatch):
    from argus.api.chat import breakdown_jobs

    finished = asyncio.Event()

    async def complete(*args, **kwargs):
        finished.set()

    monkeypatch.setattr(breakdown_jobs, "dispatch_result_breakdown", complete)

    async def stream():
        completion = breakdown_jobs.start_result_breakdown(
            None,
            language="en",
            lifecycle=SimpleNamespace(turn_id="turn"),
            settle_usage=None,
        )
        yield "working"
        await asyncio.shield(completion)

    browser = stream()
    assert await anext(browser) == "working"
    await browser.aclose()
    await asyncio.wait_for(finished.wait(), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "es-419"])
@pytest.mark.parametrize("durable", [False, True])
async def test_disconnect_preserves_one_complete_billed_answer(
    monkeypatch, language, durable
):
    run = _completed_run()
    started, release = threading.Event(), threading.Event()
    written, billed, calls = [], [], []
    gateway = _JobGateway() if durable else None
    if gateway is not None:
        gateway.messages = {}
    monkeypatch.setattr(api_state, "supabase_gateway", gateway)

    def compose(*args, **kwargs):
        calls.append(kwargs["language"])
        started.set()
        assert release.wait(5)
        return breakdown.ResultBreakdownMessage(
            text="Bought once and held."
            if language == "en"
            else "Compró una vez y mantuvo.",
            source="llm_breakdown_stage",
            fallback_used=False,
            usage=ResearchUsage(model=RESULT_RESEARCH_MODEL, cost_usd=0.01),
            sources=(ResearchSource(title="Results", url="https://example.com/results"),),
        )

    def save(**kwargs):
        if durable:
            assert next(iter(gateway.rows.values()))["status"] != "succeeded"
        message = Message(
            id=f"message-{len(written)}",
            conversation_id=run.conversation_id,
            role="assistant",
            created_at=utcnow(),
            content=kwargs["content"],
            metadata=kwargs["metadata"],
        )
        written.append(message)
        if gateway is not None:
            gateway.messages[message.id] = message
        return message

    monkeypatch.setattr(breakdown, "result_breakdown_message_with_metadata", compose)
    monkeypatch.setattr(
        breakdown, "record_result_breakdown_spend", lambda **kw: billed.append(kw)
    )
    monkeypatch.setattr("argus.api.message_store.create_message", save)
    hooks = SimpleNamespace(
        user_id="owner",
        conversation_id=run.conversation_id,
        request_id="request",
        request_message=SimpleNamespace(
            id="request-message", metadata={"chat_action": {"type": "show_breakdown"}}
        ),
        complete=save,
    )
    invoke = dispatch()
    stream = asyncio.create_task(
        invoke(run, language=language, lifecycle=hooks, settle_usage=None)
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        if durable:
            queued = await stream
            assert queued.job["operation_scope"] == "chat.research"
            assert queued.message.content == ""
            replay = await invoke(
                run, language=language, lifecycle=hooks, settle_usage=None
            )
            assert replay.job["id"] == queued.job["id"]
        else:
            stream.cancel()
            with pytest.raises(asyncio.CancelledError):
                await stream
        assert len(written) == int(durable)
        assert all(message.content == "" for message in written)
        release.set()
        await asyncio.wait_for(asyncio.gather(*research_jobs._POLLER_TASKS), 3)
    finally:
        release.set()
    assert calls == [language]
    written = [message for message in written if message.content]
    assert len(written) == len(billed) == 1
    metadata = written[0].metadata
    assert metadata["result_readout_content"]["text"] == written[0].content
    assert metadata["result_readout_content"]["language"] == language
    assert metadata["research"]["sources"][0]["url"] == "https://example.com/results"
    assert metadata["result_readout_fallback_used"] is False
    if durable:
        row = gateway.rows[queued.job["id"]]
        assert row["status"] == "succeeded"
        assert row["execution_metadata"]["research_result_message_id"] == written[0].id
        assert row.get("result_run_id") is None
        from argus.api.main import app
        from fastapi.testclient import TestClient

        response = TestClient(app).get(f"/api/v1/backtest-jobs/{row['id']}")
        assert response.status_code == 200
        settled = response.json()
        assert settled["run"] is None
        envelope = settled["result_message"]["metadata"]["result_readout_content"]
        assert envelope["language"] == language and envelope["text"] == written[0].content
        assert settled["result_message"]["metadata"]["research"]["sources"]


@pytest.mark.asyncio
async def test_job_creation_failure_never_starts_paid_work(monkeypatch):
    class UnavailableGateway(_JobGateway):
        def create_backtest_job(self, **kwargs):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(api_state, "supabase_gateway", UnavailableGateway())
    calls = []
    monkeypatch.setattr(
        breakdown, "result_breakdown_action", lambda *a, **kw: calls.append(kw)
    )
    run = _completed_run()
    hooks = SimpleNamespace(
        user_id="owner",
        conversation_id=run.conversation_id,
        request_id="request",
        request_message=SimpleNamespace(id="request-message", metadata={}),
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        await dispatch()(run, language="en", lifecycle=hooks, settle_usage=None)
    assert calls == []


@pytest.mark.asyncio
async def test_only_the_worker_that_claims_the_job_may_spend(monkeypatch):
    class ClaimedGateway(_JobGateway):
        def mark_backtest_job_running(self, **kwargs):
            raise ValueError("Already claimed by another worker")

    monkeypatch.setattr(api_state, "supabase_gateway", ClaimedGateway())
    calls = []
    monkeypatch.setattr(
        breakdown, "result_breakdown_action", lambda *a, **kw: calls.append(kw)
    )
    run = _completed_run()
    hooks = SimpleNamespace(
        user_id="owner",
        conversation_id=run.conversation_id,
        request_id="request",
        request_message=SimpleNamespace(id="request-message", metadata={}),
        complete=lambda **kw: SimpleNamespace(
            id="ack", content="", metadata=kw["metadata"]
        ),
    )
    await dispatch()(run, language="en", lifecycle=hooks, settle_usage=None)
    await asyncio.gather(*research_jobs._POLLER_TASKS, return_exceptions=True)
    assert calls == []


@pytest.mark.asyncio
async def test_disconnected_memory_turn_reloads_its_saved_terminal_envelope(monkeypatch):
    from argus.api.chat.turn_lifecycle_hooks import ChatTurnLifecycleHooks
    from argus.api.chat.turn_lifecycle_projection import reconcile_and_project_chat_turns
    from argus.api.message_store import (
        accept_chat_turn,
        memory_conversation,
        prepare_message,
    )
    from argus.domain.store import AlphaStore

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(api_state, "store", AlphaStore())
    owner = api_state.store.get_or_create_dev_user().id
    conversation = memory_conversation(
        scope=PERSONAL,
        user_id=owner,
        title="Reload proof",
        title_source="user_renamed",
        language="en",
    )
    request_id = str(uuid4())
    request = accept_chat_turn(
        user_id=owner,
        conversation_id=conversation.id,
        request_id=request_id,
        message=prepare_message(
            conversation_id=conversation.id,
            role="user",
            content="Explain result",
            metadata={"chat_action": {"type": "show_breakdown"}},
        ),
    )
    hooks = ChatTurnLifecycleHooks(
        owner="ordinary_turn",
        user_id=owner,
        conversation_id=conversation.id,
        request_id=request_id,
        request_message=request,
    )
    hooks.mark_running()
    started, release = threading.Event(), threading.Event()

    def compose(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return breakdown.ResultBreakdownMessage(
            text="Bought once and held.",
            source="llm_breakdown_stage",
            fallback_used=False,
        )

    monkeypatch.setattr(breakdown, "result_breakdown_message_with_metadata", compose)
    run = _completed_run().model_copy(update={"conversation_id": conversation.id})
    stream = asyncio.create_task(
        dispatch()(run, language="en", lifecycle=hooks, settle_usage=None)
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        stream.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stream
        pending = reconcile_and_project_chat_turns(
            user_id=owner,
            conversation_id=conversation.id,
            messages=api_state.store.messages[conversation.id],
        )
        assert pending[0].metadata["agent_runtime_turn"]["status"] == "running"
        release.set()
        await asyncio.wait_for(asyncio.gather(*research_jobs._POLLER_TASKS), 3)
    finally:
        release.set()
    reloaded = reconcile_and_project_chat_turns(
        user_id=owner,
        conversation_id=conversation.id,
        messages=api_state.store.messages[conversation.id],
    )
    answers = [message for message in reloaded if message.role == "assistant"]
    assert len(answers) == 1
    assert answers[0].metadata["agent_runtime_turn"]["terminal"] is True
    assert (
        answers[0].metadata["result_readout_content"]["text"] == "Bought once and held."
    )
    assert api_state.store.chat_turn_lifecycles[request.id]["status"] == "completed"

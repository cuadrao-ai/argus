"""Retry excludes one identified reply from runtime history, without paid calls."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import agent as agent_router
from argus.domain.owner_scope import PERSONAL
from faker import Faker
from fastapi.testclient import TestClient

fake = Faker()


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []
    replies: list[dict[str, Any] | None] = []

    async def stream(**kwargs: Any):
        calls.append(kwargs)
        reply = replies.pop(0)
        if reply is None:
            raise asyncio.CancelledError()
        yield {
            "type": "final",
            "payload": {"stage_outcome": "ready_to_respond", **reply},
        }

    monkeypatch.setattr(agent_router, "stream_agent_turn_events", stream)
    with TestClient(app) as api:
        api.post("/api/v1/dev/reset")
        conversation_id = api.post("/api/v1/conversations", json={}).json()[
            "conversation"
        ]["id"]

        def ask(
            question: str,
            reply: dict[str, Any] | None,
            *,
            expected_frame: str | None = "final",
            **fields: Any,
        ):
            replies.append(reply)
            response = api.post(
                "/api/v1/chat/stream",
                headers=fields.pop("headers", {}),
                json={
                    "conversation_id": conversation_id,
                    "message": question,
                    "language": "en",
                    **fields,
                },
            )
            assert response.status_code == 200
            assert expected_frame is None or any(
                json.loads(line[6:]).get("type") == expected_frame
                for line in response.text.splitlines()
                if line.startswith("data: {")
            )
            return list(api_state.store.messages[conversation_id])

        yield ask, calls


def failure_reply(content: str) -> dict[str, Any]:
    return {
        "assistant_response": content,
        "recovery": {"code": "research_lookup_failed", "retryable": True},
    }


def history(call: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item.role, item.content) for item in call["recent_thread_history"]]


@pytest.mark.parametrize("under_answer", [False, True])
def test_retry_history_keeps_question_and_omits_only_target_reply(chat, under_answer):
    ask, calls = chat
    question = "What is Apple trading at right now?"
    unrelated, failed, answer = (fake.sentence() for _ in range(3))
    # Same question and another retryable reply: text equality must not retire it.
    ask(question, failure_reply(unrelated))
    reply = failure_reply(failed)
    if under_answer:
        reply["recovery"]["under_answer"] = True
    messages = ask(question, reply)
    failed_id = messages[-1].id
    messages = ask(
        question, {"assistant_response": answer}, failed_assistant_id=failed_id
    )

    assert calls[-1]["message"] == question
    assert history(calls[-1]) == [
        ("user", question),
        ("assistant", unrelated),
        ("user", question),
    ]
    assert messages[-2].metadata["failed_assistant_id"] == failed_id
    ask(fake.sentence(), {"assistant_response": fake.sentence()})
    assert ("assistant", unrelated) in history(calls[-1])
    assert ("assistant", failed) not in history(calls[-1])


@pytest.mark.parametrize("legacy_link", [False, True])
def test_later_followup_preserves_other_degraded_replies(chat, legacy_link):
    ask, calls = chat
    question = "What is Apple trading at right now?"
    valid, failed, answer = (fake.sentence() for _ in range(3))
    ask(
        question,
        {
            "assistant_response": valid,
            "research": {"degraded": {"code": "result_followup_research_unused"}},
        },
    )
    messages = ask(question, failure_reply(failed))
    # Different replay wording proves the durable link, not the text fallback.
    replay = "Please look up Apple's current quote."
    messages = ask(
        replay, {"assistant_response": answer}, failed_assistant_id=messages[-1].id
    )
    if legacy_link:
        metadata = messages[-2].metadata
        metadata["chat_action"] = {
            "type": "retry_last_turn",
            "payload": {"failed_assistant_id": metadata.pop("failed_assistant_id")},
        }
    ask("When was that?", {"assistant_response": fake.sentence()})

    assert history(calls[-1]) == [
        ("user", question),
        ("assistant", valid),
        ("user", question),
        ("user", replay),
        ("assistant", answer),
    ]


@pytest.mark.parametrize("target", ["absent", "unmatched", "user"])
def test_retry_identity_never_removes_other_roles_or_unidentified_replies(chat, target):
    ask, calls = chat
    question, failed = fake.sentence(), fake.sentence()
    messages = ask(question, failure_reply(failed))
    fields = (
        {}
        if target == "absent"
        else {
            "failed_assistant_id": messages[-2].id if target == "user" else fake.uuid4()
        }
    )
    ask(question, {"assistant_response": fake.sentence()}, **fields)
    ask(fake.sentence(), {"assistant_response": fake.sentence()})
    assert ("assistant", failed) in history(calls[-1])
    assert ("user", question) in history(calls[-1])


@pytest.mark.parametrize(
    "target", ["valid_reply", "stale_failure", "nonretryable_failure", "foreign"]
)
def test_invalid_retry_target_keeps_current_and_later_history_whole(chat, target):
    ask, calls = chat
    question, content = fake.sentence(), fake.sentence()
    reply = (
        failure_reply(content)
        if target != "valid_reply"
        else {"assistant_response": content}
    )
    if target == "nonretryable_failure":
        reply["recovery"]["retryable"] = False
    messages = ask(question, reply)
    target_id = messages[-1].id
    if target == "stale_failure":
        messages = ask(fake.sentence(), failure_reply(fake.sentence()))
    elif target == "foreign":
        from argus.api.message_store import memory_conversation, memory_message

        foreign = memory_conversation(
            scope=PERSONAL,
            title=fake.sentence(),
            title_source="user_renamed",
            language="en",
            user_id=fake.uuid4(),
        )
        target_id = memory_message(
            conversation_id=foreign.id,
            role="assistant",
            content=fake.sentence(),
            metadata={"recovery": {"retryable": True}},
        ).id
    expected = [(item.role, item.content) for item in messages]
    retry = ask(
        fake.sentence(),
        {"assistant_response": fake.sentence()},
        failed_assistant_id=target_id,
    )
    assert history(calls[-1]) == expected
    assert "failed_assistant_id" not in retry[-2].metadata
    ask(fake.sentence(), {"assistant_response": fake.sentence()})
    assert history(calls[-1])[: len(expected)] == expected


@pytest.mark.parametrize("repeat_question", [False, True])
def test_ordinary_turn_clears_an_interrupted_retry_retirement(chat, repeat_question):
    ask, calls = chat
    question, failure = fake.sentence(), fake.sentence()
    messages = ask(question, failure_reply(failure))
    failed_id = messages[-1].id
    messages = ask(question, None, expected_frame=None, failed_assistant_id=failed_id)
    assert messages[-1].role == "user"
    assert messages[-1].metadata["failed_assistant_id"] == failed_id
    assert ("assistant", failure) not in history(calls[-1])
    ask(
        question if repeat_question else fake.sentence(),
        {"assistant_response": fake.sentence()},
    )
    assert ("assistant", failure) in history(calls[-1])
    messages = ask(fake.sentence(), {"assistant_response": fake.sentence()})
    assert ("assistant", failure) in history(calls[-1])
    from argus.api.message_store import reconcile_reload_message_metadata

    original = next(
        item
        for item in reconcile_reload_message_metadata(messages)
        if item.id == failed_id
    )
    assert original.metadata["recovery"]["retryable"] is True
    assert not original.metadata.get("agent_runtime_failure_superseded")


def test_canonical_run_finalization_retry_persists_its_link_for_followups(
    chat, monkeypatch
):
    from argus.api.chat import persistence
    from argus.api.chat.actions import RuntimeFallbackContext
    from argus.domain.backtest_finalization import BacktestFinalizationError

    from tests.test_alpha_api_supabase import _runtime_success_result

    ask, calls = chat
    monkeypatch.setattr(
        agent_router, "stale_confirmation_action_message", lambda **_: None
    )
    monkeypatch.setattr(
        agent_router,
        "confirmation_metadata_fallback_context",
        lambda **_: RuntimeFallbackContext(),
    )
    persist = persistence.persist_runtime_backtest_run
    executions = []

    def fail_first(**kwargs):
        executions.append(kwargs["execution_identity"])
        if len(executions) == 1:
            raise BacktestFinalizationError("scripted finalization failure")
        return persist(**kwargs)

    monkeypatch.setattr(persistence, "persist_runtime_backtest_run", fail_first)
    confirmation_id = fake.uuid4()
    fields = {
        "headers": {"Idempotency-Key": confirmation_id},
        "action": {
            "type": "run_backtest",
            "label": "Run backtest",
            "payload": {"confirmation_id": confirmation_id},
            "presentation": "confirmation",
        },
    }
    first = ask(
        "Run backtest", _runtime_success_result(), expected_frame="error", **fields
    )
    original_request, failed = first[-2:]
    assert failed.metadata["failure_code"] == "finalization_failed"
    retried = ask(
        "Run backtest", _runtime_success_result(), failed_assistant_id=failed.id, **fields
    )
    retry_request = next(
        item
        for item in retried
        if item.role == "user" and item.metadata.get("failed_assistant_id") == failed.id
    )
    assert retry_request.id != original_request.id
    assert retry_request.created_at > failed.created_at
    assert (
        retry_request.metadata["chat_action"] == original_request.metadata["chat_action"]
    )
    assert executions == [executions[0], executions[0]]
    assert ("assistant", failed.content) not in history(calls[-1])
    ask(fake.sentence(), {"assistant_response": fake.sentence()})
    assert ("assistant", failed.content) not in history(calls[-1])

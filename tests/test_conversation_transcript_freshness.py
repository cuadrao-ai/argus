"""Saved-message freshness is independent of operation/read lifecycle state."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from argus.api import state as api_state
from argus.api.conversation_activity import conversation_activity_service
from argus.api.schemas import Conversation
from argus.domain.store import AlphaStore
from faker import Faker

from tests.conversation_fixtures import seed_message

fake = Faker()


def test_plain_reply_changes_freshness_without_a_job_or_lifecycle(monkeypatch):
    store = AlphaStore()
    monkeypatch.setattr(api_state, "store", store)
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    owner, conversation_id = fake.uuid4(), fake.uuid4()
    now = datetime.now(timezone.utc)
    store.conversations[conversation_id] = Conversation(
        id=conversation_id,
        title=fake.sentence(),
        created_at=now,
        updated_at=now,
    )
    store.conversation_owners[conversation_id] = owner

    def project():
        return conversation_activity_service.project(
            user_id=owner,
            conversation_ids=[conversation_id],
        )[conversation_id]

    assert project().latest_message_id is None
    user = seed_message(
        conversation_id=conversation_id, role="user", content=fake.sentence()
    )
    assert project().latest_message_id == user.id
    reply = seed_message(
        conversation_id=conversation_id, role="assistant", content=fake.sentence()
    )
    result = project()
    assert result.latest_message_id == reply.id
    assert result.operation.status == "idle"
    assert result.operation.updated_at is None
    assert result.attention.cursor is None
    assert not store.backtest_jobs
    assert not store.chat_turn_lifecycles
    assert store.conversations[conversation_id].updated_at >= now


@pytest.mark.parametrize("store_kind", ["memory", "supabase"])
def test_freshness_cannot_expose_another_owners_latest_message(monkeypatch, store_kind):
    owner, other, conversation_id, message_id = [fake.uuid4() for _ in range(4)]
    store = AlphaStore()
    store.conversation_owners[conversation_id] = other
    monkeypatch.setattr(api_state, "store", store)
    calls = []

    def read(**kwargs):
        calls.append(kwargs)
        return []

    gateway = SimpleNamespace(
        read_conversation_activity_batch=lambda **kwargs: [
            {"conversation_id": conversation_id, "sources": [], "read_state": None}
        ],
        read_conversation_preview_messages=read,
    )
    monkeypatch.setattr(
        api_state, "supabase_gateway", gateway if store_kind == "supabase" else None
    )
    result = conversation_activity_service.project(
        user_id=owner, conversation_ids=[conversation_id]
    )
    assert result[conversation_id].latest_message_id is None
    if store_kind == "supabase":
        assert calls == [{"user_id": owner, "conversation_ids": [conversation_id]}]

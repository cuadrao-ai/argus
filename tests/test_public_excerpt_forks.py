import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.api.public_excerpt_schemas import (
    PublicExcerptAnswerTurn,
    PublicExcerptTurnsPayload,
)
from argus.domain.public_excerpt_forks import (
    FORK_PAYLOAD_BYTES,
    FORK_TEXT_BYTES,
    ForkError,
    carried_messages,
)


def test_carried_context_is_bounded_and_note_is_never_carried():
    payload = PublicExcerptTurnsPayload(
        turns=[
            PublicExcerptAnswerTurn(
                question="¿Pregunta?" * 10000,
                answer="答案" * 100000,
                owner_note="never carry this",
            )
            for _ in range(4)
        ]
    )
    messages = carried_messages(
        payload,
        snapshot_at=datetime.now(timezone.utc),
        public_id="public",
        request_id=str(uuid4()),
    )
    assert len(messages) == 8
    assert sum(len(m["content"].encode()) for m in messages) <= FORK_TEXT_BYTES
    assert len(json.dumps(messages, ensure_ascii=False).encode()) <= FORK_PAYLOAD_BYTES
    assert "never carry this" not in json.dumps(messages)
    assert [m["role"] for m in messages] == ["user", "assistant"] * 4
    assert all(set(m["metadata"]) == {"shared_conversation"} for m in messages)


def test_facts_over_payload_bound_refuse():
    from argus.api.public_excerpt_schemas import (
        PublicExcerptResearchSource,
        PublicExcerptResearchTurn,
    )

    payload = PublicExcerptTurnsPayload(
        turns=[
            PublicExcerptResearchTurn(
                question="Q",
                answer="A",
                sources=[
                    PublicExcerptResearchSource(
                        title="x" * FORK_PAYLOAD_BYTES,
                        domain="example.com",
                        url="https://example.com",
                    )
                ],
            )
        ]
    )
    with pytest.raises(ForkError, match="receipt_context_too_large"):
        carried_messages(
            payload,
            snapshot_at=datetime.now(timezone.utc),
            public_id="public",
            request_id=str(uuid4()),
        )


def test_view_no_write_and_fork_is_owned_idempotent_and_revoked_copy_survives(
    monkeypatch,
):
    from argus.api import state
    from argus.api.artifact_naming import _conversation_title_context_from_messages
    from argus.api.main import app
    from argus.api.message_store import load_runtime_thread_history
    from fastapi.testclient import TestClient

    from tests.test_public_excerpt_api import _create, _seed

    monkeypatch.setattr(state, "supabase_gateway", None)
    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")
    state.store.reset()
    client = TestClient(app)
    owner = _seed(client)
    receipt = _create(client, "private owner note")
    initial_chats = len(state.store.conversations)
    initial_messages = sum(len(m) for m in state.store.messages.values())
    path = f"/api/v1/public/receipts/{receipt['public_id']}"
    assert client.get(path).status_code == 200
    assert len(state.store.conversations) == initial_chats
    assert sum(len(m) for m in state.store.messages.values()) == initial_messages
    request = {"request_id": str(uuid4())}
    first = client.post(path + "/fork", json=request)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"]
    chat_id = body["conversation"]["id"]
    assert state.store.conversation_owners[chat_id] == owner
    assert len(state.store.conversations) == initial_chats + 1
    assert "private owner note" not in str(state.store.messages[chat_id])
    assert len(load_runtime_thread_history(user_id=owner, conversation_id=chat_id)) == 2
    assert (
        load_runtime_thread_history(
            user_id=owner, conversation_id=chat_id, drop_shared_turns=True
        )
        == []
    )
    naming = _conversation_title_context_from_messages(
        user_id=owner,
        conversation_id=chat_id,
        user_message="My own question",
        assistant_message=None,
    )
    assert "My own question" in naming
    assert state.store.messages[chat_id][0].content not in naming
    client.delete(f"/api/v1/public-excerpts/{receipt['id']}")
    replay = client.post(path + "/fork", json=request)
    assert replay.status_code == 200, replay.text
    assert replay.json()["conversation"]["id"] == chat_id
    assert not replay.json()["created"]
    assert (
        client.post(path + "/fork", json={"request_id": str(uuid4())}).status_code == 410
    )


def test_flag_off_fork_is_hidden_before_auth_or_body_validation(monkeypatch):
    from argus.api.dependencies import current_user
    from argus.api.main import app
    from fastapi.testclient import TestClient

    def auth_must_not_run():
        raise AssertionError("auth resolved behind disabled flag")

    monkeypatch.delenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", raising=False)
    app.dependency_overrides[current_user] = auth_must_not_run
    try:
        client = TestClient(app)
        result = client.post("/api/v1/public/receipts/example/fork", content="not json")
        missing = client.post("/api/v1/nonexistent")
        assert result.status_code == missing.status_code == 404
        assert result.content == missing.content
    finally:
        app.dependency_overrides.pop(current_user, None)


@pytest.mark.parametrize(
    "replayed,kind",
    [
        (False, "new_account_signup"),
        (True, "new_account_signup"),
        (False, "existing_account"),
    ],
)
def test_a_completed_handoff_counts_no_shared_signup(mocker, monkeypatch, replayed, kind):
    """Wave 1 tracks no share funnel (SPEC 0, 0C-1): a signup that came from a
    shared conversation is not looked up or counted."""
    from types import SimpleNamespace

    from argus.domain.supabase_guest_accounts import GuestAccountPersistenceMixin

    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )
    gateway = GuestAccountPersistenceMixin()
    gateway.client = mocker.MagicMock()
    gateway.client.rpc.return_value.execute.return_value = SimpleNamespace(
        data=[
            {
                "source_user_id": str(uuid4()),
                "conversation_id": str(uuid4()),
                "replayed": replayed,
            }
        ]
    )
    gateway.client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
        data=[{"handoff_kind": kind}]
    )

    payload = gateway.claim_guest_workspace_handoff(
        handoff_id=str(uuid4()),
        opaque_secret="local-fixture-secret",
        destination_user_id=str(uuid4()),
    )

    assert payload["handoff_kind"] == kind
    assert [call.args for call in gateway.client.table.call_args_list] == [
        ("guest_workspace_handoffs",)
    ]
    assert posts == []


@pytest.mark.parametrize("revoked", [False, True])
def test_memory_replay_follows_transferred_ownership(monkeypatch, revoked):
    from types import SimpleNamespace

    from argus.api import state
    from argus.api.public_excerpt_schemas import PublicExcerptView
    from argus.api.routers.receipt_forks import PublicExcerptForkRequest, _memory_fork
    from argus.domain.public_excerpt_forks import fork_marker

    state.store.reset()
    guest = state.store.get_or_create_dev_user()
    receiver = guest.model_copy(update={"id": str(uuid4())})
    request = PublicExcerptForkRequest(request_id=uuid4())
    view = PublicExcerptView(
        public_id="frozen",
        status="available",
        created_at=datetime.now(timezone.utc),
        payload=PublicExcerptTurnsPayload(
            turns=[PublicExcerptAnswerTurn(question="Question", answer="Answer")]
        ),
    )
    monkeypatch.setattr(
        "argus.api.routers.receipt_forks.public_excerpt_reader",
        lambda: SimpleNamespace(read_public_excerpt_view=lambda **_: view),
    )
    chat, _ = _memory_fork(user=guest, public_id="frozen", payload=request)
    before = list(state.store.messages[chat.id])
    assert before[0].id == fork_marker(guest.id, str(request.request_id))
    state.store.conversation_owners[chat.id] = receiver.id
    if revoked:
        view = view.model_copy(update={"status": "revoked", "payload": None})
    replay, created = _memory_fork(user=receiver, public_id="frozen", payload=request)
    assert replay.id == chat.id and not created
    assert state.store.messages[chat.id] == before
    assert len(state.store.conversations) == 1
    with pytest.raises(ForkError, match="receipt_request_conflict"):
        _memory_fork(user=receiver, public_id="different", payload=request)


def test_memory_request_collision_stays_owner_scoped_and_fails_closed_after_transfer(
    monkeypatch,
):
    from types import SimpleNamespace

    from argus.api import state
    from argus.api.public_excerpt_schemas import PublicExcerptView
    from argus.api.routers.receipt_forks import PublicExcerptForkRequest, _memory_fork

    state.store.reset()
    guest = state.store.get_or_create_dev_user()
    receiver = guest.model_copy(update={"id": str(uuid4())})
    request = PublicExcerptForkRequest(request_id=uuid4())
    payload = PublicExcerptTurnsPayload(
        turns=[PublicExcerptAnswerTurn(question="Question", answer="Answer")]
    )
    monkeypatch.setattr(
        "argus.api.routers.receipt_forks.public_excerpt_reader",
        lambda: SimpleNamespace(
            read_public_excerpt_view=lambda public_id: PublicExcerptView(
                public_id=public_id,
                status="available",
                created_at=datetime.now(timezone.utc),
                payload=payload,
            )
        ),
    )
    first, _ = _memory_fork(user=guest, public_id="first", payload=request)
    second, created = _memory_fork(user=receiver, public_id="second", payload=request)
    assert created and second.id != first.id
    assert _memory_fork(user=guest, public_id="first", payload=request)[0].id == first.id
    assert (
        _memory_fork(user=receiver, public_id="second", payload=request)[0].id
        == second.id
    )
    state.store.conversation_owners[first.id] = receiver.id
    for public_id in ("first", "second"):
        with pytest.raises(ForkError, match="receipt_request_conflict"):
            _memory_fork(user=receiver, public_id=public_id, payload=request)
    assert len(state.store.conversations) == 2

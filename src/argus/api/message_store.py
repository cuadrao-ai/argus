from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from loguru import logger

from argus.agent_runtime.history import select_thread_history
from argus.agent_runtime.state.models import ConversationMessage
from argus.api import state as api_state
from argus.api.chat.previews import (
    is_degraded_clarification_compatibility_text,
    research_lookup_failed,
    stored_message_preview,
)
from argus.api.dependencies import dev_memory_fallback_enabled
from argus.api.schemas import ChatStreamRequest, Conversation, Message, MessageRole
from argus.domain.chat_turn_lifecycle import (
    MemoryChatTurnLifecycleGateway,
    TransitionResult,
    TurnStatus,
)
from argus.domain.confirmation_turn_facts import (
    confirmation_turn_facts,
    confirmation_turn_history_text,
)
from argus.domain.owner_scope import OwnerScope, space_id, surface_of
from argus.domain.store import utcnow
from argus.domain.supabase_conversation_messages import StaleMessageArtifactError
from argus.domain.usage_limits import settle_memory_usage

_AUTHORITATIVE_ARTIFACT_KEYS = {
    "active_confirmation_reference",
    "backtest_job",
    "backtest_job_id",
    "confirmation_card",
    "confirmation_payload",
    "latest_run_id",
    "result_card",
    "result_run_id",
    "tool_result_cards",
}
_RUNTIME_FAILURE_SUPERSEDED_KEY = "agent_runtime_failure_superseded"


@dataclass(frozen=True)
class ResponseOptionActionClaim:
    source_message: Message
    request_message: Message


def accept_chat_turn(
    *,
    user_id: str,
    conversation_id: str,
    request_id: str,
    message: Message,
) -> Message:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        try:
            return gateway.accept_chat_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=request_id,
                message=message,
            )
        except Exception:
            if not dev_memory_fallback_enabled():
                raise
            logger.opt(exception=True).warning(
                "Supabase chat-turn acceptance failed; using memory fallback",
                conversation_id=conversation_id,
            )
    return MemoryChatTurnLifecycleGateway(api_state.store).accept_chat_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        message=message,
    )


def accept_response_option_chat_turn(
    *,
    user_id: str,
    conversation_id: str,
    request_id: str,
    message: Message,
    source_assistant_id: str | None,
    expected_source_metadata: dict[str, Any] | None,
    option_id: str | None,
    replacement_values: dict[str, Any] | None,
    request_message_id: str | None = None,
) -> ResponseOptionActionClaim | None:
    gateway = api_state.supabase_gateway
    claimed: tuple[Message, Message] | None
    if gateway is not None:
        try:
            claimed = gateway.accept_response_option_chat_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=request_id,
                message=message,
                source_assistant_id=source_assistant_id,
                expected_source_metadata=expected_source_metadata,
                option_id=option_id,
                replacement_values=replacement_values,
                request_message_id=request_message_id,
            )
        except ValueError:
            return None
        except Exception:
            if not dev_memory_fallback_enabled():
                raise
            logger.opt(exception=True).warning(
                "Supabase response-option acceptance failed; using memory fallback",
                conversation_id=conversation_id,
            )
            claimed = None
        else:
            source, request_message = claimed
            return ResponseOptionActionClaim(
                source_message=source,
                request_message=request_message,
            )
    claimed = MemoryChatTurnLifecycleGateway(
        api_state.store
    ).accept_response_option_chat_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        message=message,
        source_assistant_id=source_assistant_id,
        expected_source_metadata=expected_source_metadata,
        option_id=option_id,
        replacement_values=replacement_values,
        request_message_id=request_message_id,
    )
    if claimed is None:
        return None
    source, request_message = claimed
    return ResponseOptionActionClaim(
        source_message=source,
        request_message=request_message,
    )


def finalize_chat_turn(
    *,
    user_id: str,
    conversation_id: str,
    turn_id: str,
    request_id: str,
    message: Message,
    to_status: TurnStatus,
    failure_code: str | None,
    retryable: bool,
    settle_usage: dict[str, Any] | None,
) -> Message:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        try:
            return gateway.finalize_chat_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                request_id=request_id,
                message=message,
                to_status=to_status,
                failure_code=failure_code,
                retryable=retryable,
                settle_usage=settle_usage,
            )
        except Exception:
            if not dev_memory_fallback_enabled():
                raise
            logger.opt(exception=True).warning(
                "Supabase chat-turn finalization failed; using memory fallback",
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
    return MemoryChatTurnLifecycleGateway(api_state.store).finalize_chat_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        request_id=request_id,
        message=message,
        to_status=to_status,
        failure_code=failure_code,
        retryable=retryable,
        settle_usage=settle_usage,
    )


def transition_chat_turn(
    *,
    turn_id: str,
    to_status: TurnStatus,
) -> TransitionResult:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        return gateway.transition_chat_turn(
            turn_id=turn_id,
            to_status=to_status,
            assistant_message_id=None,
            reconciled_outcome=None,
            failure_code=None,
            retryable=None,
        )
    return MemoryChatTurnLifecycleGateway(api_state.store).transition_chat_turn(
        turn_id=turn_id,
        to_status=to_status,
        assistant_message_id=None,
        reconciled_outcome=None,
        failure_code=None,
        retryable=None,
    )


def reconcile_stale_chat_turns(
    *,
    user_id: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        return gateway.reconcile_stale_chat_turns(
            user_id=user_id,
            conversation_id=conversation_id,
        )
    return MemoryChatTurnLifecycleGateway(api_state.store).reconcile_stale_chat_turns(
        user_id=user_id,
        conversation_id=conversation_id,
    )


def list_projectable_chat_turns(
    *,
    user_id: str,
    conversation_id: str,
    message_ids: list[str],
) -> list[dict[str, Any]]:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        return gateway.list_projectable_chat_turns(
            user_id=user_id,
            conversation_id=conversation_id,
            message_ids=message_ids,
        )
    return MemoryChatTurnLifecycleGateway(api_state.store).list_projectable_chat_turns(
        user_id=user_id,
        conversation_id=conversation_id,
        message_ids=message_ids,
    )


def memory_conversation(
    *,
    title: str,
    title_source: str,
    language: str | None,
    scope: OwnerScope,
    user_id: str | None = None,
) -> Conversation:
    now = utcnow()
    conversation = Conversation(
        id=api_state.store.new_id(),
        title=title,
        title_source=title_source,
        language=language,
        created_at=now,
        updated_at=now,
        surface=surface_of(space_id(scope)),
    )
    api_state.store.conversations[conversation.id] = conversation
    if user_id is not None:
        api_state.store.conversation_owners[conversation.id] = user_id
    owner_space_id = space_id(scope)
    if owner_space_id is not None:
        api_state.store.conversation_spaces[conversation.id] = owner_space_id
    api_state.store.messages[conversation.id] = []
    return conversation


message_preview = stored_message_preview


def memory_message(
    *,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Message:
    return _append_memory_message(
        prepare_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
        )
    )


def prepare_message(
    *,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> Message:
    return Message(
        id=message_id or api_state.store.new_id(),
        conversation_id=conversation_id,
        role=cast(MessageRole, role),
        content=content,
        created_at=utcnow(),
        metadata=metadata if metadata is not None else {},
    )


def _append_memory_message(message: Message) -> Message:
    with api_state.store.conversation_message_lock:
        messages = api_state.store.messages.setdefault(message.conversation_id, [])
        if messages:
            latest_created_at = max(item.created_at for item in messages)
            if message.created_at <= latest_created_at:
                message = message.model_copy(
                    update={"created_at": latest_created_at + timedelta(microseconds=1)}
                )
        messages.append(message)
        api_state.store.bump_search_revision()
        preview = message_preview(
            message.content,
            role=message.role,
            metadata=message.metadata,
        )
        conversation = api_state.store.conversations.get(message.conversation_id)
        if conversation and preview:
            api_state.store.conversations[message.conversation_id] = (
                conversation.model_copy(
                    update={"last_message_preview": preview, "updated_at": utcnow()}
                )
            )
        return message


def claim_response_option_action(
    *,
    user_id: str,
    conversation_id: str,
    source_assistant_id: str,
    option_id: str,
    replacement_values: dict[str, Any],
    request_message: Message,
    expected_source_metadata: dict[str, Any] | None = None,
) -> ResponseOptionActionClaim | None:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        claimed = gateway.claim_response_option_action(
            user_id=user_id,
            conversation_id=conversation_id,
            source_assistant_id=source_assistant_id,
            option_id=option_id,
            replacement_values=replacement_values,
            request_message=request_message,
            expected_source_metadata=expected_source_metadata,
        )
        if claimed is None:
            return None
        source_message, accepted_request = claimed
        return ResponseOptionActionClaim(
            source_message=source_message,
            request_message=accepted_request,
        )

    with api_state.store.conversation_message_lock:
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            return None
        if request_message.conversation_id != conversation_id:
            raise ValueError("Request message conversation does not match claim.")

        existing = next(
            (
                message
                for messages in api_state.store.messages.values()
                for message in messages
                if message.id == request_message.id
            ),
            None,
        )
        conversation_messages = api_state.store.messages.get(conversation_id, [])
        if existing is not None:
            if not _same_immutable_message(existing, request_message):
                raise ValueError(
                    "Message identity collided with different immutable payload."
                )
            preceding = [
                message
                for message in conversation_messages
                if (message.created_at, message.id) < (existing.created_at, existing.id)
            ]
            replay_source = (
                max(preceding, key=lambda item: (item.created_at, item.id))
                if preceding
                else None
            )
            if not _is_exact_response_option_source(
                replay_source,
                source_assistant_id=source_assistant_id,
                option_id=option_id,
                replacement_values=replacement_values,
                expected_source_metadata=expected_source_metadata,
            ):
                return None
            assert replay_source is not None
            return ResponseOptionActionClaim(
                source_message=replay_source,
                request_message=existing,
            )

        latest = (
            max(conversation_messages, key=lambda item: (item.created_at, item.id))
            if conversation_messages
            else None
        )
        if not _is_exact_response_option_source(
            latest,
            source_assistant_id=source_assistant_id,
            option_id=option_id,
            replacement_values=replacement_values,
            expected_source_metadata=expected_source_metadata,
        ):
            return None
        assert latest is not None
        accepted_request = _append_memory_message(request_message)
        return ResponseOptionActionClaim(
            source_message=latest,
            request_message=accepted_request,
        )


def _same_immutable_message(existing: Message, requested: Message) -> bool:
    return (
        existing.conversation_id == requested.conversation_id
        and existing.role == requested.role
        and existing.content == requested.content
        and (existing.metadata or {}) == (requested.metadata or {})
    )


def _is_exact_response_option_source(
    source_message: Message | None,
    *,
    source_assistant_id: str,
    option_id: str,
    replacement_values: dict[str, Any],
    expected_source_metadata: dict[str, Any] | None = None,
) -> bool:
    if (
        source_message is None
        or source_message.id != source_assistant_id
        or source_message.role != "assistant"
        or not isinstance(source_message.metadata, dict)
    ):
        return False
    if (
        expected_source_metadata is not None
        and source_message.metadata != expected_source_metadata
    ):
        return False
    clarification = source_message.metadata.get("clarification")
    if not isinstance(clarification, dict):
        return False
    options = clarification.get("options")
    if not isinstance(options, list):
        return False
    return any(
        isinstance(option, dict)
        and option.get("id") == option_id
        and option.get("replacement_values") == replacement_values
        for option in options
    )


def owned_conversation_message(
    *,
    user_id: str,
    conversation_id: str,
    message_id: str,
) -> Message | None:
    gateway = api_state.supabase_gateway
    if gateway is not None:
        return gateway.get_message(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
    with api_state.store.conversation_message_lock:
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            return None
        return next(
            (
                message
                for message in api_state.store.messages.get(conversation_id, [])
                if message.id == message_id
            ),
            None,
        )


def _ephemeral_suppressed_message(
    *,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Message:
    return Message(
        id=api_state.store.new_id(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=utcnow(),
        metadata=metadata,
    )


def create_message(
    *,
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    settle_usage: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> Message:
    if _should_suppress_late_success_artifact(
        user_id=user_id,
        conversation_id=conversation_id,
        role=role,
        metadata=metadata,
    ):
        logger.warning(
            "Suppressing late assistant artifact after terminal runtime failure",
            conversation_id=conversation_id,
            artifact_keys=sorted(
                key
                for key in _AUTHORITATIVE_ARTIFACT_KEYS
                if isinstance(metadata, dict) and metadata.get(key)
            ),
        )
        return _ephemeral_suppressed_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
        )
    if api_state.supabase_gateway is not None:
        try:
            return api_state.supabase_gateway.create_message(
                user_id=user_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                metadata=metadata,
                settle_usage=settle_usage,
                message_id=message_id,
            )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase message write failed; using dev memory fallback",
                error=str(exc),
                conversation_id=conversation_id,
            )
    if message_id is not None:
        message, replayed = _append_idempotent_memory_message(
            user_id=user_id,
            message=prepare_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                metadata=metadata,
                message_id=message_id,
            ),
        )
        if settle_usage is not None and not replayed:
            settle_memory_usage(
                api_state.store.usage_counters,
                user_id=user_id,
                resource=settle_usage["resource"],
                limits=settle_usage["limits"],
            )
        return message
    if settle_usage is not None:
        settle_memory_usage(
            api_state.store.usage_counters,
            user_id=user_id,
            resource=settle_usage["resource"],
            limits=settle_usage["limits"],
        )
    return memory_message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata=metadata,
    )


def latest_message(
    *,
    user_id: str,
    conversation_id: str,
) -> Message | None:
    """The conversation's newest message by (created_at, id), both stores.

    The activity guard on in-place writes compares against this value, so
    it must come from a dedicated newest-first read, never from a bounded
    recent-window listing whose tail is not the conversation's tail.
    """
    if api_state.supabase_gateway is not None:
        try:
            return api_state.supabase_gateway.latest_message(
                user_id=user_id,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase latest-message read failed; using dev memory fallback",
                error=str(exc),
                conversation_id=conversation_id,
            )
    with api_state.store.conversation_message_lock:
        messages = api_state.store.messages.get(conversation_id, [])
        return max(messages, key=lambda item: (item.created_at, item.id), default=None)


def update_message_artifact(
    *,
    user_id: str,
    conversation_id: str,
    message_id: str,
    content: str,
    metadata: dict[str, Any],
    expected_source_metadata: dict[str, Any] | None,
    expected_latest_message_id: str | None,
    preview: str | None = None,
) -> Message:
    """Rewrite one owned message's content and metadata in place.

    The in-place half of the edit contract: a direct edit updates the card's
    own record, so the transcript gains nothing and the message identity,
    role, and position stay fixed. Turn-based edits keep superseding through
    create_message. The write is conditional on what the caller read, in
    two parts: the row guard compares the card's metadata, and the activity
    guard compares the conversation's latest message id, because every
    superseding event appends a message while a non-turn edit appends
    nothing, so an interleaved append invalidates the caller's active-state
    check. Either mismatch raises ``StaleMessageArtifactError`` in both
    stores instead of rolling the other writer back. When the rewritten row
    is the conversation's latest message, ``preview`` follows it into the
    conversation record without touching ``updated_at``: a non-turn change
    spends nothing and must not reorder recents.
    """
    if api_state.supabase_gateway is not None:
        try:
            return api_state.supabase_gateway.update_message_artifact(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                content=content,
                metadata=metadata,
                expected_source_metadata=expected_source_metadata,
                expected_latest_message_id=expected_latest_message_id,
                preview=preview,
            )
        except StaleMessageArtifactError:
            # A conflict is an answer, not an outage; it must never be
            # retried against the memory fallback.
            raise
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase message update failed; using dev memory fallback",
                error=str(exc),
                conversation_id=conversation_id,
            )
    with api_state.store.conversation_message_lock:
        if api_state.store.conversation_owners.get(conversation_id) != user_id:
            raise ValueError("Conversation not found or not owned by user.")
        messages = api_state.store.messages.get(conversation_id, [])
        latest = max(messages, key=lambda item: (item.created_at, item.id), default=None)
        for index, existing in enumerate(messages):
            if existing.id != message_id:
                continue
            if (
                expected_latest_message_id is not None
                and latest is not None
                and latest.id != expected_latest_message_id
            ):
                raise StaleMessageArtifactError(
                    "The card changed while this update was in flight."
                )
            if (
                expected_source_metadata is not None
                and existing.metadata != expected_source_metadata
            ):
                raise StaleMessageArtifactError(
                    "The card changed while this update was in flight."
                )
            updated = existing.model_copy(
                update={"content": content, "metadata": metadata}
            )
            messages[index] = updated
            api_state.store.bump_search_revision()
            conversation = api_state.store.conversations.get(conversation_id)
            if (
                preview
                and conversation
                and latest is not None
                and latest.id == message_id
            ):
                api_state.store.conversations[conversation_id] = conversation.model_copy(
                    update={"last_message_preview": preview}
                )
            return updated
    raise ValueError("Message not found or not owned by user.")


def _append_idempotent_memory_message(
    *,
    user_id: str,
    message: Message,
) -> tuple[Message, bool]:
    with api_state.store.conversation_message_lock:
        if api_state.store.conversation_owners.get(message.conversation_id) != user_id:
            raise ValueError("Conversation not found or not owned by user.")
        existing = next(
            (
                item
                for messages in api_state.store.messages.values()
                for item in messages
                if item.id == message.id
            ),
            None,
        )
        if existing is not None:
            if not _same_immutable_message(existing, message):
                raise ValueError(
                    "Message identity collided with different immutable payload."
                )
            return existing, True
        return _append_memory_message(message), False


def reconcile_reload_message_metadata(messages: list[Message]) -> list[Message]:
    retried_failure_ids = _retried_failed_assistant_ids(messages)
    artifact_request_ids_after: set[str] = set()
    same_segment_artifact_after = False
    reconciled_reversed: list[Message] = []
    for message in reversed(messages):
        metadata = message.metadata
        next_message = message
        if message.role == "user":
            same_segment_artifact_after = False
            reconciled_reversed.append(next_message)
            continue
        if message.role == "assistant" and isinstance(metadata, dict):
            request_id = _runtime_turn_request_id(metadata)
            should_supersede = (
                request_id in artifact_request_ids_after
                if request_id is not None
                else same_segment_artifact_after
            )
            if (should_supersede and _is_visible_runtime_failure(metadata)) or (
                message.id in retried_failure_ids
                and _is_retryable_recovery_failure(metadata)
            ):
                updated_metadata = _supersede_retry_last_turn(metadata)
                updated_metadata = {
                    **updated_metadata,
                    _RUNTIME_FAILURE_SUPERSEDED_KEY: True,
                }
                if updated_metadata is not metadata:
                    next_message = message.model_copy(
                        update={"metadata": updated_metadata}
                    )
            if _metadata_has_authoritative_artifact(metadata):
                same_segment_artifact_after = True
                if request_id is not None:
                    artifact_request_ids_after.add(request_id)
        reconciled_reversed.append(next_message)
    return list(reversed(reconciled_reversed))


def load_chat_request_history(
    *,
    payload: ChatStreamRequest,
    user_id: str,
    conversation_id: str,
) -> tuple[ChatStreamRequest, list[ConversationMessage]]:
    """Normalize retry identity and history from the same owned message snapshot."""
    messages = _load_runtime_thread_messages(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=20,
    )
    history, failed_id = _runtime_thread_history(
        messages,
        conversation_id=conversation_id,
        failed_assistant_id=payload.failed_assistant_id,
    )
    return payload.model_copy(update={"failed_assistant_id": failed_id}), history


def load_runtime_thread_history(
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 20,
    drop_failed_lookups: bool = False,
    drop_shared_turns: bool = False,
    failed_assistant_id: str | None = None,
) -> list[ConversationMessage]:
    messages = _load_runtime_thread_messages(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
        drop_shared_turns=drop_shared_turns,
    )
    history, _ = _runtime_thread_history(
        messages,
        conversation_id=conversation_id,
        limit=limit,
        drop_failed_lookups=drop_failed_lookups,
        drop_shared_turns=drop_shared_turns,
        failed_assistant_id=failed_assistant_id,
    )
    return history


def _load_runtime_thread_messages(
    *,
    user_id: str,
    conversation_id: str,
    limit: int,
    drop_shared_turns: bool = False,
) -> list[Message]:
    messages: list[Message] = []
    imported: list[Message] = []
    if api_state.supabase_gateway is not None:
        try:
            messages = api_state.supabase_gateway.list_messages(
                user_id=user_id,
                conversation_id=conversation_id,
                limit=limit,
                newest_first_window=True,
            )
            if not drop_shared_turns:
                imported = api_state.supabase_gateway.list_shared_messages(
                    user_id=user_id, conversation_id=conversation_id
                )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            messages = []
            logger.warning(
                "Supabase message history read failed; using dev memory fallback",
                error=str(exc),
                conversation_id=conversation_id,
            )
    if (
        not messages
        and api_state.store.conversation_owners.get(conversation_id) == user_id
    ):
        stored = list(api_state.store.messages.get(conversation_id, []))
        messages = stored[-limit:]
        if not drop_shared_turns:
            imported = [
                message
                for message in stored
                if isinstance((message.metadata or {}).get("shared_conversation"), dict)
            ]
    return sorted(
        {message.id: message for message in [*imported, *messages]}.values(),
        key=lambda item: (item.created_at, item.id),
    )


def _runtime_thread_history(
    messages: list[Message],
    *,
    conversation_id: str,
    limit: int = 20,
    drop_failed_lookups: bool = False,
    drop_shared_turns: bool = False,
    failed_assistant_id: str | None = None,
) -> tuple[list[ConversationMessage], str | None]:
    # Runtime history uses explicit retry identity, never repeated-question text.
    excluded_reply_ids = _retried_failed_assistant_ids(messages, explicit_only=True)
    failed_assistant_id = _validated_retry_reply_id(
        next((item for item in reversed(messages) if item.role == "assistant"), None),
        failed_assistant_id,
        conversation_id=conversation_id,
    )
    if failed_assistant_id is not None:
        excluded_reply_ids.add(failed_assistant_id)
    history: list[ConversationMessage] = []
    for message in messages:
        if drop_shared_turns and (message.metadata or {}).get("shared_conversation"):
            continue
        if message.role not in {"user", "assistant", "system", "tool"}:
            continue
        if message.role == "assistant" and message.id in excluded_reply_ids:
            continue
        if is_degraded_clarification_compatibility_text(
            role=message.role,
            metadata=message.metadata,
        ):
            continue
        if drop_failed_lookups and research_lookup_failed(message.metadata):
            continue
        # A card turn reaches the model as the card's typed facts, never prose.
        card_facts = (
            confirmation_turn_facts(message.metadata)
            if message.role == "assistant"
            else None
        )
        content = (
            confirmation_turn_history_text(card_facts)
            if card_facts is not None
            else message.content
        )
        history.append(
            ConversationMessage(
                role=message.role,
                content=content,
                shared_context=isinstance(
                    (message.metadata or {}).get("shared_conversation"), dict
                ),
            )
        )
    return select_thread_history(history, recent_limit=limit), failed_assistant_id


def _should_suppress_late_success_artifact(
    *,
    user_id: str,
    conversation_id: str,
    role: str,
    metadata: dict[str, Any] | None,
) -> bool:
    if role != "assistant" or not _metadata_has_authoritative_artifact(metadata):
        return False
    messages = _recent_persisted_messages_for_guard(
        user_id=user_id,
        conversation_id=conversation_id,
    )
    return _has_unresolved_visible_runtime_failure(
        messages,
        candidate_request_id=_runtime_turn_request_id(metadata),
    )


def _recent_persisted_messages_for_guard(
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 25,
) -> list[Message]:
    messages: list[Message] = []
    if api_state.supabase_gateway is not None:
        try:
            messages = api_state.supabase_gateway.list_messages(
                user_id=user_id,
                conversation_id=conversation_id,
                limit=limit,
            )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Terminal runtime failure guard could not read Supabase messages",
                error=str(exc),
                conversation_id=conversation_id,
            )
    if not messages or (
        dev_memory_fallback_enabled()
        and conversation_id in api_state.store.conversations
        and api_state.store.messages.get(conversation_id)
    ):
        messages = list(api_state.store.messages.get(conversation_id, []))[-limit:]
    return sorted(messages, key=lambda item: (item.created_at, item.id))


def latest_unresolved_terminal_runtime_failure_metadata(
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 25,
) -> dict[str, Any] | None:
    messages = _recent_persisted_messages_for_guard(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    for message in reversed(messages):
        if message.role == "user":
            return None
        if message.role != "assistant" or not isinstance(message.metadata, dict):
            continue
        if _metadata_has_authoritative_artifact(message.metadata):
            return None
        if _is_terminal_owner_runtime_failure(message.metadata):
            return message.metadata
    return None


def _has_unresolved_visible_runtime_failure(
    messages: list[Message],
    *,
    candidate_request_id: str | None,
) -> bool:
    if candidate_request_id:
        resolved_request_ids: set[str] = set()
        for message in reversed(messages):
            if message.role != "assistant" or not isinstance(message.metadata, dict):
                continue
            message_request_id = _runtime_turn_request_id(message.metadata)
            if (
                message_request_id == candidate_request_id
                and _metadata_has_authoritative_artifact(message.metadata)
            ):
                resolved_request_ids.add(message_request_id)
                continue
            if (
                message_request_id == candidate_request_id
                and message_request_id not in resolved_request_ids
                and _is_terminal_owner_runtime_failure(message.metadata)
            ):
                return True
        return False

    for message in reversed(messages):
        if message.role == "user":
            return False
        if message.role != "assistant" or not isinstance(message.metadata, dict):
            continue
        if _metadata_has_authoritative_artifact(message.metadata):
            return False
        if _is_terminal_owner_runtime_failure(message.metadata):
            return True
    return False


def _metadata_has_authoritative_artifact(
    metadata: dict[str, Any] | None,
) -> bool:
    if not isinstance(metadata, dict):
        return False
    if any(metadata.get(key) for key in _AUTHORITATIVE_ARTIFACT_KEYS):
        return True
    artifact_references = metadata.get("artifact_references")
    if isinstance(artifact_references, list):
        return any(
            isinstance(reference, dict)
            and str(reference.get("artifact_kind") or "")
            in {"confirmation", "result", "backtest_result", "backtest_job"}
            for reference in artifact_references
        )
    return False


def _is_retryable_recovery_failure(metadata: dict[str, Any]) -> bool:
    recovery = metadata.get("recovery")
    return isinstance(recovery, dict) and recovery.get("retryable") is True


def _validated_retry_reply_id(
    latest_assistant: Message | None,
    failed_id: Any,
    *,
    conversation_id: str,
) -> str | None:
    if (
        latest_assistant is not None
        and latest_assistant.conversation_id == conversation_id
        and latest_assistant.id == failed_id
        and isinstance(latest_assistant.metadata, dict)
        and _is_retryable_recovery_failure(latest_assistant.metadata)
    ):
        return latest_assistant.id
    return None


def _retried_failed_assistant_ids(
    messages: list[Message], *, explicit_only: bool = False
) -> set[str]:
    """Retire an identified failure once an assistant follows its retry request.

    Runtime history requires the explicit link. Transcript display also accepts
    a repeated question for legacy clients. An interrupted retry must keep the
    original failure's Retry affordance.
    """
    retired: set[str] = set()
    open_failures: dict[str, str] = {}
    pending_retirements: list[str] = []
    last_user_content: str | None = None
    latest_assistant: Message | None = None
    for message in messages:
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        if message.role == "user":
            if pending_retirements:
                open_failures = {
                    content: failure_id
                    for content, failure_id in open_failures.items()
                    if failure_id not in pending_retirements
                }
            pending_retirements = []
            content = " ".join((message.content or "").split()).casefold()
            action = metadata.get("chat_action")
            payload = action.get("payload") if isinstance(action, dict) else None
            failed_id = metadata.get("failed_assistant_id")
            if failed_id is None:
                failed_id = (
                    payload.get("failed_assistant_id")
                    if isinstance(payload, dict)
                    and isinstance(action, dict)
                    and action.get("type") == "retry_last_turn"
                    else None
                )
            validated_id = _validated_retry_reply_id(
                latest_assistant,
                failed_id,
                conversation_id=message.conversation_id,
            )
            if validated_id is not None:
                pending_retirements.append(validated_id)
            elif failed_id is None and not explicit_only and content in open_failures:
                pending_retirements.append(open_failures.pop(content))
            last_user_content = content or None
            continue
        if message.role == "assistant":
            latest_assistant = message
            if pending_retirements:
                retired.update(pending_retirements)
                pending_retirements = []
            if _is_retryable_recovery_failure(metadata) and last_user_content:
                open_failures[last_user_content] = message.id
            last_user_content = None
    return retired


def _is_visible_runtime_failure(metadata: dict[str, Any]) -> bool:
    if metadata.get("agent_runtime_stage_outcome") != "agent_runtime_failure":
        return False
    recovery = metadata.get("recovery")
    if not isinstance(recovery, dict):
        return metadata.get("conversation_mode") == "recovery"
    return (
        recovery.get("code") in {"runtime_failure", "agent_runtime_failure"}
        or metadata.get("conversation_mode") == "recovery"
    )


def _is_terminal_owner_runtime_failure(metadata: dict[str, Any]) -> bool:
    turn = metadata.get("agent_runtime_turn")
    return (
        isinstance(turn, dict)
        and turn.get("status") in {"failed", "recoverable_failed"}
        and turn.get("terminal") is True
        and _is_visible_runtime_failure(metadata)
    )


def _runtime_turn_request_id(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    turn = metadata.get("agent_runtime_turn")
    if not isinstance(turn, dict):
        return None
    request_id = turn.get("request_id")
    if not isinstance(request_id, str):
        return None
    return request_id.strip() or None


def _supersede_retry_last_turn(metadata: dict[str, Any]) -> dict[str, Any]:
    recovery = metadata.get("recovery")
    retryable_recovery = isinstance(recovery, dict) and recovery.get("retryable") is True
    if "retry_last_turn" not in metadata and not retryable_recovery:
        return metadata
    updated = dict(metadata)
    updated.pop("retry_last_turn", None)
    if retryable_recovery:
        updated_recovery = dict(recovery)
        updated_recovery["retryable"] = False
        updated["recovery"] = updated_recovery
    return updated

"""Focused Supabase persistence boundary for durable conversation messages."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from argus.api.chat.previews import stored_message_preview
from argus.api.schemas import Message, MessageRole
from argus.domain.store import utcnow
from supabase import Client


class StaleMessageArtifactError(ValueError):
    """The message changed after the caller read it; nothing was written.

    In-place artifact updates are conditional on the exact metadata the
    caller read, so a concurrent writer surfaces as this conflict instead
    of a silent last-writer rollback.
    """


def _row_one(result: Any) -> dict[str, Any] | None:
    data = getattr(result, "data", None)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return cast(dict[str, Any], data)


_message_preview = stored_message_preview


def _serialized_usage_limits(limits: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for window in limits:
        if isinstance(window, dict):
            item = dict(window)
            for key in ("period_start", "period_end"):
                value = item.get(key)
                if hasattr(value, "isoformat"):
                    item[key] = value.isoformat()
            serialized.append(item)
            continue
        period, limit_count = window
        serialized.append({"period": period, "limit": limit_count})
    return serialized


class ConversationMessagePersistenceMixin:
    """Owner-scoped message queries and serialized RPC-backed appends."""

    client: Client

    def get_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> Message | None:
        result = (
            self.client.table("messages")
            .select("id,conversation_id,role,content,metadata,created_at")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .eq("id", message_id)
            .limit(1)
            .execute()
        )
        row = _row_one(result)
        return Message.model_validate(row) if row else None

    def message_conversation_id(self, *, user_id: str, message_id: str) -> str | None:
        result = (
            self.client.table("messages")
            .select("conversation_id")
            .eq("user_id", user_id)
            .eq("id", message_id)
            .limit(1)
            .execute()
        )
        row = _row_one(result)
        return str(row["conversation_id"]) if row else None

    def latest_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> Message | None:
        result = (
            self.client.table("messages")
            .select("id,conversation_id,role,content,metadata,created_at")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        row = _row_one(result)
        return Message.model_validate(row) if row else None

    def update_message_artifact(
        self,
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

        In-place artifact edits update the record they describe instead of
        appending a superseding row; the row's identity and position in the
        transcript do not change. The write rides the serialized
        conversation writer and is conditional on what the caller read, in
        two parts: the row guard compares the card's metadata, and the
        activity guard compares the conversation's latest message id,
        because every superseding event appends a message while a non-turn
        edit appends nothing. Either mismatch raises
        ``StaleMessageArtifactError`` instead of silently overwriting the
        other writer. When the rewritten row is the conversation's latest
        message, ``preview`` replaces the conversation's denormalized
        preview without reordering recents.
        """
        try:
            result = self.client.rpc(
                "update_conversation_message_artifact",
                {
                    "p_user_id": user_id,
                    "p_conversation_id": conversation_id,
                    "p_message_id": message_id,
                    "p_content": content,
                    "p_metadata": metadata,
                    "p_expected_source_metadata": expected_source_metadata,
                    "p_expected_latest_message_id": expected_latest_message_id,
                    "p_preview": preview,
                },
            ).execute()
        except Exception as exc:
            if getattr(exc, "code", None) == "P0002":
                raise ValueError("Message not found or not owned by user.") from exc
            raise
        row = _row_one(result)
        if row is None:
            raise StaleMessageArtifactError(
                "The card changed while this update was in flight."
            )
        return Message.model_validate(row["message"])

    def create_message(
        self,
        *,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        settle_usage: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> Message:
        message = Message(
            id=message_id or str(uuid4()),
            conversation_id=conversation_id,
            role=cast(MessageRole, role),
            content=content,
            metadata=metadata if metadata is not None else {},
            created_at=utcnow(),
        )
        appended, _source, _replayed = self._append_conversation_message(
            user_id=user_id,
            message=message,
            preview=_message_preview(content, role=role, metadata=metadata),
            settle_usage=settle_usage,
        )
        return appended

    def claim_response_option_action(
        self,
        *,
        user_id: str,
        conversation_id: str,
        source_assistant_id: str,
        option_id: str,
        replacement_values: dict[str, Any],
        request_message: Message,
        expected_source_metadata: dict[str, Any] | None = None,
    ) -> tuple[Message, Message] | None:
        if request_message.conversation_id != conversation_id:
            raise ValueError("Request message conversation does not match claim.")
        appended, source, _replayed = self._append_conversation_message(
            user_id=user_id,
            message=request_message,
            preview=_message_preview(
                request_message.content,
                role=request_message.role,
                metadata=request_message.metadata,
            ),
            expected_source_assistant_id=source_assistant_id,
            option_id=option_id,
            replacement_values=replacement_values,
            expected_source_metadata=expected_source_metadata,
        )
        if source is None:
            return None
        return source, appended

    def _append_conversation_message(
        self,
        *,
        user_id: str,
        message: Message,
        preview: str | None,
        expected_source_assistant_id: str | None = None,
        option_id: str | None = None,
        replacement_values: dict[str, Any] | None = None,
        expected_source_metadata: dict[str, Any] | None = None,
        settle_usage: dict[str, Any] | None = None,
    ) -> tuple[Message, Message | None, bool]:
        if settle_usage is not None:
            if expected_source_assistant_id is not None or option_id is not None:
                raise ValueError(
                    "Usage settlement cannot combine with response-option claims."
                )
            result = self.client.rpc(
                "append_conversation_message_settling_usage",
                {
                    "p_user_id": user_id,
                    "p_conversation_id": message.conversation_id,
                    "p_message_id": message.id,
                    "p_role": message.role,
                    "p_content": message.content,
                    "p_metadata": (
                        message.metadata if message.metadata is not None else {}
                    ),
                    "p_created_at": message.created_at.isoformat(),
                    "p_preview": preview,
                    "p_usage_resource": settle_usage["resource"],
                    "p_usage_limits": _serialized_usage_limits(settle_usage["limits"]),
                },
            ).execute()
            row = _row_one(result)
            if row is None:
                return message, None, False
            appended = Message.model_validate(row["message"])
            return appended, None, bool(row.get("replayed", False))
        result = self.client.rpc(
            "append_conversation_message",
            {
                "p_user_id": user_id,
                "p_conversation_id": message.conversation_id,
                "p_message_id": message.id,
                "p_role": message.role,
                "p_content": message.content,
                "p_metadata": message.metadata if message.metadata is not None else {},
                "p_created_at": message.created_at.isoformat(),
                "p_preview": preview,
                "p_expected_source_assistant_id": expected_source_assistant_id,
                "p_expected_source_metadata": expected_source_metadata,
                "p_option_id": option_id,
                "p_replacement_values": replacement_values,
            },
        ).execute()
        row = _row_one(result)
        if row is None:
            return message, None, False
        appended = Message.model_validate(row["message"])
        source_row = row.get("source_message")
        source = Message.model_validate(source_row) if source_row else None
        return appended, source, bool(row.get("replayed", False))

"""Thin route hooks for the durable ordinary-turn lifecycle owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from argus.api.chat.legacy_onboarding_markers import is_legacy_onboarding_marker
from argus.api.chat.retry import durable_retry_last_turn_metadata
from argus.api.message_store import (
    create_message,
    finalize_chat_turn,
    prepare_message,
    transition_chat_turn,
)
from argus.api.schemas import Message

AdmissionOwner = Literal["ordinary_turn", "message_only"]
_PUBLIC_INTERNAL_KEYS = {
    "input_fingerprint",
    "output_fingerprint",
    "runtime_diagnostics",
    "turn_execution",
}


def _public_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if key not in _PUBLIC_INTERNAL_KEYS
    }


@dataclass(frozen=True)
class ChatTurnLifecycleHooks:
    owner: AdmissionOwner
    user_id: str
    conversation_id: str
    request_id: str
    request_message: Message

    @property
    def turn_id(self) -> str | None:
        return self.request_message.id if self.owner == "ordinary_turn" else None

    def mark_running(self) -> None:
        if self.turn_id is None:
            return
        result = transition_chat_turn(
            turn_id=self.turn_id,
            to_status="running",
        )
        if result.outcome not in {"applied", "noop"}:
            raise RuntimeError("Chat-turn running transition failed.")

    def complete(
        self,
        *,
        content: str,
        metadata: dict[str, Any] | None,
        settle_usage: dict[str, Any] | None = None,
    ) -> Message:
        return self._complete(
            content=content, metadata=metadata, settle_usage=settle_usage
        )

    def _complete(
        self,
        *,
        content: str,
        metadata: dict[str, Any] | None,
        settle_usage: dict[str, Any] | None,
    ) -> Message:
        public_metadata = _public_metadata(metadata)
        if self.turn_id is None:
            return create_message(
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                role="assistant",
                content=content,
                metadata=public_metadata,
                settle_usage=settle_usage,
            )
        public_metadata["agent_runtime_turn"] = {
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "status": "completed",
            "terminal": True,
        }
        public_metadata.pop("retry_last_turn", None)
        candidate = prepare_message(
            conversation_id=self.conversation_id,
            role="assistant",
            content=content,
            metadata=public_metadata,
        )
        return finalize_chat_turn(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            turn_id=self.turn_id,
            request_id=self.request_id,
            message=candidate,
            to_status="completed",
            failure_code=None,
            retryable=False,
            settle_usage=settle_usage,
        )

    def recoverable_failure(
        self,
        *,
        content: str,
        metadata: dict[str, Any] | None,
        failure_code: str,
        retryable: bool,
    ) -> Message:
        return self._recoverable_failure(
            content=content,
            metadata=metadata,
            failure_code=failure_code,
            retryable=retryable,
        )

    def _recoverable_failure(
        self,
        *,
        content: str,
        metadata: dict[str, Any] | None,
        failure_code: str,
        retryable: bool,
    ) -> Message:
        public_metadata = _public_metadata(metadata)
        if retryable and not is_legacy_onboarding_marker(self.request_message.content):
            public_metadata.update(durable_retry_last_turn_metadata(self.request_message))
        else:
            public_metadata.pop("retry_last_turn", None)
        if self.turn_id is None:
            return create_message(
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                role="assistant",
                content=content,
                metadata=public_metadata,
            )
        public_metadata["agent_runtime_turn"] = {
            "turn_id": self.turn_id,
            "request_id": self.request_id,
            "status": "recoverable_failed",
            "terminal": True,
            "failure_code": failure_code,
            "retryable": retryable,
        }
        candidate = prepare_message(
            conversation_id=self.conversation_id,
            role="assistant",
            content=content,
            metadata=public_metadata,
        )
        return finalize_chat_turn(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            turn_id=self.turn_id,
            request_id=self.request_id,
            message=candidate,
            to_status="recoverable_failed",
            failure_code=failure_code,
            retryable=retryable,
            settle_usage=None,
        )

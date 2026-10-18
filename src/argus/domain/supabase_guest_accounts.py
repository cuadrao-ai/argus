from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from argus.api.schemas import Conversation, Language
from argus.domain.guest_funnel_milestones import purge_expired_milestones
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.usage_limits import QuotaExceededError
from argus.domain.visitor_usage import purge_expired_visitor_usage


def _row_one(result: Any) -> dict[str, Any] | None:
    data = getattr(result, "data", None)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


class EmailAlreadyRegisteredError(RuntimeError):
    """The signup email already belongs to another permanent account."""


class GuestAccountPersistenceMixin:
    """Supabase operations owned by the guest account and allowance spine."""

    def get_auth_user_from_token(self, token: str) -> dict[str, Any]:
        response = self.client.auth.get_user(token)
        if not response or not response.user:
            raise RuntimeError("Invalid or missing user in token response.")
        return response.user.model_dump(mode="json")

    def refresh_browser_session(self, refresh_token: str) -> dict[str, Any]:
        response = self._auth().refresh_session(refresh_token)
        if not response or not response.session:
            raise RuntimeError("Session renewal returned no session.")
        return response.model_dump(mode="json")

    def private_alpha_email_disabled(self, email: str) -> bool:
        rows = (
            self.client.table("private_alpha_allowlist")
            .select("disabled_at")
            .eq("email", email.strip().lower())
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return bool(row and row.get("disabled_at") is not None)

    def sign_in_anonymously(
        self,
        *,
        captcha_token: str,
        language: Language,
        age_confirmed_at: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._auth().sign_in_anonymously(
                {
                    "options": {
                        "captcha_token": captcha_token,
                        "data": {
                            "language": language,
                            **({"age_confirmed_at": age_confirmed_at.isoformat()} if age_confirmed_at is not None else {}),
                        },
                    }
                }
            )
            if not response.user or not response.session:
                raise RuntimeError("Anonymous sign-in returned no session.")
            return response.model_dump(mode="json")
        except Exception as exc:
            raise RuntimeError("Anonymous sign-in failed.") from exc

    def delete_auth_user(self, user_id: str) -> None:
        self.client.auth.admin.delete_user(user_id)

    def create_guest_workspace_handoff(
        self,
        *,
        source_user_id: str,
        destination_email: str,
        source_conversation_id: str,
        pending_action: dict[str, Any] | None,
        handoff_kind: str = "existing_account",
        existing_opaque_secret: str | None = None,
    ) -> dict[str, Any]:
        opaque_secret = secrets.token_urlsafe(32)
        secret_hash = hashlib.sha256(opaque_secret.encode("utf-8")).hexdigest()
        existing_secret_hash = (
            hashlib.sha256(existing_opaque_secret.encode("utf-8")).hexdigest()
            if existing_opaque_secret
            else None
        )
        try:
            prepared = self.client.rpc(
                "prepare_guest_workspace_handoff",
                {
                    "p_source_user_id": source_user_id,
                    "p_destination_email_hash": hashlib.sha256(
                        destination_email.strip().lower().encode("utf-8")
                    ).hexdigest(),
                    "p_source_conversation_id": source_conversation_id,
                    "p_pending_action": pending_action,
                    "p_secret_hash": secret_hash,
                    "p_existing_secret_hash": existing_secret_hash,
                    "p_handoff_kind": handoff_kind,
                },
            ).execute()
        except Exception as exc:
            detail = str(exc)
            known_codes = (
                "guest_signup_destination_bound",
                "guest_handoff_source_not_anonymous",
                "guest_handoff_workspace_unavailable",
                "guest_handoff_invalid",
            )
            code = next((value for value in known_codes if value in detail), None)
            raise RuntimeError(code or "guest_handoff_prepare_unavailable") from None
        row = _row_one(prepared)
        if row is None:
            raise RuntimeError("guest_handoff_prepare_unavailable")
        return {
            "id": str(row["id"]),
            "expires_at": row["expires_at"],
            "opaque_secret": (
                existing_opaque_secret
                if row.get("reused_secret") is True and existing_opaque_secret
                else opaque_secret
            ),
        }

    def get_guest_signup_handoff(
        self,
        *,
        handoff_id: str,
        opaque_secret: str,
        source_user_id: str,
        destination_email: str,
        at: datetime,
    ) -> dict[str, Any]:
        secret_hash = hashlib.sha256(opaque_secret.encode("utf-8")).hexdigest()
        destination_email_hash = hashlib.sha256(
            destination_email.strip().lower().encode("utf-8")
        ).hexdigest()
        row = _row_one(
            self.client.table("guest_workspace_handoffs")
            .select(
                "id,secret_hash,source_user_id,destination_user_id,"
                "destination_email_hash,source_conversation_id,pending_action,"
                "handoff_kind,status,expires_at"
            )
            .eq("id", handoff_id)
            .eq("source_user_id", source_user_id)
            .eq("secret_hash", secret_hash)
            .eq("destination_email_hash", destination_email_hash)
            .eq("handoff_kind", "new_account_signup")
            .in_("status", ["pending", "consumed"])
            .gt("expires_at", at.isoformat())
            .limit(1)
            .execute()
        )
        if row is None:
            raise RuntimeError("guest_handoff_invalid")
        return {
            "id": str(row["id"]),
            "source_user_id": str(row["source_user_id"]),
            "destination_user_id": (
                str(row["destination_user_id"])
                if row.get("destination_user_id")
                else None
            ),
            "source_conversation_id": str(row["source_conversation_id"]),
            "pending_action": row.get("pending_action"),
            "handoff_kind": str(row["handoff_kind"]),
            "status": str(row["status"]),
            "expires_at": row["expires_at"],
            "proof": str(row["secret_hash"]),
        }

    def claim_guest_workspace_handoff(
        self,
        *,
        handoff_id: str,
        opaque_secret: str,
        destination_user_id: str,
        allow_same_destination_replay: bool = False,
    ) -> dict[str, Any]:
        secret_hash = hashlib.sha256(opaque_secret.encode("utf-8")).hexdigest()
        try:
            result = self.client.rpc(
                "claim_guest_workspace_handoff_by_email",
                {
                    "p_handoff_id": handoff_id,
                    "p_secret_hash": secret_hash,
                    "p_destination_user_id": destination_user_id,
                    "p_allow_same_destination_replay": (allow_same_destination_replay),
                },
            ).execute()
        except Exception as exc:
            detail = str(exc)
            known_codes = (
                "guest_handoff_consumed",
                "guest_handoff_expired",
                "guest_handoff_wrong_destination",
                "guest_handoff_source_not_anonymous",
                "guest_handoff_workspace_unavailable",
                "guest_handoff_unsafe_product_graph",
                "guest_handoff_invalid",
            )
            code = next((value for value in known_codes if value in detail), None)
            raise RuntimeError(code or "guest_handoff_claim_unavailable") from None
        row = _row_one(result)
        if row is None:
            raise RuntimeError("guest_handoff_invalid")
        payload = dict(row)
        try:
            handoff = _row_one(
                self.client.table("guest_workspace_handoffs")
                .select("handoff_kind")
                .eq("id", handoff_id)
                .eq("secret_hash", secret_hash)
                .limit(1)
                .execute()
            )
        except Exception:
            handoff = None
        if handoff and handoff.get("handoff_kind") in {
            "existing_account",
            "new_account_signup",
        }:
            payload["handoff_kind"] = str(handoff["handoff_kind"])
        return payload

    def get_active_guest_workspace(
        self,
        *,
        user_id: str,
        at: datetime,
    ) -> GuestWorkspace | None:
        rows = (
            self.client.table("guest_workspaces")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .gt("expires_at", at.isoformat())
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return GuestWorkspace.model_validate(row) if row else None

    def get_guest_workspace_for_signup_retry(
        self,
        *,
        user_id: str,
        at: datetime,
    ) -> GuestWorkspace | None:
        """Recover a claimed source only for the idempotent signup retry path."""
        rows = (
            self.client.table("guest_workspaces")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "claimed")
            .gt("expires_at", at.isoformat())
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return GuestWorkspace.model_validate(row) if row else None

    def create_guest_workspace(
        self,
        *,
        user_id: str,
        created_at: datetime,
    ) -> GuestWorkspace:
        payload = {
            "user_id": user_id,
            "status": "active",
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(days=7)).isoformat(),
            "updated_at": created_at.isoformat(),
        }
        created = self.client.table("guest_workspaces").insert(payload).execute()
        row = _row_one(created)
        if row is None:
            raise RuntimeError("Failed to create guest workspace.")
        return GuestWorkspace.model_validate(row)

    def bind_guest_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> GuestWorkspace:
        result = self.client.rpc(
            "bind_guest_conversation",
            {
                "p_user_id": user_id,
                "p_conversation_id": conversation_id,
            },
        ).execute()
        row = _row_one(result)
        if row is None:
            raise RuntimeError("Failed to bind guest conversation.")
        return GuestWorkspace.model_validate(row)

    def replace_empty_guest_conversation(
        self,
        *,
        user_id: str,
        title: str,
        title_source: str,
        language: str,
    ) -> Conversation:
        result = self.client.rpc(
            "replace_empty_guest_conversation",
            {
                "p_user_id": user_id,
                "p_title": title,
                "p_title_source": title_source,
                "p_language": language,
            },
        ).execute()
        row = _row_one(result)
        if row is None:
            raise RuntimeError("Failed to replace guest conversation.")
        return Conversation.model_validate(row)

    def replace_guest_conversation(
        self,
        *,
        user_id: str,
        title: str,
        title_source: str,
        language: str,
    ) -> Conversation:
        result = self.client.rpc(
            "replace_guest_conversation",
            {
                "p_user_id": user_id,
                "p_title": title,
                "p_title_source": title_source,
                "p_language": language,
            },
        ).execute()
        row = _row_one(result)
        if row is None:
            raise RuntimeError("Failed to replace guest conversation.")
        return Conversation.model_validate(row)

    def claim_expired_guest_workspaces(
        self,
        *,
        limit: int,
        dry_run: bool,
    ) -> list[dict[str, object]]:
        result = self.client.rpc(
            "claim_expired_guest_workspaces",
            {
                "p_limit": limit,
                "p_dry_run": dry_run,
            },
        ).execute()
        data = result.data or []
        if isinstance(data, dict):
            return [dict(data)]
        return [dict(row) for row in data]

    def purge_expired_visitor_usage(self, *, before: datetime | None = None) -> int:
        return purge_expired_visitor_usage(self.client, before=before)

    def purge_expired_guest_funnel_milestones(
        self,
        *,
        before: datetime | None = None,
    ) -> int:
        return purge_expired_milestones(self.client, before=before)

    def check_allowance_windows(
        self,
        *,
        user_id: str,
        resource: str,
        windows: list[dict[str, object]],
    ) -> None:
        for window in windows:
            period = str(window["period"])
            period_start = window.get("period_start")
            query = (
                self.client.table("usage_counters")
                .select("used_count")
                .eq("user_id", user_id)
                .eq("resource", resource)
                .eq("period", period)
            )
            if period_start is not None:
                value = (
                    period_start.isoformat()
                    if hasattr(period_start, "isoformat")
                    else str(period_start)
                )
                query = query.eq("period_start", value)
            rows = query.limit(1).execute()
            row = _row_one(rows)
            if int((row or {}).get("used_count", 0)) >= int(window["limit"]):
                raise QuotaExceededError(f"Quota exceeded for {resource} ({period})")

    def create_feedback_settling_usage(
        self,
        *,
        user_id: str,
        feedback_type: str,
        message: str,
        context: dict[str, Any] | None,
        allowance_limits: list[dict[str, object]],
    ) -> dict[str, Any]:
        serialized: list[dict[str, object]] = []
        for window in allowance_limits:
            item = dict(window)
            for key in ("period_start", "period_end"):
                value = item.get(key)
                if hasattr(value, "isoformat"):
                    item[key] = value.isoformat()  # type: ignore[union-attr]
            serialized.append(item)
        result = self.client.rpc(
            "create_feedback_settling_usage",
            {
                "p_feedback_id": self.new_id(),
                "p_user_id": user_id,
                "p_feedback_type": feedback_type,
                "p_message": message,
                "p_context": context or {},
                "p_usage_resource": "feedback",
                "p_usage_limits": serialized,
            },
        ).execute()
        row = _row_one(result)
        if not isinstance(row, dict):
            raise RuntimeError("Feedback settlement returned no decision.")
        return row

from __future__ import annotations

import http.cookiejar
import os
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx
from loguru import logger
from supabase_auth import SyncGoTrueClient

from argus.api.age_confirmation import parse_age_confirmation
from argus.api.schemas import (
    BacktestRun,
    Conversation,
    DecisionNote,
    EvidenceArtifact,
    Idea,
    IdeaVersion,
    Language,
    Locale,
    Strategy,
    User,
)
from argus.domain.backtest_finalization import (
    FinalizedBacktest,
    PreparedBacktestFinalization,
)
from argus.domain.backtest_job_scopes import RESEARCH_OPERATION_SCOPE
from argus.domain.chat_turn_lifecycle_gateway import (
    ChatTurnLifecycleGatewayMixin,
)
from argus.domain.decision_attachment import (
    DECISION_NOTE_ID_METADATA_KEY,
    DECISION_STATE_METADATA_KEY,
)
from argus.domain.evidence import CapturedEvidence, attach_decision_to_result_card
from argus.domain.login_browser_check import (
    LOGIN_PROVIDER_TIMEOUT_SECONDS,
    complete_password_login,
)
from argus.domain.owner_scope import OwnerScope, postgrest_scoped, scope_of, space_id
from argus.domain.postgres_history_reader import (
    PostgresHistoryReader,
    history_reader_for_database_url,
)
from argus.domain.postgres_keyset_reader import (
    ConversationKeysetCursorError,
    PostgresKeysetReader,
)
from argus.domain.postgres_run_dossier_reader import (
    PostgresRunDossierReader,
    RunDossierSourcePage,
)
from argus.domain.postgres_search_reader import (
    PostgresSearchReader,
    SearchReadResult,
)
from argus.domain.store import utcnow
from argus.domain.supabase_backtest_finalization import finalize_backtest
from argus.domain.supabase_computed_answers import SupabaseComputedAnswerReadMixin
from argus.domain.supabase_conversation_activity import (
    SupabaseConversationActivityMixin,
)
from argus.domain.supabase_conversation_messages import (
    ConversationMessagePersistenceMixin,
)
from argus.domain.supabase_decisions import DecisionAttachmentPersistenceMixin
from argus.domain.supabase_guest_accounts import GuestAccountPersistenceMixin
from argus.domain.supabase_message_reads import (
    _COMPLETED_RESULT_BATCH_SIZE,
    SupabaseMessageReadMixin,
    _distinct_chunks,
    _unique_owned_rows_by_id,
)
from argus.domain.supabase_message_reads import (
    MessageAnchorError as MessageAnchorError,
)
from argus.domain.supabase_message_reads import (
    MessageCursorError as MessageCursorError,
)
from argus.domain.supabase_public_excerpts import SupabasePublicExcerptMixin
from argus.domain.supabase_query_helpers import fetch_all_rows as fetch_all_rows_batched
from argus.domain.supabase_signup import SupabaseSignupMixin
from argus.domain.usage_counter_reader import UsageCounterReader, align_usage_period
from argus.domain.usage_limits import (
    USAGE_COUNTER_LOCK as _USAGE_COUNTER_LOCK,
)
from argus.domain.usage_limits import (
    QuotaExceededError,
)
from argus.domain.usage_limits import (
    check_usage_limits as _check_usage_limits,
)
from argus.observability.cost_ledger import normalize_cost_ledger_entry
from supabase import Client, ClientOptions, create_client


class DecisionCaptureIntegrityError(RuntimeError):
    """Raised when the decision RPC does not return the committed object spine."""


class ConversationCursorError(ValueError):
    """Raised when a conversation cursor pivot cannot be resolved exactly."""


_PROFILE_LOCALE_BY_LANGUAGE: dict[Language, Locale] = {
    "en": "en-US",
    "es-419": "es-419",
}


def _now_iso() -> str:
    return utcnow().isoformat()


def _row_one(result: Any) -> dict[str, Any] | None:
    data = getattr(result, "data", None)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_username(username: object) -> str | None:
    if not isinstance(username, str):
        return None
    normalized = username.strip().casefold()
    return normalized or None


def _supabase_client_options() -> ClientOptions:
    return ClientOptions(
        httpx_client=httpx.Client(http2=False, timeout=120),
        postgrest_client_timeout=120,
    )


AuthClientFactory = Callable[[], SyncGoTrueClient]


def _auth_client_factory(url: str, key: str) -> AuthClientFactory:
    """One throwaway Auth client per call: the server keeps no user's session.

    A shared supabase-py client retains, auto-refreshes, and forwards as its
    default Authorization header the last session it signed in.
    """
    auth_url = f"{url.rstrip('/')}/auth/v1"
    headers = {"apiKey": key, "Authorization": f"Bearer {key}"}
    refuse_cookies = http.cookiejar.DefaultCookiePolicy(allowed_domains=[])
    http_client = httpx.Client(
        http2=False,
        timeout=120,
        cookies=http.cookiejar.CookieJar(policy=refuse_cookies),
    )

    def build() -> SyncGoTrueClient:
        return SyncGoTrueClient(
            url=auth_url,
            headers=dict(headers),
            auto_refresh_token=False,
            persist_session=False,
            flow_type="pkce",
            http_client=http_client,
        )

    return build


@dataclass
class SupabaseGateway(
    SupabaseSignupMixin,
    GuestAccountPersistenceMixin,
    ChatTurnLifecycleGatewayMixin,
    SupabaseConversationActivityMixin,
    SupabaseMessageReadMixin,
    SupabasePublicExcerptMixin,
    ConversationMessagePersistenceMixin,
    UsageCounterReader,
    DecisionAttachmentPersistenceMixin,
    SupabaseComputedAnswerReadMixin,
):
    client: Client
    auth_client_factory: AuthClientFactory | None = None
    history_reader: PostgresHistoryReader | None = None
    search_reader: PostgresSearchReader | None = None
    keyset_reader: PostgresKeysetReader | None = None
    run_dossier_reader: PostgresRunDossierReader | None = None
    mock_user_email: str | None = os.getenv("MOCK_USER_EMAIL")
    mock_user_password: str | None = os.getenv("MOCK_USER_PASSWORD")
    _cached_mock_user: User | None = None
    check_usage_limits = _check_usage_limits

    @classmethod
    def from_env(cls) -> SupabaseGateway:
        url = os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_PROJECT_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not url or not key or not database_url:
            raise RuntimeError(
                "Supabase mode requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, "
                "and DATABASE_URL."
            )
        auth_key = (
            os.getenv("SUPABASE_ANON_KEY", "").strip()
            or os.getenv("SUPABASE_ANON_PUBLIC_KEY", "").strip()
        )
        if not auth_key:
            logger.error("startup_config_refused{reason=missing_SUPABASE_ANON_KEY}")
            raise RuntimeError("Set SUPABASE_ANON_KEY or SUPABASE_ANON_PUBLIC_KEY.")
        history_reader = history_reader_for_database_url(database_url)
        return cls(
            client=create_client(url, key, options=_supabase_client_options()),
            auth_client_factory=_auth_client_factory(url, auth_key),
            history_reader=history_reader,
            keyset_reader=PostgresKeysetReader(history_reader.pool),
            search_reader=PostgresSearchReader(history_reader.pool),
            run_dossier_reader=PostgresRunDossierReader(history_reader.pool),
        )

    def new_id(self) -> str:
        return str(uuid4())

    def _auth(self) -> SyncGoTrueClient:
        if self.auth_client_factory is None:
            raise RuntimeError("Supabase Auth is not configured.")
        return self.auth_client_factory()

    def _fetch_all_rows(
        self,
        query_factory: Callable[[int, int], Any],
    ) -> list[dict[str, Any]]:
        return fetch_all_rows_batched(query_factory)

    def reset_dev_data(self) -> None:
        user = self.get_or_create_mock_user()
        user_id = user.id
        for table in (
            "feedback",
            "usage_counters",
            "conversation_read_states",
            "chat_turn_lifecycles",
            "collection_strategies",
            "decision_notes",
            "evidence_artifacts",
            "idea_versions",
            "ideas",
            "backtest_runs",
            "messages",
            "strategies",
            "collections",
            "conversations",
        ):
            self.client.table(table).delete().eq("user_id", user_id).execute()

    def get_or_create_mock_user(self) -> User:
        if self._cached_mock_user is not None:
            return self._cached_mock_user
        user_id: str | None = None
        try:
            created = self.client.auth.admin.create_user(
                {
                    "email": self.mock_user_email,
                    "password": self.mock_user_password,
                    "email_confirm": True,
                }
            )
            user_id = created.user.id if created and created.user else None
        except Exception:
            try:
                listed_raw = self.client.auth.admin.list_users(page=1, per_page=200)
                if isinstance(listed_raw, list):
                    listed = listed_raw
                else:
                    listed = getattr(listed_raw, "users", []) or getattr(
                        listed_raw, "data", []
                    )
                existing = next(
                    (
                        row
                        for row in listed
                        if getattr(row, "email", None) == self.mock_user_email
                    ),
                    None,
                )
                if existing is not None:
                    user_id = existing.id
            except Exception:
                pass

        if user_id is None:
            existing_profile = (
                self.client.table("profiles")
                .select("id")
                .eq("email", self.mock_user_email)
                .limit(1)
                .execute()
                .data
                or []
            )
            if existing_profile:
                user_id = existing_profile[0]["id"]

        if user_id is None:
            raise RuntimeError("Unable to resolve mock auth user.")

        existing = (
            self.client.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        )
        existing_row = _row_one(existing)
        if existing_row is not None:
            user = User.model_validate(existing_row)
            self._cached_mock_user = user
            return user

        now = _now_iso()
        profile = {
            "id": user_id,
            "email": self.mock_user_email,
            "username": "mock-developer",
            "display_name": "Mock Developer",
            "language": "en",
            "locale": "en-US",
            "is_admin": True,
            "updated_at": now,
        }
        self.client.table("profiles").upsert(profile, on_conflict="id").execute()
        loaded = (
            self.client.table("profiles").select("*").eq("id", user_id).single().execute()
        )
        user = User.model_validate(_row_one(loaded))
        self._cached_mock_user = user
        return user

    def get_auth_user_by_id(self, user_id: str) -> dict[str, Any]:
        response = self.client.auth.admin.get_user_by_id(user_id)
        if response.user is None:
            raise RuntimeError("Auth user was not found.")
        return response.user.model_dump(mode="json")

    def resend_signup_confirmation(self, *, email: str, captcha_token: str) -> None:
        self._auth().resend(
            {
                "type": "signup",
                "email": email,
                "options": {"captcha_token": captcha_token},
            }
        )

    def private_alpha_role_for_email(self, email: str) -> str | None:
        rows = (
            self.client.table("private_alpha_allowlist")
            .select("email,role,disabled_at")
            .eq("email", _normalize_email(email))
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        if not row or row.get("disabled_at") is not None:
            return None
        role = str(row.get("role") or "").strip().lower()
        return role if role in {"admin", "developer", "user"} else None

    def private_alpha_email_allowed(self, email: str) -> bool:
        return self.private_alpha_role_for_email(email) is not None

    def request_private_alpha_access(
        self,
        *,
        email: str,
        language: Language,
    ) -> None:
        self.client.table("private_alpha_allowlist").upsert(
            {
                "email": _normalize_email(email),
                "role": "requested",
                "language": language,
            },
            on_conflict="email",
            ignore_duplicates=True,
        ).execute()

    def get_requested_private_alpha_access(self, email: str) -> dict[str, Any] | None:
        rows = (
            self.client.table("private_alpha_allowlist")
            .select("email,role,language,disabled_at")
            .eq("email", _normalize_email(email))
            .eq("role", "requested")
            .is_("disabled_at", "null")
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        if row is None or row.get("language") not in {"en", "es-419"}:
            return None
        return row

    def get_private_alpha_access_welcome_delivery(
        self,
        email: str,
    ) -> dict[str, Any] | None:
        rows = (
            self.client.table("private_alpha_access_welcome_deliveries")
            .select(
                "recipient_email,language,content_version,subject,"
                "provider_receipt,sent_at"
            )
            .eq("recipient_email", _normalize_email(email))
            .limit(1)
            .execute()
        )
        return _row_one(rows)

    def claim_private_alpha_access_welcome(
        self,
        *,
        email: str,
        language: Language,
        content_version: str,
        subject: str,
    ) -> dict[str, Any] | None:
        result = self.client.rpc(
            "claim_private_alpha_access_welcome",
            {
                "p_email": _normalize_email(email),
                "p_language": language,
                "p_content_version": content_version,
                "p_subject": subject,
            },
        ).execute()
        return _row_one(result)

    def complete_private_alpha_access_welcome(
        self,
        *,
        email: str,
        language: Language,
        content_version: str,
        subject: str,
        provider_receipt: str,
        claim_token: str | None,
    ) -> bool:
        result = self.client.rpc(
            "complete_private_alpha_access_welcome",
            {
                "p_email": _normalize_email(email),
                "p_language": language,
                "p_content_version": content_version,
                "p_subject": subject,
                "p_provider_receipt": provider_receipt,
                "p_claim_token": claim_token,
            },
        ).execute()
        return result.data is True

    def release_expired_private_alpha_access_welcome_claims(self) -> int:
        result = self.client.rpc(
            "release_expired_private_alpha_access_welcome_claims",
            {},
        ).execute()
        return int(result.data or 0)

    def login(self, email: str, password: str, captcha_token: str) -> dict[str, Any]:
        return complete_password_login(
            lambda: self._auth().sign_in_with_password(
                {
                    "email": email,
                    "password": password,
                    "options": {"captcha_token": captcha_token},
                }
            ),
            LOGIN_PROVIDER_TIMEOUT_SECONDS,
        )

    def update_user(self, user_id: str, updates: dict[str, Any]) -> User:
        payload = {key: value for key, value in updates.items() if key != "id"}
        payload["updated_at"] = _now_iso()
        self.client.table("profiles").update(payload).eq("id", user_id).execute()
        loaded = (
            self.client.table("profiles").select("*").eq("id", user_id).single().execute()
        )
        return User.model_validate(_row_one(loaded))

    def get_user(self, *, user_id: str) -> User | None:
        rows = (
            self.client.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        )
        row = _row_one(rows)
        return User.model_validate(row) if row else None

    def create_conversation(
        self,
        *,
        user_id: str,
        title: str,
        title_source: str,
        language: str | None,
        scope: OwnerScope,
    ) -> Conversation:
        now = _now_iso()
        payload: dict[str, Any] = {
            "user_id": user_id,
            "title": title,
            "title_source": title_source,
            "language": language,
            "created_at": now,
            "updated_at": now,
            "pinned": False,
            "archived": False,
        }
        if (owner_space_id := space_id(scope)) is not None:
            payload["owner_space_id"] = owner_space_id
        created = self.client.table("conversations").insert(payload).execute()
        return Conversation.model_validate(_row_one(created))

    def list_conversations(
        self,
        *,
        user_id: str,
        scope: OwnerScope,
        limit: int | None,
        archived: bool | None = None,
        deleted: bool = False,
        cursor_updated_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> list[Conversation]:
        if (cursor_updated_at is None) != (cursor_id is None):
            raise ConversationCursorError("invalid conversation cursor pivot")

        if cursor_id is not None:
            try:
                normalized_cursor_id = str(UUID(cursor_id))
            except (AttributeError, TypeError, ValueError):
                raise ConversationCursorError(
                    "invalid conversation cursor pivot"
                ) from None
            if normalized_cursor_id != cursor_id:
                raise ConversationCursorError("invalid conversation cursor pivot")

        if limit is not None and self.keyset_reader is not None:
            try:
                keyset_rows = self.keyset_reader.list_conversation_rows(
                    user_id=user_id,
                    scope=scope,
                    limit=limit,
                    archived=archived,
                    deleted=deleted,
                    cursor_updated_at=cursor_updated_at,
                    cursor_id=cursor_id,
                )
            except ConversationKeysetCursorError as exc:
                raise ConversationCursorError(
                    "invalid conversation cursor pivot"
                ) from exc
            return [Conversation.model_validate(row) for row in keyset_rows]

        cursor_pinned: bool | None = None
        canonical_cursor_id: str | None = None
        if cursor_updated_at is not None and cursor_id is not None:
            pivot_rows = (
                self.client.table("conversations")
                .select("id,pinned")
                .eq("user_id", user_id)
                .eq("id", cursor_id)
                .limit(2)
                .execute()
                .data
                or []
            )
            if len(pivot_rows) != 1:
                raise ConversationCursorError("invalid conversation cursor pivot")
            pivot = pivot_rows[0]
            canonical_cursor_id = str(pivot.get("id") or "")
            pinned = pivot.get("pinned")
            if canonical_cursor_id != cursor_id or not isinstance(pinned, bool):
                raise ConversationCursorError("invalid conversation cursor pivot")
            cursor_pinned = pinned

        query = postgrest_scoped(
            self.client.table("conversations").select("*").eq("user_id", user_id),
            scope,
            "owner_space_id",
        )
        if deleted:
            query = query.not_.is_("deleted_at", "null")
        else:
            query = query.is_("deleted_at", "null")

        if archived is not None:
            query = query.eq("archived", archived)

        if (
            cursor_updated_at is not None
            and canonical_cursor_id is not None
            and cursor_pinned is not None
        ):
            timestamp = cursor_updated_at.isoformat()
            within_tier = (
                f"or(updated_at.lt.{timestamp},"
                f"and(updated_at.eq.{timestamp},id.lt.{canonical_cursor_id}))"
            )
            if cursor_pinned:
                keyset_filter = f"pinned.eq.false,and(pinned.eq.true,{within_tier})"
            else:
                keyset_filter = f"and(pinned.eq.false,{within_tier})"
            query = query.or_(keyset_filter)

        ordered = (
            query.order("pinned", desc=True)
            .order("updated_at", desc=True)
            .order("id", desc=True)
        )
        if limit is None:
            rows_data = self._fetch_all_rows(lambda start, end: ordered.range(start, end))
        else:
            rows_data = ordered.limit(limit + 1).execute().data or []
        return [Conversation.model_validate(row) for row in rows_data]

    def get_conversation(
        self, *, user_id: str, conversation_id: str
    ) -> Conversation | None:
        rows = (
            self.client.table("conversations")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return Conversation.model_validate(row) if row else None

    def patch_conversation(
        self, *, user_id: str, conversation_id: str, patch: dict[str, Any]
    ) -> Conversation | None:
        patch["updated_at"] = _now_iso()
        self.client.table("conversations").update(patch).eq("id", conversation_id).eq(
            "user_id", user_id
        ).execute()
        return self.get_conversation(user_id=user_id, conversation_id=conversation_id)

    def soft_delete_conversation(self, *, user_id: str, conversation_id: str) -> bool:
        now = _now_iso()
        result = (
            self.client.table("conversations")
            .update({"deleted_at": now, "updated_at": now})
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)

    def soft_delete_all_conversations(self, *, user_id: str, scope: OwnerScope) -> int:
        now = _now_iso()
        query = (
            self.client.table("conversations")
            .update({"deleted_at": now, "updated_at": now})
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
        )
        result = postgrest_scoped(query, scope, "owner_space_id").execute()
        return len(result.data or [])

    def conversation_scope(
        self, *, user_id: str, conversation_id: str
    ) -> OwnerScope | None:
        """The stored conversation's scope, or None when the person has no such row."""
        rows = (
            self.client.table("conversations")
            .select("owner_space_id")
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return scope_of(row.get("owner_space_id")) if row else None

    def create_backtest_run(self, *, user_id: str, run: BacktestRun) -> BacktestRun:
        self._require_owned_conversation(
            user_id=user_id,
            conversation_id=run.conversation_id,
        )
        self._require_owned_strategy(
            user_id=user_id,
            strategy_id=run.strategy_id,
        )
        payload = run.model_dump(mode="json")
        payload["user_id"] = user_id
        created = self.client.table("backtest_runs").insert(payload).execute()
        return BacktestRun.model_validate(_row_one(created))

    def finalize_backtest_completion(
        self,
        *,
        finalization: PreparedBacktestFinalization,
    ) -> FinalizedBacktest:
        return finalize_backtest(self.client, finalization=finalization)

    def finalize_direct_backtest_success(
        self,
        *,
        job_id: str,
        finalization: PreparedBacktestFinalization,
    ) -> FinalizedBacktest | None:
        from argus.domain.supabase_backtest_finalization import (
            finalize_direct_backtest,
        )

        return finalize_direct_backtest(
            self.client, job_id=job_id, finalization=finalization
        )

    def update_backtest_run_result_card(
        self,
        *,
        user_id: str,
        run_id: str,
        conversation_result_card: dict[str, Any],
    ) -> BacktestRun:
        self._require_owned_backtest_run_if_present(user_id=user_id, run_id=run_id)
        updated = (
            self.client.table("backtest_runs")
            .update(
                {
                    "conversation_result_card": conversation_result_card,
                }
            )
            .eq("user_id", user_id)
            .eq("id", run_id)
            .execute()
        )
        return BacktestRun.model_validate(_row_one(updated))

    def mark_result_card_decision_for_run(
        self,
        *,
        user_id: str,
        run_id: str,
        evidence_artifact_id: str,
        decision_id: str,
        decision_state: str,
    ) -> None:
        run = self.get_backtest_run(user_id=user_id, run_id=run_id)
        if run is None:
            raise ValueError("Backtest run not found or not owned by user.")
        enriched_card = attach_decision_to_result_card(
            dict(run.conversation_result_card),
            decision_id=decision_id,
            decision_state=decision_state,  # type: ignore[arg-type]
        )
        self.update_backtest_run_result_card(
            user_id=user_id,
            run_id=run_id,
            conversation_result_card=enriched_card,
        )
        if not run.conversation_id:
            return
        for message in self._decision_result_messages(
            user_id=user_id,
            conversation_id=run.conversation_id,
            run=run,
            evidence_artifact_id=evidence_artifact_id,
            enriched_card=enriched_card,
        ):
            metadata = dict(message.metadata or {})
            result_card = metadata.get("result_card")
            if not isinstance(result_card, dict):
                continue
            is_matching_run = (
                metadata.get("result_run_id") == run_id
                or metadata.get("latest_run_id") == run_id
            )
            is_matching_artifact = (
                result_card.get("evidence_artifact_id") == evidence_artifact_id
            )
            if not is_matching_run and not is_matching_artifact:
                continue
            metadata["result_card"] = attach_decision_to_result_card(
                result_card,
                decision_id=decision_id,
                decision_state=decision_state,  # type: ignore[arg-type]
            )
            metadata[DECISION_NOTE_ID_METADATA_KEY] = decision_id
            metadata[DECISION_STATE_METADATA_KEY] = decision_state
            self.client.table("messages").update({"metadata": metadata}).eq(
                "user_id", user_id
            ).eq("id", message.id).execute()

    def create_idea(self, *, user_id: str, idea: Idea) -> Idea:
        self._require_owned_conversation(
            user_id=user_id,
            conversation_id=idea.source_conversation_id,
        )
        payload = idea.model_dump(mode="json")
        payload["user_id"] = user_id
        created = self.client.table("ideas").insert(payload).execute()
        return Idea.model_validate(_row_one(created))

    def update_idea_active_version(
        self, *, user_id: str, idea_id: str, active_version_id: str
    ) -> Idea:
        self._require_owned_idea(user_id=user_id, idea_id=idea_id)
        self._require_owned_idea_version(
            user_id=user_id,
            idea_version_id=active_version_id,
        )
        updated = (
            self.client.table("ideas")
            .update({"active_version_id": active_version_id, "updated_at": _now_iso()})
            .eq("user_id", user_id)
            .eq("id", idea_id)
            .execute()
        )
        return Idea.model_validate(_row_one(updated))

    def create_idea_version(self, *, user_id: str, version: IdeaVersion) -> IdeaVersion:
        self._require_owned_idea(user_id=user_id, idea_id=version.idea_id)
        self._require_owned_conversation(
            user_id=user_id,
            conversation_id=version.source_conversation_id,
        )
        self._require_owned_backtest_run_if_present(
            user_id=user_id,
            run_id=version.source_run_id,
        )
        payload = version.model_dump(mode="json")
        payload["user_id"] = user_id
        created = self.client.table("idea_versions").insert(payload).execute()
        return IdeaVersion.model_validate(_row_one(created))

    def create_evidence_artifact(
        self, *, user_id: str, artifact: EvidenceArtifact
    ) -> EvidenceArtifact:
        self._require_owned_idea(user_id=user_id, idea_id=artifact.idea_id)
        self._require_owned_idea_version(
            user_id=user_id,
            idea_version_id=artifact.idea_version_id,
        )
        self._require_owned_conversation(
            user_id=user_id,
            conversation_id=artifact.source_conversation_id,
        )
        self._require_owned_backtest_run_if_present(
            user_id=user_id,
            run_id=artifact.source_run_id,
        )
        payload = artifact.model_dump(mode="json")
        payload["user_id"] = user_id
        created = self.client.table("evidence_artifacts").insert(payload).execute()
        return EvidenceArtifact.model_validate(_row_one(created))

    def get_evidence_capture_by_run(
        self, *, user_id: str, run_id: str
    ) -> CapturedEvidence | None:
        artifact_result = (
            self.client.table("evidence_artifacts")
            .select("*")
            .eq("user_id", user_id)
            .eq("source_run_id", run_id)
            .limit(1)
            .execute()
        )
        artifact_row = _row_one(artifact_result)
        if artifact_row is None:
            return None
        artifact = EvidenceArtifact.model_validate(artifact_row)
        idea_result = (
            self.client.table("ideas")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", artifact.idea_id)
            .limit(1)
            .execute()
        )
        version_result = (
            self.client.table("idea_versions")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", artifact.idea_version_id)
            .limit(1)
            .execute()
        )
        idea_row = _row_one(idea_result)
        version_row = _row_one(version_result)
        if idea_row is None or version_row is None:
            raise ValueError("Evidence artifact sidecar records are incomplete.")
        return CapturedEvidence(
            idea=Idea.model_validate(idea_row),
            idea_version=IdeaVersion.model_validate(version_row),
            evidence_artifact=artifact,
        )

    def create_backtest_evidence_capture(
        self, *, user_id: str, captured: CapturedEvidence
    ) -> CapturedEvidence:
        run_id = captured.evidence_artifact.source_run_id
        if run_id is not None:
            existing = self.get_evidence_capture_by_run(user_id=user_id, run_id=run_id)
            if existing is not None:
                return existing

        idea_for_insert = captured.idea.model_copy(update={"active_version_id": None})
        idea: Idea | None = None
        version: IdeaVersion | None = None
        try:
            idea = self.create_idea(user_id=user_id, idea=idea_for_insert)
            version = self.create_idea_version(
                user_id=user_id, version=captured.idea_version
            )
            idea = self.update_idea_active_version(
                user_id=user_id,
                idea_id=idea.id,
                active_version_id=version.id,
            )
            artifact = self.create_evidence_artifact(
                user_id=user_id,
                artifact=captured.evidence_artifact,
            )
        except Exception:
            existing_after_error = None
            if run_id is not None:
                existing_after_error = self.get_evidence_capture_by_run(
                    user_id=user_id,
                    run_id=run_id,
                )
                if (
                    existing_after_error is not None
                    and idea is not None
                    and version is not None
                    and existing_after_error.idea.id == idea.id
                    and existing_after_error.idea_version.id == version.id
                ):
                    return existing_after_error
            if idea is not None:
                self._discard_transient_evidence_sidecars(
                    user_id=user_id,
                    idea_id=idea.id,
                    idea_version_id=version.id if version is not None else None,
                )
            if existing_after_error is not None:
                return existing_after_error
            if run_id is not None:
                existing = self.get_evidence_capture_by_run(
                    user_id=user_id,
                    run_id=run_id,
                )
                if existing is not None:
                    return existing
            raise
        return CapturedEvidence(
            idea=idea,
            idea_version=version,
            evidence_artifact=artifact,
        )

    def _discard_transient_evidence_sidecars(
        self,
        *,
        user_id: str,
        idea_id: str,
        idea_version_id: str | None,
    ) -> None:
        with suppress(Exception):
            self.client.table("ideas").update({"active_version_id": None}).eq(
                "user_id", user_id
            ).eq("id", idea_id).execute()
        if idea_version_id is not None:
            with suppress(Exception):
                self.client.table("idea_versions").delete().eq("user_id", user_id).eq(
                    "id", idea_version_id
                ).execute()
        with suppress(Exception):
            self.client.table("ideas").delete().eq("user_id", user_id).eq(
                "id", idea_id
            ).execute()

    def get_evidence_artifact(
        self, *, user_id: str, artifact_id: str
    ) -> EvidenceArtifact | None:
        rows = (
            self.client.table("evidence_artifacts")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", artifact_id)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return EvidenceArtifact.model_validate(row) if row else None

    def get_decision_note_by_artifact(
        self, *, user_id: str, artifact_id: str
    ) -> DecisionNote | None:
        rows = (
            self.client.table("decision_notes")
            .select("*")
            .eq("user_id", user_id)
            .eq("evidence_artifact_id", artifact_id)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return DecisionNote.model_validate(row) if row else None

    def create_decision_note(
        self, *, user_id: str, decision: DecisionNote
    ) -> DecisionNote:
        self._require_owned_idea(user_id=user_id, idea_id=decision.idea_id)
        self._require_owned_idea_version(
            user_id=user_id,
            idea_version_id=decision.idea_version_id,
        )
        self._require_owned_evidence_artifact(
            user_id=user_id,
            artifact_id=decision.evidence_artifact_id,
        )
        self._require_owned_conversation(
            user_id=user_id,
            conversation_id=decision.source_conversation_id,
        )
        payload = decision.model_dump(mode="json")
        payload["user_id"] = user_id
        created = self.client.table("decision_notes").insert(payload).execute()
        return DecisionNote.model_validate(_row_one(created))

    def upsert_decision_note(
        self, *, user_id: str, decision: DecisionNote
    ) -> DecisionNote:
        existing = self.get_decision_note_by_artifact(
            user_id=user_id,
            artifact_id=decision.evidence_artifact_id,
        )
        if existing is None:
            try:
                return self.create_decision_note(user_id=user_id, decision=decision)
            except Exception:
                existing = self.get_decision_note_by_artifact(
                    user_id=user_id,
                    artifact_id=decision.evidence_artifact_id,
                )
                if existing is None:
                    raise

        updated = (
            self.client.table("decision_notes")
            .update(
                {
                    "decision_state": decision.decision_state,
                    "note": decision.note,
                    "updated_at": _now_iso(),
                }
            )
            .eq("user_id", user_id)
            .eq("id", existing.id)
            .execute()
        )
        return DecisionNote.model_validate(_row_one(updated))

    def capture_current_decision_note(
        self, *, user_id: str, decision: DecisionNote
    ) -> tuple[DecisionNote, EvidenceArtifact, Idea, IdeaVersion]:
        result = self.client.rpc(
            "upsert_current_decision_note",
            {
                "p_user_id": user_id,
                "p_evidence_artifact_id": decision.evidence_artifact_id,
                "p_decision_id": decision.id,
                "p_decision_state": decision.decision_state,
                "p_note": decision.note,
            },
        ).execute()
        row = _row_one(result)
        if row is None:
            raise DecisionCaptureIntegrityError(
                "Decision capture did not return durable artifact state."
            )
        return (
            DecisionNote.model_validate(row["decision"]),
            EvidenceArtifact.model_validate(row["evidence_artifact"]),
            Idea.model_validate(row["idea"]),
            IdeaVersion.model_validate(row["idea_version"]),
        )

    def mark_evidence_artifact_lifecycle(
        self,
        *,
        user_id: str,
        artifact_id: str,
        lifecycle: str,
    ) -> EvidenceArtifact:
        self._require_owned_evidence_artifact(
            user_id=user_id,
            artifact_id=artifact_id,
        )
        updated = (
            self.client.table("evidence_artifacts")
            .update({"lifecycle": lifecycle, "updated_at": _now_iso()})
            .eq("user_id", user_id)
            .eq("id", artifact_id)
            .execute()
        )
        return EvidenceArtifact.model_validate(_row_one(updated))

    def create_backtest_job(
        self,
        *,
        user_id: str,
        conversation_id: str,
        payload_hash: str,
        launch_payload: dict[str, Any],
        request_message_id: str | None = None,
        confirmation_message_id: str | None = None,
        idempotency_key: str | None = None,
        execution_metadata: dict[str, Any] | None = None,
        operation_scope: str | None = None,
    ) -> dict[str, Any]:
        clean_idempotency_key = (
            idempotency_key.strip()
            if isinstance(idempotency_key, str) and idempotency_key.strip()
            else None
        )
        if clean_idempotency_key is not None:
            existing = (
                self.client.table("backtest_jobs")
                .select("*")
                .eq("user_id", user_id)
                .eq("idempotency_key", clean_idempotency_key)
                .limit(1)
                .execute()
            )
            existing_row = _row_one(existing)
            if existing_row is not None:
                return dict(existing_row)

        self._require_owned_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
        )

        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "request_message_id": request_message_id,
            "confirmation_message_id": confirmation_message_id,
            "idempotency_key": clean_idempotency_key,
            "payload_hash": payload_hash,
            "launch_payload": launch_payload,
            "status": "queued",
            "priority": "normal",
            "attempts": 0,
            "max_attempts": 1,
            "execution_metadata": execution_metadata or {},
        }
        if operation_scope is not None:
            payload["operation_scope"] = operation_scope
        created = self.client.table("backtest_jobs").insert(payload).execute()
        return dict(_row_one(created) or {})

    def complete_research_job(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Terminal success for a research-scope job. No run finalization:
        the research result is an assistant message, referenced through
        execution_metadata, and result_run_id stays null by design."""
        existing = self.get_backtest_job(user_id=user_id, job_id=job_id)
        if existing is None:
            raise ValueError("Research job not found or not owned by user.")
        metadata = dict(existing.get("execution_metadata") or {})
        metadata.update(execution_metadata or {})
        payload = {
            "status": "succeeded",
            "finished_at": _now_iso(),
            "failure_code": None,
            "failure_detail": None,
            "retryable": False,
            "execution_metadata": metadata,
            "updated_at": _now_iso(),
        }
        updated = (
            self.client.table("backtest_jobs")
            .update(payload)
            .eq("user_id", user_id)
            .eq("id", job_id)
            .eq("operation_scope", RESEARCH_OPERATION_SCOPE)
            .in_("status", ["queued", "running"])
            .execute()
        )
        row = _row_one(updated)
        if row is None:
            raise ValueError("Research job is not in a completable state.")
        return dict(row)

    def admit_backtest_job(self, **kwargs: Any) -> dict[str, Any]:
        from argus.domain import backtest_admission_gateway as jobs

        return jobs.admit_backtest_job(self.client, **kwargs)

    def get_backtest_job_reservation(self, **kwargs: Any) -> dict[str, Any] | None:
        from argus.domain import backtest_admission_gateway as jobs

        return jobs.get_backtest_job_reservation(self.client, **kwargs)

    def list_backtest_job_reservations(self, **kwargs: Any) -> list[dict[str, Any]]:
        from argus.domain import backtest_admission_gateway as jobs

        return jobs.list_backtest_job_reservations(self.client, **kwargs)

    def record_backtest_job_rejection(self, **kwargs: Any) -> dict[str, Any]:
        from argus.domain import backtest_admission_gateway as jobs

        return jobs.record_backtest_job_rejection(self.client, **kwargs)

    def finalize_direct_backtest_job(self, **kwargs: Any) -> dict[str, Any] | None:
        from argus.domain import backtest_admission_gateway as jobs

        return jobs.finalize_direct_backtest_job(self.client, **kwargs)

    def find_backtest_job_by_idempotency_key(
        self,
        *,
        user_id: str,
        operation_scope: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        """The row an earlier admission created for this key, whatever its status."""
        result = (
            self.client.table("backtest_jobs")
            .select("*")
            .eq("user_id", user_id)
            .eq("operation_scope", operation_scope)
            .eq("idempotency_key", idempotency_key)
            .limit(1)
            .execute()
        )
        row = _row_one(result)
        return dict(row) if row is not None else None

    def get_backtest_job(self, *, user_id: str, job_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("backtest_jobs")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", job_id)
            .limit(1)
            .execute()
        )
        row = _row_one(result)
        return dict(row) if row is not None else None

    def get_backtest_jobs_by_ids(
        self,
        *,
        user_id: str,
        conversation_id: str,
        job_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not job_ids:
            return {}
        jobs_by_id: dict[str, dict[str, Any]] = {}
        for requested in _distinct_chunks(
            job_ids,
            size=_COMPLETED_RESULT_BATCH_SIZE,
        ):
            rows = (
                self.client.table("backtest_jobs")
                .select("*")
                .eq("user_id", user_id)
                .eq("conversation_id", conversation_id)
                .in_("id", requested)
                .limit(len(requested) + 1)
                .execute()
                .data
                or []
            )
            if len(rows) > len(requested):
                continue
            jobs_by_id.update(
                _unique_owned_rows_by_id(
                    rows,
                    requested_ids=set(requested),
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
            )
        return jobs_by_id

    def count_backtest_jobs(
        self, *, status: str, user_id: str | None = None, limit: int = 100
    ) -> int:
        query = self.client.table("backtest_jobs").select("id").eq("status", status)
        if user_id is not None:
            query = query.eq("user_id", user_id)
        result = query.limit(max(1, limit)).execute()
        return len(result.data or [])

    def list_backtest_jobs(
        self,
        *,
        status: str,
        user_id: str | None = None,
        limit: int = 100,
        oldest_first: bool = False,
    ) -> list[dict[str, Any]]:
        query = (
            self.client.table("backtest_jobs")
            .select("*")
            .eq("status", status)
            .order("created_at", desc=not oldest_first)
        )
        if user_id is not None:
            query = query.eq("user_id", user_id)
        result = query.limit(max(1, limit)).execute()
        return [dict(row) for row in result.data or []]

    def merge_backtest_job_execution_metadata(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_backtest_job(user_id=user_id, job_id=job_id)
        if existing is None:
            raise ValueError("Backtest job not found or not owned by user.")
        metadata = dict(existing.get("execution_metadata") or {})
        metadata.update(execution_metadata)
        updated = (
            self.client.table("backtest_jobs")
            .update({"execution_metadata": metadata, "updated_at": _now_iso()})
            .eq("user_id", user_id)
            .eq("id", job_id)
            .execute()
        )
        return dict(_row_one(updated) or {})

    def link_backtest_job_result(
        self,
        *,
        user_id: str,
        job_id: str,
        result_run_id: str,
        execution_metadata: dict[str, Any] | None = None,
        mark_succeeded: bool = False,
    ) -> dict[str, Any]:
        existing = self.get_backtest_job(user_id=user_id, job_id=job_id)
        if existing is None:
            raise ValueError("Backtest job not found or not owned by user.")
        if existing.get("result_run_id"):
            return existing

        metadata = dict(existing.get("execution_metadata") or {})
        metadata.update(execution_metadata or {})
        payload: dict[str, Any] = {
            "result_run_id": result_run_id,
            "execution_metadata": metadata,
            "updated_at": _now_iso(),
        }
        if mark_succeeded:
            payload["status"] = "succeeded"
            payload["finished_at"] = _now_iso()
            payload["failure_code"] = None
            payload["failure_detail"] = None
            payload["retryable"] = False

        from argus.domain.backtest_job_lifecycle import (
            job_result_attach_postgrest_filter,
            job_success_write_postgrest_filter,
        )

        # Every result attach passes the lifecycle statement, with no
        # caller able to opt out: a dead or unknown job refuses the link,
        # and only a state a worker legitimately holds may also convert to
        # succeeded. The filters are generated beside the card-restore
        # classification so the two cannot drift; the success set is a
        # subset of the attach set, so one filter carries both statements.
        # A refused write returns the standing row and the caller derives
        # publication from what actually landed.
        update_query = (
            self.client.table("backtest_jobs")
            .update(payload)
            .eq("user_id", user_id)
            .eq("id", job_id)
            .or_(
                job_success_write_postgrest_filter()
                if mark_succeeded
                else job_result_attach_postgrest_filter()
            )
        )
        updated = update_query.execute()
        row = _row_one(updated)
        if row is None:
            standing = self.get_backtest_job(user_id=user_id, job_id=job_id)
            if standing is not None:
                return dict(standing)
        return dict(row or {})

    def mark_backtest_job_running(
        self,
        *,
        user_id: str,
        job_id: str,
        execution_metadata: dict[str, Any] | None = None,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_backtest_job(user_id=user_id, job_id=job_id)
        if existing is None:
            raise ValueError("Backtest job not found or not owned by user.")
        can_retry_finalization = (
            existing.get("status") == "failed"
            and existing.get("failure_code") == "finalization_failed"
            and bool(existing.get("retryable"))
        )
        existing_status = str(existing.get("status") or "")
        if existing_status != "queued" and not can_retry_finalization:
            raise ValueError("Backtest job cannot be started or retried.")

        metadata = dict(existing.get("execution_metadata") or {})
        metadata.update(execution_metadata or {})
        payload = {
            "status": "running",
            "started_at": started_at or existing.get("started_at") or _now_iso(),
            "attempts": int(existing.get("attempts") or 0) + 1,
            "result_run_id": None,
            "finished_at": None,
            "failure_code": None,
            "failure_detail": None,
            "retryable": False,
            "execution_metadata": metadata,
            "updated_at": _now_iso(),
        }
        update_query = (
            self.client.table("backtest_jobs")
            .update(payload)
            .eq("user_id", user_id)
            .eq("id", job_id)
            .eq("status", existing_status)
        )
        if can_retry_finalization:
            update_query = update_query.eq("failure_code", "finalization_failed").eq(
                "retryable", True
            )
        updated = update_query.execute()
        row = _row_one(updated)
        if row is None:
            raise ValueError("Backtest job cannot be started or retried.")
        return dict(row)

    def mark_backtest_job_failed(
        self,
        *,
        user_id: str,
        job_id: str,
        failure_code: str,
        failure_detail: str,
        retryable: bool,
        execution_metadata: dict[str, Any] | None = None,
        finished_at: str | None = None,
        expected_status: str | None = None,
        expected_updated_at: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_backtest_job(user_id=user_id, job_id=job_id)
        if existing is None:
            raise ValueError("Backtest job not found or not owned by user.")
        metadata = dict(existing.get("execution_metadata") or {})
        metadata.update(execution_metadata or {})
        payload = {
            "status": "failed",
            "result_run_id": None,
            "finished_at": finished_at or _now_iso(),
            "failure_code": failure_code,
            "failure_detail": failure_detail,
            "retryable": retryable,
            "execution_metadata": metadata,
            "updated_at": _now_iso(),
        }
        update_query = (
            self.client.table("backtest_jobs")
            .update(payload)
            .eq("user_id", user_id)
            .eq("id", job_id)
        )
        if expected_status is not None:
            update_query = update_query.eq("status", expected_status)
        if expected_updated_at is not None:
            update_query = update_query.eq("updated_at", expected_updated_at)
        updated = update_query.execute()
        return dict(_row_one(updated) or {})

    def create_context_packet(
        self,
        *,
        user_id: str,
        packet: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(packet)
        payload["user_id"] = user_id
        payload["packet"] = dict(packet)
        created = self.client.table("context_packets").insert(payload).execute()
        return dict(_row_one(created) or {})

    def attach_context_packet_to_run(
        self,
        *,
        user_id: str,
        attachment: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = str(attachment["run_id"])
        packet_id = str(attachment["packet_id"])
        self._require_owned_backtest_run(user_id=user_id, run_id=run_id)
        if not self._context_packet_owned_by_user(
            user_id=user_id,
            packet_id=packet_id,
        ):
            raise ValueError("Context packet not found or not owned by user.")

        payload = {
            "user_id": user_id,
            "run_id": run_id,
            "context_packet_id": packet_id,
            "explanation_id": attachment.get("explanation_id"),
            "attached_at": attachment.get("attached_at") or _now_iso(),
            "immutable_snapshot": bool(attachment.get("immutable_snapshot", True)),
        }
        created = self.client.table("run_context_packets").insert(payload).execute()
        return dict(_row_one(created) or {})

    def _require_owned_conversation(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
    ) -> None:
        if conversation_id is None:
            return
        if self.get_conversation(user_id=user_id, conversation_id=conversation_id):
            return
        raise ValueError("Conversation not found or not owned by user.")

    def _require_owned_strategy(
        self,
        *,
        user_id: str,
        strategy_id: str | None,
    ) -> None:
        if strategy_id is None:
            return
        if self.get_strategy(user_id=user_id, strategy_id=strategy_id):
            return
        raise ValueError("Strategy not found or not owned by user.")

    def _require_owned_backtest_run(self, *, user_id: str, run_id: str) -> None:
        if self.get_backtest_run(user_id=user_id, run_id=run_id):
            return
        raise ValueError("Backtest run not found or not owned by user.")

    def _require_owned_backtest_run_if_present(
        self, *, user_id: str, run_id: str | None
    ) -> None:
        if run_id is None:
            return
        self._require_owned_backtest_run(user_id=user_id, run_id=run_id)

    def _require_owned_idea(self, *, user_id: str, idea_id: str | None) -> None:
        if idea_id is None:
            return
        rows = (
            self.client.table("ideas")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", idea_id)
            .limit(1)
            .execute()
        )
        if _row_one(rows) is not None:
            return
        raise ValueError("Idea not found or not owned by user.")

    def _require_owned_idea_version(
        self, *, user_id: str, idea_version_id: str | None
    ) -> None:
        if idea_version_id is None:
            return
        rows = (
            self.client.table("idea_versions")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", idea_version_id)
            .limit(1)
            .execute()
        )
        if _row_one(rows) is not None:
            return
        raise ValueError("Idea version not found or not owned by user.")

    def _require_owned_evidence_artifact(
        self, *, user_id: str, artifact_id: str | None
    ) -> None:
        if artifact_id is None:
            return
        rows = (
            self.client.table("evidence_artifacts")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", artifact_id)
            .limit(1)
            .execute()
        )
        if _row_one(rows) is not None:
            return
        raise ValueError("Evidence artifact not found or not owned by user.")

    def _context_packet_owned_by_user(self, *, user_id: str, packet_id: str) -> bool:
        rows = (
            self.client.table("context_packets")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", packet_id)
            .limit(1)
            .execute()
        )
        return _row_one(rows) is not None

    def create_route_receipt(
        self,
        *,
        user_id: str | None,
        receipt: dict[str, Any],
        conversation_id: str | None = None,
        run_id: str | None = None,
        message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "message_id": message_id,
            "task": receipt["task"],
            "tier": receipt["tier"],
            "model": receipt.get("model"),
            "fallback_model": receipt.get("fallback_model"),
            "mode": receipt["mode"],
            "schema_name": receipt.get("schema_name"),
            "latency_ms": receipt.get("latency_ms", 0),
            "outcome": receipt["outcome"],
            "failure_mode": receipt.get("failure_mode"),
            "fallback_used": bool(receipt.get("fallback_used")),
            "token_usage": receipt.get("token_usage"),
            "context_packet_ids": receipt.get("context_packet_ids") or [],
            "metadata": metadata or {},
            "created_at": receipt.get("created_at") or _now_iso(),
        }
        created = self.client.table("route_receipts").insert(payload).execute()
        return dict(_row_one(created) or {})

    def create_cost_ledger_entry(self, *, entry: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_cost_ledger_entry(entry)
        payload["occurred_at"] = payload["occurred_at"] or _now_iso()
        created = self.client.table("cost_ledger_entries").insert(payload).execute()
        return dict(_row_one(created) or {})

    def health_check(self) -> dict[str, Any]:
        started = time.perf_counter()
        self.client.table("profiles").select("id").limit(1).execute()
        return {
            "status": "ready",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    def get_backtest_run(self, *, user_id: str, run_id: str) -> BacktestRun | None:
        rows = (
            self.client.table("backtest_runs")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", run_id)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return BacktestRun.model_validate(row) if row else None

    def get_backtest_runs_by_ids(
        self,
        *,
        user_id: str,
        conversation_id: str,
        run_ids: list[str],
    ) -> dict[str, BacktestRun]:
        if not run_ids:
            return {}
        runs_by_id: dict[str, BacktestRun] = {}
        for requested in _distinct_chunks(
            run_ids,
            size=_COMPLETED_RESULT_BATCH_SIZE,
        ):
            rows = (
                self.client.table("backtest_runs")
                .select("*")
                .eq("user_id", user_id)
                .eq("conversation_id", conversation_id)
                .in_("id", requested)
                .limit(len(requested) + 1)
                .execute()
                .data
                or []
            )
            if len(rows) > len(requested):
                continue
            owned_rows = _unique_owned_rows_by_id(
                rows,
                requested_ids=set(requested),
                user_id=user_id,
                conversation_id=conversation_id,
            )
            runs_by_id.update(
                {
                    run_id: BacktestRun.model_validate(row)
                    for run_id, row in owned_rows.items()
                }
            )
        return runs_by_id

    def delete_withheld_backtest_result(self, *, user_id: str, run_id: str) -> bool:
        """Remove the full finalized tuple of a withheld run atomically.

        One database function owns the removal (children first, run row
        last, ideas with earlier versions repointed), so product reads
        can never observe a partial tuple; both this gateway and the
        workflow gateway call it. The refusal record on the job's
        execution metadata and the turn's message is the audit trail.
        """
        result = self.client.rpc(
            "delete_withheld_backtest_result",
            {"p_user_id": user_id, "p_run_id": run_id},
        ).execute()
        return bool(result.data)

    def get_latest_completed_run_for_conversation(
        self, *, user_id: str, conversation_id: str
    ) -> BacktestRun | None:
        rows = (
            self.client.table("backtest_runs")
            .select("*")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return BacktestRun.model_validate(row) if row else None

    def count_completed_runs(self, *, user_id: str) -> int:
        rows = (
            self.client.table("backtest_runs")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("status", "completed")
            .execute()
        )
        return int(rows.count or 0)

    def touch_conversation_title(
        self,
        *,
        user_id: str,
        conversation_id: str,
        title: str,
        title_source: str,
        last_message_preview: str,
    ) -> None:
        self.client.table("conversations").update(
            {
                "title": title,
                "title_source": title_source,
                "last_message_preview": last_message_preview,
                "updated_at": _now_iso(),
            }
        ).eq("id", conversation_id).eq("user_id", user_id).execute()

    def list_history_rows(
        self,
        *,
        user_id: str,
        scope: OwnerScope,
        limit: int,
        archived: bool = False,
        deleted: bool = False,
        cursor_activity_at: datetime | None = None,
        cursor_id: str | None = None,
        cursor_pinned: bool | None = None,
        cursor_type_rank: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if self.history_reader is None:
            raise RuntimeError("Persistent History requires its Postgres reader.")
        return self.history_reader.list_rows(
            user_id=user_id,
            scope=scope,
            limit=limit,
            archived=archived,
            deleted=deleted,
            cursor_activity_at=cursor_activity_at,
            cursor_id=cursor_id,
            cursor_pinned=cursor_pinned,
            cursor_type_rank=cursor_type_rank,
        )

    def read_conversation_preview_messages(
        self, *, user_id: str, conversation_ids: list[str]
    ) -> list[dict[str, Any]]:
        if self.keyset_reader is None:
            raise RuntimeError("Persistent previews require the Postgres reader.")
        return self.keyset_reader.read_conversation_preview_messages(
            user_id=user_id, conversation_ids=conversation_ids
        )

    def search_rows(
        self,
        *,
        user_id: str,
        scope: OwnerScope,
        query: str,
        source_limit: int,
        cursor_updated_at: datetime | None = None,
        cursor_id: str | None = None,
        decision_state: str | None = None,
        include_ledger_groups: bool = False,
        guest_scope: bool = False,
        guest_conversation_id: str | None = None,
        conversation_ids: list[str] | None = None,
    ) -> SearchReadResult:
        if self.search_reader is None:
            raise RuntimeError("Persistent Search requires its Postgres reader.")
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "scope": scope,
            "query": query,
            "source_limit": source_limit,
            "cursor_updated_at": cursor_updated_at,
            "cursor_id": cursor_id,
            "decision_state": decision_state,
            "include_ledger_groups": include_ledger_groups,
            "guest_scope": guest_scope,
            "guest_conversation_id": guest_conversation_id,
        }
        if conversation_ids is not None:
            kwargs["conversation_ids"] = conversation_ids
        return self.search_reader.search_rows(
            **kwargs,
        )

    def list_run_dossier_source_rows(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int,
        cursor_completed_at: datetime | None,
        cursor_run_id: str | None,
    ) -> RunDossierSourcePage:
        if self.run_dossier_reader is None:
            raise RuntimeError(
                "Persistent run dossier history requires its Postgres reader."
            )
        return self.run_dossier_reader.list_source_rows(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=limit,
            cursor_completed_at=cursor_completed_at,
            cursor_run_id=cursor_run_id,
        )

    def get_strategy(self, *, user_id: str, strategy_id: str) -> Strategy | None:
        rows = (
            self.client.table("strategies")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", strategy_id)
            .limit(1)
            .execute()
        )
        row = _row_one(rows)
        return Strategy.model_validate(row) if row else None

    def check_and_increment_usage(
        self, *, user_id: str, resource: str, period: str, limit_count: int
    ) -> None:
        self.check_and_increment_usage_limits(
            user_id=user_id,
            resource=resource,
            limits=[(period, limit_count)],
        )

    def check_and_increment_usage_limits(
        self,
        *,
        user_id: str,
        resource: str,
        limits: list[tuple[str, int]],
    ) -> None:
        if not limits:
            return
        now = datetime.now(timezone.utc)
        with _USAGE_COUNTER_LOCK:
            checked_rows: list[tuple[dict[str, Any], int, int, str]] = []
            for period, limit_count in limits:
                row = self._get_or_create_usage_counter_row(
                    user_id=user_id,
                    resource=resource,
                    period=period,
                    limit_count=limit_count,
                    now=now,
                )
                current_used = int(row.get("used_count", 0))
                if current_used >= limit_count:
                    raise QuotaExceededError(f"Quota exceeded for {resource} ({period})")
                checked_rows.append((row, current_used, limit_count, period))

            for row, current_used, limit_count, period in checked_rows:
                updated = (
                    self.client.table("usage_counters")
                    .update(
                        {
                            "used_count": current_used + 1,
                            "limit_count": limit_count,
                            "updated_at": _now_iso(),
                        }
                    )
                    .eq("id", row["id"])
                    .eq("used_count", current_used)
                    .execute()
                )
                if updated.data:
                    continue

                raise RuntimeError(
                    f"Failed to increment usage counter for {resource} ({period})."
                )

    def _get_or_create_usage_counter_row(
        self,
        *,
        user_id: str,
        resource: str,
        period: str,
        limit_count: int,
        now: datetime,
    ) -> dict[str, Any]:
        start, end = align_usage_period(now, period)
        start_iso = start.isoformat()
        end_iso = end.isoformat()
        for _ in range(5):
            rows = (
                self.client.table("usage_counters")
                .select("*")
                .eq("user_id", user_id)
                .eq("resource", resource)
                .eq("period", period)
                .eq("period_start", start_iso)
                .limit(1)
                .execute()
            )
            row = _row_one(rows)
            if row is not None:
                return row

            try:
                self.client.table("usage_counters").insert(
                    {
                        "user_id": user_id,
                        "resource": resource,
                        "period": period,
                        "period_start": start_iso,
                        "period_end": end_iso,
                        "used_count": 0,
                        "limit_count": limit_count,
                        "created_at": _now_iso(),
                        "updated_at": _now_iso(),
                    }
                ).execute()
            except Exception:
                pass

        raise RuntimeError(
            f"Failed to initialize usage counter for {resource} ({period})."
        )

    def get_or_create_profile_for_auth_user(self, auth_user: dict[str, Any]) -> User:
        user_id = auth_user["id"]
        is_anonymous = auth_user.get("is_anonymous") is True
        email = None if is_anonymous else str(auth_user.get("email") or "").strip()
        if not is_anonymous and not email:
            raise RuntimeError("Permanent Auth user is missing a verified email.")
        allowlist_role = (
            None if is_anonymous else self.private_alpha_role_for_email(email or "")
        )
        is_admin = allowlist_role in {"admin", "developer"}
        existing = self.get_user(user_id=user_id)
        if existing is not None:
            if not is_anonymous and existing.email is None:
                return self.update_user(
                    user_id=user_id,
                    updates={"id": user_id, "email": email, "is_admin": is_admin},
                )
            if is_admin and not existing.is_admin:
                return self.update_user(user_id, {"id": user_id, "is_admin": True})
            return existing

        now = _now_iso()
        raw_user_metadata = auth_user.get("user_metadata")
        user_metadata = raw_user_metadata if isinstance(raw_user_metadata, dict) else {}
        metadata_language = user_metadata.get("language")
        language: Language = "es-419" if metadata_language == "es-419" else "en"
        payload = {
            "id": user_id,
            "email": email,
            "username": _normalize_username(user_metadata.get("username")),
            "display_name": user_metadata.get("display_name"),
            "language": language,
            "locale": _PROFILE_LOCALE_BY_LANGUAGE[language],
            "is_admin": is_admin,
            "created_at": now,
            "updated_at": now,
        }

        if user_metadata.get("age_confirmed_at") is not None:
            with suppress(ValueError):
                payload["age_confirmed_at"] = parse_age_confirmation(
                    user_metadata["age_confirmed_at"]
                ).isoformat()

        created = (
            self.client.table("profiles")
            .upsert(payload, on_conflict="id", ignore_duplicates=True)
            .execute()
        )
        row = _row_one(created)
        if row is not None:
            return User.model_validate(row)
        existing = self.get_user(user_id=user_id)
        if existing is None:
            raise RuntimeError("Failed to create user profile.")
        if is_admin and not existing.is_admin:
            return self.update_user(user_id, {"id": user_id, "is_admin": True})
        return existing

    @staticmethod
    def parse_iso(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def create_feedback(
        self,
        user_id: str,
        feedback_type: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Persists feedback to the Supabase database."""
        self.client.table("feedback").insert(
            {
                "id": self.new_id(),
                "user_id": user_id,
                "type": feedback_type,
                "message": message,
                "context": context,
                "created_at": _now_iso(),
            }
        ).execute()

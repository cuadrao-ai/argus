"""The account deletion command (Lane 6).

Order, matching ``docs/specs/lanes/account-deletion-fk-census.md``:

1. Claim the run, opening it on the first request. The run is keyed on a hash
   of the user id; the id itself is held only while the run is in flight, so a
   retry finds the same run and reuses the same placeholders. Every pass (a
   request, a retry, the sweep) first takes the run's claim and releases it at
   the end, so two passes never revoke or delete in parallel; a pass that
   finds the claim held gets ``AccountDeletionIncomplete("in_progress")``.
   From here the account is locked: the session check rejects any JWT whose
   user has a run in flight (except on the delete route itself, so the person
   can resume), and the auth user is banned through the Admin API so no
   refresh or sign-in succeeds.
2. Reserve one placeholder id per sharing scope the person's rows are pinned
   in (a household, or an activity group shared outside any plan), then
   create each placeholder through the Admin API. Ids are registered before
   the create, so the auth triggers already skip them.
3. One database transaction: steps 1.1 to 1.3 per household, archives passed
   on, sources captured for revocation and removed (2), invite ids forgotten
   (4), future responsibilities returned, each unit moved to its placeholder
   (5.1, 5.2), the person's own plans deleted (5.3), feedback stripped (6),
   then a check that nothing still holds the id.
4. Every third-party step runs before the account delete, inside the run:
   Sign in with Apple (#793), then the captured Plaid access tokens and Gmail
   (Google) refresh tokens, then PostHog person deletion (8). Revoked counts as
   done; a provider that no longer held the grant (``invalid_grant``, Google
   ``invalid_token``, Plaid's item gone; #802 for Apple) is recorded
   ``already_revoked`` and counted for the spike alert. The person's retained
   document sources (#778) are deleted from Storage by their owner prefix,
   which also takes any object a crashed capture left unreferenced. A transient failure
   leaves that step pending: the run stays ``data_deleted``, the account stays
   locked, the auth delete waits, and the operator-run resume sweep
   (``scripts/ops/resume_account_deletions.py`` inside scheduled_maintenance)
   or the person's own retry resumes it. A step pending for 7 days raises an
   operator alert; only an operator can force-complete it, with a reason kept
   in the run record (``force_complete_step``). There is no user-facing
   bypass.
   A credential that does not open is given up only when ``key_check`` shows
   it was sealed under this process's key (its stored key fingerprint equals
   the key's): then a Plaid or Gmail one is recorded ``unrecoverable`` and an
   Apple one goes through #802's ``discard_unreadable``. A different or
   missing fingerprint, or no key, keeps the credential pending with its
   ciphertext and alerts. No token is ever logged.
5. Right before the auth delete, every RESTRICT key to auth.users is read from
   the catalog; a late write that still holds the person is scrubbed once more.
   The auth user is deleted through the Admin API (7); unused placeholders are
   deleted; the run drops the user id, both hashes, the placeholder map and the
   revocation rows, keeping only counts, and ends ``done``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

import psycopg
from loguru import logger

from argus.domain.account_deletion.apple import (
    AccountDeletionAdmissionError,
    lock_apple_state,
    require_admission,
)
from argus.domain.account_deletion.auth_admin import AuthAdmin, placeholder_email
from argus.domain.account_deletion.key_check import KeyCheck, check_current_key
from argus.domain.apple_sign_in.client import AppleError
from argus.domain.apple_sign_in.credentials import (
    AppleIdentityMismatch,
    AppleIdentityMissing,
    AppleRevocationPending,
    DiscardOutcome,
    RevokeOutcome,
    StoredAppleCredential,
)
from argus.domain.apple_sign_in.credentials_postgres import (
    PostgresAppleCredentialRepository,
)
from argus.domain.household import deletion as household_deletion
from argus.domain.ingestion.documents.objects import SourceObjects, owner_prefix
from argus.domain.ingestion.secrets import SecretBox
from argus.observability.analytics_deletion import (
    NOT_APPLICABLE_REASON,
    AnalyticsDeletion,
    EventAnalyticsDeletion,
    NoAnalyticsEvents,
    advance_with_retry,
)
from argus.observability.envelope import posthog_project_token_configured
from argus.observability.product_events import actor_hash_for_user

RunStatus = Literal["started", "data_deleted", "done"]
DeletionOrigin = Literal["route_first_pass", "sweep", "force"]
_ATTEMPTS = 3
# A run the sweep may resume: one no request has touched for this long.
SWEEP_IDLE_SECONDS = 120
# A pass's claim on its run lapses after this, should the pass die mid-way.
CLAIM_SECONDS = 900
# A third-party step pending this long needs an operator (Priya, #802 eval).
ESCALATE_AFTER = timedelta(days=7)
# already_revoked in this many runs within the window is a spike worth a look:
# a token we hold should normally still be live when the person deletes.
ALREADY_REVOKED_SPIKE = 5
ALREADY_REVOKED_WINDOW = timedelta(hours=24)
FORCEABLE_STEPS = ("apple", "plaid", "gmail", "analytics")


class AccountDeletionRejected(Exception):
    """The request names no deletable account (bad id, unknown user,
    placeholder)."""


class AccountDeletionStateUnknown(RuntimeError):
    """The command could not establish whether a deletion run exists."""


class AccountDeletionIncomplete(Exception):
    """The run is open and the account locked, but a step could not finish yet.

    ``pending`` names the third-party steps still owed (``apple``, ``gmail``,
    ``plaid``, ``analytics``); it is empty when the data step itself must be
    retried. ``in_progress`` means another pass holds the run's claim. The
    sweep or a retry resumes the same run."""

    def __init__(self, reason: str, pending: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.pending = sorted(set(pending or []))


class ProviderRevoker(Protocol):
    def revoke_for_deletion(
        self,
        *,
        source: str,
        connection_id: str,
        external_ref: str,
        envelope: bytes | None,
    ) -> str: ...


class AppleCredentials(Protocol):
    def capture(
        self, *, user_id: str, authorization_code: str, deletion_claim: str | None = None
    ) -> None: ...

    def ensure_readable(self, row: StoredAppleCredential) -> None: ...

    def revoke_stored(self, row: StoredAppleCredential) -> RevokeOutcome: ...

    def unreadable_discard_status(self, row: StoredAppleCredential) -> DiscardOutcome: ...


@dataclass
class DeletionOutcome:
    status: RunStatus
    pending: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    run_id: str | None = None


def subject_hash(user_id: str) -> str:
    return hashlib.sha256(f"argus:account-deletion:{user_id}".encode()).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise AccountDeletionRejected("invalid_user_id") from None


def _value(outcome: Any) -> str:
    return str(getattr(outcome, "value", outcome))


class AccountDeletionService:
    def __init__(
        self,
        *,
        households: Any,
        auth_admin: AuthAdmin,
        revoker: ProviderRevoker | None,
        analytics: AnalyticsDeletion | EventAnalyticsDeletion,
        apple: AppleCredentials | None = None,
        secret_box: SecretBox | None = None,
        allow_fake_analytics: bool = False,
        source_objects: SourceObjects | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        # The household repository owns the pool and binds one connection per
        # context, so its leave helpers run inside this command's transaction.
        self._households = households
        self._auth = auth_admin
        self._revoker = revoker
        self._analytics = analytics
        self._apple = apple
        # The credential key, for key_check only; it never opens a token here.
        self._box = secret_box
        # The recording fake counts as done only where it is explicitly the
        # adapter (tests, local dev). Anywhere else the PostHog step stays
        # pending until a real deletion adapter ships, unless the server sends
        # no PostHog events at all (not_applicable, decision 1B).
        self._allow_fake_analytics = allow_fake_analytics
        self._sources = source_objects
        self._clock = clock

    # -- entry point -------------------------------------------------------------

    def delete_account(
        self,
        *,
        user_id: str,
        apple_authorization_code: str | None = None,
        origin: DeletionOrigin = "route_first_pass",
    ) -> DeletionOutcome:
        user_id = _uuid(user_id)
        subject = subject_hash(user_id)
        run = None
        try:
            if apple_authorization_code is not None:
                run = self._claim_classified(
                    user_id, subject, existing_only=True, origin=origin
                )
                try:
                    if self._apple is None:
                        raise AccountDeletionAdmissionError(
                            "account_deletion_unavailable"
                        )
                    self._apple.capture(
                        user_id=user_id,
                        authorization_code=apple_authorization_code,
                        deletion_claim=run["claim"] if run else None,
                    )
                except Exception as exc:
                    if run is not None or self._has_started(user_id):
                        raise AccountDeletionIncomplete(
                            "third_party_pending", ["apple"]
                        ) from None
                    if isinstance(exc, AppleError) and (
                        exc.invalid_grant or exc.reason == "malformed_code"
                    ):
                        raise AccountDeletionAdmissionError(
                            "apple_authorization_invalid", 400
                        ) from None
                    if isinstance(exc, (AppleIdentityMismatch, AppleIdentityMissing)):
                        raise AccountDeletionAdmissionError(
                            "apple_identity_mismatch", 409
                        ) from None
                    raise AccountDeletionAdmissionError(
                        "account_deletion_unavailable"
                    ) from None
            if run is None:
                run = self._claim_classified(user_id, subject, origin=origin)
            return self._run(user_id, subject, run)
        finally:
            if run is not None:
                self._release(run["id"], run["claim"])

    def _claim_classified(
        self,
        user_id: str,
        subject: str,
        *,
        existing_only: bool = False,
        origin: DeletionOrigin = "route_first_pass",
    ) -> dict[str, Any] | None:
        try:
            return self._claim(
                user_id, subject, existing_only=existing_only, origin=origin
            )
        except (
            AccountDeletionAdmissionError,
            AccountDeletionIncomplete,
            AccountDeletionRejected,
        ):
            raise
        except Exception:
            if self._has_started(user_id):
                raise AccountDeletionIncomplete("admission_unknown") from None
            raise AccountDeletionAdmissionError("account_deletion_unavailable") from None

    def _has_started(self, user_id: str) -> bool:
        try:
            with self._households.connection() as connection:
                if (
                    connection.execute(
                        "select 1 from argus_private.account_deletion_runs where user_id = %s",
                        (user_id,),
                    ).fetchone()
                    is not None
                ):
                    return True
                if (
                    connection.execute(
                        "select 1 from auth.users where id = %s",
                        (user_id,),
                    ).fetchone()
                    is None
                ):
                    raise AccountDeletionRejected("unknown_user")
                return False
        except AccountDeletionRejected:
            raise
        except Exception:
            raise AccountDeletionStateUnknown from None

    def _run(self, user_id: str, subject: str, run: dict[str, Any]) -> DeletionOutcome:
        # Idempotent: every attempt re-applies the ban, so a refresh token
        # issued before the run can't outlive it.
        self._auth.lock_user(user_id)
        if run["status"] == "started":
            for attempt in range(_ATTEMPTS):
                self._reserve_placeholders(user_id, subject)
                try:
                    self._delete_data(user_id, subject)
                    break
                except _UnitsChanged:
                    if attempt == _ATTEMPTS - 1:
                        raise AccountDeletionIncomplete("units_changed") from None
        # Every third-party step is attempted on each pass, so one provider's
        # outage doesn't hide another's; the account delete waits for all.
        pending: dict[str, str] = {}
        apple = self._revoke_apple(user_id, subject, run)
        if apple is not None:
            self._record_step(subject, "apple_revoke", "pending", run=run)
            pending["apple"] = apple
        pending.update(self._revoke_providers(user_id, subject))
        analytics = self._delete_analytics(subject, run)
        if analytics is not None:
            pending["analytics"] = analytics
        storage = self._erase_sources(user_id, subject, run)
        if storage is not None:
            pending["storage"] = storage
        self._track_pending(subject, pending)
        if pending:
            logger.warning(
                "Account deletion waiting on third parties", pending=sorted(pending)
            )
            raise AccountDeletionIncomplete("third_party_pending", list(pending))
        self._settle_late_writes(user_id, subject)
        # An upload authenticated before the lock can still write after the
        # first erase; capture refuses it, and this second erase takes the rest.
        late = self._erase_sources(user_id, subject, run)
        if late is not None:
            self._track_pending(subject, {"storage": late})
            raise AccountDeletionIncomplete("third_party_pending", ["storage"])
        counts = self._delete_auth_user(user_id, run["id"], run["claim"])
        return DeletionOutcome(status="done", counts=counts, run_id=run["id"])

    # -- the sweep ----------------------------------------------------------------

    def resume_pending(
        self, *, limit: int = 25, idle_seconds: int = SWEEP_IDLE_SECONDS
    ) -> dict[str, int]:
        """Resume every run still in flight that no request has touched for
        ``idle_seconds`` and nobody holds, through the same command, so the
        sweep and a person's own retry can't diverge. A run another pass
        claimed meanwhile is counted ``busy`` and left alone."""

        now = self._clock()
        cutoff = now - timedelta(seconds=idle_seconds)
        with self._households.connection() as connection:
            user_ids = [
                str(uid)
                for (uid,) in connection.execute(
                    "select user_id from argus_private.account_deletion_runs"
                    " where status in ('started', 'data_deleted') and updated_at < %s"
                    "   and (claim_id is null or claimed_until < %s)"
                    " order by updated_at limit %s",
                    (cutoff, now, limit),
                ).fetchall()
            ]
        result = {"resumed": 0, "done": 0, "pending": 0, "failed": 0, "busy": 0}
        for uid in user_ids:
            try:
                self.delete_account(user_id=uid, origin="sweep")
                result["resumed"] += 1
                result["done"] += 1
                continue
            except AccountDeletionIncomplete as exc:
                if exc.reason == "in_progress":
                    result["busy"] += 1
                    continue
                result["resumed"] += 1
                result["pending"] += 1
            except Exception as exc:
                # No user id in logs: the run is keyed on a hash for that reason.
                logger.error(
                    "Account deletion sweep failed", failure_mode=type(exc).__name__
                )
                result["resumed"] += 1
                result["failed"] += 1
            # Touched, so the next pass reaches the stalest runs first.
            with self._households.connection() as connection, connection.transaction():
                connection.execute(
                    "update argus_private.account_deletion_runs set updated_at = %s"
                    " where user_id = %s",
                    (self._clock(), uid),
                )
        return result

    # -- operator only -------------------------------------------------------------

    def force_complete_step(
        self,
        *,
        user_id: str,
        step: str,
        reason: str,
        operator: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Close one third-party step an operator has decided can't complete
        (Apple ``invalid_request`` after the person revoked the app, a provider
        down for good, a token sealed under a key no process holds any more).
        Only ``scripts/ops/force_account_deletion_step.py`` calls this; no route
        does.

        Refused unless the step has been pending for ``ESCALATE_AFTER`` (7
        days). Without ``confirm`` nothing changes: the plan is returned. With
        it, an Apple, Plaid or Gmail step first gets one more revoke attempt
        through the normal path, recorded like any pass; only what is still
        pending after it is dropped, as ``operator_forced`` with the reason and
        operator kept in the run record. The next pass then finishes the
        deletion."""

        user_id = _uuid(user_id)
        if step not in FORCEABLE_STEPS:
            raise ValueError(f"step must be one of {', '.join(FORCEABLE_STEPS)}")
        reason = (reason or "").strip()
        operator = (operator or "").strip()
        if not reason or len(reason) > 200:
            raise ValueError("a reason of 1 to 200 characters is required")
        if not operator or len(operator) > 80:
            raise ValueError("the operator's name is required")
        subject = subject_hash(user_id)
        now = self._clock()
        with self._households.connection() as connection:
            row = connection.execute(
                "select status, steps from argus_private.account_deletion_runs"
                " where subject_hash = %s",
                (subject,),
            ).fetchone()
        if row is None or row[0] != "data_deleted":
            raise AccountDeletionRejected("no_run_awaiting_third_parties")
        steps = row[1] or {}
        since = (steps.get("pending_since") or {}).get(step)
        if since is None:
            raise AccountDeletionRejected("step_not_pending")
        waited = now - datetime.fromisoformat(since)
        if waited < ESCALATE_AFTER:
            raise AccountDeletionRejected("step_pending_under_7_days")
        plan: dict[str, Any] = {
            "step": step,
            "pending_days": waited.days,
            "last_error": (steps.get("last_error") or {}).get(step),
        }
        if not confirm:
            return {**plan, "dry_run": True, "forced": False}
        run = self._claim(user_id, subject, origin="force")
        try:
            # One more revoke first, recorded like any pass: forcing must
            # never skip a token that would revoke now.
            if step == "apple":
                left = self._revoke_apple(user_id, subject, run)
            elif step == "analytics":
                left = self._delete_analytics(subject, run)
            else:
                left = self._revoke_providers(user_id, subject, only=step).get(step)
            plan["revoke_attempt"] = left or "completed"
            if left is None:
                return {**plan, "dry_run": False, "forced": False}
            if step == "analytics" and not posthog_project_token_configured():
                self._track_pending(subject, {**steps.get("last_error", {}), step: left})
                return {**plan, "dry_run": False, "forced": False}
            self._force(run, user_id, subject, step, reason, operator)
        finally:
            self._release(run["id"], run["claim"])
        logger.warning(
            "Account deletion step force-completed by an operator",
            step=step,
            operator=operator,
        )
        return {**plan, "dry_run": False, "forced": True}

    def _force(
        self,
        run: dict[str, Any],
        user_id: str,
        subject: str,
        step: str,
        reason: str,
        operator: str,
    ) -> None:
        now = self._clock()
        with self._households.connection() as connection, connection.transaction():
            lock_apple_state(connection, user_id)
            self._lock_live_claim(connection, run)
            if step == "apple":
                connection.execute(
                    "delete from public.apple_sign_in_credentials where user_id = %s",
                    (user_id,),
                )
                marker = {"apple_revoke": "operator_forced"}
            elif step == "analytics":
                marker = {"analytics": "operator_forced"}
            else:
                connection.execute(
                    "update argus_private.account_deletion_revocations"
                    " set status = 'operator_forced', secret_ciphertext = null,"
                    "     secret_key_fingerprint = null, external_ref = null,"
                    "     last_error = null, updated_at = %s"
                    " where subject_hash = %s and provider = %s and status = 'pending'",
                    (now, subject, step),
                )
                marker = {}
            forced = {
                step: {"reason": reason, "operator": operator, "at": now.isoformat()}
            }
            connection.execute(
                "update argus_private.account_deletion_runs"
                " set steps = steps || %s::jsonb || jsonb_build_object('forced',"
                "     coalesce(steps -> 'forced', '{}'::jsonb) || %s::jsonb),"
                "     updated_at = %s"
                " where id = %s",
                (json.dumps(marker), json.dumps(forced), now, run["id"]),
            )

    # -- 1. the run and its claim --------------------------------------------------

    def _claim(
        self,
        user_id: str,
        subject: str,
        *,
        existing_only: bool = False,
        origin: DeletionOrigin = "route_first_pass",
    ) -> dict[str, Any] | None:
        """Open the run if this is the first request (idempotent: two first
        requests open one run), then take its claim for this pass."""

        select = (
            "select id, status, steps, claim_id, claimed_until"
            " from argus_private.account_deletion_runs"
            " where subject_hash = %s for update"
        )
        with self._households.connection() as connection, connection.transaction():
            user, apple_state = lock_apple_state(connection, user_id)
            row = connection.execute(select, (subject,)).fetchone()
            if row is None:
                if existing_only:
                    return None
                if origin != "route_first_pass":
                    raise AccountDeletionRejected("no_existing_run")
                if user is None:
                    raise AccountDeletionRejected("unknown_user")
                # A guest is deleted by this same command (Lane 6 acceptance);
                # it simply has no household, plan or provider rows to move.
                placeholder = connection.execute(
                    "select argus_private.is_account_placeholder(%s, %s::jsonb)",
                    (user_id, json.dumps(user[0] or {})),
                ).fetchone()[0]
                if placeholder:
                    raise AccountDeletionRejected("placeholder")
                require_admission(apple_state, self._apple)
                # A concurrent first request waits here on the unique keys,
                # then inserts nothing and locks the row the other one made.
                connection.execute(
                    "insert into argus_private.account_deletion_runs"
                    " (subject_hash, user_id, analytics_distinct_id, status, steps)"
                    " values (%s, %s, %s, 'started', %s::jsonb) on conflict do nothing",
                    (
                        subject,
                        user_id,
                        actor_hash_for_user(user_id),
                        json.dumps(self._analytics_at_open(origin)),
                    ),
                )
                row = connection.execute(select, (subject,)).fetchone()
                if row is None:
                    # Finished by another pass in between.
                    raise AccountDeletionIncomplete("in_progress")
            run_id, status, steps, claim_id, claimed_until = row
            now = self._clock()
            if claim_id is not None and claimed_until > now:
                raise AccountDeletionIncomplete("in_progress")
            claim = str(uuid.uuid4())
            connection.execute(
                "update argus_private.account_deletion_runs"
                " set claim_id = %s, claimed_until = %s where id = %s",
                (claim, now + timedelta(seconds=CLAIM_SECONDS), run_id),
            )
        return {
            "id": str(run_id),
            "status": status,
            "steps": steps or {},
            "claim": claim,
            "origin": origin,
        }

    def _lock_live_claim(self, connection: Any, run: dict[str, Any]) -> dict[str, Any]:
        held = connection.execute(
            "select claim_id::text, claimed_until, steps from argus_private.account_deletion_runs "
            "where id = %s for update",
            (run["id"],),
        ).fetchone()
        if held is None or held[0] != run["claim"] or held[1] <= self._clock():
            raise AccountDeletionIncomplete("in_progress")
        return held[2] or {}

    def _renew(self, run_id: str, claim: str) -> None:
        """Extend this pass's claim before the account delete (Marcus re-check
        N1): third-party calls can take most of CLAIM_SECONDS, and a pass whose
        claim lapsed and was taken stops here instead of racing the new one."""

        now = self._clock()
        with self._households.connection() as connection, connection.transaction():
            renewed = connection.execute(
                "update argus_private.account_deletion_runs"
                " set claimed_until = %s"
                " where id = %s and claim_id = %s and claimed_until > %s returning 1",
                (now + timedelta(seconds=CLAIM_SECONDS), run_id, claim, now),
            ).fetchone()
        if renewed is None:
            raise AccountDeletionIncomplete("in_progress")

    def _release(self, run_id: str, claim: str) -> None:
        with self._households.connection() as connection, connection.transaction():
            connection.execute(
                "update argus_private.account_deletion_runs"
                " set claim_id = null, claimed_until = null"
                " where id = %s and claim_id = %s",
                (run_id, claim),
            )

    # -- 2. placeholders ---------------------------------------------------------

    def _units(
        self, connection: Any, user_id: str
    ) -> dict[tuple[str, str], tuple[str, str]]:
        """Each plan or activity group the person's rows are pinned to, and the
        sharing scope whose placeholder it moves to: the plan's household, or
        the group itself when it is shared outside any plan."""
        return {
            (str(kind), str(unit)): (str(scope_kind), str(scope))
            for kind, unit, scope_kind, scope in connection.execute(
                "select unit_kind, unit_id, scope_kind, scope_id"
                " from argus_private.deletion_placeholder_units(%s)",
                (user_id,),
            ).fetchall()
        }

    def _reserve_placeholders(self, user_id: str, subject: str) -> None:
        with self._households.connection() as connection:
            with connection.transaction():
                # Serializes duplicate requests: the second waits here, then
                # sees the first one's reservations instead of racing them.
                connection.execute(
                    "select 1 from argus_private.account_deletion_runs"
                    " where subject_hash = %s for update",
                    (subject,),
                )
                scopes = set(self._units(connection, user_id).values())
                known = {
                    (str(kind), str(scope))
                    for kind, scope in connection.execute(
                        "select scope_kind, scope_id from argus_private.account_deletion_placeholders"
                        " where subject_hash = %s",
                        (subject,),
                    ).fetchall()
                }
                for kind, scope in sorted(scopes - known):
                    pid = str(uuid.uuid4())
                    # Registered before the Admin API create, so the auth
                    # triggers already skip it when it arrives.
                    connection.execute(
                        "insert into argus_private.account_placeholders (id) values (%s)",
                        (pid,),
                    )
                    connection.execute(
                        "insert into argus_private.account_deletion_placeholders"
                        " (subject_hash, scope_kind, scope_id, placeholder_id)"
                        " values (%s, %s, %s, %s)",
                        (subject, kind, scope, pid),
                    )
            pending = connection.execute(
                "select placeholder_id from argus_private.account_deletion_placeholders"
                " where subject_hash = %s and not created order by placeholder_id",
                (subject,),
            ).fetchall()
        for (pid,) in pending:
            pid = str(pid)
            if not self._auth.user_exists(pid):
                try:
                    self._auth.create_placeholder(
                        user_id=pid, email=placeholder_email(str(uuid.uuid4()))
                    )
                except Exception:
                    # A concurrent request created the same reserved id first.
                    if not self._auth.user_exists(pid):
                        raise
            with self._households.connection() as connection, connection.transaction():
                connection.execute(
                    "update argus_private.account_deletion_placeholders set created = true"
                    " where placeholder_id = %s",
                    (pid,),
                )

    # -- 3. the data transaction -------------------------------------------------

    def _delete_data(self, user_id: str, subject: str) -> None:
        now = self._clock()
        with self._households.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"account_deletion:{user_id}",),
                )
                status = connection.execute(
                    "select status from argus_private.account_deletion_runs"
                    " where subject_hash = %s for update",
                    (subject,),
                ).fetchone()[0]
                if status != "started":
                    return
                connection.execute(
                    "select set_config('argus.locked_history_writer', 'deletion', true)"
                )
                scopes = {
                    (str(kind), str(scope)): str(pid)
                    for kind, scope, pid in connection.execute(
                        "select scope_kind, scope_id, placeholder_id"
                        " from argus_private.account_deletion_placeholders"
                        " where subject_hash = %s and created",
                        (subject,),
                    ).fetchall()
                }
                units = self._units(connection, user_id)
                if not set(units.values()) <= set(scopes):
                    # Something new was pinned since the reservation: roll back
                    # and reserve again rather than delete a row someone keeps.
                    raise _UnitsChanged()
                counts = self._delete_in_transaction(
                    connection,
                    user_id=user_id,
                    subject=subject,
                    units={unit: scopes[scope] for unit, scope in units.items()},
                    now=now,
                )
                connection.execute(
                    "update argus_private.account_deletion_runs"
                    " set status = 'data_deleted', updated_at = %s,"
                    "     steps = steps || jsonb_build_object('counts', %s::jsonb)"
                    " where subject_hash = %s",
                    (now, json.dumps(counts), subject),
                )

    def _delete_in_transaction(
        self,
        connection: Any,
        *,
        user_id: str,
        subject: str,
        units: dict[tuple[str, str], str],
        now: datetime,
    ) -> dict[str, int]:
        # 1.1 to 1.3, and 5.2 for archives left by earlier departures.
        result = household_deletion.leave_every_household(
            connection, self._households, user_id=user_id, now=now
        )
        events = list(result.events)
        # 2: capture every provider credential, then remove the sources.
        captured = connection.execute(
            """insert into argus_private.account_deletion_revocations
                 (subject_hash, provider, source_ref, external_ref, secret_ciphertext,
                  secret_key_fingerprint)
               select %s, source, id, external_ref, secret_ciphertext,
                      secret_key_fingerprint
                 from public.financial_source_connections
                where user_id = %s and source in ('plaid', 'gmail')
                  and secret_ciphertext is not null
               on conflict (subject_hash, provider, source_ref) do update
                 set secret_ciphertext = excluded.secret_ciphertext,
                     secret_key_fingerprint = excluded.secret_key_fingerprint,
                     external_ref = excluded.external_ref
               returning 1""",
            (subject, user_id),
        ).fetchall()
        connection.execute(
            "delete from public.financial_source_connections where user_id = %s",
            (user_id,),
        )
        # 4: invite ids, through the Household-owned writer.
        household_deletion.forget_invite_party(connection, user_id=user_id)
        # 5.1: future shares in other people's plans go back to their owner.
        events += household_deletion.return_future_responsibilities(
            connection, user_id=user_id, today=now.date()
        )
        # 5.1 / 5.2: every pinned row moves to its unit's placeholder.
        used: set[str] = set()
        # Groups first, so a plan's claims are rewritten with every account
        # copy its scope made; every unit of one scope shares its placeholder.
        for (kind, unit), pid in sorted(
            units.items(), key=lambda i: (i[0][0] != "group", i[0])
        ):
            if connection.execute(
                "select argus_private.deletion_place_unit(%s, %s, %s, %s)",
                (user_id, kind, unit, pid),
            ).fetchone()[0]:
                used.add(pid)
                connection.execute(
                    "update argus_private.account_deletion_placeholders set used = true"
                    " where placeholder_id = %s",
                    (pid,),
                )
        household_deletion.write_events(connection, events)
        # Decision c: claims or archives in another household's plan that now
        # name this run's placeholder as a read-only reference.
        cross_scope = connection.execute(
            """select count(*) from (
                 select binding_id, activity_owner_id from public.financial_plan_links
                  where binding_id is not null
                 union all
                 select binding_id, activity_owner_id from public.household_plan_archived_claims
                 union all
                 select binding_id, activity_owner_id from public.household_plan_archived_activities
               ) r
               join public.household_plan_bindings b on b.id = r.binding_id
               join argus_private.account_deletion_placeholders p
                 on p.placeholder_id = r.activity_owner_id and p.subject_hash = %s
              where p.scope_kind = 'household' and p.scope_id <> b.household_id""",
            (subject,),
        ).fetchone()[0]
        # 5.3, 6 and the rows outside the FKs, then the no-blocker check.
        connection.execute(
            "select argus_private.deletion_finish(%s, %s)",
            (user_id, actor_hash_for_user(user_id)),
        )
        return {
            "households_left": result.households_left,
            "households_closed": result.households_closed,
            "admin_handoffs": result.admin_handoffs,
            "plans_handed_over": result.plans_handed_over,
            "archives_passed_on": result.archives_passed_on,
            "placeholders_used": len(used),
            "credentials_captured": len(captured),
            "events": len(events),
            "cross_scope_references": int(cross_scope),
        }

    # -- 4. Apple, before the account delete ------------------------------------

    def _revoke_apple(
        self, user_id: str, subject: str, run: dict[str, Any]
    ) -> str | None:
        with self._households.connection() as connection, connection.transaction():
            _, state = lock_apple_state(connection, user_id)
            steps = self._lock_live_claim(connection, run)
            receipt = steps.get("apple_revoke")
            stored = state.credential
            if stored is None:
                if receipt in {
                    "revoked",
                    "already_revoked",
                    "unrecoverable",
                    "operator_forced",
                }:
                    return None
                if state.unavailable:
                    return "identity_unavailable"
                if state.identity is not None:
                    return "credential_missing"
                return None
            if state.unavailable:
                return "identity_unavailable"
            if stored.apple_subject is not None and (
                state.identity is None or stored.apple_subject != state.identity.subject
            ):
                return "credential_identity_mismatch"
        if self._apple is None:
            return "apple_unconfigured"
        try:
            outcome = _value(self._apple.revoke_stored(stored))
        except AppleRevocationPending as exc:
            if exc.reason != "credential_unreadable":
                return exc.reason
            check = self._key_check("apple", key_id=stored.key_id)
            if check != "verified":
                return f"key_{check}"
            try:
                if _value(self._apple.unreadable_discard_status(stored)) == "readable":
                    return "credential_readable"
            except AppleRevocationPending as unreadable:
                return unreadable.reason
            outcome = "unrecoverable"
        with self._households.connection() as connection, connection.transaction():
            _, current = lock_apple_state(connection, user_id)
            self._lock_live_claim(connection, run)
            if current != state:
                return "credential_replaced"
            if not PostgresAppleCredentialRepository.delete_exact_on(connection, stored):
                return "credential_replaced"
            connection.execute(
                "update argus_private.account_deletion_runs set steps = steps || "
                "jsonb_build_object('apple_revoke', %s::text), updated_at = %s where id = %s",
                (outcome, self._clock(), run["id"]),
            )
        if outcome == "already_revoked":
            self._note_already_revoked(subject, "apple")
        return None

    def _key_check(self, step: str, *, key_id: str | None) -> KeyCheck:
        check = check_current_key(self._box, key_id=key_id)
        if check != "verified":
            # The credential is kept: it may be live under another key (a
            # rolling rotation, a stale environment). Someone has to look.
            logger.error(
                "Account deletion credential kept: key not verified",
                metric="account_deletion.key_check_failed",
                step=step,
                key_check=check,
            )
        return check

    def _record_step(
        self,
        subject: str,
        name: str,
        value: str | None,
        *,
        keep_existing: bool = False,
        run: dict[str, Any] | None = None,
    ) -> None:
        with self._households.connection() as connection, connection.transaction():
            if run is not None:
                self._lock_live_claim(connection, run)
            if keep_existing:
                # "none" only when no earlier attempt recorded an outcome.
                connection.execute(
                    "update argus_private.account_deletion_runs"
                    " set steps = jsonb_build_object(%s::text, 'none') || steps"
                    " where subject_hash = %s",
                    (name, subject),
                )
                return
            connection.execute(
                "update argus_private.account_deletion_runs"
                " set steps = steps || jsonb_build_object(%s::text, %s::text), updated_at = %s"
                " where subject_hash = %s",
                (name, value, self._clock(), subject),
            )

    def _note_already_revoked(self, subject: str, provider: str) -> None:
        """Counted per run and kept after it is done, for the spike alert."""

        now = self._clock()
        with self._households.connection() as connection, connection.transaction():
            connection.execute(
                "update argus_private.account_deletion_runs"
                " set steps = steps || jsonb_build_object('already_revoked',"
                "     coalesce(steps -> 'already_revoked', '{}'::jsonb)"
                "     || jsonb_build_object(%s::text,"
                "          coalesce((steps -> 'already_revoked' ->> %s)::int, 0) + 1))"
                " where subject_hash = %s",
                (provider, provider, subject),
            )
            runs = connection.execute(
                "select count(*) from argus_private.account_deletion_runs"
                " where steps ? 'already_revoked' and updated_at >= %s",
                (now - ALREADY_REVOKED_WINDOW,),
            ).fetchone()[0]
        logger.info(
            "Account deletion credential already revoked",
            metric="account_deletion.already_revoked",
            provider=provider,
        )
        if runs >= ALREADY_REVOKED_SPIKE:
            logger.error(
                "Account deletion already_revoked spike",
                metric="account_deletion.already_revoked_spike",
                runs=int(runs),
                window_hours=int(ALREADY_REVOKED_WINDOW.total_seconds() // 3600),
            )

    def _track_pending(self, subject: str, pending: dict[str, str]) -> None:
        """When each third-party step started waiting and why; an operator
        alert once one has waited ``ESCALATE_AFTER``."""

        now = self._clock()
        with self._households.connection() as connection, connection.transaction():
            steps = (
                connection.execute(
                    "select steps from argus_private.account_deletion_runs"
                    " where subject_hash = %s for update",
                    (subject,),
                ).fetchone()[0]
                or {}
            )
            since = {
                step: (steps.get("pending_since") or {}).get(step, now.isoformat())
                for step in pending
            }
            connection.execute(
                "update argus_private.account_deletion_runs"
                " set steps = (steps - 'pending_since' - 'last_error')"
                "     || jsonb_build_object('pending_since', %s::jsonb, 'last_error', %s::jsonb)"
                " where subject_hash = %s",
                (json.dumps(since), json.dumps(pending), subject),
            )
        for step, started in sorted(since.items()):
            waited = now - datetime.fromisoformat(started)
            if waited >= ESCALATE_AFTER and step == "storage":
                # Our own Storage: nothing to force, it has to be fixed.
                logger.error(
                    "Account deletion cannot erase document sources; fix Storage",
                    metric="account_deletion.storage_failing",
                    step=step,
                    error=pending[step],
                    pending_days=waited.days,
                )
            elif waited >= ESCALATE_AFTER:
                logger.error(
                    "Account deletion step needs an operator",
                    metric="account_deletion.needs_operator",
                    step=step,
                    error=pending[step],
                    pending_days=waited.days,
                )

    # -- 5. late writes and the auth user ------------------------------------------

    def _settle_late_writes(self, user_id: str, subject: str) -> None:
        """Every RESTRICT key to auth.users, read from the catalog. A write
        that committed after the data step (a plan edit already in flight) is
        scrubbed once more by deletion_finish; anything still holding the
        person keeps the run pending instead of failing the Admin API delete."""

        query = "select argus_private.deletion_auth_blockers(%s)"
        try:
            with self._households.connection() as connection, connection.transaction():
                blockers = [
                    r[0] for r in connection.execute(query, (user_id,)).fetchall()
                ]
                if not blockers:
                    return
                logger.warning(
                    "Account deletion re-scrubbing late writes", blockers=blockers
                )
                connection.execute(
                    "select set_config('argus.locked_history_writer', 'deletion', true)"
                )
                connection.execute(
                    "select argus_private.deletion_finish(%s, %s)",
                    (user_id, actor_hash_for_user(user_id)),
                )
                blockers = [
                    r[0] for r in connection.execute(query, (user_id,)).fetchall()
                ]
                if blockers:
                    raise _LateWrite(blockers)
        except (_LateWrite, psycopg.Error) as exc:
            if (
                isinstance(exc, psycopg.Error)
                and getattr(exc, "sqlstate", None) != "55000"
            ):
                raise
            blockers = exc.blockers if isinstance(exc, _LateWrite) else []
            logger.error("Account deletion held by a late write", blockers=blockers)
            pending = (
                ["apple"]
                if "public.apple_sign_in_credentials.user_id" in blockers
                else []
            )
            raise AccountDeletionIncomplete("late_write", pending) from None

    def _delete_auth_user(self, user_id: str, run_id: str, claim: str) -> dict[str, int]:
        self._renew(run_id, claim)
        self._auth.delete_user(user_id)
        with self._households.connection() as connection:
            subject = subject_hash(user_id)
            unused = [
                str(pid)
                for (pid,) in connection.execute(
                    "select placeholder_id from argus_private.account_deletion_placeholders"
                    " where subject_hash = %s and not used",
                    (subject,),
                ).fetchall()
            ]
        for pid in unused:
            self._auth.delete_user(pid)
        now = self._clock()
        with self._households.connection() as connection, connection.transaction():
            connection.execute(
                "delete from argus_private.account_deletion_placeholders where subject_hash = %s",
                (subject,),
            )
            if unused:
                connection.execute(
                    "delete from argus_private.account_placeholders where id = any(%s::uuid[])",
                    (unused,),
                )
            revocations: dict[str, dict[str, int]] = {}
            for provider, status, n in connection.execute(
                "delete from argus_private.account_deletion_revocations"
                " where subject_hash = %s returning provider, status, 1",
                (subject,),
            ).fetchall():
                by = revocations.setdefault(str(provider), {})
                by[str(status)] = by.get(str(status), 0) + int(n)
            # Done: the id and both hashes go, so the record names nobody.
            # Fenced on the claim: if it was lost meanwhile, this transaction
            # rolls back and the pass that holds it finishes the run.
            done = connection.execute(
                "update argus_private.account_deletion_runs"
                " set status = 'done', user_id = null, subject_hash = null,"
                "     analytics_distinct_id = null, claim_id = null, claimed_until = null,"
                "     updated_at = %s, completed_at = %s,"
                "     steps = (steps - 'pending_since' - 'last_error')"
                "       || jsonb_build_object('storage', coalesce(steps ->> 'storage', 'not_applicable'),"
                "                             'revocations', %s::jsonb)"
                " where id = %s and claim_id = %s returning steps",
                (now, now, json.dumps(revocations), run_id, claim),
            ).fetchone()
            if done is None:
                raise AccountDeletionIncomplete("in_progress")
            steps = done[0]
        return dict((steps or {}).get("counts", {}))

    # -- 4. providers and analytics, before the account delete -------------------

    def _revoke_providers(
        self, user_id: str, subject: str, *, only: str | None = None
    ) -> dict[str, str]:
        """Plaid and Gmail tokens captured by the data step (or only one of
        them, for ``force_complete_step``). Returns the providers still
        pending, with the reason."""

        providers = [only] if only else ["plaid", "gmail"]
        with self._households.connection() as connection:
            rows = connection.execute(
                "select provider, source_ref, external_ref, secret_ciphertext,"
                "       secret_key_fingerprint"
                " from argus_private.account_deletion_revocations"
                " where subject_hash = %s and status = 'pending'"
                "   and provider = any(%s) order by provider, source_ref",
                (subject, providers),
            ).fetchall()
        pending: dict[str, str] = {}
        for provider, source_ref, external_ref, ciphertext, key_id in rows:
            error: str | None = None
            if self._revoker is None:
                outcome = "failed"
                error = "connector_unavailable"
            else:
                outcome = self._revoker.revoke_for_deletion(
                    source=provider,
                    connection_id=str(source_ref),
                    external_ref=external_ref or "",
                    envelope=bytes(ciphertext) if ciphertext is not None else None,
                )
            if outcome in ("revoked", "not_applicable"):
                status = "revoked"
            elif outcome == "already_revoked":
                status = "already_revoked"
                self._note_already_revoked(subject, str(provider))
            elif outcome == "unreadable":
                # Given up only when this key sealed it and it still doesn't
                # open; otherwise the ciphertext is kept for a pass that holds
                # the key that sealed it.
                key = self._key_check(str(provider), key_id=key_id)
                status = "unrecoverable" if key == "verified" else "pending"
                error = None if key == "verified" else f"key_{key}"
            else:
                status = "pending"
                error = error or "provider_revoke_failed"
            if status == "pending":
                pending[str(provider)] = error or "provider_revoke_failed"
            self._record_revocation(subject, provider, str(source_ref), status, error)
        return pending

    def _erase_sources(
        self, user_id: str, subject: str, run: dict[str, Any]
    ) -> str | None:
        """The reason while the person's Storage objects are still owed."""

        if self._sources is None:
            return None
        try:
            self._sources.delete(owner_prefix(user_id))
        except Exception as exc:
            logger.warning(
                "Account deletion could not erase document sources",
                failure_mode=type(exc).__name__,
            )
            return "storage_delete_failed"
        self._record_step(subject, "storage", "deleted", run=run)
        return None

    def _analytics_at_open(self, origin: DeletionOrigin) -> dict[str, Any]:
        """Only the route opening a run can decide there are no events."""
        if origin != "route_first_pass" or not isinstance(
            self._analytics, NoAnalyticsEvents
        ):
            return {}
        return {
            "analytics": "not_applicable",
            "analytics_origin": origin,
            "analytics_evidence": {"reason": NOT_APPLICABLE_REASON},
        }

    def _delete_analytics(self, subject: str, run: dict[str, Any]) -> str | None:
        """Advance one claimed step; absence of configuration never settles it."""
        done = {"deleted", "operator_forced", "not_applicable"}
        if self._allow_fake_analytics:
            done.add("recorded_by_fake")
        with self._households.connection() as connection, connection.transaction():
            steps = self._lock_live_claim(connection, run)
            if steps.get("analytics") in done:
                return None
            distinct_id = connection.execute(
                "select analytics_distinct_id from argus_private.account_deletion_runs "
                "where id = %s",
                (run["id"],),
            ).fetchone()[0]
            connection.execute(
                "update argus_private.account_deletion_runs set steps = steps || "
                "jsonb_build_object('analytics', 'pending', 'analytics_origin', %s::text) "
                "where id = %s and claim_id = %s",
                (run["origin"], run["id"], run["claim"]),
            )
        evidence = None
        attempts = 0
        if isinstance(self._analytics, EventAnalyticsDeletion):
            request_id = (steps.get("analytics_evidence") or {}).get("request_id")
            result, attempts = advance_with_retry(
                self._analytics, distinct_id, run["id"], request_id
            )
            outcome = "pending" if result.outcome == "failed" else result.outcome
            evidence = result.evidence(run["id"])
            error = (
                None
                if result.outcome == "deleted"
                else f"analytics_delete_{result.outcome}"
            )
        else:
            outcome = self._analytics.delete_person(distinct_id)
            if outcome == "not_applicable" or (
                outcome == "recorded_by_fake" and not self._allow_fake_analytics
            ):
                outcome, error = "pending", "analytics_adapter_unconfigured"
            elif outcome == "failed":
                outcome, error = "pending", "analytics_delete_failed"
            else:
                error = None
        with self._households.connection() as connection, connection.transaction():
            self._lock_live_claim(connection, run)
            changed = connection.execute(
                "update argus_private.account_deletion_runs set steps = steps || "
                "jsonb_build_object('analytics', %s::text, 'analytics_attempts', "
                "coalesce((steps ->> 'analytics_attempts')::int, 0) + %s) || %s::jsonb, "
                "updated_at = %s where id = %s and claim_id = %s "
                "and steps ->> 'analytics' = 'pending' returning id",
                (
                    outcome,
                    attempts,
                    json.dumps({"analytics_evidence": evidence} if evidence else {}),
                    self._clock(),
                    run["id"],
                    run["claim"],
                ),
            ).fetchone()
            if changed is None:
                raise AccountDeletionIncomplete("in_progress")
        return error

    def _record_revocation(
        self, subject: str, provider: str, source_ref: str, status: str, error: str | None
    ) -> None:
        with self._households.connection() as connection, connection.transaction():
            if status != "pending":
                connection.execute(
                    "update argus_private.account_deletion_revocations"
                    " set status = %s, secret_ciphertext = null, secret_key_fingerprint = null,"
                    "     external_ref = null, attempts = attempts + 1, last_error = null,"
                    "     updated_at = now()"
                    " where subject_hash = %s and provider = %s and source_ref = %s",
                    (status, subject, provider, source_ref),
                )
            else:
                connection.execute(
                    "update argus_private.account_deletion_revocations"
                    " set attempts = attempts + 1, last_error = %s, updated_at = now()"
                    " where subject_hash = %s and provider = %s and source_ref = %s",
                    (error, subject, provider, source_ref),
                )


class _UnitsChanged(Exception):
    pass


class _LateWrite(Exception):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__(", ".join(blockers))
        self.blockers = blockers

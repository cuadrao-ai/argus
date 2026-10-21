"""Recording reviewed imports: preview, accept, reviewed batches, linking.

Canonical writes happen in exactly one place, ``accept``, through
``MoneyService.write`` with an idempotency key derived from the event and the
key that claimed it. The claim stores the reviewed request, so an acceptance
interrupted after the money write committed is completed by replaying that
same request and key, never by a second write under another key. Only errors
the money service raises before writing release the claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from argus.domain.ingestion.reconcile.matching import ACTIVITY_EVIDENCE
from argus.domain.ingestion.reconcile.model import (
    EventNotFound,
    ImportEvent,
    ReconcileError,
    StaleEvent,
)
from argus.domain.ingestion.reconcile.render import counterpart
from argus.domain.owner_scope import OwnerScope
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.money_schemas import DESTINATION_ELIGIBILITY, MoneyRequest

DEFAULT_ZONE = "America/Santo_Domingo"
MAX_CLIENT_KEY = 80
MAX_BATCH_KEY = 40
MAX_BATCH = 100
# Refusals the money service raises before it writes anything.
_NOT_WRITTEN = (RecordingInputError, StaleVersion, AccountNotFound, ValidationError)
_KIND_QUESTIONS = frozenset({"kind", "source_account_id", "destination_account_id"})
_ITEM_REFUSALS = (
    *_NOT_WRITTEN,
    ReconcileError,
    StaleEvent,
    EventNotFound,
    IdempotencyConflict,
)


class Recording:
    """Mixed into ``ReconciliationService``; uses its ``store``, ``money``,
    ``clock``, ``detail``, ``_editable`` and ``_remember_account``."""

    def preview(
        self,
        *,
        user_id: str,
        event_id: str,
        overrides: dict[str, Any] | None = None,
        kind: str | None = None,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        detail = self.detail(user_id=user_id, event_id=event_id, scope=scope)
        if detail["state"] != "open":
            raise ReconcileError(
                "import_not_open", "This import is not waiting for review."
            )
        if detail["evidence"] not in ACTIVITY_EVIDENCE:
            raise ReconcileError(
                "import_not_activity", "This is information, not money that moved."
            )
        try:
            request = MoneyRequest.model_validate(
                {**self._draft(user_id, detail, kind, scope=scope), **(overrides or {})}
            )
        except ValidationError:
            raise ReconcileError(
                "activity_invalid", "The proposed activity is not valid."
            ) from None
        return {
            "event": detail,
            "preview": self.money.preview(user_id=user_id, request=request, scope=scope),
        }

    def accept(
        self,
        *,
        user_id: str,
        event_id: str,
        idempotency_key: str,
        version: int,
        request: MoneyRequest,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        if len(idempotency_key) > MAX_CLIENT_KEY:
            raise ReconcileError("idempotency_key_too_long", "Use at most 80 characters.")
        now = self.clock()
        claimed_now = False
        with self.store.transaction(user_id, scope=scope) as tx:
            event = tx.event(event_id)
            self._require_legacy(event)
            if event.state == "open":
                claimed_now = True
                if event.version != version:
                    raise StaleEvent()
                if event.evidence not in ACTIVITY_EVIDENCE:
                    raise ReconcileError(
                        "import_not_activity",
                        "This is information, not money that moved.",
                    )
                pending = request.model_dump(mode="json")
                event = _bump(
                    replace(
                        event,
                        state="accepting",
                        accept_key=idempotency_key,
                        resolution={**event.resolution, "pending_request": pending},
                    ),
                    now,
                )
                tx.put_event(event)
            elif event.state not in ("accepting", "accepted"):
                raise ReconcileError("import_not_open", "Reopen it to record it.")
        if event.accept_key != idempotency_key:
            if event.state == "accepting":
                # Someone else's interrupted acceptance: finish it, do not
                # record a second time under this key.
                self._complete(user_id, event, scope=scope)
            raise ReconcileError(
                "import_already_accepted", "This import is already recorded."
            )
        # A retry of an already-claimed acceptance replays what was claimed,
        # not whatever this request body says.
        result = self._write(
            user_id, event, request if claimed_now else None, now, scope=scope
        )
        return {
            "event": self.detail(user_id=user_id, event_id=event_id, scope=scope),
            "activity": result["activity"],
            "replayed": result["replayed"],
        }

    def accept_batch(
        self,
        *,
        user_id: str,
        items: Sequence[tuple[str, int]],
        idempotency_key: str,
        scope: OwnerScope,
    ) -> list[dict[str, Any]]:
        """Record a reviewed batch; exceptions stay for individual review.

        Each item names the event version the person saw, so nothing changed
        since review is recorded. An item is recorded only when it has no open
        question: nothing unresolved, no duplicate warning, and a preview that
        is ready without balance-coverage answers. Every other item, including
        one the money service refuses, is returned as ``needs_review`` with
        its reason; nothing about it changes.
        """

        if len(idempotency_key) > MAX_BATCH_KEY:
            raise ReconcileError("idempotency_key_too_long", "Use at most 40 characters.")
        if len(items) > MAX_BATCH:
            raise ReconcileError("import_batch_too_large", "Confirm at most 100 at once.")
        results = []
        for event_id, version in items:
            try:
                results.append(
                    self._accept_one(
                        user_id, event_id, version, idempotency_key, scope=scope
                    )
                )
            except _ITEM_REFUSALS as error:
                results.append(
                    {
                        "event_id": event_id,
                        "outcome": "needs_review",
                        "code": _code(error),
                    }
                )
        return results

    def accept_reviewed(
        self,
        *,
        user_id: str,
        event_id: str,
        version: int,
        idempotency_key: str,
        kind: str | None = None,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        """Record one import as reviewed, with its preview built here.

        For a client that confirms by version and key alone; ``kind``, when
        given, is what the client always records an import as. A retry under
        the claiming key replays what was claimed. Another key's acceptance,
        even an interrupted one, is finished first, so the import is recorded
        once. A version other than the open import's is stale.
        """

        for _ in range(3):
            with self.store.transaction(user_id, scope=scope) as tx:
                event = tx.event(event_id)
                self._require_legacy(event)
            if (
                event.state in ("accepting", "accepted")
                and event.accept_key == idempotency_key
            ):
                result = self._write(user_id, event, None, self.clock(), scope=scope)
                return {
                    "event": self.detail(user_id=user_id, event_id=event_id, scope=scope),
                    "activity": result["activity"],
                    "replayed": True,
                }
            if event.state == "accepting":
                self._complete(user_id, event, scope=scope)
                continue
            if event.state == "accepted":
                raise ReconcileError(
                    "import_already_accepted", "This import is already recorded."
                )
            if event.state != "open":
                raise ReconcileError("import_not_open", "Reopen it to record it.")
            if event.version != version:
                raise StaleEvent()
            try:
                request = self._reviewed_request(user_id, event_id, kind, scope=scope)
            except ReconcileError as error:
                # Claimed between the read and the preview; read it again.
                if error.code != "import_not_open":
                    raise
                continue
            return self.accept(
                user_id=user_id,
                event_id=event_id,
                idempotency_key=idempotency_key,
                version=version,
                request=request,
                scope=scope,
            )
        raise ReconcileError("import_not_open", "This import is not waiting for review.")

    def link_activity(
        self,
        *,
        user_id: str,
        event_id: str,
        activity_id: str,
        version: int,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        """The purchase is already recorded (by hand, by voice, earlier import)."""

        activity = self.money.detail(
            user_id=user_id, activity_id=activity_id, scope=scope
        )
        now = self.clock()
        with self.store.transaction(user_id, scope=scope) as tx:
            event = self._editable(tx, event_id, version)
            if tx.events(("accepting",)):
                # Its new activity is not linked yet; linking now could point
                # two imports at it.
                raise ReconcileError(
                    "import_accept_in_progress", "Another import is being recorded."
                )
            if activity["activity_id"] in tx.activity_links():
                raise ReconcileError(
                    "activity_already_linked", "Another import already points to it."
                )
            event = replace(
                event,
                state="accepted",
                activity_id=activity["activity_id"],
                resolution={**event.resolution, "accepted": _recorded(activity)},
            )
            tx.put_event(_bump(event, now))
        return self.detail(user_id=user_id, event_id=event_id, scope=scope)

    # --- Internals -----------------------------------------------------
    def _accept_one(
        self,
        user_id: str,
        event_id: str,
        version: int,
        batch_key: str,
        *,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        key = f"b:{batch_key}:{event_id}"
        with self.store.transaction(user_id, scope=scope) as tx:
            event = tx.event(event_id)
            self._require_legacy(event)
        if event.state in ("accepted", "accepting") and event.accept_key == key:
            # A retried batch: this item was already claimed by this batch.
            result = self._write(user_id, event, None, self.clock(), scope=scope)
            return _outcome(event_id, result["activity"]["activity_id"], True)
        detail = self.detail(user_id=user_id, event_id=event_id, scope=scope)
        if detail["version"] != version:
            raise StaleEvent()
        if (
            detail["attention"]
            or detail["possible_duplicates"]
            or detail["existing_activity_matches"]
            or detail["recorded_duplicates"]
        ):
            raise ReconcileError(
                "import_possible_duplicate", "Review this one individually."
            )
        result = self.accept(
            user_id=user_id,
            event_id=event_id,
            idempotency_key=key,
            version=version,
            request=self._reviewed_request(user_id, event_id, scope=scope),
            scope=scope,
        )
        return _outcome(event_id, result["activity"]["activity_id"], result["replayed"])

    def _reviewed_request(
        self, user_id: str, event_id: str, kind: str | None = None, *, scope: OwnerScope
    ) -> MoneyRequest:
        preview = self.preview(
            user_id=user_id, event_id=event_id, kind=kind, scope=scope
        )["preview"]
        if not preview["ready"]:
            raise ReconcileError(
                "balance_coverage_required", "Answer its balance question."
            )
        return MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        )

    def _complete(self, user_id: str, event: ImportEvent, *, scope: OwnerScope) -> None:
        try:
            self._write(user_id, event, None, self.clock(), scope=scope)
        except _NOT_WRITTEN:
            pass  # released back to open by _write

    def _write(
        self,
        user_id: str,
        event: ImportEvent,
        request: MoneyRequest | None,
        now: datetime,
        *,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        """Write (or replay) under the claiming key, then finalize the event."""

        try:
            if request is None:
                stored = event.resolution.get("pending_request")
                if stored is None and event.state == "accepted":
                    stored = event.resolution.get("accepted_request")
                if stored is None:
                    raise ReconcileError(
                        "import_not_open", "Nothing is waiting to be recorded."
                    )
                request = MoneyRequest.model_validate(stored)
            result = self.money.write(
                user_id=user_id,
                request=request,
                idempotency_key=f"imp:{event.id}:{event.accept_key}",
                scope=scope,
            )
        except _NOT_WRITTEN:
            self._release(user_id, event, now, scope=scope)
            raise
        activity = result["activity"]
        with self.store.transaction(user_id, scope=scope) as tx:
            current = tx.event(event.id)
            if current.state == "accepting":
                resolution = dict(current.resolution)
                resolution["accepted_request"] = resolution.pop("pending_request", None)
                resolution["accepted"] = _recorded(activity)
                current = replace(
                    current,
                    state="accepted",
                    activity_id=activity["activity_id"],
                    resolution=resolution,
                )
                # Keep any warning raised while this was being recorded (a
                # source withdrew or changed it); the person must see it.
                account = request.account_id or request.source_account_id
                if account:
                    self._remember_account(tx, current, account, now)
                tx.put_event(_bump(current, now))
        return result

    def _release(
        self, user_id: str, event: ImportEvent, now: datetime, *, scope: OwnerScope
    ) -> None:
        with self.store.transaction(user_id, scope=scope) as tx:
            current = tx.event(event.id)
            if current.state == "accepting" and current.accept_key == event.accept_key:
                resolution = dict(current.resolution)
                resolution.pop("pending_request", None)
                tx.put_event(
                    _bump(
                        replace(
                            current, state="open", accept_key=None, resolution=resolution
                        ),
                        now,
                    )
                )

    def _draft(
        self,
        user_id: str,
        detail: dict[str, Any],
        kind: str | None = None,
        *,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        facts, resolution = detail["facts"], detail["resolution"]
        missing = missing_fields(detail)
        if kind is not None and kind not in DESTINATION_ELIGIBILITY:
            # The caller decided the kind, so the import's kind questions are moot.
            missing = [f for f in missing if f not in _KIND_QUESTIONS]
        kind = kind or resolution.get("kind") or facts["kind"]
        if missing:
            raise ReconcileError("import_unresolved", "Complete: " + ", ".join(missing))
        account_id = facts["account_id"]
        accounts = {
            s.account.id: s.account
            for s in self.money.accounts.list_accounts(user_id=user_id, scope=scope)
        }
        account = accounts.get(account_id)
        if account is None:
            raise ReconcileError(
                "financial_account_not_found", "Choose your own account."
            )
        if facts["currency"] and facts["currency"] != account.currency:
            raise ReconcileError(
                "import_currency_mismatch",
                "This import is in another currency than the account; nothing is converted.",
            )
        zone = resolution.get("time_zone") or DEFAULT_ZONE
        draft: dict[str, Any] = {
            "kind": kind,
            "amount": facts["amount"],
            "occurred_at": _start_of_day(facts["occurred_on"], zone),
            "time_zone": zone,
            "note": recorded_note(detail),
        }
        if kind in DESTINATION_ELIGIBILITY:
            other = counterpart(facts["direction"])
            observed = (
                "destination_account_id"
                if other == "source_account_id"
                else "source_account_id"
            )
            draft[observed] = account_id
            draft[other] = resolution.get(other)
        else:
            draft["account_id"] = account_id
        for field in ("category_id", "source_id", "purchase_activity_id"):
            if resolution.get(field):
                draft[field] = resolution[field]
        return draft


def _recorded(activity: dict[str, Any]) -> dict[str, Any]:
    """Facts of the recorded activity, kept so the event can still be matched
    after its evidence is redacted (a disconnect)."""

    when = activity["occurred_at"]
    if isinstance(when, str):
        when = datetime.fromisoformat(when)
    try:
        when = when.astimezone(ZoneInfo(activity.get("time_zone") or DEFAULT_ZONE))
    except (ZoneInfoNotFoundError, ValueError):
        pass
    legs = activity.get("legs") or []
    return {
        "activity_id": activity["activity_id"],
        "kind": activity["kind"],
        "amount": activity["amount"],
        "currency": activity["currency"],
        "occurred_on": when.date().isoformat(),
        "account_id": legs[0]["account_id"] if legs else None,
    }


def _outcome(event_id: str, activity_id: str, replayed: bool) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "outcome": "accepted",
        "activity_id": activity_id,
        "replayed": replayed,
    }


def _code(error: Exception) -> str:
    if isinstance(error, (ReconcileError, RecordingInputError)):
        return error.code
    return {
        StaleEvent: "stale_version",
        StaleVersion: "stale_version",
        EventNotFound: "financial_import_not_found",
        AccountNotFound: "financial_account_not_found",
        IdempotencyConflict: "idempotency_conflict",
    }.get(type(error), "validation_error")


def missing_fields(detail: dict[str, Any]) -> list[str]:
    """What the person must still supply before ``accept`` can record it."""

    return [f for f in detail["unresolved"] if f != "direction"]


def recorded_note(detail: dict[str, Any]) -> str | None:
    """The activity note ``accept`` records: the person's note, else the merchant."""

    if "business" in detail["resolution"]:
        from argus.domain.business.contracts.facts import BusinessResolution

        value = BusinessResolution.model_validate(
            detail["resolution"]["business"]
        ).facts.counterparty.value
        return value[:200] if value is not None else None
    if detail["resolution"].get("note"):
        return detail["resolution"]["note"]
    for observation in detail["observations"]:
        if observation["live"] and observation["merchant"]:
            return observation["merchant"][:200]
    return None


def _start_of_day(day: str, zone: str) -> datetime:
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ReconcileError("time_zone_unknown", "Choose a valid time zone.") from None
    return datetime.combine(date.fromisoformat(day), time(0, 0), tzinfo=tz)


def _bump(event: ImportEvent, now: datetime) -> ImportEvent:
    return replace(event, updated_at=now, version=event.version + 1)

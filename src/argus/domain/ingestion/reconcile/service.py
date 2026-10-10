"""Reconciliation service: the connectors' sink and the person's review queue.

Recording reviewed imports (the only canonical write) lives in ``recording``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, get_args
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argus.domain.business.contracts.facts import BusinessResolution, legacy_projection
from argus.domain.ingestion.connections import (
    LIVE,
    ConnectionNotFound,
    ConnectionRepository,
)
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.reconcile import duplicates, intake
from argus.domain.ingestion.reconcile.matching import (
    ACTIVITY_EVIDENCE,
    account_key,
    activity_matches,
    event_facts,
    match_key,
    primary,
)
from argus.domain.ingestion.reconcile.model import (
    RESOLVABLE,
    AccountLink,
    EventNotFound,
    ImportEvent,
    ReconcileError,
    StaleEvent,
)
from argus.domain.ingestion.reconcile.recording import Recording
from argus.domain.ingestion.reconcile.render import event_view, proposed_kind, unresolved
from argus.domain.ingestion.reconcile.store import ImportStore, ImportTx
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import OwnerScope
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_schemas import SOURCE_IDS, ActivityKind
from argus.domain.recording.money_service import MoneyService


class ReconciliationService(Recording):
    def __init__(
        self,
        store: ImportStore,
        money: MoneyService,
        clock: Callable[[], datetime],
        *,
        connections: ConnectionRepository | None = None,
    ) -> None:
        self.store = store
        self.money = money
        self.clock = clock
        self.connections = connections

    # --- CandidateSink -------------------------------------------------
    def submit(
        self,
        *,
        user_id: str,
        connection_id: str,
        candidates: Sequence[ImportCandidate],
        scope: OwnerScope,
    ) -> SubmitResult:
        def is_live() -> bool:
            if self.connections is None:
                return True
            try:
                row = self.connections.get(
                    user_id=user_id, connection_id=connection_id, scope=scope
                )
            except ConnectionNotFound:
                return False
            return row.status in LIVE

        return intake.submit(
            self.store,
            self.clock(),
            user_id=user_id,
            connection_id=connection_id,
            candidates=candidates,
            is_live=is_live,
            scope=scope,
        )

    def forget_connection(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> int:
        return intake.forget(
            self.store,
            self.clock(),
            user_id=user_id,
            connection_id=connection_id,
            scope=scope,
        )

    # --- Review --------------------------------------------------------
    def list(
        self, *, user_id: str, states: tuple[str, ...], scope: OwnerScope
    ) -> list[dict[str, Any]]:
        activities = current_activities(
            self.money.accounts.list_accounts(user_id=user_id, scope=scope)
        )
        with self.store.transaction(user_id, scope=scope) as tx:
            context = _ViewContext(tx.links(), tx.activity_links(), activities)
            return [self._view(tx, e, context) for e in tx.events(states)]

    def detail(self, *, user_id: str, event_id: str, scope: OwnerScope) -> dict[str, Any]:
        activities = current_activities(
            self.money.accounts.list_accounts(user_id=user_id, scope=scope)
        )
        with self.store.transaction(user_id, scope=scope) as tx:
            context = _ViewContext(tx.links(), tx.activity_links(), activities)
            return self._view(tx, tx.event(event_id), context)

    def resolve(
        self,
        *,
        user_id: str,
        event_id: str,
        version: int,
        changes: dict[str, Any],
        scope: OwnerScope,
    ) -> dict[str, Any]:
        unknown = set(changes) - RESOLVABLE
        if unknown:
            raise ReconcileError("field_not_resolvable", ", ".join(sorted(unknown)))
        cleaned = _clean_resolution(changes)
        owned = {
            s.account.id
            for s in self.money.accounts.list_accounts(user_id=user_id, scope=scope)
        }
        for field in ("account_id", "source_account_id", "destination_account_id"):
            if cleaned.get(field) and cleaned[field] not in owned:
                raise ReconcileError(
                    "financial_account_not_found", "Choose your own account."
                )
        now = self.clock()
        with self.store.transaction(user_id, scope=scope) as tx:
            event = self._editable(tx, event_id, version)
            links = tx.links()
            matched_before = match_key(
                event_facts(event, tx.observations(event.id), links)
            )
            resolution = {**event.resolution, **cleaned}
            resolution = {k: v for k, v in resolution.items() if v is not None}
            event = replace(event, resolution=resolution)
            if cleaned.get("account_id"):
                self._remember_account(tx, event, cleaned["account_id"], now)
            event = intake.reanchor(tx, event)
            facts = event_facts(event, tx.observations(event.id), tx.links())
            if match_key(facts) == matched_before:
                # A note or category edit: keep the person's earlier answer
                # about duplicates instead of raising the question again.
                tx.put_event(_bump(event, now))
            else:
                previous = event.possible_duplicates
                event = _bump(intake.recheck(tx, event), now)
                tx.put_event(event)
                duplicates.mirror(tx, event, previous, now)
        return self.detail(user_id=user_id, event_id=event_id, scope=scope)

    def merge(
        self,
        *,
        user_id: str,
        event_id: str,
        into_event_id: str,
        version: int,
        into_version: int,
        scope: OwnerScope,
    ) -> dict[str, Any]:
        """The person says two events are the same purchase."""

        if event_id == into_event_id:
            raise ReconcileError("import_merge_self", "Choose a different import.")
        now = self.clock()
        with self.store.transaction(user_id, scope=scope) as tx:
            source = tx.event(event_id)
            self._require_legacy(source)
            if source.version != version:
                raise StaleEvent()
            target = tx.event(into_event_id)
            self._require_legacy(target)
            if target.version != into_version:
                raise StaleEvent()
            if "dismissed" in (source.state, target.state):
                raise ReconcileError(
                    "import_dismissed", "Reopen the dismissed import first."
                )
            if "accepting" in (source.state, target.state):
                raise ReconcileError("import_accept_in_progress", "Try again shortly.")
            if source.state == target.state == "accepted":
                raise ReconcileError(
                    "import_merge_two_records",
                    "Both are already recorded; correct or remove one of the records.",
                )
            survivor, absorbed = (
                (source, target) if source.state == "accepted" else (target, source)
            )
            moving = tx.observations(absorbed.id)
            staying = tx.observations(survivor.id)
            live_sources = {o.source for o in staying if o.live}
            if any(o.live and o.source in live_sources for o in moving):
                raise ReconcileError(
                    "import_merge_same_source",
                    "One source reported both; they are separate purchases.",
                )
            for observation in moving:
                tx.put_observation(replace(observation, event_id=survivor.id))
            # The absorbed event's open questions become the survivor's.
            others = (
                set(survivor.possible_duplicates) | set(absorbed.possible_duplicates)
            ) - {
                survivor.id,
                absorbed.id,
            }
            duplicates.forget(tx, absorbed, now)
            tx.delete_event(absorbed.id)
            survivor = tx.event(survivor.id)
            previous = survivor.possible_duplicates
            survivor = replace(
                survivor,
                resolution={**absorbed.resolution, **survivor.resolution},
            )
            survivor = _bump(
                intake.reanchor(
                    tx,
                    duplicates.flag(
                        survivor,
                        others,
                        ambiguous=survivor.attention == "ambiguous_match",
                    ),
                ),
                now,
            )
            tx.put_event(survivor)
            duplicates.mirror(tx, survivor, previous, now)
            survivor_id = survivor.id
        return self.detail(user_id=user_id, event_id=survivor_id, scope=scope)

    def dismiss(
        self, *, user_id: str, event_id: str, version: int, scope: OwnerScope
    ) -> dict[str, Any]:
        now = self.clock()
        with self.store.transaction(user_id, scope=scope) as tx:
            event = self._editable(tx, event_id, version)
            # A dismissed event is no longer anyone's possible duplicate.
            duplicates.forget(tx, event, now)
            event = replace(
                tx.event(event_id),
                state="dismissed",
                possible_duplicates=(),
                attention=None
                if event.attention in duplicates.DUPLICATE_ATTENTION
                else event.attention,
            )
            tx.put_event(_bump(event, now))
        return self.detail(user_id=user_id, event_id=event_id, scope=scope)

    def reopen(
        self, *, user_id: str, event_id: str, version: int, scope: OwnerScope
    ) -> dict[str, Any]:
        now = self.clock()
        with self.store.transaction(user_id, scope=scope) as tx:
            event = tx.event(event_id)
            self._require_legacy(event)
            if event.version != version:
                raise StaleEvent()
            if event.state != "dismissed":
                raise ReconcileError(
                    "import_not_dismissed", "Only dismissed imports reopen."
                )
            if not any(o.live for o in tx.observations(event_id)):
                raise ReconcileError("import_source_removed", "The source withdrew this.")
            tx.put_event(_bump(replace(event, state="open", attention_detail=None), now))
        return self.detail(user_id=user_id, event_id=event_id, scope=scope)

    def acknowledge(
        self, *, user_id: str, event_id: str, version: int, scope: OwnerScope
    ) -> dict[str, Any]:
        """The person checked it: clear a source warning, or say a possible
        duplicate is a different purchase (cleared on both events)."""

        now = self.clock()
        with self.store.transaction(user_id, scope=scope) as tx:
            event = tx.event(event_id)
            self._require_legacy(event)
            if event.version != version:
                raise StaleEvent()
            duplicates.forget(tx, event, now)
            event = tx.event(event_id)
            tx.put_event(
                _bump(
                    replace(
                        event,
                        attention=None,
                        attention_detail=None,
                        possible_duplicates=(),
                    ),
                    now,
                )
            )
        return self.detail(user_id=user_id, event_id=event_id, scope=scope)

    # --- Internals -----------------------------------------------------
    def _view(
        self, tx: ImportTx, event: ImportEvent, context: _ViewContext
    ) -> dict[str, Any]:
        if "business" in event.resolution:
            facts = BusinessResolution.model_validate(event.resolution["business"]).facts
            event = replace(
                event, resolution={**event.resolution, **legacy_projection(facts)}
            )
        observations = tx.observations(event.id)
        facts = event_facts(event, observations, context.links)
        unlinked: list[str] = []
        recorded: list[str] = []
        if event.state == "open" and event.evidence in ACTIVITY_EVIDENCE:
            for activity_id in activity_matches(facts, context.activities):
                owner = context.activity_links.get(activity_id)
                if owner is None:
                    unlinked.append(activity_id)
                elif owner != event.id:
                    recorded.append(owner)
        shared = tx.account_shared(facts.account_id) if facts.account_id else None
        return event_view(
            event,
            observations,
            facts,
            existing_activity_matches=unlinked,
            recorded_duplicates=recorded,
            account_shared=shared,
        )

    @staticmethod
    def _require_legacy(event: ImportEvent) -> None:
        if "business" in event.resolution:
            raise ReconcileError(
                "business_action_required", "Use the Business draft review."
            )

    def _editable(self, tx: ImportTx, event_id: str, version: int) -> ImportEvent:
        event = tx.event(event_id)
        self._require_legacy(event)
        if event.version != version:
            raise StaleEvent()
        if event.state != "open":
            raise ReconcileError(
                "import_not_open", "This import is not waiting for review."
            )
        return event

    def _remember_account(
        self, tx: ImportTx, event: ImportEvent, account_id: str, now: datetime
    ) -> None:
        """Each confirmed mapping is reused for that source's later imports."""

        first = primary(tx.observations(event.id))
        if first is None:
            return
        key = account_key(first.candidate)
        if key is None:
            return
        tx.put_link(
            AccountLink(
                user_id=event.user_id,
                connection_id=first.connection_id,
                account_key=key,
                account_id=account_id,
                created_at=now,
            )
        )


def _clean_resolution(changes: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(changes)
    if cleaned.get("amount") is not None:
        try:
            number = Decimal(str(cleaned["amount"]))
        except InvalidOperation:
            raise ReconcileError("amount_invalid", "Enter a plain amount.") from None
        if not number.is_finite() or number <= 0:
            raise ReconcileError("amount_positive_required", "Enter a positive amount.")
        cleaned["amount"] = format(number.normalize(), "f")
    if cleaned.get("currency") is not None:
        code = str(cleaned["currency"]).strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ReconcileError("currency_invalid", "Use a three-letter currency code.")
        cleaned["currency"] = code
    if cleaned.get("occurred_on") is not None:
        try:
            cleaned["occurred_on"] = date.fromisoformat(
                str(cleaned["occurred_on"])
            ).isoformat()
        except ValueError:
            raise ReconcileError("date_invalid", "Use YYYY-MM-DD.") from None
    if cleaned.get("direction") not in (None, "outflow", "inflow"):
        raise ReconcileError("direction_invalid", "Use outflow or inflow.")
    if cleaned.get("note") is not None:
        cleaned["note"] = str(cleaned["note"])[:200]
    if cleaned.get("kind") is not None and cleaned["kind"] not in get_args(ActivityKind):
        raise ReconcileError("kind_invalid", "Choose an available activity type.")
    if (
        cleaned.get("category_id") is not None
        and cleaned["category_id"] not in CATEGORY_IDS
    ):
        raise ReconcileError("category_unknown", "Choose an available category.")
    if cleaned.get("source_id") is not None and cleaned["source_id"] not in SOURCE_IDS:
        raise ReconcileError("source_unknown", "Choose an available income source.")
    if cleaned.get("time_zone") is not None:
        try:
            ZoneInfo(str(cleaned["time_zone"]))
        except (ZoneInfoNotFoundError, ValueError):
            raise ReconcileError(
                "time_zone_unknown", "Choose a valid time zone."
            ) from None
    for field in (
        "account_id",
        "source_account_id",
        "destination_account_id",
        "purchase_activity_id",
    ):
        if cleaned.get(field) is not None:
            try:
                cleaned[field] = str(UUID(str(cleaned[field])))
            except ValueError:
                raise ReconcileError(f"{field}_invalid", "Use a valid id.") from None
    return cleaned


@dataclass(frozen=True)
class _ViewContext:
    """Loaded once per list/detail call, not once per event."""

    links: dict[tuple[str, str], str]
    activity_links: dict[str, str]
    activities: list[dict[str, Any]]


def _bump(event: ImportEvent, now: datetime) -> ImportEvent:
    return replace(event, updated_at=now, version=event.version + 1)


__all__ = ["EventNotFound", "ReconciliationService", "proposed_kind", "unresolved"]

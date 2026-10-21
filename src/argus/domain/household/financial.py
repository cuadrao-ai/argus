"""Household adapters reuse Recording under live membership locks."""

import base64
import json
from typing import Any

from argus.domain.backtest_admission import canonical_hash
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording import canonical_groups
from argus.domain.recording.errors import (
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.money_plan import plan, request_identity
from argus.domain.recording.money_postgres import load_owner, owner_lock, persist
from argus.domain.recording.money_schemas import MoneyRequest

from .access import HouseholdFinancialScope, dependencies, require_edit, resolve
from .errors import HouseholdNotFound as HouseholdUnavailable
from .errors import HouseholdRule
from .postgres import PostgresHouseholdRepository
from .projection import account, activity, positions
from .service import HouseholdService


class HouseholdFinancialService:
    def __init__(self, households: HouseholdService) -> None:
        if not isinstance(households._repository, PostgresHouseholdRepository):
            raise HouseholdUnavailable()
        self.households = households
        self.repository = households._repository._accounts._repository

    def records(self, c: Any, scope: HouseholdFinancialScope) -> list:
        return [
            self.repository._load(c, a.owner_id, aid, scope=PERSONAL)
            for aid, a in sorted(scope.accounts.items())
        ]

    def snapshot(self, actor: str, hid: str) -> dict:
        with self.households.transaction(actor, hid) as (c, h, m):
            scope = resolve(c, actor, h, m)
            from . import planning_store
            from .planning import SharedPlanningService

            people = planning_store.members(c, hid)
            # Personal writes use the same owner locks, keeping one coherent read.
            owners = canonical_groups.owner_closure(
                c, {p["user_id"] for p in people.values()}
            )
            for owner in owners:
                owner_lock(c, owner)
            records = self.records(c, scope)
            canonical = canonical_groups.load(self.repository, c, owners, scope=PERSONAL)
            projected = []
            for aid, number in canonical.current_visible(scope.accounts).items():
                projected.append(
                    activity(
                        scope,
                        canonical.records,
                        aid,
                        number,
                        all_owner_records=canonical.records,
                        canonical=canonical,
                    )
                )
            projected.sort(
                key=lambda x: (
                    x["activity"]["occurred_at"],
                    x["activity"]["activity_id"],
                ),
                reverse=True,
            )
            access = {
                aid: (a.owner_id, a.permission, hid) for aid, a in scope.accounts.items()
            }
            access.update(
                {
                    s.account.id: (actor, "edit", None)
                    for s in canonical.records
                    if s.account.user_id == actor
                }
            )
            plans = SharedPlanningService(self.households).snapshot_context(
                (c, h, scope.membership_id, people, access, canonical), actor, hid
            )["plans"]
            return {
                "household_id": hid,
                "membership_id": scope.membership_id,
                "authorization_version": scope.authorization_version,
                "accounts": [account(scope, s) for s in records],
                "activities": projected,
                "positions": positions(records),
                "plans": plans,
            }

    def detail(self, actor: str, hid: str, aid: str) -> dict:
        snapshot = self.snapshot(actor, hid)
        found = next((a for a in snapshot["accounts"] if a["account"]["id"] == aid), None)
        if not found:
            raise HouseholdUnavailable()
        return {
            "account": found,
            "activities": [
                a
                for a in snapshot["activities"]
                if any(leg["account_id"] == aid for leg in a["activity"]["legs"])
            ],
        }

    def history(self, actor: str, hid: str, aid: str) -> dict:
        with self.households.transaction(actor, hid) as (c, h, m):
            scope = resolve(c, actor, h, m)
            for owner in sorted({a.owner_id for a in scope.accounts.values()}):
                owner_lock(c, owner)
            canonical = canonical_groups.load(
                self.repository,
                c,
                {a.owner_id for a in scope.accounts.values()},
                scope=PERSONAL,
            )
            hist = canonical.history.get(aid)
            if not hist or not any(
                s.account.id in scope.accounts
                for legs in hist.values()
                for s, _, __ in legs
            ):
                raise HouseholdUnavailable()
            return {
                "items": [
                    activity(
                        scope,
                        canonical.records,
                        aid,
                        revision,
                        canonical=canonical,
                    )
                    for revision in sorted(hist, reverse=True)
                    if any(s.account.id in scope.accounts for s, _, __ in hist[revision])
                ]
            }

    def search(
        self, actor: str, hid: str, q: str, cursor: str | None, limit: int
    ) -> dict:
        snap = self.snapshot(actor, hid)
        items = []
        query = q.casefold().strip()
        for item in snap["accounts"]:
            a = item["account"]
            title = a["nickname"] or a["type"]
            if query in title.casefold():
                items.append(
                    {
                        "id": a["id"],
                        "kind": "account",
                        "title": title,
                        "account_id": a["id"],
                        "activity_id": None,
                    }
                )
        for item in snap["activities"]:
            a = item["activity"]
            title = a["note"] or a["kind"]
            if query in title.casefold():
                items.append(
                    {
                        "id": a["activity_id"],
                        "kind": "activity",
                        "title": title,
                        "account_id": a["legs"][0]["account_id"],
                        "activity_id": a["activity_id"],
                    }
                )
        for item in snap["plans"]:
            title = item["definition"]["name"]
            if query in title.casefold():
                items.append(
                    dict(
                        id=str(item["ref"]["id"]),
                        kind="plan",
                        title=title,
                        account_id=None,
                        activity_id=None,
                        plan_ref=item["ref"],
                    )
                )
        basis = canonical_hash(
            {
                "actor": actor,
                "household": hid,
                "membership": snap["membership_id"],
                "version": snap["authorization_version"],
                "q": query,
                "items": items,
                "accounts": [
                    (a["account"]["id"], a["account"]["version"])
                    for a in snap["accounts"]
                ],
                "plans": [
                    (p["ref"], p["version"], p["archive_reason"]) for p in snap["plans"]
                ],
            }
        )
        offset = 0
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor))
                offset = decoded["offset"]
                if decoded["basis"] != basis or not isinstance(offset, int) or offset < 0:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise HouseholdRule("household_cursor_stale") from None
        more = (
            base64.urlsafe_b64encode(
                json.dumps({"basis": basis, "offset": offset + limit}).encode()
            ).decode()
            if offset + limit < len(items)
            else None
        )
        return {"items": items[offset : offset + limit], "next_cursor": more}

    def money(
        self,
        actor: str,
        hid: str,
        request: MoneyRequest,
        activity_id: str | None = None,
        key: str | None = None,
        *,
        membership_id: str,
        expected_household_version: int,
    ) -> dict:
        with self.households.transaction(actor, hid) as (c, h, m):
            scope = resolve(c, actor, h, m)
            if scope.membership_id != membership_id:
                raise HouseholdUnavailable()
            targets = {
                a
                for a in (
                    request.account_id,
                    request.source_account_id,
                    request.destination_account_id,
                )
                if a
            }
            owner = require_edit(scope, targets)
            for dependency_owner in canonical_groups.owner_closure(c, {owner}):
                owner_lock(c, dependency_owner)
            canonical = canonical_groups.load(self.repository, c, {owner}, scope=PERSONAL)
            records = canonical_groups.VisibleAccounts(
                load_owner(self.repository, c, owner, scope=PERSONAL), canonical
            )
            required = dependencies(records, request, activity_id)
            require_edit(scope, required)
            receipt_scope = f"household:{hid}:{actor}:{scope.membership_id}"
            identity = request_identity(request, activity_id)
            receipt = None
            if key:
                receipt = c.execute(
                    "select identity_hash,activity_id,revision,affected_accounts from public.financial_activity_receipts where user_id=%s and scope=%s and idempotency_key=%s",
                    (owner, receipt_scope, key),
                ).fetchone()
            if receipt:
                if receipt[0] != identity:
                    raise IdempotencyConflict()
                require_edit(scope, set(str(a) for a in receipt[3]))
                return self.receipt(
                    scope,
                    records,
                    str(receipt[1]),
                    receipt[2],
                    tuple(str(a) for a in receipt[3]),
                    True,
                    canonical,
                )
            if scope.authorization_version != expected_household_version:
                raise StaleVersion()
            result = plan(
                records,
                request,
                activity_id,
                self.households._repository._clock(),
                actor_id=actor,
            )
            if not key:
                return result.preview
            if request.expected_versions != result.preview["expected_versions"]:
                raise StaleVersion()
            if not result.preview["ready"]:
                raise RecordingInputError(
                    "balance_coverage_required", "Review each balance question."
                )
            if request.preview_token != result.preview["preview_token"]:
                raise RecordingInputError(
                    "preview_required", "Review the proposed change before saving it."
                )
            for aid in result.affected:
                c.execute(
                    "select id from public.financial_accounts where id=%s and user_id=%s for update",
                    (aid, owner),
                )
            persist(c, owner, result)
            c.execute(
                "insert into public.financial_activity_receipts(user_id,scope,idempotency_key,identity_hash,activity_id,revision,affected_accounts) values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    owner,
                    receipt_scope,
                    key,
                    identity,
                    result.activity_id,
                    result.revision,
                    list(result.affected),
                ),
            )
            return self.receipt(
                scope,
                load_owner(self.repository, c, owner, scope=PERSONAL),
                result.activity_id,
                result.revision,
                result.affected,
                False,
                canonical_groups.load(self.repository, c, {owner}, scope=PERSONAL),
            )

    def receipt(
        self,
        scope: HouseholdFinancialScope,
        records: list,
        aid: str,
        revision: int,
        affected: tuple[str, ...],
        replayed: bool,
        canonical: canonical_groups.ResolvedGroups,
    ) -> dict:
        visible = [s for s in records if s.account.id in scope.accounts]
        return {
            "activity": activity(
                scope,
                records,
                aid,
                revision,
                all_owner_records=records,
                canonical=canonical,
            ),
            "accounts": [account(scope, s) for s in visible if s.account.id in affected],
            "replayed": replayed,
        }

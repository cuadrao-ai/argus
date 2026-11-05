"""Personal planning commands over one canonical financial snapshot."""

from datetime import date, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argus.domain.idempotency import canonical_hash
from argus.domain.planning import claims, model, storage
from argus.domain.planning.projection import matches, occurrence_response, projection
from argus.domain.planning.schemas import (
    ExpectationCreate,
    ExpectationEdit,
    Fulfillment,
    LinkWrite,
    SelectionWrite,
)
from argus.domain.recording.errors import AccountNotFound, StaleVersion
from argus.domain.recording.money_plan import plan
from argus.domain.recording.money_reads import activity, current_activities
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import account_response
from argus.domain.recording.service import FinancialAccountService


class PlanService:
    def __init__(self, accounts: FinancialAccountService) -> None:
        self.accounts = accounts
        self.repository = accounts._repository

    def today(self, state: dict[str, Any]) -> date:
        return (
            self.accounts._clock()
            .astimezone(ZoneInfo(state["selection"]["time_zone"]))
            .date()
        )

    def read(
        self, user_id: str, start: date | None = None, end: date | None = None
    ) -> dict[str, Any]:
        state, accounts = storage.read(self.repository, user_id)
        today = self.today(state)
        start = start or today
        end = end or start + timedelta(days=30)
        if start != today or end < start or (end - start).days > 366:
            model.fail(
                "forecast_period_invalid",
                "Start today and choose an end within 366 days.",
            )
        return projection(state, accounts, start, end, self.accounts._clock())

    def get(self, user_id: str, expectation_id: str) -> dict[str, Any]:
        try:
            identifier = str(UUID(expectation_id))
        except ValueError:
            raise AccountNotFound() from None
        state, _ = storage.read(self.repository, user_id)
        item = state["expectations"].get(identifier)
        if item is None:
            raise AccountNotFound()
        return model.expectation_response(
            item, claims.protected_links(state), self.today(state)
        )

    def _write(
        self, user_id: str, scope: str, body: Any, key: str, action: Any
    ) -> dict[str, Any]:
        return storage.write(
            self.repository,
            user_id,
            scope,
            key,
            canonical_hash(body.model_dump(mode="json", exclude_unset=True)),
            action,
            self.accounts._clock(),
        )

    def create(self, user_id: str, body: ExpectationCreate, key: str) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list) -> tuple:
            item = model.create(body, accounts)
            state["expectations"][item["id"]] = item
            return {
                "expectation": model.expectation_response(
                    item, state["links"], self.today(state)
                )
            }, None

        return self._write(user_id, "expectation.create", body, key, action)

    def edit(
        self, user_id: str, eid: str, body: ExpectationEdit, key: str
    ) -> dict[str, Any]:
        try:
            eid = str(UUID(eid))
        except ValueError:
            raise AccountNotFound() from None

        def action(state: dict[str, Any], accounts: list) -> tuple:
            item = state["expectations"].get(eid)
            if item is None:
                raise AccountNotFound()
            model.edit(
                item, body, accounts, claims.protected_links(state), self.today(state)
            )
            return {
                "expectation": model.expectation_response(
                    item, claims.protected_links(state), self.today(state)
                )
            }, None

        return self._write(user_id, "expectation.edit:" + eid, body, key, action)

    def selection(self, user_id: str, body: SelectionWrite, key: str) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list) -> tuple:
            if body.expected_version != state["selection"]["version"]:
                raise StaleVersion()
            try:
                ZoneInfo(body.time_zone)
            except (ZoneInfoNotFoundError, ValueError):
                model.fail("time_zone_invalid", "Choose a valid reporting time zone.")
            ids = [str(aid) for aid in body.account_ids]
            if len(ids) != len(set(ids)):
                model.fail("accounts_duplicate", "Select each cash account once.")
            for aid in ids:
                model.cash_account(accounts, aid)
            state["selection"] = {
                "version": body.expected_version + 1,
                "account_ids": ids,
                "time_zone": body.time_zone,
            }
            return {"selection": state["selection"]}, None

        return self._write(user_id, "selection", body, key, action)

    def _occurrence(
        self, state: dict[str, Any], oid: str, version: int | None = None
    ) -> dict[str, Any]:
        item = model.find_occurrence(state, oid, self.today(state))
        if version is not None and item["expectation_version"] != version:
            raise StaleVersion()
        return item

    def _validate_money(
        self, item: dict[str, Any], body: Fulfillment, accounts: list
    ) -> None:
        model.cash_account(accounts, item["account_id"], item["currency"])
        if (
            not item["account_id"]
            or body.activity.account_id != item["account_id"]
            or body.activity.kind != ("income" if item["kind"] == "income" else "expense")
        ):
            model.fail(
                "fulfillment_mismatch",
                "Choose the expectation's cash account and activity type.",
            )

    def preview(self, user_id: str, oid: str, body: Fulfillment) -> dict[str, Any]:
        state, accounts = storage.read(self.repository, user_id)
        item = self._occurrence(state, oid, body.expected_version)
        if oid in state["links"]:
            model.fail(
                "occurrence_already_linked",
                "Open the existing activity or explicitly link another entry.",
            )
        self._validate_money(item, body, accounts)
        preview = plan(accounts, body.activity, None, self.accounts._clock()).preview
        return {
            "occurrence": occurrence_response(item, state, {}, self.today(state)),
            "money": preview,
        }

    def fulfill(
        self, user_id: str, oid: str, body: Fulfillment, key: str
    ) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list) -> tuple:
            item = self._occurrence(state, oid, body.expected_version)
            if oid in state["links"]:
                model.fail(
                    "occurrence_already_linked",
                    "Open the existing activity or explicitly link another entry.",
                )
            self._validate_money(item, body, accounts)
            money = MoneyService(self.accounts).prepare(accounts, body.activity)
            updated = storage.projected(accounts, money, self.accounts._clock())
            actual = activity(updated, money.activity_id)
            state["links"][oid] = {
                "expectation_id": item["expectation_id"],
                "activity_id": money.activity_id,
                "activity_revision": money.revision,
                "snapshot": item,
            }
            return {
                "occurrence": occurrence_response(
                    item, state, {actual["activity_id"]: actual}, self.today(state)
                ),
                "activity": actual,
                "accounts": [
                    account_response(s) for s in updated if s.account.id in money.affected
                ],
            }, money

        return self._write(user_id, "fulfill:" + oid, body, key, action)

    def candidates(self, user_id: str, oid: str) -> dict[str, Any]:
        state, accounts = storage.read(self.repository, user_id)
        item = self._occurrence(state, oid)
        used = {link["activity_id"] for key, link in state["links"].items() if key != oid}
        return {
            "items": [
                a
                for a in current_activities(accounts)
                if a["activity_id"] not in used and matches(item, a)
            ]
        }

    def link(self, user_id: str, oid: str, body: LinkWrite, key: str) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list) -> tuple:
            item = self._occurrence(state, oid, body.expected_version)
            actual = activity(accounts, str(body.activity_id))
            if actual["revision"] != body.activity_revision:
                raise StaleVersion()
            if not matches(item, actual):
                model.fail(
                    "fulfillment_mismatch",
                    "Choose activity matching the expected account, currency and type.",
                )
            if any(
                link["activity_id"] == actual["activity_id"] and other != oid
                for other, link in state["links"].items()
            ):
                model.fail(
                    "activity_already_linked",
                    "That activity already fulfills another occurrence.",
                )
            snapshot = state["links"].get(oid, {}).get("snapshot", item)
            state["links"][oid] = {
                "expectation_id": item["expectation_id"],
                "activity_id": actual["activity_id"],
                "activity_revision": actual["revision"],
                "snapshot": snapshot,
            }
            return {
                "occurrence": occurrence_response(
                    item, state, {actual["activity_id"]: actual}, self.today(state)
                )
            }, None

        return self._write(user_id, "link:" + oid, body, key, action)

"""Debt commands share Plan serialization, replay and Money confirmation."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from argus.domain.planning import (
    debt_model,
    debt_projection,
    goal_commands,
    model,
    storage,
)
from argus.domain.planning.debt_schemas import DebtCreate, DebtEdit, DebtLink, DebtRecord
from argus.domain.planning.service import PlanService
from argus.domain.recording.errors import StaleVersion
from argus.domain.recording.money_plan import plan
from argus.domain.recording.money_reads import activity, current_activities
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.schemas import account_response


class DebtService:
    def __init__(self, planner: PlanService) -> None:
        self.planner = planner

    def _view(
        self, state: dict[str, Any], accounts: list[StoredAccount], did: str
    ) -> dict[str, Any]:
        today = self.planner.today(state)
        return next(
            p
            for p in debt_projection.project(
                state, accounts, today, today + timedelta(days=366)
            )
            if p["debt"]["id"] == did
        )

    def get(self, owner: str, did: str) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        item = debt_model.get(state, did)
        return self._view(state, accounts, item["id"])

    def create(self, owner: str, body: DebtCreate, key: str) -> dict[str, Any]:
        def action(
            state: dict[str, Any], accounts: list[Any]
        ) -> tuple[dict[str, Any], Any]:
            item = debt_model.create(body, accounts, state)
            state["debts"][item["id"]] = item
            return {"debt": self._view(state, accounts, item["id"])}, None

        return self.planner._write(owner, "debt.create", body, key, action)

    def edit(self, owner: str, did: str, body: DebtEdit, key: str) -> dict[str, Any]:
        did = debt_model.goal_model.identifier(did)

        def action(
            state: dict[str, Any], accounts: list[Any]
        ) -> tuple[dict[str, Any], Any]:
            item = debt_model.get(state, did, body.expected_version)
            debt_model.edit(item, body, accounts, state, self.planner.today(state))
            return {"debt": self._view(state, accounts, did)}, None

        return self.planner._write(owner, "debt.edit:" + did, body, key, action)

    def candidates(self, owner: str, did: str) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        item = debt_model.get(state, did)
        used = {leg["activity_id"] for leg in state["links"].values()}
        sources = {
            s.account.id
            for s in accounts
            if s.account.type in {"cash", "checking", "savings"}
            and not s.account.archived
        }
        return {
            "items": [
                a
                for a in current_activities(accounts)
                if a["activity_id"] not in used
                and any(
                    debt_model.matches(
                        a, source, item["debt_account_id"], item["currency"]
                    )
                    for source in sources
                )
            ]
        }

    def _attach(
        self,
        state: dict[str, Any],
        accounts: list[Any],
        item: dict[str, Any],
        actual: dict[str, Any],
        oid: str | None,
    ) -> None:
        if item["archived"] or not debt_model.eligible(item, accounts):
            model.fail(
                "debt_setup_invalid",
                "Restore an eligible debt plan before assigning a payment.",
            )
        if any(
            leg["activity_id"] == actual["activity_id"] for leg in state["links"].values()
        ):
            model.fail(
                "activity_already_linked", "That payment already has an assignment."
            )
        occurrence = (
            debt_model.find_occurrence(state, item["id"], oid, self.planner.today(state))
            if oid
            else None
        )
        source = (
            occurrence["source_account_id"]
            if occurrence
            else next(
                (leg["account_id"] for leg in actual["legs"] if leg["role"] == "source"),
                None,
            )
        )
        if not source or not debt_model.matches(
            actual, source, item["debt_account_id"], item["currency"]
        ):
            model.fail(
                "debt_payment_mismatch",
                "Choose a payment for this debt and scheduled funding account.",
            )
        model.cash_account(accounts, source, item["currency"])
        state["links"][str(uuid4())] = {
            "expectation_id": None,
            "goal_id": None,
            "debt_plan_id": item["id"],
            "occurrence_id": oid,
            "activity_id": actual["activity_id"],
            "activity_revision": actual["revision"],
            "snapshot": occurrence or {},
            "attribution": {
                "source_account_id": source,
                "destination_account_id": item["debt_account_id"],
                "currency": item["currency"],
            },
        }

    def link(self, owner: str, did: str, body: DebtLink, key: str) -> dict[str, Any]:
        did = debt_model.goal_model.identifier(did)

        def action(
            state: dict[str, Any], accounts: list[Any]
        ) -> tuple[dict[str, Any], Any]:
            item = debt_model.get(state, did, body.expected_version)
            entry = activity(accounts, str(body.activity_id))
            if entry["revision"] != body.activity_revision:
                raise StaleVersion()
            goal_commands.account_versions(
                accounts,
                body.expected_account_versions,
                {leg["account_id"] for leg in entry["legs"]},
            )
            self._attach(
                state,
                accounts,
                item,
                entry,
                str(body.occurrence_id) if body.occurrence_id else None,
            )
            item["version"] += 1
            return {"debt": self._view(state, accounts, did)}, None

        return self.planner._write(owner, "debt.link:" + did, body, key, action)

    def _record(
        self,
        state: dict[str, Any],
        accounts: list[Any],
        did: str,
        body: DebtRecord,
        confirming: bool,
    ) -> tuple[dict[str, Any], Any]:
        item = debt_model.get(state, did, body.expected_version)
        did = item["id"]
        if (
            body.activity.kind not in {"card_payment", "debt_payment"}
            or body.activity.expected_revision is not None
        ):
            model.fail("debt_payment_mismatch", "Record a new payment for this debt.")
        money = (
            MoneyService(self.planner.accounts).prepare(accounts, body.activity)
            if confirming
            else plan(accounts, body.activity, None, self.planner.accounts._clock())
        )
        if not money.preview["ready"]:
            return {
                "debt": self._view(state, accounts, did),
                "money": money.preview,
            }, None
        updated = storage.projected(accounts, money, self.planner.accounts._clock())
        entry = activity(updated, money.activity_id)
        self._attach(
            state,
            updated,
            item,
            entry,
            str(body.occurrence_id) if body.occurrence_id else None,
        )
        if confirming:
            item["version"] += 1
            return {
                "debt": self._view(state, updated, did),
                "activity": entry,
                "accounts": [
                    account_response(s) for s in updated if s.account.id in money.affected
                ],
            }, money
        return {"debt": self._view(state, updated, did), "money": money.preview}, None

    def preview(self, owner: str, did: str, body: DebtRecord) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        return self._record(state, accounts, did, body, False)[0]

    def record(self, owner: str, did: str, body: DebtRecord, key: str) -> dict[str, Any]:
        did = debt_model.goal_model.identifier(did)
        return self.planner._write(
            owner,
            "debt.record:" + did,
            body,
            key,
            lambda state, accounts: self._record(state, accounts, did, body, True),
        )

"""Complete goal commands over the existing Plan and Recording transaction."""

from datetime import timedelta
from typing import Any

from argus.domain.planning import goal_commands, goal_model, goal_projection, storage
from argus.domain.planning.goal_schemas import (
    AllocationWrite,
    ContributionLink,
    ContributionRecord,
    ContributionRelease,
    GoalCreate,
    GoalEdit,
)
from argus.domain.planning.schemas import CASH_TYPES
from argus.domain.recording.money_plan import plan
from argus.domain.recording.money_reads import (
    activity,
    activity_in_currency,
    current_activities,
)
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.repository import StoredAccount
from argus.domain.recording.schemas import account_response


class GoalService:
    def __init__(self, planner: Any) -> None:
        self.planner = planner

    def _view(
        self, state: dict[str, Any], accounts: list[StoredAccount], gid: str
    ) -> dict[str, Any]:
        today = self.planner.today(state)
        return next(
            p
            for p in goal_projection.project(
                state, accounts, today, today + timedelta(days=30)
            )[0]
            if p["goal"]["id"] == gid
        )

    def get(self, owner: str, gid: str) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        item = goal_model.get(state, gid)
        return self._view(state, accounts, item["id"])

    def create(self, owner: str, body: GoalCreate, key: str) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            item = goal_model.create(body, accounts)
            state["goals"][item["id"]] = item
            return {"goal": self._view(state, accounts, item["id"])}, None

        return self.planner._write(owner, "goal.create", body, key, action)

    def edit(self, owner: str, gid: str, body: GoalEdit, key: str) -> dict[str, Any]:
        gid = goal_model.identifier(gid)

        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            item = goal_model.get(state, gid, body.expected_version)
            goal_model.edit(item, body, accounts, state, self.planner.today(state))
            return {"goal": self._view(state, accounts, gid)}, None

        return self.planner._write(owner, "goal.edit:" + gid, body, key, action)

    def allocate(self, owner: str, body: AllocationWrite, key: str) -> dict[str, Any]:
        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            today = self.planner.today(state)
            goal_commands.replace_allocations(state, accounts, body, today)
            goals, pools = goal_projection.project(
                state, accounts, today, today + timedelta(days=30)
            )
            return {"goals": goals, "pools": pools}, None

        return self.planner._write(owner, "goal.allocate", body, key, action)

    def candidates(self, owner: str, gid: str) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        item = goal_model.get(state, gid)
        used = {link["activity_id"] for link in state["links"].values()}
        eligible = {
            stored.account.id
            for stored in accounts
            if stored.account.type in CASH_TYPES
            and stored.account.currency == item["currency"]
        }
        return {
            "items": [
                a
                for a in current_activities(accounts)
                if a["activity_id"] not in used
                and a["kind"] == "transfer"
                and activity_in_currency(a, item["currency"])
                and all(leg["account_id"] in eligible for leg in a["legs"])
                and any(
                    leg["role"] == "destination"
                    and leg["account_id"] == item["destination_account_id"]
                    for leg in a["legs"]
                )
            ]
        }

    def link(
        self, owner: str, gid: str, body: ContributionLink, key: str
    ) -> dict[str, Any]:
        gid = goal_model.identifier(gid)

        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            goal_commands.link(state, accounts, gid, body, self.planner.today(state))
            return {"goal": self._view(state, accounts, gid)}, None

        return self.planner._write(owner, "goal.link:" + gid, body, key, action)

    def release(
        self, owner: str, gid: str, cid: str, body: ContributionRelease, key: str
    ) -> dict[str, Any]:
        gid, cid = goal_model.identifier(gid), goal_model.identifier(cid)

        def action(state: dict[str, Any], accounts: list[StoredAccount]) -> tuple:
            item = goal_model.get(state, gid, body.expected_version)
            goal_commands.release(state, gid, cid)
            item["version"] += 1
            return {"goal": self._view(state, accounts, gid)}, None

        return self.planner._write(
            owner, "goal.release:" + gid + ":" + cid, body, key, action
        )

    def _record(
        self,
        state: dict[str, Any],
        accounts: list[StoredAccount],
        gid: str,
        body: ContributionRecord,
        confirming: bool,
    ) -> tuple:
        gid = goal_model.identifier(gid)
        item = goal_model.get(state, gid, body.expected_version)
        if (
            body.activity.kind != "transfer"
            or body.activity.expected_revision is not None
        ):
            from argus.domain.planning.model import fail

            fail(
                "goal_contribution_mismatch",
                "Record a new transfer for this contribution.",
            )
        before = goal_commands.amounts(state, accounts)
        money = (
            MoneyService(self.planner.accounts).prepare(accounts, body.activity)
            if confirming
            else plan(accounts, body.activity, None, self.planner.accounts._clock())
        )
        if not money.preview["ready"]:
            return {
                "goal": self._view(state, accounts, gid),
                "money": money.preview,
                "pools": goal_projection.project(
                    state, accounts, self.planner.today(state), self.planner.today(state)
                )[1],
            }, None
        updated = storage.projected(accounts, money, self.planner.accounts._clock())
        actual = activity(updated, money.activity_id)
        goal_commands.attach(
            state,
            updated,
            item,
            actual,
            "add",
            str(body.occurrence_id) if body.occurrence_id else None,
            self.planner.today(state),
        )
        goal_commands.require_backing(state, updated, before, self.planner.today(state))
        if confirming:
            item["version"] += 1
            return {
                "goal": self._view(state, updated, gid),
                "activity": actual,
                "accounts": [
                    account_response(s) for s in updated if s.account.id in money.affected
                ],
            }, money
        return {
            "goal": self._view(state, updated, gid),
            "money": money.preview,
            "pools": goal_projection.project(
                state, updated, self.planner.today(state), self.planner.today(state)
            )[1],
        }, None

    def preview(self, owner: str, gid: str, body: ContributionRecord) -> dict[str, Any]:
        state, accounts = storage.read(self.planner.repository, owner)
        return self._record(state, accounts, gid, body, False)[0]

    def record(
        self, owner: str, gid: str, body: ContributionRecord, key: str
    ) -> dict[str, Any]:
        gid = goal_model.identifier(gid)
        return self.planner._write(
            owner,
            "goal.record:" + gid,
            body,
            key,
            lambda state, accounts: self._record(state, accounts, gid, body, True),
        )

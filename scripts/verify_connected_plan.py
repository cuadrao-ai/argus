"""Exercise connected Plan against the isolated local Auth/API/Postgres demo."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx


class LocalPlan:
    def __init__(self, fixture: Path):
        self.config = json.loads(fixture.read_text())
        if (
            self.config["apiURL"] != "http://127.0.0.1:58600/api/v1"
            or self.config["supabaseURL"] != "http://127.0.0.1:58601"
        ):
            raise ValueError("Only the isolated connected Plan stack is accepted.")
        self.client = httpx.Client(base_url=self.config["apiURL"], timeout=30)
        self.headers: dict[int, dict[str, str]] = {}
        self.now = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.today = self.now.astimezone(ZoneInfo("America/Santo_Domingo")).date()
        self.stamp = uuid4().hex[:6]
        self.checks: list[str] = []

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        user: int = 0,
        key: str | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> Any:
        for attempt in range(2):
            if user not in self.headers:
                identity = self.config["users"][user]
                response = self.client.post(
                    "/auth/login",
                    json={
                        "email": identity["email"],
                        "password": identity["password"],
                        "captcha_token": "argus-local-browser-qa",
                    },
                )
                assert (
                    response.status_code == 200
                ), f"Local authentication failed: {response.status_code}"
                self.headers[user] = {
                    "Authorization": "Bearer "
                    + response.json()["session"]["access_token"]
                }
            response = self.client.request(
                method,
                path,
                json=body,
                headers={
                    **self.headers[user],
                    **({"Idempotency-Key": key} if key else {}),
                },
            )
            if response.status_code != 401 or attempt:
                break
            self.headers.pop(user)
        assert (
            response.status_code in expected
        ), f"{method} {path}: {response.status_code}; {response.text[:600]}"
        return response.json()

    def account(self, name: str, amount: str | None, currency: str = "DOP") -> dict:
        return self.request(
            "POST",
            "/financial-accounts",
            {
                "type": "checking",
                "currency": currency,
                "nickname": name + " " + self.stamp,
                "amount": amount,
                "as_of": (self.now - timedelta(days=60)).isoformat()
                if amount is not None
                else None,
            },
            key=str(uuid4()),
        )

    def selection(
        self, accounts: list[dict], zone: str = "America/Santo_Domingo"
    ) -> None:
        current = self.projection()["selection"]
        result = self.request(
            "PUT",
            "/financial-plan/selection",
            {
                "expected_version": current["version"],
                "account_ids": [a["id"] for a in accounts],
                "time_zone": zone,
            },
            key=str(uuid4()),
        )
        assert set(result["selection"]["account_ids"]) == {a["id"] for a in accounts}

    def expectation(
        self,
        name: str,
        kind: str,
        amount: str,
        account: dict,
        days: int = 0,
        cadence: str = "once",
    ) -> dict:
        body = {
            "kind": kind,
            "title": name + " " + self.stamp,
            "currency": account["currency"],
            "amount": amount,
            "account_id": account["id"],
            "schedule": {
                "cadence": cadence,
                "start_date": str(self.today + timedelta(days=days)),
                "end_date": None,
                "month_days": [],
            },
        }
        key = str(uuid4())
        result = self.request("POST", "/financial-plan/expectations", body, key=key)
        replay = self.request("POST", "/financial-plan/expectations", body, key=key)
        assert (
            replay["replayed"]
            and replay["expectation"]["id"] == result["expectation"]["id"]
        )
        return result["expectation"]

    def projection(self) -> dict:
        return self.request("GET", "/financial-plan")

    def occurrence(self, expectation: dict) -> dict:
        return next(
            o
            for o in self.projection()["occurrences"]
            if o["expectation_id"] == expectation["id"]
        )

    def money(self, kind: str, amount: str, account: dict, **extra: Any) -> dict:
        return {
            "kind": kind,
            "amount": amount,
            "account_id": account["id"],
            "occurred_at": self.now.isoformat(),
            "time_zone": "America/Santo_Domingo",
            "note": "Connected Plan proof " + self.stamp,
            **extra,
        }

    def prepare(self, route: str, body: dict, wrapped: bool = False) -> dict:
        for _ in range(3):
            result = self.request("POST", route + "/preview", body)
            preview = result["money"] if wrapped else result
            if preview["ready"]:
                reviewed = {
                    **preview["reviewed_request"],
                    "preview_token": preview["preview_token"],
                }
                return {**body, "activity": reviewed} if wrapped else reviewed
            command = body["activity"] if wrapped else body
            command["coverage"] = [
                {
                    "account_id": a["account_id"],
                    "observation_id": o["observation_id"],
                    "included": False,
                }
                for a in preview["affected_accounts"]
                for o in a["observations"]
            ]
        raise AssertionError("Observation review did not become ready")

    def record(self, body: dict, activity: dict | None = None) -> dict:
        route = "/financial-activities" + (
            "/" + activity["activity_id"] if activity else ""
        )
        reviewed = self.prepare(route, body)
        return self.request(
            "PATCH" if activity else "POST", route, reviewed, key=str(uuid4())
        )["activity"]

    def check(self, label: str, condition: bool) -> None:
        assert condition, label
        self.checks.append(label)

    def run(self) -> dict:
        bank = self.account("Plan checking", "100")
        cash = self.account("Plan reserve", "50")
        unknown = self.account("Plan unknown dollars", None, "USD")
        self.selection([bank, cash])
        bill = self.expectation("Rent before payday", "bill", "300", bank)
        income = self.expectation("Next income", "income", "500", bank, days=5)
        projection = self.projection()
        dop = next(c for c in projection["currencies"] if c["currency"] == "DOP")
        self.check(
            "Earlier bill shows shortfall despite positive period ending",
            dop["starting_minor"] == "15000"
            and dop["ending_minor"] == "35000"
            and dop["first_shortfall_date"] == str(self.today),
        )
        self.check(
            "Expected income and bills leave actual balances unchanged",
            self.request("GET", "/financial-accounts/" + bank["id"])["balance"][
                "amount_minor"
            ]
            == 10000,
        )
        occurrence = self.occurrence(bill)
        route = "/financial-plan/occurrences/" + occurrence["id"] + "/fulfillment"
        body = self.prepare(
            route,
            {
                "expected_version": occurrence["expectation_version"],
                "activity": self.money("expense", "280", bank),
            },
            wrapped=True,
        )
        key = str(uuid4())
        posted = self.request("POST", route, body, key=key)
        replay = self.request("POST", route, body, key=key)
        activity = posted["activity"]
        self.check(
            "Same-key fulfillment retries preserve one canonical activity",
            replay["replayed"]
            and replay["activity"]["activity_id"] == activity["activity_id"],
        )
        self.request("POST", route, body, key=str(uuid4()), expected=(409, 422))
        dop = next(c for c in self.projection()["currencies"] if c["currency"] == "DOP")
        self.check(
            "Fulfilled occurrence is not subtracted twice",
            self.occurrence(bill)["status"] == "fulfilled"
            and dop["ending_minor"] == "37000",
        )
        activity = self.record(
            self.money(
                "expense",
                "250",
                bank,
                expected_revision=activity["revision"],
                reason="Correct receipt amount",
            ),
            activity,
        )
        self.check(
            "Amount correction keeps the same occurrence fulfilled",
            self.occurrence(bill)["status"] == "fulfilled",
        )
        refund = self.record(
            self.money("refund", "50", bank, purchase_activity_id=activity["activity_id"])
        )
        self.check(
            "Actual refund does not reopen a paid bill",
            self.occurrence(bill)["status"] == "fulfilled",
        )
        received = self.record(self.money("income", "400", bank, source_id="salary"))
        incoming = self.occurrence(income)
        link_route = "/financial-plan/occurrences/" + incoming["id"] + "/link"
        candidates = self.request(
            "GET", "/financial-plan/occurrences/" + incoming["id"] + "/candidates"
        )["items"]
        self.check(
            "Matching activity is offered for explicit linking",
            received["activity_id"] in {a["activity_id"] for a in candidates},
        )
        link_body = {
            "expected_version": incoming["expectation_version"],
            "activity_id": received["activity_id"],
            "activity_revision": received["revision"],
        }
        link_key = str(uuid4())
        self.request("POST", link_route, link_body, key=link_key)
        self.check(
            "Link retries replay without new activity",
            self.request("POST", link_route, link_body, key=link_key)["replayed"],
        )
        dop = next(c for c in self.projection()["currencies"] if c["currency"] == "DOP")
        self.check(
            "Linked receipt replaces expected income in forecast",
            self.occurrence(income)["status"] == "fulfilled"
            and dop["ending_minor"] == "35000"
            and dop["net_cash_change_minor"] == "0",
        )
        current = next(
            e for e in self.projection()["expectations"] if e["id"] == income["id"]
        )
        self.request(
            "PATCH",
            "/financial-plan/expectations/" + income["id"],
            {
                "expected_version": current["version"],
                "title": "Confirmed payday " + self.stamp,
                "amount": "600",
            },
            key=str(uuid4()),
        )
        self.check(
            "Expectation edit preserves already fulfilled future occurrence",
            self.occurrence(income)["status"] == "fulfilled"
            and self.occurrence(income)["id"] == incoming["id"],
        )
        activity = self.record(
            self.money(
                "expense",
                "250",
                cash,
                expected_revision=activity["revision"],
                reason="Review funding account",
            ),
            activity,
        )
        self.check(
            "Account correction re-evaluates linked status",
            self.occurrence(bill)["status"] == "needs_review",
        )
        activity = self.record(
            self.money(
                "expense",
                "250",
                bank,
                expected_revision=activity["revision"],
                reason="Restore confirmed funding account",
            ),
            activity,
        )
        self.check(
            "Corrected linked account restores derived fulfillment",
            self.occurrence(bill)["status"] == "fulfilled",
        )
        self.expectation("Weekly travel", "bill", "20", cash, days=1, cadence="weekly")
        usd = self.expectation("Expected dollars", "income", "100", unknown, days=3)
        self.selection([bank, cash, unknown], zone="America/New_York")
        projected = self.projection()
        dollars = next(c for c in projected["currencies"] if c["currency"] == "USD")
        self.check(
            "Unknown cash remains unknown and currencies stay separate",
            dollars["starting_minor"] is None
            and dollars["ending_minor"] is None
            and dollars["unknown_account_ids"] == [unknown["id"]]
            and self.occurrence(usd)["status"] == "planned",
        )
        self.check(
            "Saved reporting zone persists",
            projected["selection"]["time_zone"] == "America/New_York",
        )
        self.request(
            "PATCH",
            "/financial-plan/expectations/" + bill["id"],
            {"expected_version": bill["version"], "title": "Unauthorized edit"},
            user=1,
            key=str(uuid4()),
            expected=(404,),
        )
        other = self.request("GET", "/financial-plan", user=1)
        self.check(
            "Second authenticated identity cannot read or edit owner expectations",
            bill["id"] not in {e["id"] for e in other["expectations"]}
            and bank["id"] not in other["selection"]["account_ids"],
        )
        self.headers.pop(0, None)
        reopened = self.projection()
        self.check(
            "Fresh authentication reopens the same durable links",
            next(o for o in reopened["occurrences"] if o["id"] == incoming["id"])[
                "activity_id"
            ]
            == received["activity_id"],
        )
        return {
            "status": "passed",
            "checks": self.checks,
            "accounts": [
                {"id": a["id"], "nickname": a["nickname"], "currency": a["currency"]}
                for a in [bank, cash, unknown]
            ],
            "expectation_ids": [bill["id"], income["id"]],
            "activity_ids": [
                activity["activity_id"],
                received["activity_id"],
                refund["activity_id"],
            ],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "limitations": [
                "Synthetic local identities only; no physical-device or internet deployment proof.",
                "Recurrence boundary and concurrency coverage belongs to the real-Postgres test matrix.",
            ],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = LocalPlan(args.fixture)
    try:
        result = proof.run()
    finally:
        proof.client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"Verified {len(result['checks'])} connected Plan HTTP checks; sanitized evidence saved."
    )

"""Real local financial Search proof. No provider or hosted access."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from verify_connected_plan import LocalPlan


class LocalSearch(LocalPlan):
    def __init__(self, fixture: Path):
        self.config = json.loads(fixture.read_text())
        if (
            self.config["apiURL"] != "http://127.0.0.1:58800/api/v1"
            or self.config["supabaseURL"] != "http://127.0.0.1:58801"
        ):
            raise ValueError("Only the isolated connected Search stack is accepted.")
        self.client = httpx.Client(base_url=self.config["apiURL"], timeout=30)
        self.headers: dict[int, dict[str, str]] = {}
        self.now = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.today = self.now.astimezone(ZoneInfo("America/Santo_Domingo")).date()
        self.stamp = uuid4().hex[:6]
        self.checks: list[str] = []

    def search(self, *, user: int = 0, **query: object) -> dict:
        return self.request(
            "GET", "/financial-search?" + str(httpx.QueryParams(query)), user=user
        )

    def run(self) -> dict:
        accounts = [self.account(f"Search {self.stamp} {i:02}", "100") for i in range(23)]
        dollar = self.account("Café 100%_ ' " + chr(92), None, "USD")
        bank, cash = accounts[:2]
        bill = self.expectation("Search future rent", "bill", "25", bank, days=500)
        activity = self.record(
            {
                "kind": "transfer",
                "source_account_id": bank["id"],
                "destination_account_id": cash["id"],
                "amount": "20",
                "occurred_at": self.now.isoformat(),
                "time_zone": "America/Santo_Domingo",
                "note": "Old transfer " + self.stamp,
            }
        )
        found = self.search(q="Old transfer " + self.stamp, kind="activity")["items"]
        self.check(
            "One logical transfer result",
            len(found) == 1
            and found[0]["activity"]["activity_id"] == activity["activity_id"],
        )
        corrected = self.record(
            {
                "kind": "transfer",
                "source_account_id": bank["id"],
                "destination_account_id": cash["id"],
                "amount": "21",
                "occurred_at": self.now.isoformat(),
                "time_zone": "America/Santo_Domingo",
                "note": "Corrected transfer " + self.stamp,
                "expected_revision": activity["revision"],
                "reason": "Search correction proof",
            },
            activity,
        )
        self.check(
            "Obsolete note is absent",
            not self.search(q="Old transfer " + self.stamp)["items"],
        )
        self.check(
            "Current correction projects canonical amount",
            self.search(q="Corrected transfer " + self.stamp)["items"][0]["activity"][
                "amount"
            ]
            == corrected["amount"],
        )
        for query in ("cafe", "%_", "'", chr(92)):
            self.check(
                "Literal/accent query " + query,
                any(
                    hit["account"]["id"] == dollar["id"]
                    for hit in self.search(q=query, kind="account")["items"]
                ),
            )
        query = "Search " + self.stamp
        page = self.search(q=query, kind="account", limit=7)
        ids = [hit["account"]["id"] for hit in page["items"]]
        first_cursor = page["next_cursor"]
        while page["next_cursor"]:
            page = self.search(
                q=query, kind="account", limit=7, cursor=page["next_cursor"]
            )
            ids.extend(hit["account"]["id"] for hit in page["items"])
        self.check(
            "All pages have unique canonical account IDs",
            set(ids) == {a["id"] for a in accounts} and len(ids) == len(set(ids)),
        )
        current = self.request("GET", "/financial-accounts/" + bank["id"])
        archived = self.request(
            "PATCH",
            "/financial-accounts/" + bank["id"],
            {"expected_version": current["version"], "archived": True},
        )
        response = self.request(
            "GET",
            "/financial-search?"
            + str(httpx.QueryParams(q=query, kind="account", cursor=first_cursor)),
            expected=(409,),
        )
        self.check(
            "Edits invalidate snapshot cursor",
            response["code"] == "financial_search_stale_cursor",
        )
        self.check(
            "Archived account remains findable",
            any(
                hit["account"]["id"] == archived["id"] and hit["account"]["archived"]
                for hit in self.search(q=query, kind="account", limit=50)["items"]
            ),
        )
        archived_bill = self.request(
            "PATCH",
            "/financial-plan/expectations/" + bill["id"],
            {"expected_version": bill["version"], "archived": True},
            key=str(uuid4()),
        )["expectation"]
        self.check(
            "Archived expectation outside forecast remains findable",
            any(
                hit["expectation"]["id"] == archived_bill["id"]
                for hit in self.search(q=self.stamp, kind="expectation")["items"]
            ),
        )
        self.check(
            "Currency filter preserves unknown balance",
            self.search(q=self.stamp, kind="account", currency="USD")["items"][0][
                "account"
            ]["balance"]["state"]
            == "unknown",
        )
        self.check(
            "Other owner cannot search these records",
            not self.search(user=1, q=self.stamp)["items"],
        )
        for route in (
            "/financial-accounts/" + bank["id"],
            "/financial-activities/" + activity["activity_id"],
            "/financial-plan/expectations/" + bill["id"],
        ):
            self.request("GET", route, user=1, expected=(404,))
        self.check("Other owner cannot open typed destinations", True)
        self.check(
            "Expectation opens by exact ID",
            self.request("GET", "/financial-plan/expectations/" + bill["id"])["id"]
            == bill["id"],
        )
        return {
            "checks": self.checks,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "search_query": query,
            "account_ids": ids,
            "activity_id": activity["activity_id"],
            "expectation_id": bill["id"],
            "limitations": [
                "Local synthetic data only; native interaction acceptance is separate."
            ],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = LocalSearch(args.fixture)
    try:
        result = proof.run()
    finally:
        proof.client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Verified {len(result['checks'])} connected Search HTTP checks.")

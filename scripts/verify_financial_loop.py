"""Replay the financial loop against a local API and local synthetic Auth fixture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx


def run(fixture: Path) -> dict[str, object]:
    config = json.loads(fixture.read_text())
    if (
        config["apiURL"] != "http://127.0.0.1:58400/api/v1"
        or config["supabaseURL"] != "http://127.0.0.1:58401"
    ):
        raise ValueError("This proof accepts only the isolated local financial stack.")
    now = datetime.now(timezone.utc)

    def date(days):
        return (now - timedelta(days=days)).isoformat()

    with httpx.Client(base_url=config["apiURL"], timeout=30) as client:
        sessions = []
        for user in config["users"]:
            response = client.post(
                "/auth/login",
                json={
                    "email": user["email"],
                    "password": user["password"],
                    "captcha_token": "argus-local-browser-qa",
                },
                headers={"Origin": "http://127.0.0.1:3001"},
            )
            assert (
                response.status_code == 200
            ), f"Local sign-in failed ({response.status_code})"
            sessions.append(
                {"Authorization": "Bearer " + response.json()["session"]["access_token"]}
            )
        owner, other = sessions

        def post(path, body, key=None, headers=owner):
            result = client.post(
                path,
                json=body,
                headers={**headers, **({"Idempotency-Key": key} if key else {})},
            )
            assert result.status_code in {
                200,
                201,
            }, f"{path} failed ({result.status_code})"
            return result.json()

        def totals():
            rows = client.get("/financial-home", headers=owner).json()["currencies"]
            row = next((r for r in rows if r["currency"] == "DOP"), {})
            return int(row.get("net_worth_minor", "0")), int(
                row.get("recorded_spending_minor", "0")
            )

        initial_position, initial_spending = totals()

        def home_delta(position, spending):
            assert totals() == (initial_position + position, initial_spending + spending)

        account = post(
            "/financial-accounts",
            {
                "type": "checking",
                "currency": "DOP",
                "nickname": "Loop verification",
                "amount": "10000",
                "as_of": date(10),
            },
            str(uuid4()),
        )
        home_delta(1000000, 0)
        path = "/financial-accounts/" + account["id"]

        def expense(amount, days, coverage=(), record_id=None):
            current = client.get(path, headers=owner).json()
            body = {
                "expected_version": current["version"],
                "amount": amount,
                "occurred_at": date(days),
                "note": "Synthetic verification",
                "coverage": list(coverage),
            }
            if record_id:
                body.update(expected_revision=1, reason="Correct synthetic amount")
            route = path + "/activity" + ("/" + record_id if record_id else "")
            preview = post(route + "/preview", body)
            assert preview["ready"]
            body["preview_token"] = preview["preview_token"]
            key = str(uuid4())
            result = client.request(
                "PATCH" if record_id else "POST",
                route,
                json=body,
                headers={**owner, "Idempotency-Key": key},
            )
            assert result.status_code in {
                200,
                201,
            }, f"Expense write failed ({result.status_code})"
            return result.json(), body, key, route

        first, _, _, _ = expense("2000", 8)
        assert first["account"]["balance"]["amount_minor"] == 800000
        home_delta(800000, 200000)
        fixed, _, _, _ = expense("1900", 8, record_id=first["activity"]["record_id"])
        assert fixed["account"]["balance"]["amount_minor"] == 810000
        home_delta(810000, 190000)
        body = {
            "expected_version": fixed["account"]["version"],
            "amount": "7500",
            "as_of": date(5),
            "note": "Synthetic checked balance",
        }
        preview = post(path + "/balance-checks/preview", body)
        assert preview["difference_minor"] == -60000
        body["preview_token"] = preview["preview_token"]
        checked = post(path + "/balance-checks", body, str(uuid4()))
        home_delta(750000, 190000)
        late, late_body, key, route = expense(
            "600",
            7,
            [{"observation_id": checked["check"]["record_id"], "included": True}],
        )
        assert late["account"]["balance"]["amount_minor"] == 750000
        home_delta(750000, 250000)
        new, _, _, _ = expense("500", 2)
        assert new["account"]["balance"]["amount_minor"] == 700000
        home_delta(700000, 300000)
        replay = post(route, late_body, key)
        assert (
            replay["replayed"]
            and replay["activity"]["record_id"] == late["activity"]["record_id"]
        )
        assert replay["account"]["balance"]["amount_minor"] == 700000
        home_delta(700000, 300000)
        assert client.get(path, headers=other).status_code == 404
        assert client.get(path + "/activity", headers=other).status_code == 404
        checks = client.get(path + "/balance-checks", headers=owner).json()["items"]
        assert (
            checks[0]["difference_minor"] == -60000
            and checks[0]["unexplained_minor"] == 0
        )
        unknown = post(
            "/financial-accounts",
            {"type": "cash", "currency": "USD", "nickname": "Unknown verification"},
            str(uuid4()),
        )
        assert (
            unknown["balance"]["state"] == "unknown"
            and unknown["balance"]["amount_minor"] is None
        )
    with httpx.Client(base_url=config["apiURL"], timeout=30) as reopened:
        account = reopened.get(path, headers=owner).json()
        assert account["balance"]["amount_minor"] == 700000
        home = reopened.get("/financial-home", headers=owner).json()
        assert all(isinstance(row["net_worth_minor"], str) for row in home["currencies"])
        assert any(
            row["currency"] == "USD" and row["unknown_accounts"] >= 1
            for row in home["currencies"]
        )
    return {
        "result": "passed",
        "account_id": account["id"],
        "balance_minor": 700000,
        "original_difference_minor": -60000,
        "remaining_unexplained_minor": 0,
        "replay": "one accepted record",
        "isolation": "other owner refused",
        "unknown": "preserved",
        "reopen": "durable HTTP read",
        "home": "position and spending deltas agree after every write and replay",
        "proof": "localhost synthetic Auth/API/Postgres, not physical iPhone",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.fixture), indent=2))

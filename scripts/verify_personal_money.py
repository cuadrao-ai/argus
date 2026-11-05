"""Verify the personal money outcome through isolated local Auth/API/Postgres."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx


def run(fixture: Path) -> dict[str, Any]:
    config = json.loads(fixture.read_text())
    if (
        config["apiURL"] != "http://127.0.0.1:58500/api/v1"
        or config["supabaseURL"] != "http://127.0.0.1:58501"
    ):
        raise ValueError("This proof accepts only the isolated 58500 local money stack.")
    now = datetime.now(timezone.utc)
    zone = ZoneInfo("America/Santo_Domingo")
    month = now.astimezone(zone).strftime("%Y-%m")
    prior_month = now.astimezone(zone).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)
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

        def post(
            path: str, body: dict[str, Any], key: str | None = None
        ) -> dict[str, Any]:
            result = client.post(
                path,
                json=body,
                headers={**owner, **({"Idempotency-Key": key} if key else {})},
            )
            assert result.status_code in (
                200,
                201,
            ), f"{path} failed ({result.status_code})"
            return cast(dict[str, Any], result.json())

        def get(path: str) -> dict[str, Any]:
            result = client.get(path, headers=owner)
            assert result.status_code == 200, f"{path} failed ({result.status_code})"
            return cast(dict[str, Any], result.json())

        def account(kind: str, currency: str, amount: str | None) -> dict[str, Any]:
            return post(
                "/financial-accounts",
                {
                    "type": kind,
                    "currency": currency,
                    "amount": amount,
                    "as_of": (now - timedelta(days=70)).isoformat()
                    if amount is not None
                    else None,
                    "nickname": "Synthetic personal money proof",
                },
                str(uuid4()),
            )

        def monthly() -> dict[str, int]:
            home = get(
                "/financial-home?month=" + month + "&time_zone=America/Santo_Domingo"
            )
            assert (
                home["period"]["month"] == month and home["coverage"] == "recorded_only"
            )
            row: dict[str, Any] = next(
                (r for r in home["currencies"] if r["currency"] == "DOP"), {}
            )
            return {
                k: int(row.get(k, "0"))
                for k in (
                    "gross_income_minor",
                    "gross_purchases_minor",
                    "refunds_minor",
                    "net_spending_minor",
                )
            }

        baseline = monthly()
        cash = account("checking", "DOP", "1000")
        savings = account("savings", "DOP", "100")
        card = account("credit_card", "DOP", "10")
        unknown = account("investment", "USD", None)

        def record(
            body: dict[str, Any], aid: str | None = None
        ) -> tuple[dict[str, Any], dict[str, Any], str]:
            body = {
                "occurred_at": (now - timedelta(seconds=1)).isoformat(),
                "time_zone": "America/Santo_Domingo",
                **body,
            }
            route = "/financial-activities" + ("/" + aid if aid else "")
            preview = post(route + "/preview", body)
            if not preview["ready"]:
                body["coverage"] = [
                    {
                        "account_id": effect["account_id"],
                        "observation_id": q["observation_id"],
                        "included": False,
                    }
                    for effect in preview["affected_accounts"]
                    for q in effect["observations"]
                ]
                preview = post(route + "/preview", body)
            assert preview["ready"]
            reviewed = {
                **preview["reviewed_request"],
                "preview_token": preview["preview_token"],
            }
            key = str(uuid4())
            result = client.request(
                "PATCH" if aid else "POST",
                route,
                json=reviewed,
                headers={**owner, "Idempotency-Key": key},
            )
            assert result.status_code in (
                200,
                201,
            ), f"Confirm failed ({result.status_code})"
            return cast(dict[str, Any], result.json()), reviewed, key

        income, _, _ = record(
            {
                "kind": "income",
                "account_id": cash["id"],
                "amount": "100",
                "source_id": "salary",
            }
        )
        purchase, _, _ = record(
            {
                "kind": "expense",
                "account_id": cash["id"],
                "amount": "40",
                "category_id": "shopping",
                "occurred_at": prior_month.isoformat(),
            }
        )
        transfer, transfer_body, transfer_key = record(
            {
                "kind": "transfer",
                "source_account_id": cash["id"],
                "destination_account_id": savings["id"],
                "amount": "50",
            }
        )
        payment, _, _ = record(
            {
                "kind": "card_payment",
                "source_account_id": savings["id"],
                "destination_account_id": card["id"],
                "amount": "10",
            }
        )
        refund, _, _ = record(
            {
                "kind": "refund",
                "account_id": card["id"],
                "amount": "25",
                "purchase_activity_id": purchase["activity"]["activity_id"],
            }
        )
        assert refund["activity"]["category_id"] == "shopping"
        credit = get("/financial-accounts/" + card["id"])["balance"]
        assert credit["amount_minor"] == 2500 and credit["credit_minor"] == 2500
        delta = {k: v - baseline[k] for k, v in monthly().items()}
        assert delta == {
            "gross_income_minor": 10000,
            "gross_purchases_minor": 0,
            "refunds_minor": 2500,
            "net_spending_minor": -2500,
        }
        positions = {
            aid: get("/financial-accounts/" + aid)["balance"]["amount_minor"]
            for aid in (cash["id"], savings["id"], card["id"])
        }
        assert positions == {cash["id"]: 101000, savings["id"]: 14000, card["id"]: 2500}
        replay = post("/financial-activities", transfer_body, transfer_key)
        assert replay["replayed"] and replay["activity"] == transfer["activity"]
        assert (
            len(
                get("/financial-activities/" + transfer["activity"]["activity_id"])[
                    "legs"
                ]
            )
            == 2
        )
        for aid in (cash["id"], savings["id"]):
            assert any(
                i["activity_id"] == transfer["activity"]["activity_id"]
                for i in get("/financial-accounts/" + aid + "/activity")["items"]
            )
        cap = client.post(
            "/financial-activities/preview",
            headers=owner,
            json={
                "kind": "refund",
                "account_id": card["id"],
                "amount": "16",
                "purchase_activity_id": purchase["activity"]["activity_id"],
                "occurred_at": (now - timedelta(seconds=1)).isoformat(),
            },
        )
        assert cap.status_code == 422
        corrected, _, _ = record(
            {
                "kind": "expense",
                "account_id": savings["id"],
                "amount": "40",
                "category_id": "shopping",
                "occurred_at": prior_month.isoformat(),
                "expected_revision": 1,
                "reason": "Correct synthetic account",
            },
            purchase["activity"]["activity_id"],
        )
        assert len(corrected["accounts"]) == 2
        assert (
            len(
                get(
                    "/financial-activities/"
                    + purchase["activity"]["activity_id"]
                    + "/history"
                )["items"]
            )
            == 2
        )
        unknown_income, _, _ = record(
            {
                "kind": "income",
                "account_id": unknown["id"],
                "amount": "12",
                "source_id": "interest",
            }
        )
        unknown_balance = unknown_income["accounts"][0]["balance"]
        assert (
            unknown_balance["state"] == "unknown"
            and unknown_balance["amount_minor"] is None
            and unknown_balance["activity_since_tracking_minor"] == 1200
        )
        for item in (income, purchase, transfer, payment, refund):
            assert (
                client.get(
                    "/financial-activities/" + item["activity"]["activity_id"],
                    headers=other,
                ).status_code
                == 404
            )
        assert monthly() == {k: baseline[k] + delta[k] for k in baseline}
        expected = {
            aid: get("/financial-accounts/" + aid)["balance"] for aid in positions
        }
    with httpx.Client(base_url=config["apiURL"], timeout=30) as reopened:
        for aid, balance in expected.items():
            assert (
                reopened.get("/financial-accounts/" + aid, headers=owner).json()[
                    "balance"
                ]
                == balance
            )
    return {
        "result": "passed",
        "scope": "localhost58500 synthetic Auth/API/Postgres",
        "activity_kinds": ["income", "expense", "transfer", "card_payment", "refund"],
        "monthly_delta": delta,
        "credit_minor": 2500,
        "pair_replay": "one accepted operation",
        "pair_detail": "reachable from both account legs",
        "correction": "old and new accounts reviewed; history retained",
        "refund_cap": "rejected excess",
        "unknown": "investment income preserves unknown",
        "isolation": "other owner refused",
        "reopen": "durable HTTP read",
        "account_ids": list(expected),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.fixture), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    sys.stdout.write(result)

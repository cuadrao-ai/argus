#!/usr/bin/env python3
"""Capture staging Home totals and verify one synthetic native money journey."""

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = "https://cuadrao-api-staging.onrender.com/api/v1"
AUTH = "https://skedzwocnmrhfigiwyzi.supabase.co"
ZONE = "America/Santo_Domingo"
MINOR = (
    "assets_minor",
    "cash_minor",
    "other_assets_minor",
    "debts_minor",
    "net_worth_minor",
    "recorded_spending_minor",
    "gross_income_minor",
    "gross_purchases_minor",
    "refunds_minor",
    "net_spending_minor",
)
COUNTS = ("known_accounts", "unknown_accounts")
FIELDS = MINOR + COUNTS
EXPECTED = {
    "income": {
        "DOP": {
            "assets_minor": 190000,
            "cash_minor": 190000,
            "net_worth_minor": 190000,
            "recorded_spending_minor": 27500,
            "gross_income_minor": 110000,
            "gross_purchases_minor": 27500,
            "refunds_minor": 7500,
            "net_spending_minor": 20000,
            "known_accounts": 1,
        }
    },
    "transfer": {
        "DOP": {
            "assets_minor": 97500,
            "cash_minor": 97500,
            "net_worth_minor": 97500,
            "recorded_spending_minor": 12500,
            "gross_purchases_minor": 12500,
            "net_spending_minor": 12500,
            "known_accounts": 2,
        }
    },
    "card": {
        "DOP": {
            "assets_minor": 83000,
            "cash_minor": 80000,
            "other_assets_minor": 3000,
            "net_worth_minor": 83000,
            "recorded_spending_minor": 12000,
            "gross_purchases_minor": 12000,
            "refunds_minor": 25000,
            "net_spending_minor": -13000,
            "known_accounts": 2,
        }
    },
    "currencies": {
        "DOP": {
            "assets_minor": 150000,
            "cash_minor": 150000,
            "net_worth_minor": 150000,
            "known_accounts": 2,
        },
        "USD": {
            "gross_income_minor": 10000,
            "refunds_minor": 2500,
            "net_spending_minor": -2500,
            "unknown_accounts": 1,
        },
    },
}


def currencies(rows):
    result = {}
    if not isinstance(rows, list):
        raise ValueError("Currency rows must be a list")
    for row in rows:
        code = row["currency"]
        if (
            not isinstance(code, str)
            or not re.fullmatch(r"[A-Z]{3}", code)
            or code in result
        ):
            raise ValueError("Invalid or duplicate currency")
        values = {}
        for field in MINOR:
            value = row[field]
            if not isinstance(value, str) or not re.fullmatch(
                r"-?(0|[1-9][0-9]*)", value
            ):
                raise ValueError("Invalid exact minor-unit amount")
            values[field] = int(value)
        for field in COUNTS + ("currency_fraction_digits",):
            value = row[field]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("Invalid currency coverage or precision")
            values[field] = value
        result[code] = values
    return result


def request(client, method, url, **kwargs):
    response = client.request(method, url, **kwargs)
    if response.status_code != 200:
        raise ValueError(f"{method} request failed with HTTP {response.status_code}")
    return response.json()


def capture(args):
    fixture = Path(args.fixture)
    if stat.S_IMODE(fixture.stat().st_mode) != 0o600:
        raise ValueError("Credential fixture must have mode 0600")
    config = json.loads(fixture.read_text())
    if config["apiURL"] != API or config["supabaseURL"] != AUTH:
        raise ValueError("Only the approved staging endpoints are allowed")
    key = config["anonKey"]
    if not key.startswith("sb_publishable_"):
        payload = key.split(".")[1]
        if (
            json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))[
                "role"
            ]
            != "anon"
        ):
            raise ValueError("An anonymous public key is required")
    datetime.strptime(args.month + "-01", "%Y-%m-%d")
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", args.month):
        raise ValueError("Month must use YYYY-MM")
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        session = request(
            client,
            "POST",
            AUTH + "/auth/v1/token?grant_type=password",
            headers={"apikey": key},
            json={"email": config["email"], "password": config["password"]},
        )
        home = request(
            client,
            "GET",
            API + "/financial-home",
            headers={"Authorization": "Bearer " + session["access_token"]},
            params={"month": args.month, "time_zone": ZONE},
        )
    if (
        home["coverage"] != "recorded_only"
        or home["period"]["month"] != args.month
        or home["period"]["time_zone"] != ZONE
    ):
        raise ValueError("Home returned the wrong reporting period or coverage")
    currencies(home["currencies"])
    snapshot = {
        "api_url": API,
        "phase": args.phase,
        "period": home["period"],
        "coverage": home["coverage"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "owner_hash": hashlib.sha256(session["user"]["id"].encode()).hexdigest(),
        "currencies": [
            {k: row[k] for k in ("currency", "currency_fraction_digits") + FIELDS}
            for row in home["currencies"]
        ],
    }
    with os.fdopen(
        os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as stream:
        json.dump(snapshot, stream, indent=2)
        stream.write("\n")
    return {"captured": args.phase, "month": args.month}


def verify(before, after, journey):
    if before["phase"] != "before" or after["phase"] != "after":
        raise ValueError("Snapshots must be supplied in before/after order")
    for field in ("api_url", "period", "coverage", "owner_hash"):
        if before[field] != after[field]:
            raise ValueError("Snapshots have different " + field)
    if (
        before["api_url"] != API
        or before["coverage"] != "recorded_only"
        or before["period"]["time_zone"] != ZONE
    ):
        raise ValueError("Snapshots are outside the approved staging projection")
    first, last = currencies(before["currencies"]), currencies(after["currencies"])
    deltas = {}
    for code in sorted(first.keys() | last.keys() | EXPECTED[journey].keys()):
        empty = dict.fromkeys(FIELDS, 0)
        old, new = first.get(code, empty), last.get(code, empty)
        if (
            code in first
            and code in last
            and old["currency_fraction_digits"] != new["currency_fraction_digits"]
        ):
            raise ValueError("Currency precision changed")
        actual = {field: new[field] - old[field] for field in FIELDS}
        expected = EXPECTED[journey].get(code, {})
        for field, found in actual.items():
            wanted = expected.get(field, 0)
            if found != wanted:
                raise ValueError(f"{code} {field} delta {found}; expected {wanted}")
        deltas[code] = actual
    return {"journey": journey, "passed": True, "deltas": deltas}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("capture")
    read.add_argument("phase", choices=("before", "after"))
    read.add_argument("--fixture", required=True)
    read.add_argument("--month", required=True)
    read.add_argument("--output", required=True)
    check = commands.add_parser("verify")
    check.add_argument("journey", choices=EXPECTED)
    check.add_argument("before")
    check.add_argument("after")
    args = parser.parse_args()
    try:
        result = (
            capture(args)
            if args.command == "capture"
            else verify(
                json.loads(Path(args.before).read_text()),
                json.loads(Path(args.after).read_text()),
                args.journey,
            )
        )
        print(json.dumps(result, indent=2))
    except ValueError as error:
        print(
            str(error) if not isinstance(error, json.JSONDecodeError) else "Invalid JSON",
            file=sys.stderr,
        )
        return 1
    except (KeyError, TypeError, IndexError, AttributeError, OSError, httpx.HTTPError):
        print(
            "Readback failed; input shape, local file, or network error", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Mock only (#2044): fill the mock-auth user's Business on a local stack with
synthetic purchases and sales, most with an RNC or a cédula.

Refuses any API that is not on 127.0.0.1. All values are made up.

    python scripts/qa/mock_2044_seed.py --api http://127.0.0.1:58800
"""

from __future__ import annotations

import argparse
import random
from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from argus.domain.business.contracts.dgii import PurchaseDeclaration, SalesDeclaration
from argus.domain.business.fiscal_identity import (
    cedula_check_digit_ok,
    rnc_check_digit_ok,
)
from faker import Faker
from loguru import logger

fake = Faker("es_ES")
FILER = "199990013"


def rnc() -> str:
    while True:
        digits = f"1{random.randint(0, 99_999_999):08d}"
        if rnc_check_digit_ok(digits):
            return digits


def cedula() -> str:
    while True:
        digits = f"{random.randint(1, 402):03d}{random.randint(0, 99_999_999):08d}"
        if cedula_check_digit_ok(digits):
            return digits


def known(values: dict) -> dict:
    return {key: {"state": "known", "value": value} for key, value in values.items()}


class Api:
    def __init__(self, base: str) -> None:
        self.client = httpx.Client(base_url=f"{base}/api/v1", timeout=60)

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        response = self.client.request(
            method, path, json=body, headers={"Idempotency-Key": str(uuid4())}
        )
        if response.status_code >= 300:
            raise RuntimeError(f"{method} {path} {response.status_code} {response.text[:800]}")
        return response.json() if response.content else {}


def record(api: Api, kind: str, account: str, day: str, index: int) -> None:
    identity = random.choice([rnc, rnc, rnc, cedula, None])
    taxpayer = identity() if identity else None
    name = fake.company() if kind == "expense" else fake.name()
    total = Decimal(random.choice([850, 2_360, 14_750, 118_000, 1_250_000])) + Decimal(
        random.randint(0, 99)
    ) / 100
    itbis = (total * Decimal("18") / Decimal("118")).quantize(Decimal("0.01"))
    draft = api.call("POST", "/business/captures", {"text": f"{name} {total}"})["draft_id"]
    version = api.call("GET", f"/business/drafts/{draft}/dossier")["version"]
    facts = {
        "kind": kind,
        "amount": str(total),
        "currency": "DOP",
        "occurred_on": day,
        "counterparty": name,
        "funding": {"kind": "owner_funds"}
        if kind == "expense"
        else {"kind": "business_account", "account_id": account},
        "business_share": {"kind": "all"},
    }
    fiscal = {
        "rnc": taxpayer,
        "ncf": f"B01{random.randint(1, 99_999_999):08d}",
        "itbis": str(itbis),
    }
    declaration = (
        {
            **{name: None for name in PurchaseDeclaration.model_fields},
            "form": "606",
            "actual_refund": False,
            "category_suggested": False,
        }
        if kind == "expense"
        else {
            **{name: None for name in SalesDeclaration.model_fields},
            "form": "607",
            "income_type": "1",
        }
    )
    dgii = {"fiscal": fiscal, "declaration": declaration}
    reviewed = api.call(
        "PATCH",
        f"/business/drafts/{draft}/review",
        {"version": version, "facts": known(facts), "dgii": dgii},
    )
    action = "record_expense" if kind == "expense" else "record_income"
    approved = api.call(
        "POST", f"/business/drafts/{draft}/approve", {"version": reviewed["version"], "action": action}
    )
    if kind == "expense" and index % 3:
        api.call(
            "PATCH",
            f"/business/drafts/{draft}/review",
            {
                "version": approved["version"],
                "purchase": {"category": random.choice(["02", "03", "09"]), "payment_method": "01"},
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:58800")
    parser.add_argument("--purchases", type=int, default=24)
    parser.add_argument("--sales", type=int, default=10)
    args = parser.parse_args()
    if urlparse(args.api).hostname != "127.0.0.1":
        raise SystemExit("local API only")
    api = Api(args.api)
    api.call("GET", "/me")
    spaces = api.call("GET", "/business/spaces")["spaces"]
    if not spaces:
        api.call("POST", "/business/space", {"name": "Ferretería Sintética"})
    profile = api.client.get("/business/fiscal-profile").json()
    if not profile.get("tax_id"):
        api.call(
            "PATCH",
            "/business/fiscal-profile",
            {
                "name": "Ferretería Sintética",
                "previous_name": "Ferretería Sintética",
                "tax_id": {"type": "rnc", "value": FILER},
                "previous_tax_id": None,
            },
        )
    account = api.call(
        "POST",
        "/business/accounts",
        {"nickname": "Operaciones", "type": "checking", "currency": "DOP"},
    )["id"]
    for index in range(args.purchases):
        record(api, "expense", account, f"2026-10-{1 + index % 28:02d}", index)
    for index in range(args.sales):
        record(api, "income", account, f"2026-10-{1 + index * 2 % 28:02d}", index)
    logger.info("seeded {} purchases and {} sales", args.purchases, args.sales)


if __name__ == "__main__":
    main()

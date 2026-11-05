"""Record which countries and products Plaid's institution directory reports.

Coverage evidence, kept separate from Sandbox lifecycle success: a working
Sandbox Item says nothing about whether a real bank is reachable. For every
country code Plaid's API accepts, plus the Dominican Republic (``DO``), it asks
``/institutions/get`` for the number of institutions supporting
``transactions``, and searches for the largest Dominican banks by name. Calls
are paced for Plaid's ``/institutions/get`` rate limit, with one bounded retry
after ``INSTITUTIONS_GET_LIMIT``. Only totals, Plaid error codes and matched
public institution names are recorded.

    PLAID_ENV=sandbox PLAID_CREDENTIALS_INJECTED=true \\
        python scripts/ingestion/plaid_institution_coverage.py
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argus.domain.ingestion.plaid.client import PlaidClient, PlaidError
from argus.domain.ingestion.plaid.config import (
    SUPPORTED_COUNTRY_CODES,
    plaid_config_from_env,
)
from loguru import logger

OUT = Path("docs/reports/evidence/ingestion-plaid/institution-coverage.json")
DOMINICAN = "DO"
DOMINICAN_BANKS = ("Banreservas", "Banco Popular Dominicano", "Banco BHD")


PACE_SECONDS = 7
LIMIT_BACKOFF_SECONDS = 65
RATE_LIMITED = "INSTITUTIONS_GET_LIMIT"


def _total(client: PlaidClient, country: str) -> tuple[Any, int]:
    body: dict[str, Any] = {
        "count": 1,
        "offset": 0,
        "country_codes": [country],
        "options": {"products": ["transactions"]},
    }
    for attempt in (1, 2):
        try:
            return client.post("/institutions/get", body).get("total"), attempt
        except PlaidError as exc:
            if exc.error_code != RATE_LIMITED or attempt == 2:
                return {"error_code": exc.error_code}, attempt
            time.sleep(LIMIT_BACKOFF_SECONDS)
    raise AssertionError("unreachable")


def run() -> dict[str, Any]:
    config = plaid_config_from_env()
    if not config.configured:
        raise SystemExit("Plaid credentials are not configured (see module doc).")
    client = PlaidClient(config)
    calls = 0
    countries: dict[str, Any] = {}
    for country in [DOMINICAN, *sorted(SUPPORTED_COUNTRY_CODES)]:
        total, used = _total(client, country)
        countries[country] = {"institutions_with_transactions": total}
        calls += used
        time.sleep(PACE_SECONDS)
    searches: dict[str, Any] = {}
    for name in DOMINICAN_BANKS:
        calls += 1
        try:
            found = client.post(
                "/institutions/search",
                {
                    "query": name,
                    "country_codes": sorted(SUPPORTED_COUNTRY_CODES),
                    "products": ["transactions"],
                },
            ).get("institutions", [])
            searches[name] = {
                "matches": len(found),
                "names": sorted({i.get("name", "") for i in found})[:10],
                "countries": sorted(
                    {c for i in found for c in i.get("country_codes", [])}
                ),
            }
        except PlaidError as exc:
            searches[name] = {"error_code": exc.error_code}
    calls += 1
    try:
        client.post(
            "/institutions/search",
            {"query": "Banreservas", "country_codes": [DOMINICAN]},
        )
        dominican_search: Any = "accepted"
    except PlaidError as exc:
        dominican_search = {"error_code": exc.error_code}
    client.close()
    return {
        "environment": config.environment,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_country_codes": sorted(SUPPORTED_COUNTRY_CODES),
        "countries": countries,
        "dominican_bank_search_in_supported_countries": searches,
        "dominican_country_code_search": dominican_search,
        "provider_calls_total": calls,
        "note": (
            "Directory metadata from the named environment only; Sandbox Items "
            "are synthetic and do not prove a real institution connects."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    summary = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    logger.info("Plaid institution coverage written", path=str(args.out))


if __name__ == "__main__":
    main()

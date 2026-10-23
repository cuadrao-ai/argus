"""One-shot staging preflight. A successful credential probe is not delivery proof."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from argus.domain.ingestion.whatsapp.config import load_whatsapp_settings
from argus.domain.ingestion.whatsapp.media import GRAPH_HOST, graph_error
from argus.domain.ingestion.whatsapp.payload import delivery_failure

MAX_RESPONSE_BYTES = 64 * 1024
MAX_EVENTS_BYTES = 1024 * 1024
_DELIVERY_FAILURE_LINE = re.compile(
    r"WhatsApp outbound delivery failed: code=(unknown|[0-9]{1,10}) reason=[a-z_]+$"
)


def probe_credential(
    client: httpx.Client, *, token: str, number_id: str, version: str
) -> dict[str, Any]:
    if not (number_id.isascii() and number_id.isdigit() and len(number_id) <= 64):
        return {"status": "unverified", "reason": "number_id_invalid"}
    started = time.monotonic()
    try:
        with client.stream(
            "GET",
            f"https://{GRAPH_HOST}/{version}/{number_id}",
            params={"fields": "id"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
            follow_redirects=False,
        ) as response:
            content = bytearray()
            for chunk in response.iter_bytes():
                if (
                    time.monotonic() - started > 10
                    or len(content) + len(chunk) > MAX_RESPONSE_BYTES
                ):
                    return {"status": "unverified", "reason": "response_limit"}
                content.extend(chunk)
            status = response.status_code
    except httpx.HTTPError:
        return {"status": "unverified", "reason": "transport"}
    safe_response = httpx.Response(status, content=bytes(content))
    if status == 200:
        try:
            payload = safe_response.json()
            matches = isinstance(payload, dict) and payload.get("id") == number_id
        except ValueError:
            matches = False
        return {
            "status": "authorized" if matches else "unverified",
            "reason": "number_access" if matches else "unexpected_response",
        }
    error = graph_error(safe_response)
    code, subcode = error.get("code"), error.get("error_subcode")
    if code == "190":
        reason = {"463": "expired", "464": "token_user_unconfirmed"}.get(
            subcode, "invalid_or_revoked"
        )
        result = {"status": "invalid", "reason": reason}
    elif status == 403 or code in ("10", "200"):
        result = {"status": "denied", "reason": "permission_denied"}
    else:
        result = {"status": "unverified", "reason": "number_access_unverified"}
    return {**result, "http_status": status, "graph_code": code, "graph_subcode": subcode}


def delivery_observation(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "unverified", "reason": "no_observation", "failures": []}
    try:
        with path.open("rb") as source:
            content = source.read(MAX_EVENTS_BYTES + 1)
        if len(content) > MAX_EVENTS_BYTES:
            raise ValueError
        failures = []
        callbacks = 0
        for line in content.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError
            record = record.get("record", record)
            if not isinstance(record, dict):
                raise ValueError
            extra = record.get("extra", {})
            if not isinstance(extra, dict):
                raise ValueError
            if extra.get("event") == "whatsapp_delivery_failed":
                failure = delivery_failure(extra.get("graph_code"))
                failures.append({"code": failure.code, "reason": failure.reason})
            else:
                message = record.get("message")
                found = (
                    _DELIVERY_FAILURE_LINE.search(message)
                    if isinstance(message, str)
                    else None
                )
                if found is not None:
                    failure = delivery_failure(found.group(1))
                    failures.append({"code": failure.code, "reason": failure.reason})
            if record.get("message") == "WhatsApp delivery verified":
                callbacks += 1
        return {
            "status": "failed" if failures else "unverified",
            "reason": "failed_delivery_observed" if failures else "no_delivery_proof",
            "callbacks": callbacks,
            "failures": failures,
        }
    except (OSError, ValueError, UnicodeError, RecursionError):
        return {"status": "unverified", "reason": "events_invalid", "failures": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe-credential",
        action="store_true",
        help="Make one read-only number-access GET in the approved staging runtime.",
    )
    parser.add_argument(
        "--events", type=Path, help="Operator-selected JSONL log window, at most 1 MiB."
    )
    args = parser.parse_args(argv)
    settings = load_whatsapp_settings()
    configured = settings.intake_ready
    credential = {"status": "not_checked", "reason": "probe_not_requested"}
    if args.probe_credential and configured:
        with httpx.Client(trust_env=False) as client:
            credential = probe_credential(
                client,
                token=settings.access_token.get_secret_value(),
                number_id=settings.phone_number_id,
                version=settings.graph_api_version,
            )
    delivery = delivery_observation(args.events)
    actions = []
    if not configured:
        actions.append("check_staging_intake_configuration")
    if credential["status"] in ("invalid", "denied"):
        actions.append("repair_staging_credential_then_repeat_preflight")
    if credential["status"] == "unverified":
        actions.append("inspect_number_access_without_sending")
    if delivery["status"] == "failed":
        actions.append("inspect_receipt_before_any_sender_resend")
    if delivery["reason"] == "events_invalid":
        actions.append("check_delivery_events_export")
    report = {
        "configuration": "configured" if configured else "blocked",
        "outbound_enabled": settings.outbound_enabled,
        "credential": credential,
        "delivery": delivery,
        "receipt_and_extraction": "unverified",
        "end_to_end": "unverified",
        "actions": actions,
    }
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 2 if actions else 0


if __name__ == "__main__":
    raise SystemExit(main())

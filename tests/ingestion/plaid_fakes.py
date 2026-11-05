"""Hermetic Plaid: a scripted provider behind ``httpx.MockTransport``.

Payloads are shaped like Plaid Sandbox responses (API 2020-09-14) recorded in
this lane, with synthetic ids. Nothing here reaches the network.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.plaid.config import PlaidConfig
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL, OwnerScope

NOW = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)
ACCESS_TOKEN = "access-sandbox-11111111-2222-3333-4444-555555555555"
ITEM_ID = "item-sandbox-aaaa"
PUBLIC_TOKEN = "public-sandbox-0000-1111"
CHECKING = {
    "account_id": "acc-checking",
    "mask": "0000",
    "name": "Plaid Checking",
    "official_name": "Plaid Gold Standard 0% Interest Checking",
    "type": "depository",
    "subtype": "checking",
    "balances": {"iso_currency_code": "USD", "unofficial_currency_code": None},
}
CARD = {
    "account_id": "acc-card",
    "mask": "3333",
    "name": "Plaid Credit Card",
    "official_name": None,
    "type": "credit",
    "subtype": "credit card",
    "balances": {"iso_currency_code": "USD", "unofficial_currency_code": None},
}


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now = self.now + timedelta(**delta)


class RecordingSink:
    """Idempotent by ``ImportCandidate.key`` plus fingerprint, like the real one."""

    def __init__(self) -> None:
        self.batches: list[list[ImportCandidate]] = []
        self.evidence: dict[tuple[str, str, str], ImportCandidate] = {}
        self.fail = False

    def submit(
        self,
        *,
        user_id: str,
        connection_id: str,
        candidates: Sequence[ImportCandidate],
        scope: OwnerScope,
    ) -> SubmitResult:
        assert scope == PERSONAL
        if self.fail:
            raise RuntimeError("sink unavailable")
        assert all(c.source.connection_id == connection_id for c in candidates)
        self.batches.append(list(candidates))
        recorded = unchanged = withdrawn = 0
        for candidate in candidates:
            known = self.evidence.get(candidate.key)
            if candidate.status == "removed":
                withdrawn += known is not None
            elif known is not None and known.fingerprint() == candidate.fingerprint():
                unchanged += 1
            else:
                recorded += 1
            self.evidence[candidate.key] = candidate
        return SubmitResult(recorded, unchanged, withdrawn)

    def forget_connection(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> int:
        assert scope == PERSONAL
        drop = [k for k in self.evidence if k[1] == connection_id]
        for key in drop:
            del self.evidence[key]
        return len(drop)


def txn(
    transaction_id: str,
    amount: float,
    *,
    pending: bool = False,
    pending_transaction_id: str | None = None,
    date: str = "2026-09-28",
    authorized_date: str | None = "2026-09-27",
    iso: str | None = "USD",
    unofficial: str | None = None,
    account_id: str = "acc-checking",
    merchant: str | None = "Blue Bottle Coffee",
    name: str = "BLUE BOTTLE COFFEE 123",
    primary: str | None = "FOOD_AND_DRINK",
    detailed: str | None = "FOOD_AND_DRINK_COFFEE",
) -> dict[str, Any]:
    return {
        "transaction_id": transaction_id,
        "account_id": account_id,
        "amount": amount,
        "iso_currency_code": iso,
        "unofficial_currency_code": unofficial,
        "date": date,
        "authorized_date": authorized_date,
        "authorized_datetime": None,
        "datetime": None,
        "pending": pending,
        "pending_transaction_id": pending_transaction_id,
        "merchant_name": merchant,
        "name": name,
        "payment_channel": "in store",
        "personal_finance_category": None
        if primary is None
        else {"primary": primary, "detailed": detailed, "confidence_level": "HIGH"},
    }


def page(
    *,
    added: Sequence[dict] = (),
    modified: Sequence[dict] = (),
    removed: Sequence[dict] = (),
    next_cursor: str = "cursor-1",
    has_more: bool = False,
    accounts: Sequence[dict] = (CHECKING, CARD),
    status: str = "HISTORICAL_UPDATE_COMPLETE",
) -> dict[str, Any]:
    return {
        "accounts": list(accounts),
        "added": list(added),
        "modified": list(modified),
        "removed": list(removed),
        "next_cursor": next_cursor,
        "has_more": has_more,
        "transactions_update_status": status,
        "request_id": "req-sync",
    }


def plaid_error(code: str, error_type: str = "ITEM_ERROR", status: int = 400) -> dict:
    return {
        "error": {
            "error_type": error_type,
            "error_code": code,
            "error_message": "synthetic",
            "display_message": None,
            "request_id": "req-err",
        },
        "status": status,
    }


@dataclass
class FakePlaid:
    """Scripted provider. ``sync`` maps a request cursor to a queue of replies:
    a page dict, or ``{"error": ..., "status": ...}``; the last reply repeats."""

    sync: dict[str | None, list[dict]] = field(default_factory=dict)
    errors: dict[str, list[dict]] = field(default_factory=dict)
    item_error: str | None = None
    jwk: dict[str, Any] | None = None
    accounts: list[dict[str, Any]] | None = None
    removed_items: set[str] = field(default_factory=set)
    calls: list[tuple[str, dict[str, Any], dict[str, str]]] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        path = request.url.path
        self.calls.append((path, body, dict(request.headers)))
        scripted = self.errors.get(path)
        if scripted:
            reply = scripted.pop(0) if len(scripted) > 1 else scripted[0]
            return httpx.Response(reply["status"], json=reply["error"])
        token = body.get("access_token")
        if token is not None and (token != ACCESS_TOKEN or ITEM_ID in self.removed_items):
            code = (
                "ITEM_NOT_FOUND"
                if ITEM_ID in self.removed_items
                else "INVALID_ACCESS_TOKEN"
            )
            return _err(plaid_error(code, "INVALID_INPUT"))
        return getattr(self, "_" + path.strip("/").replace("/", "_"))(body)

    def paths(self) -> list[str]:
        return [call[0] for call in self.calls]

    def _link_token_create(self, body: dict) -> httpx.Response:
        mode = "update" if "access_token" in body else "new"
        return httpx.Response(
            200,
            json={
                "link_token": f"link-sandbox-{mode}",
                "expiration": "2026-10-01T17:00:00Z",
                "request_id": "req-link",
            },
        )

    def _item_public_token_exchange(self, body: dict) -> httpx.Response:
        if body.get("public_token") != PUBLIC_TOKEN:
            return _err(plaid_error("INVALID_PUBLIC_TOKEN", "INVALID_INPUT"))
        return httpx.Response(
            200,
            json={"access_token": ACCESS_TOKEN, "item_id": ITEM_ID, "request_id": "r"},
        )

    def _item_get(self, body: dict) -> httpx.Response:
        error = None
        if self.item_error:
            error = plaid_error(self.item_error)["error"]
        return httpx.Response(
            200,
            json={
                "item": {
                    "item_id": ITEM_ID,
                    "institution_id": "ins_109508",
                    "error": error,
                },
                "request_id": "r",
            },
        )

    def _institutions_get_by_id(self, body: dict) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "institution": {
                    "institution_id": "ins_109508",
                    "name": "First Platypus Bank",
                },
                "request_id": "r",
            },
        )

    def _accounts_get(self, body: dict) -> httpx.Response:
        accounts = [CHECKING, CARD] if self.accounts is None else self.accounts
        return httpx.Response(200, json={"accounts": accounts, "request_id": "r"})

    def _transactions_sync(self, body: dict) -> httpx.Response:
        if self.item_error:
            return _err(plaid_error(self.item_error))
        queue = self.sync.get(body.get("cursor"))
        assert queue, f"unscripted sync cursor {body.get('cursor')!r}"
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if "error" in reply:
            return _err(reply)
        return httpx.Response(200, json=reply)

    def _item_remove(self, body: dict) -> httpx.Response:
        self.removed_items.add(ITEM_ID)
        return httpx.Response(200, json={"request_id": "r"})

    def _webhook_verification_key_get(self, body: dict) -> httpx.Response:
        if self.jwk is not None and body.get("key_id") == self.jwk["kid"]:
            return httpx.Response(200, json={"key": self.jwk, "request_id": "r"})
        return _err(plaid_error("INVALID_WEBHOOK_VERIFICATION_KEY_ID", "INVALID_INPUT"))


def _err(reply: dict) -> httpx.Response:
    return httpx.Response(reply["status"], json=reply["error"])


def make_connector(
    fake: FakePlaid,
    *,
    sink: RecordingSink | None = None,
    repo: Any = None,
    clock: Clock | None = None,
    config: PlaidConfig | None = None,
) -> PlaidConnector:
    hub = IngestionHub(
        repo or InMemoryConnectionRepository(),
        box=SecretBox(os.urandom(32)),
        sink=sink,
        clock=clock or Clock(),
    )
    connector = PlaidConnector(
        hub,
        config or PlaidConfig(client_id="client-id", secret="plaid-secret-value"),
        transport=httpx.MockTransport(fake),
    )
    connector.adapter.sleep = lambda seconds: None
    hub.register(connector.adapter)
    return connector

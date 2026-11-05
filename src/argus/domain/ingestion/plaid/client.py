"""Bounded HTTP client for the Plaid API (no SDK).

Every call is one JSON POST with a 30 second timeout, no redirects and no
automatic retries: the retry policy belongs to the caller (``sync``), where it
is bounded and visible. Failures become ``PlaidError`` carrying only Plaid's
error type and code, never the request body, so an access token cannot leak
through an exception message or a log line.
"""

from __future__ import annotations

from typing import Any

import httpx

from argus.domain.ingestion.plaid.config import API_VERSION, CLIENT_NAME, PlaidConfig

TIMEOUT_SECONDS = 30.0
UNREACHABLE = "PROVIDER_UNREACHABLE"
MALFORMED = "MALFORMED_RESPONSE"


class PlaidError(RuntimeError):
    def __init__(
        self, *, error_type: str, error_code: str, status: int | None = None
    ) -> None:
        super().__init__(f"plaid {error_type}/{error_code}")
        self.error_type = error_type
        self.error_code = error_code
        self.status = status


class PlaidClient:
    def __init__(
        self, config: PlaidConfig, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.config = config
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Plaid-Version": API_VERSION, **self.config.auth_headers()}
        try:
            response = self._http.post(path, json=body, headers=headers)
        except httpx.HTTPError:
            raise PlaidError(error_type="TRANSPORT", error_code=UNREACHABLE) from None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code != 200 or not isinstance(payload, dict):
            raise _error(response.status_code, payload)
        return payload

    def link_token_create(
        self,
        *,
        client_user_id: str,
        language: str,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "client_name": CLIENT_NAME,
            "language": language,
            "country_codes": list(self.config.country_codes),
            "user": {"client_user_id": client_user_id},
        }
        if access_token is None:
            body["products"] = ["transactions"]
        else:
            # Update mode: the Item is named server-side; no products are added.
            body["access_token"] = access_token
        if self.config.webhook_url:
            body["webhook"] = self.config.webhook_url
        return self.post("/link/token/create", body)

    def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        payload = self.post("/item/public_token/exchange", {"public_token": public_token})
        return _text(payload, "access_token"), _text(payload, "item_id")

    def item_get(self, access_token: str) -> dict[str, Any]:
        payload = self.post("/item/get", {"access_token": access_token})
        item = payload.get("item")
        if not isinstance(item, dict):
            raise PlaidError(error_type="API_ERROR", error_code=MALFORMED)
        return item

    def institution_name(self, institution_id: str) -> str | None:
        payload = self.post(
            "/institutions/get_by_id",
            {
                "institution_id": institution_id,
                "country_codes": list(self.config.country_codes),
            },
        )
        institution = payload.get("institution") or {}
        name = institution.get("name") if isinstance(institution, dict) else None
        return name if isinstance(name, str) and name.strip() else None

    def accounts_get(self, access_token: str) -> list[dict[str, Any]]:
        payload = self.post("/accounts/get", {"access_token": access_token})
        accounts = payload.get("accounts")
        return [a for a in accounts if isinstance(a, dict)] if accounts else []

    def transactions_sync(
        self, *, access_token: str, cursor: str | None, count: int
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"access_token": access_token, "count": count}
        if cursor:
            body["cursor"] = cursor
        return self.post("/transactions/sync", body)

    def item_remove(self, access_token: str) -> None:
        self.post("/item/remove", {"access_token": access_token})

    def webhook_verification_key(self, key_id: str) -> dict[str, Any]:
        payload = self.post("/webhook_verification_key/get", {"key_id": key_id})
        key = payload.get("key")
        if not isinstance(key, dict):
            raise PlaidError(error_type="API_ERROR", error_code=MALFORMED)
        return key


def is_transient(exc: PlaidError) -> bool:
    """Worth retrying later: unreachable, rate limited (429) or a Plaid 5xx."""

    status = exc.status or 0
    return (
        exc.error_code == UNREACHABLE
        or exc.error_type == "RATE_LIMIT_EXCEEDED"
        or status == 429
        or status >= 500
    )


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PlaidError(error_type="API_ERROR", error_code=MALFORMED)
    return value


def _error(status: int, payload: object) -> PlaidError:
    error_type = "API_ERROR"
    error_code = MALFORMED if status == 200 else f"HTTP_{status}"
    if isinstance(payload, dict):
        if isinstance(payload.get("error_type"), str):
            error_type = payload["error_type"]
        if isinstance(payload.get("error_code"), str):
            error_code = payload["error_code"]
    return PlaidError(error_type=error_type, error_code=error_code, status=status)

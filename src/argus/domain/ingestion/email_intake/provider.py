"""Bounded Resend receiving transport; message content never selects a tenant."""

from __future__ import annotations

import asyncio
import ipaddress
import json
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES
from argus.domain.ingestion.email_intake.budget import FetchBudget

RECEIVING_DEADLINE_SECONDS = 60
_AUTH_KEYS = ("spf", "dkim", "dmarc")


def _authentication(metadata: dict) -> dict | None:
    """The server's authentication object, or none when the message predates it."""

    raw = metadata.get("authentication", None)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError
    found = {}
    for key in _AUTH_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value or len(value) > 32:
            raise ValueError
        found[key] = value
    return found


class EmailProviderError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class ReceivedEmail:
    raw: bytes
    recipients: tuple[str, ...]
    authentication: dict | None = None


class ResendReceivingClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        allowed_download_hosts: tuple[str, ...],
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._hosts = frozenset(allowed_download_hosts)

    async def preview_from(self, email_id: str) -> str | None:
        """Sender address from provider metadata. This read is not metered."""

        try:
            if str(UUID(email_id)) != email_id:
                return None
        except (ValueError, AttributeError):
            return None
        try:
            payload = await self._get(self._metadata_url(email_id), authenticated=True)
            sender = json.loads(payload).get("from")
        except (EmailProviderError, ValueError, TypeError):
            return None
        if not isinstance(sender, str):
            return None
        address = parseaddr(sender)[1].strip().lower()
        return address or None

    async def raw_message(
        self, email_id: str, *, budget: FetchBudget | None = None
    ) -> ReceivedEmail:
        try:
            return await asyncio.wait_for(
                self._raw_message(email_id, budget), RECEIVING_DEADLINE_SECONDS
            )
        except asyncio.TimeoutError:
            raise EmailProviderError("provider_unavailable", retryable=True) from None

    async def _raw_message(
        self, email_id: str, budget: FetchBudget | None
    ) -> ReceivedEmail:
        try:
            if str(UUID(email_id)) != email_id:
                raise ValueError
        except (ValueError, AttributeError):
            raise EmailProviderError("invalid_email_id") from None
        metadata_bytes = await self._get(
            self._metadata_url(email_id), authenticated=True, budget=budget
        )
        try:
            metadata = json.loads(metadata_bytes)
            if metadata["id"] != email_id:
                raise ValueError
            recipients = metadata["to"]
            if not isinstance(recipients, list) or not recipients:
                raise ValueError
            if any(
                not isinstance(value, str) or not value or len(value) > 320
                for value in recipients
            ):
                raise ValueError
            url = metadata["raw"]["download_url"]
            if not isinstance(url, str):
                raise ValueError
            authentication = _authentication(metadata)
        except (ValueError, KeyError, TypeError):
            raise EmailProviderError("invalid_provider_metadata") from None
        self._validate_download(url)
        raw = await self._get(url, authenticated=False, budget=budget)
        if not raw:
            raise EmailProviderError("empty_email")
        return ReceivedEmail(
            raw=raw, recipients=tuple(recipients), authentication=authentication
        )

    def _metadata_url(self, email_id: str) -> str:
        return f"https://api.resend.com/emails/receiving/{email_id}?html_format=cid"

    def _validate_download(self, url: str) -> None:
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            if (
                parsed.scheme != "https"
                or not host
                or host not in self._hosts
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or parsed.fragment
                or host == "localhost"
                or host.endswith(".localhost")
            ):
                raise ValueError
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError
        except ValueError:
            raise EmailProviderError("unsafe_download_url") from None

    async def _get(
        self, url: str, *, authenticated: bool, budget: FetchBudget | None = None
    ) -> bytes:
        reservation = await budget.reserve() if budget is not None else None
        # Build Request directly so client defaults cannot leak credentials to signed URLs.
        headers = {"Accept-Encoding": "identity"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = httpx.Request(
            "GET",
            url,
            headers=headers,
            extensions={
                "timeout": {"connect": 10.0, "read": 30.0, "write": 10.0, "pool": 10.0}
            },
        )
        try:
            response = await self._client.send(
                request, stream=True, auth=None, follow_redirects=False
            )
            try:
                status = response.status_code
                if status != 200:
                    raise EmailProviderError(
                        "provider_unavailable"
                        if status in (408, 429) or status >= 500
                        else "provider_rejected",
                        retryable=status in (408, 429) or status >= 500,
                    )
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise EmailProviderError("encoded_provider_response")
                length = response.headers.get("content-length")
                if length is not None and (
                    not length.isdecimal() or int(length) > SOURCE_MAX_BYTES
                ):
                    raise EmailProviderError("provider_response_too_large")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > SOURCE_MAX_BYTES:
                        raise EmailProviderError("provider_response_too_large")
                    chunks.extend(chunk)
                if budget is not None:
                    await budget.settle(reservation, len(chunks))
                return bytes(chunks)
            finally:
                await response.aclose()
        except httpx.HTTPError:
            raise EmailProviderError("provider_unavailable", retryable=True) from None

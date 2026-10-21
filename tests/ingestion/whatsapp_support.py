"""Replay fixtures, signing, a scripted Graph API and a recording reply transport.

Nothing here opens a socket: Graph traffic goes through ``httpx.MockTransport``
and replies are appended to a list.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parents[1] / "fixtures" / "whatsapp"
DOCUMENT_FIXTURES = Path(__file__).parents[1] / "document_extraction_fixtures"
APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"
SENDER_KEY = "test-sender-key"
PHONE_NUMBER_ID = "100000000000001"
ALICE_PHONE = "15550101234"
BOB_PHONE = "15550105678"
STRANGER_PHONE = "15550109999"
RECEIPT_PNG = (DOCUMENT_FIXTURES / "receipt-dop.png").read_bytes()
RECEIPT_PDF = (DOCUMENT_FIXTURES / "statement-dop.pdf").read_bytes()

ENV = {
    "ARGUS_WHATSAPP_INTAKE_ENABLED": "true",
    "ARGUS_WHATSAPP_AGENT_ENABLED": "true",
    "ARGUS_WHATSAPP_VERIFY_TOKEN": VERIFY_TOKEN,
    "ARGUS_WHATSAPP_APP_SECRET": APP_SECRET,
    "ARGUS_WHATSAPP_ACCESS_TOKEN": "test-access-token",
    "ARGUS_WHATSAPP_SENDER_KEY": SENDER_KEY,
    "ARGUS_WHATSAPP_PHONE_NUMBER_ID": PHONE_NUMBER_ID,
    "ARGUS_WHATSAPP_DISPLAY_PHONE_NUMBER": "+1 555 000 9999",
    "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "true",
    "ARGUS_BUSINESS_PILOT_ENABLED": "true",
}


def fixture(name: str, **overrides: Any) -> dict[str, Any]:
    """A fixture body with the first message's fields replaced.

    ``text`` replaces a text body; any other keyword replaces that message key.
    """

    body = json.loads((FIXTURES / name).read_text())
    message = body["entry"][0]["changes"][0]["value"].get("messages", [{}])[0]
    for key, value in overrides.items():
        if key == "text":
            message["text"] = {"body": value}
        elif key == "sender":
            message["from"] = value
        else:
            message[key] = value
    return copy.deepcopy(body)


def encode(body: dict[str, Any], sent_at: datetime | None = None) -> bytes:
    """The raw body, with every message stamped ``sent_at`` (default: now)."""

    stamp = str(int((sent_at or datetime.now(timezone.utc)).timestamp()))
    body = copy.deepcopy(body)
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                message["timestamp"] = stamp
    return json.dumps(body).encode()


def sign(raw: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


@dataclass
class Media:
    content: bytes
    mime_type: str
    meta_status: int = 200
    download_status: int = 200
    host: str = "lookaside.fbsbx.com"
    content_length: str | None = None
    file_size: int | None = None
    url: str | None = None


@dataclass
class FakeGraph:
    """Answers ``GET /{version}/{media-id}`` and the CDN download it points to."""

    media: dict[str, Media] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-access-token"
        if request.url.host == "graph.facebook.com":
            media_id = request.url.path.rsplit("/", 1)[-1]
            item = self.media.get(media_id)
            if item is None or item.meta_status != 200:
                return httpx.Response(item.meta_status if item else 404)
            return httpx.Response(
                200,
                json={
                    "messaging_product": "whatsapp",
                    "url": item.url
                    or f"https://{item.host}/whatsapp_business/attachments/?mid={media_id}",
                    "mime_type": item.mime_type,
                    "sha256": hashlib.sha256(item.content).hexdigest(),
                    "file_size": item.file_size
                    if item.file_size is not None
                    else len(item.content),
                    "id": media_id,
                },
            )
        media_id = request.url.params["mid"]
        item = self.media[media_id]
        headers = (
            {"content-length": item.content_length}
            if item.content_length is not None
            else {}
        )
        if item.download_status != 200:
            return httpx.Response(item.download_status)
        return httpx.Response(200, content=item.content, headers=headers)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def hosts(self) -> set[str]:
        return {request.url.host for request in self.requests}


@dataclass
class RecordingTransport:
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    def bodies(self) -> list[str]:
        return [payload["text"]["body"] for payload in self.sent]


class RefusingExtractor:
    """Fails the test if anything tries to prepare a WhatsApp capture."""

    calls = 0

    async def extract(self, **_: Any):  # noqa: ANN201
        RefusingExtractor.calls += 1
        raise AssertionError("WhatsApp intake must never start AI preparation")

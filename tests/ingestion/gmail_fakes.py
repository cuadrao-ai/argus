"""Hermetic Google: an in-process OAuth server and Gmail API behind
``httpx.MockTransport``. Nothing here reaches the network; any request to a
host or path it does not model fails the test.

Shapes follow Google's documented responses (OAuth 2.0 token and revocation
endpoints, Gmail API v1 profile, messages, attachments and history). The
mailbox content is synthetic (``gmail_mailbox``).
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.gmail.config import SCOPE, GmailConfig
from argus.domain.ingestion.gmail.connector import GmailConnector
from argus.domain.ingestion.gmail.senders import (
    InMemorySenderRepository,
    normalize_senders,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL, OwnerScope

from tests.ingestion.gmail_mailbox import MAILBOX, NOW, Mail, b64

CLIENT_ID = "synthetic-client.apps.googleusercontent.test"
CLIENT_SECRET = "synthetic-client-secret-value"
REDIRECT = "https://app.example.test/settings/connections/gmail"
CONFIG = GmailConfig(
    client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT
)
GMAIL = "/gmail/v1/users/me"


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
        self.results: list[SubmitResult] = []
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
        recorded = unchanged = 0
        for candidate in candidates:
            known = self.evidence.get(candidate.key)
            if known is not None and known.fingerprint() == candidate.fingerprint():
                unchanged += 1
            else:
                recorded += 1
            self.evidence[candidate.key] = candidate
        result = SubmitResult(recorded, unchanged, 0)
        self.results.append(result)
        return result

    def forget_connection(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> int:
        assert scope == PERSONAL
        drop = [k for k in self.evidence if k[1] == connection_id]
        for key in drop:
            del self.evidence[key]
        return len(drop)


def google_error(status: int, reason: str, api_status: str = "") -> tuple[int, dict]:
    return status, {
        "error": {
            "code": status,
            "message": "synthetic",
            "errors": [{"reason": reason, "domain": "global"}],
            "status": api_status or reason.upper(),
        }
    }


@dataclass
class FakeGoogle:
    mails: list[Mail] = field(default_factory=list)
    email: str = MAILBOX
    clock: Clock = field(default_factory=Clock)
    history_id: int = 1000
    min_history_id: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    access: dict[str, str] = field(default_factory=dict)
    refresh_tokens: dict[str, str] = field(default_factory=dict)
    revoked: set[str] = field(default_factory=set)
    fail: dict[str, list[tuple[int, dict]]] = field(default_factory=dict)
    calls: list[tuple[str, str, dict[str, list[str]]]] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    # Per-item replies: (message id, "metadata"|"full"|"attachment") -> response.
    item_replies: dict[tuple[str, str], httpx.Response] = field(default_factory=dict)
    _serial: Any = field(default_factory=lambda: itertools.count(1))

    # Scripting ---------------------------------------------------------------

    def issue_code(
        self,
        authorization_url: str,
        *,
        scopes: Sequence[str] = (SCOPE,),
        refresh: bool = True,
        email: str | None = None,
        refresh_lifetime: int | None = None,
    ) -> tuple[str, str]:
        """What Google does after consent: a code tied to the PKCE challenge.
        Returns ``(code, state)`` as the browser would receive them."""

        query = parse_qs(urlsplit(authorization_url).query)
        code = f"4/synthetic-code-{next(self._serial)}"
        self.codes[code] = {
            "challenge": query["code_challenge"][0],
            "scopes": list(scopes),
            "refresh": refresh,
            "lifetime": refresh_lifetime,
            "email": email or self.email,
            "redirect_uri": query["redirect_uri"][0],
        }
        return code, query["state"][0]

    def deliver(self, mail: Mail, *, record: bool = True) -> None:
        self.mails.append(mail)
        self.history_id += 1
        if record:
            self.history.append(
                {
                    "id": str(self.history_id),
                    "messages": [{"id": mail.id, "threadId": f"t{mail.id}"}],
                    "messagesAdded": [
                        {
                            "message": {
                                "id": mail.id,
                                "threadId": f"t{mail.id}",
                                "labelIds": list(mail.labels),
                            }
                        }
                    ],
                }
            )

    def paths(self) -> list[str]:
        return [path for _, path, _ in self.calls]

    def count(self, suffix: str) -> int:
        return sum(1 for path in self.paths() if path.endswith(suffix))

    # Transport ---------------------------------------------------------------

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        query = parse_qs(url.query.decode())
        self.calls.append((request.method, url.path, query))
        if url.host == "oauth2.googleapis.com" and url.path == "/token":
            return self._token(parse_qs(request.content.decode()))
        if url.host == "oauth2.googleapis.com" and url.path == "/revoke":
            return self._revoke(parse_qs(request.content.decode()))
        if url.host != "gmail.googleapis.com" or not url.path.startswith(GMAIL):
            self.unexpected.append(str(url))
            raise AssertionError(f"unexpected request to {url.host}{url.path}")
        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if bearer not in self.access:
            return _json(*google_error(401, "authError", "UNAUTHENTICATED"))
        path = url.path[len(GMAIL) :]
        key = _route(path)
        scripted = self.fail.get(key)
        if scripted:
            return _json(*(scripted.pop(0) if len(scripted) > 1 else scripted[0]))
        if path == "/profile":
            return _json(
                200,
                {"emailAddress": self.access[bearer], "historyId": str(self.history_id),
                 "messagesTotal": len(self.mails), "threadsTotal": len(self.mails)},
            )  # fmt: skip
        if path == "/messages":
            return self._list(query)
        if path == "/history":
            return self._history(query)
        parts = path.strip("/").split("/")
        mail = next((m for m in self.mails if m.id == parts[1]), None)
        if mail is None:
            return _json(*google_error(404, "notFound", "NOT_FOUND"))
        if len(parts) == 2:
            return self._message(mail, query)
        if (mail.id, "attachment") in self.item_replies:
            return self.item_replies[(mail.id, "attachment")]
        part = mail.attachment_ids().get(parts[3])
        if part is None:
            return _json(*google_error(404, "notFound", "NOT_FOUND"))
        assert part.data is not None, "a part over the size cap was downloaded"
        return _json(200, {"size": len(part.data), "data": b64(part.data)})

    def _token(self, form: dict[str, list[str]]) -> httpx.Response:
        scripted = self.fail.get("token")
        if scripted:
            return _json(*(scripted.pop(0) if len(scripted) > 1 else scripted[0]))
        get = lambda key: (form.get(key) or [""])[0]  # noqa: E731
        if get("client_id") != CLIENT_ID or get("client_secret") != CLIENT_SECRET:
            return _json(401, {"error": "invalid_client"})
        if get("grant_type") == "authorization_code":
            issued = self.codes.pop(get("code"), None)
            verifier = get("code_verifier")
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            if (
                issued is None
                or issued["challenge"] != challenge
                or issued["redirect_uri"] != get("redirect_uri")
            ):
                return _json(
                    400, {"error": "invalid_grant", "error_description": "Bad Request"}
                )
            access = self._mint(issued["email"])
            body = {"access_token": access, "expires_in": 3599, "token_type": "Bearer",
                    "scope": " ".join(issued["scopes"])}  # fmt: skip
            if issued["refresh"]:
                refresh = f"1//synthetic-refresh-{next(self._serial)}"
                self.refresh_tokens[refresh] = issued["email"]
                body["refresh_token"] = refresh
                if issued["lifetime"] is not None:
                    body["refresh_token_expires_in"] = issued["lifetime"]
            return _json(200, body)
        if get("grant_type") == "refresh_token":
            refresh = get("refresh_token")
            if refresh in self.revoked or refresh not in self.refresh_tokens:
                return _json(400, {"error": "invalid_grant",
                                   "error_description": "Token has been expired or revoked."})  # fmt: skip
            return _json(200, {"access_token": self._mint(self.refresh_tokens[refresh]),
                               "expires_in": 3599, "token_type": "Bearer", "scope": SCOPE})  # fmt: skip
        return _json(400, {"error": "unsupported_grant_type"})

    def _revoke(self, form: dict[str, list[str]]) -> httpx.Response:
        scripted = self.fail.get("revoke")
        if scripted:
            return _json(*(scripted.pop(0) if len(scripted) > 1 else scripted[0]))
        token = (form.get("token") or [""])[0]
        if token not in self.refresh_tokens and token not in self.access:
            return _json(400, {"error": "invalid_token"})
        self.revoked.add(token)
        email = self.refresh_tokens.get(token) or self.access.get(token)
        # Google revokes the whole grant.
        self.revoked.update(t for t, e in self.refresh_tokens.items() if e == email)
        for access in [a for a, e in self.access.items() if e == email]:
            del self.access[access]
        return httpx.Response(200)

    def _mint(self, email: str) -> str:
        token = f"ya29.synthetic-access-{next(self._serial)}"
        self.access[token] = email
        return token

    def _visible(self, query: str) -> list[Mail]:
        days = re.search(r"newer_than:(\d+)d", query)
        cutoff = NOW - timedelta(days=int(days.group(1))) if days else None
        senders = re.search(r"from:\(([^)]*)\)", query)
        tokens = senders.group(1).split(" OR ") if senders else None
        found = []
        for mail in self.mails:
            if {"SPAM", "TRASH"} & set(mail.labels):
                continue
            if "-in:sent" in query and "SENT" in mail.labels:
                continue
            if cutoff and NOW - timedelta(days=mail.days_ago) < cutoff:
                continue
            # Gmail's from: is a loose match; the connector re-checks strictly.
            if tokens is not None and not any(t in mail.address for t in tokens):
                continue
            found.append(mail)
        return sorted(found, key=lambda m: -m.internal_ms)

    def _list(self, query: dict[str, list[str]]) -> httpx.Response:
        mails = self._visible(query.get("q", [""])[0])
        size = int(query.get("maxResults", ["100"])[0])
        start = int(query.get("pageToken", ["0"])[0])
        page = mails[start : start + size]
        body: dict[str, Any] = {"resultSizeEstimate": len(mails)}
        if page:
            body["messages"] = [{"id": m.id, "threadId": f"t{m.id}"} for m in page]
        if start + size < len(mails):
            body["nextPageToken"] = str(start + size)
        return _json(200, body)

    def _message(self, mail: Mail, query: dict[str, list[str]]) -> httpx.Response:
        fmt = query.get("format", ["full"])[0]
        if (mail.id, fmt) in self.item_replies:
            return self.item_replies[(mail.id, fmt)]
        full = mail.full(self.history_id)
        if query.get("format", ["full"])[0] == "metadata":
            wanted = {h.lower() for h in query.get("metadataHeaders", [])}
            headers = [
                h for h in full["payload"]["headers"] if h["name"].lower() in wanted
            ]
            full["payload"] = {"mimeType": "multipart/mixed", "headers": headers}
        return _json(200, full)

    def _history(self, query: dict[str, list[str]]) -> httpx.Response:
        start = int(query["startHistoryId"][0])
        if start < self.min_history_id:
            return _json(*google_error(404, "notFound", "NOT_FOUND"))
        records = [r for r in self.history if int(r["id"]) > start]
        size = int(query.get("maxResults", ["100"])[0])
        offset = int(query.get("pageToken", ["0"])[0])
        body: dict[str, Any] = {"historyId": str(self.history_id)}
        if records[offset : offset + size]:
            body["history"] = records[offset : offset + size]
        if offset + size < len(records):
            body["nextPageToken"] = str(offset + size)
        return _json(200, body)


def _route(path: str) -> str:
    if path in ("/profile", "/messages", "/history"):
        return path.strip("/")
    return "attachment" if "/attachments/" in path else "message"


def _json(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})  # fmt: skip


def make_connector(
    fake: FakeGoogle,
    *,
    sink: RecordingSink | None = None,
    repo: Any = None,
    senders: Any = None,
    clock: Clock | None = None,
    config: GmailConfig = CONFIG,
    sleeps: list[float] | None = None,
) -> GmailConnector:
    hub = IngestionHub(
        repo or InMemoryConnectionRepository(),
        box=SecretBox(os.urandom(32)),
        sink=sink,
        clock=clock or fake.clock,
    )
    recorded = sleeps if sleeps is not None else []
    connector = GmailConnector(
        hub,
        config,
        senders=senders or InMemorySenderRepository(),
        transport=httpx.MockTransport(fake),
        sleep=recorded.append,
    )
    hub.register(connector.adapter)
    return connector


def connect(
    connector: GmailConnector,
    fake: FakeGoogle,
    user_id: str,
    senders: Sequence[str] | None = ("banco-ejemplo.test", "alerts@card-example.test"),
    **issue: Any,
):
    started = connector.oauth.authorize(user_id=user_id)
    code, state = fake.issue_code(started.authorization_url, **issue)
    return connector.oauth.callback(
        user_id=user_id,
        code=code,
        state=state,
        senders=None if senders is None else normalize_senders(list(senders)),
    )

"""Run the signed WhatsApp walkthrough on a disposable, local Supabase stack.

From the repo root: poetry run python scripts/qa/whatsapp_walkthrough.py
Set ARGUS_DISPOSABLE_DATABASE_URL and ARGUS_LOCAL_SUPABASE_{URL,ANON_KEY,
SERVICE_ROLE_KEY} from that stack. Use its own non-default port block.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import httpx
from argus.domain.ingestion.whatsapp.media import DOWNLOAD_HOSTS, GRAPH_HOST
from PIL import Image, ImageDraw


def local_targets() -> tuple[str, str]:
    dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "")
    api = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "")
    db, storage = urlsplit(dsn), urlsplit(api)
    if (
        db.scheme not in {"postgres", "postgresql"}
        or storage.scheme != "http"
        or db.hostname not in {"localhost", "127.0.0.1", "::1"}
        or storage.hostname != db.hostname
        or not db.port
        or (5432 == db.port or 54320 <= db.port <= 54339)
        or storage.port != db.port - 1
        or db.query
        or db.fragment
        or storage.query
        or storage.fragment
        or storage.username
        or storage.password
        or storage.path.rstrip("/")
        or os.getenv("PGHOSTADDR")
        or os.getenv("PGSERVICE")
    ):
        raise ValueError(
            "Set both URLs to the same disposable loopback stack on a dedicated port block."
        )
    if not all(
        os.getenv("ARGUS_LOCAL_SUPABASE_" + key)
        for key in ("ANON_KEY", "SERVICE_ROLE_KEY")
    ):
        raise ValueError("Set the local stack's anon and service-role keys.")
    return dsn, api


@dataclass(frozen=True)
class Receipt:
    name: str
    issuer: str
    buyer: str | None

    def png(self) -> bytes:
        image = Image.new("RGB", (500, 240), color="white")
        ImageDraw.Draw(image).multiline_text(
            (20, 20),
            f"{self.name}\nEmisor: {self.issuer}\nComprador: {self.buyer or ''}\nDOP 250.50",
            fill="black",
            spacing=10,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class ToLocalMedia(httpx.AsyncHTTPTransport):
    """Only the two hosts used by these fixtures may reach the loopback server."""

    def __init__(self, port: int) -> None:
        super().__init__(trust_env=False)
        self.port = port

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.host not in {
            GRAPH_HOST,
            *DOWNLOAD_HOSTS,
        }:
            raise AssertionError("Unexpected media destination")
        request.url = request.url.copy_with(
            scheme="http", host="127.0.0.1", port=self.port
        )
        return await super().handle_async_request(request)


@contextmanager
def media_server(
    media: dict[str, bytes], downloads: list[str], replies: list[str]
) -> Iterator[ToLocalMedia]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(self, payload: bytes, mime: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            key = self.path.rsplit("/", 1)[-1]
            if (
                self.headers.get("Authorization") != "Bearer test-access-token"
                or key not in media
            ):
                self.send_error(403)
                return
            content = media[key]
            if self.path.startswith("/files/"):
                downloads.append(key)
                self.respond(content, "image/png")
            else:
                host = next(iter(DOWNLOAD_HOSTS))
                self.respond(
                    json.dumps(
                        {
                            "url": f"https://{host}/files/{key}",
                            "mime_type": "image/png",
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "file_size": len(content),
                        }
                    ).encode(),
                    "application/json",
                )

        def do_POST(self) -> None:
            if (
                not self.path.endswith("/messages")
                or self.headers.get("Authorization") != "Bearer test-access-token"
            ):
                self.send_error(403)
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            replies.append(body["text"]["body"])
            self.respond(b'{"messages":[{"id":"wamid.LOCAL"}]}', "application/json")

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield ToLocalMedia(server.server_port)
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    import sys

    import pytest

    try:
        local_targets()
    except ValueError as error:
        sys.exit(str(error))
    root = Path(__file__).resolve().parents[2]

    class Evidence:
        def pytest_terminal_summary(self, terminalreporter):
            for report in terminalreporter.stats.get("passed", ()):
                for key, line in report.user_properties:
                    if key == "walkthrough":
                        terminalreporter.write_line(line)

    sys.exit(
        pytest.main(
            [
                "-o",
                "addopts=",
                "-q",
                "--tb=short",
                "--no-cov",
                str(root / "tests/test_whatsapp_walkthrough_postgres.py"),
            ],
            plugins=[Evidence()],
        )
    )

"""Fixed sandbox transport. Private credentials enter curl on stdin only."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import shutil
import socket
from typing import Any
from urllib.parse import unquote, urlsplit

from .config import API_ORIGIN, Settings
from .contracts import Case, Observation

STORAGE_HOST = "api-alanube-e-provider-dom-sand.s3.us-east-1.amazonaws.com"
_MAX = 8 * 1024 * 1024


class ProviderError(RuntimeError):
    def __init__(self, code: str = "transport_uncertain") -> None:
        super().__init__(code)
        self.code = code


def _quote(value: str) -> str:
    if any(ord(c) < 32 for c in value):
        raise ProviderError("invalid_transport_value")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


async def curl(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    resolve: str | None = None,
) -> tuple[bytes, str]:
    lines = [
        "silent",
        "show-error",
        "request = " + _quote(method),
        "url = " + _quote(url),
        'proto = "=https"',
        'proto-redir = "=https"',
        "max-redirs = 0",
        "retry = 0",
        "connect-timeout = 5",
        "max-time = 15",
        f"max-filesize = {_MAX}",
        'write-out = "\\n%{http_code}\\n%{content_type}"',
        'noproxy = "*"',
    ]
    if token:
        lines.append("header = " + _quote("Authorization: Bearer " + token))
    if payload is not None:
        lines += [
            'header = "Content-Type: application/json"',
            "data-binary = " + _quote(json.dumps(payload, separators=(",", ":"))),
        ]
    if resolve:
        lines.append("resolve = " + _quote(resolve))
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/curl",
        "-q",
        "--config",
        "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(("\n".join(lines) + "\n").encode())
        await process.stdin.drain()
        process.stdin.close()

        async def read_output() -> bytes:
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = await process.stdout.read(65536)
                if not chunk:
                    return b"".join(chunks)
                size += len(chunk)
                if size > _MAX + 1024:
                    raise ProviderError("response_too_large")
                chunks.append(chunk)

        output = await asyncio.wait_for(read_output(), timeout=18)
        await asyncio.wait_for(process.wait(), timeout=2)
        if process.returncode:
            raise ProviderError()
        body, status, content_type = output.rsplit(b"\n", 2)
        if len(body) > _MAX:
            raise ProviderError("response_too_large")
        if not status.isdigit() or not 200 <= int(status) < 300:
            raise ProviderError("http_uncertain")
        return body, content_type.decode("ascii", errors="replace").split(";")[0]
    except (ValueError, asyncio.TimeoutError, BrokenPipeError):
        raise ProviderError() from None
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


def observation(raw: bytes, source: str) -> Observation:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        data = {
            k: value[k]
            for k in (
                "id",
                "companyIdentification",
                "status",
                "legalStatus",
                "xml",
                "pdf",
            )
            if k in value
        }
        number = value.get("documentNumber", value.get("encf"))
        # Retain diagnostic codes and a body digest; no arbitrary messages/URLs.
        error = value.get("error") or value.get("governmentResponse") or {}
        code = error.get("code") if isinstance(error, dict) else None
        if code is not None and not re.fullmatch(
            r"(?:[0-9]{1,6}|AEP[0-9]{4})", str(code)
        ):
            code = "provider_diagnostic"
        return Observation(
            source=source,
            provider_id=data.get("id"),
            issuer=data.get("companyIdentification"),
            number=number,
            processing=data.get("status") or "unreported",
            legal=data.get("legalStatus") or "unreported",
            xml="available"
            if isinstance(data.get("xml"), str) and data["xml"].startswith("https://")
            else "unreported",
            pdf="available"
            if isinstance(data.get("pdf"), str) and data["pdf"].startswith("https://")
            else "unreported",
            xml_url=data.get("xml")
            if isinstance(data.get("xml"), str) and data["xml"].startswith("https://")
            else None,
            pdf_url=data.get("pdf")
            if isinstance(data.get("pdf"), str) and data["pdf"].startswith("https://")
            else None,
            code=str(code) if code is not None else None,
            evidence_digest=hashlib.sha256(raw).hexdigest(),
        )
    except (ValueError, TypeError):
        raise ProviderError("invalid_provider_response") from None


class Provider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _path(case: Case) -> str:
        return "/fiscal-invoices" if case.kind == "E31" else "/invoices"

    async def create(self, case: Case) -> Observation:
        raw, _ = await curl(
            "POST",
            API_ORIGIN + self._path(case),
            token=self.settings.api_token.get_secret_value(),
            payload=case.payload,
        )
        event = observation(raw, "response")
        if not event.provider_id:
            raise ProviderError("identity_missing")
        return event

    async def status(self, case: Case, provider_id: str) -> Observation:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", provider_id):
            raise ProviderError("invalid_provider_id")
        raw, _ = await curl(
            "GET",
            API_ORIGIN + self._path(case) + "/" + provider_id,
            token=self.settings.api_token.get_secret_value(),
        )
        return observation(raw, "poll")

    async def artifact(self, case: Case, provider_id: str, kind: str, url: str) -> bytes:
        target = urlsplit(url)
        path = unquote(target.path)
        section = "fiscalInvoice" if case.kind == "E31" else "invoice"
        pattern = (
            r"/users/[0-9a-fA-F-]{36}/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/"
            + section
            + ("/pdf/" if kind == "pdf" else "/")
            + r"[^/]+\."
            + kind
        )
        if (
            target.scheme != "https"
            or target.hostname != STORAGE_HOST
            or self.settings.storage_host != STORAGE_HOST
            or target.port not in (None, 443)
            or target.username
            or target.password
            or target.fragment
            or self.settings.storage_path_prefix != "/users/"
            or not re.fullmatch(pattern, path)
            or provider_id not in path.rsplit("/", 1)[-1]
            or ".." in path
            or any(ord(c) < 32 for c in url)
        ):
            raise ProviderError("artifact_destination_denied")
        addresses = await asyncio.get_running_loop().getaddrinfo(
            target.hostname, 443, type=socket.SOCK_STREAM
        )
        hosts = sorted({a[4][0] for a in addresses})
        if not hosts or any(not ipaddress.ip_address(host).is_global for host in hosts):
            raise ProviderError("artifact_destination_denied")
        address = hosts[0]
        pinned = "[" + address + "]" if ":" in address else address
        raw, media_type = await curl("GET", url, resolve=f"{STORAGE_HOST}:443:{pinned}")
        if kind == "pdf":
            if (
                media_type not in ("application/pdf", "application/octet-stream")
                or not raw.startswith(b"%PDF-")
                or b"%%EOF" not in raw[-1024:]
            ):
                raise ProviderError("artifact_invalid")
            executable = shutil.which("pdfinfo")
            if executable is None:
                raise ProviderError("artifact_parser_unavailable")
            parser = await asyncio.create_subprocess_exec(
                executable,
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(parser.communicate(raw), timeout=5)
                if parser.returncode:
                    raise ProviderError("artifact_invalid")
            finally:
                if parser.returncode is None:
                    parser.kill()
                await parser.wait()
        else:
            from lxml import etree

            try:
                if media_type not in (
                    "application/xml",
                    "text/xml",
                    "application/octet-stream",
                ):
                    raise ValueError
                document = etree.fromstring(
                    raw,
                    parser=etree.XMLParser(
                        resolve_entities=False, no_network=True, load_dtd=False
                    ),
                )
                if (
                    document.getroottree().docinfo.doctype
                    or document.tag.rsplit("}", 1)[-1] != "ECF"
                ):
                    raise ValueError
                for parent, leaf, expected in (
                    ("IdDoc", "eNCF", case.number),
                    ("Emisor", "RNCEmisor", case.issuer),
                ):
                    nodes = document.xpath(
                        "./*[local-name()='Encabezado']/*[local-name()='"
                        + parent
                        + "']/*[local-name()='"
                        + leaf
                        + "']"
                    )
                    if len(nodes) != 1 or len(nodes[0]) or nodes[0].text != expected:
                        raise ValueError
            except Exception:
                raise ProviderError("artifact_invalid") from None
        if case.invoice_revision_id is not None:
            from argus.domain.business.invoicing.artifacts import verify_pdf, verify_xml

            try:
                if kind == "pdf":
                    await verify_pdf(raw, case)
                else:
                    verify_xml(document, case)
            except Exception:
                raise ProviderError("artifact_invoice_mismatch") from None
        return raw

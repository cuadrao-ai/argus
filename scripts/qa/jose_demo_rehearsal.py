"""Rehearse José's five acceptance cases, or seed them ready to demo.

``run --mode rehearse`` drives the five cases (standing order 29) through the
product API on saved data and prints PASS/FAIL/UNTESTED per step:

  2  informal cash purchase from a note: no RNC/NCF/ITBIS, informal receipt,
     settled in month close as pagado efectivo
  3  personal purchase (03-farmacia): marked personal, kept out of business
     totals and the accountant handoff, original kept
  1  fiscal receipt (02-ferreteria) over a signed WhatsApp webhook: read,
     corrected, approved, reloaded; then the same bytes again (replay)
  4  statement imported, the existing matcher's suggestion confirmed: no new
     expense, settlement pagado, payables down
  5  October export ZIP opened and compared with the saved records; the 606
     is never filing-ready

``run --mode seed`` puts cases 2-5 in their ready-to-demo state and stops
before the action the presenter performs live. Case 1 is not seeded. Seeding
is idempotent: it looks for its own synthetic records (names carry "Ensayo",
files are the numbered pack, keys start with ``jose-seed-v1``) before it
writes, so a rerun creates nothing. ``--dry-run`` (rehearse and seed) only
reads and prints the planned writes; the client refuses any write while it is
on. Seed always requires ``--expect-business <id prefix>`` and refuses any
other Business. It saves ``--business-name`` only when the server reports
``name_required``, and turns receipt reading on only with ``--enable-reading``
(otherwise it stops when reading is off).

``--profile alive`` adds Aug-Oct 2026 synthetic history after the demo states
(``ALIVE_ROWS``): notes entered by hand and approved (DOP, a few USD, no fiscal
fact), one personal purchase, cash settled in month close, a statement whose
matches are confirmed and bank charges marked, open notes, four pack uploads
(07 approved, 04 to review, 08 and 13 needing attention), and, when the API has
invoicing on, customers and incomplete drafts that are never prepared or
issued. Markers ``(ensayo A01)`` and ``jose-seed-alive-v1-*`` keys make a rerun
write nothing. Each model read the seed causes, including the unread backlog
that turning reading on reads, is counted at ``--read-cost-ceiling``; the seed
refuses past $0.75 (``--spent-usd``, ``--reserve-reads``). One export call.

Evidence: ``<evidence>/steps/<case>-<step>.json``, ``summary.json``, ``calls.json``
(method, path, status, request id; never bodies of secrets) and ``screens/``
at 1440 px. Nothing secret is written.

Local (disposable Supabase stack; never ports 54332/58432/4390)::

    # API at the tip with two local-only seams: a stub reader that returns what
    # the pack files print, and a scripted Meta media host. --extractor real
    # keeps the product's model reader (one read, about a cent).
    python scripts/qa/jose_demo_rehearsal.py serve-api --env-file <api.env> --port 57741 \\
        --outbound-log <replies.jsonl>
    # web: bun run build --webpack && bun run start -p 57742 (staging flags)
    python scripts/qa/jose_demo_rehearsal.py run --target local \\
        --api http://127.0.0.1:57741 --web http://127.0.0.1:57742 \\
        --env-file <api.env> --outbound-log <replies.jsonl> --evidence <dir>
    python scripts/qa/jose_demo_rehearsal.py run --target local --mode seed \\
        --env-file <api.env> --local-account <file> --expect-business <prefix> ...

On local, ``run`` creates a fresh synthetic owner and Business unless
``--local-account`` names a JSON file holding one; ``env-file`` must point at a
loopback Supabase.

Staging (only after Lucas approves the milestone deploy and the seed)::

    python scripts/qa/jose_demo_rehearsal.py run --target staging --mode seed \\
        --api https://cuadrao-api-staging.onrender.com \\
        --web https://cuadrao-web-staging.onrender.com \\
        --account qa-owner-tester --expect-business b65130e8 --evidence <dir>

Staging refuses any ``--api``/``--web`` host that is not an https
``<service>-staging.onrender.com`` and always needs ``--expect-business``
(seed and rehearse alike).

The account file (``--accounts-file``, default ``temp/staging-walk-accounts.json``
in the main checkout, ``{"<entry>": {"<email>": "<password>"}}``) is read only inside this process; sign-in goes through the
web login headless and the session token stays in memory. On staging the script
never signs a webhook: case 1 waits ``--whatsapp-wait`` seconds for a document
from the linked phone, else it is UNTESTED.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
import traceback
import zipfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[2]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
PERIOD = ("2026-10-01", "2026-10-31")
MONTH = "2026-10"

# Synthetic pack: numbered files from cuadrao-test-receipts/LEEME.txt only.
PACK = {
    "R": (
        "02-ferreteria-recibo.jpg",
        "image/jpeg",
        "a1106fb14c2d7fb48b1ec513582917ac1952ff33568c8290d6e0e61f05076cff",
    ),
    "P": (
        "03-farmacia-recibo.png",
        "image/png",
        "6f34e9aefacdbf260b679619314156150f366a1bb352e863454bacaf8a95a85d",
    ),
    "C": (
        "01-colmado-recibo.png",
        "image/png",
        "68d74726c786a245155f3ed5c672e229f318c542b4c37ebcbfe607bf56012eba",
    ),
}
# What each pack file prints. The local stub reader answers these; checks expect them.
PRINTED = {
    "R": {
        "merchant": "FERRETERÍA EL TORNILLO",
        "occurred_on": "2026-10-10",
        "subtotal": "2395.00",
        "itbis": "431.10",
        "total": "2826.10",
        "rnc": "1-23-45678-9",
        "ncf": "B0100000456",
    },
    "P": {
        "merchant": "FARMACIA SAN RAFAEL",
        "occurred_on": "2026-10-09",
        "subtotal": "465.00",
        "itbis": "83.70",
        "total": "548.70",
        "rnc": "1-23-45678-9",
        "ncf": "B0100000789",
    },
    "C": {
        "merchant": "COLMADO LA ESQUINA",
        "occurred_on": "2026-10-11",
        "subtotal": "607.50",
        "itbis": "109.35",
        "total": "716.85",
        "rnc": "1-23-45678-9",
        "ncf": "B0100000123",
    },
}
STATEMENT = (
    "date,name,amount,iso_currency_code,pending\n"
    "2026-10-10,FERRETERÍA EL TORNILLO,-2826.10,DOP,false\n"
    "2026-10-09,SUPERMERCADO ENSAYO DEMO,-1985.50,DOP,false\n"
    "2026-10-12,DEPOSITO ENSAYO DEMO,4200.00,DOP,false\n"
).encode()
STATEMENT_SHA256 = "fd9acf03942d7bc9371d598a2821b0052894d76f62c52899dfa9f82a13114f30"
# Seed statement: S plus the line of the already-recorded 01-colmado expense.
SEED_STATEMENT = STATEMENT + b"2026-10-11,COLMADO LA ESQUINA,-716.85,DOP,false\n"

CASE2_NOTE = (
    "Compra en efectivo en Colmado Ensayo Demo, RD$ 450.00, 27/10/2026, sin comprobante."
)
CASE2_FACTS = {
    "amount": "450.00",
    "occurred_on": "2026-10-27",
    "counterparty": "Colmado Ensayo Demo",
}
SEED_INFORMAL_NOTE = "Compra en efectivo en Colmado Ensayo Demo (registrada), RD$ 365.80, 20/10/2026, sin comprobante."
SEED_INFORMAL_FACTS = {
    "amount": "365.80",
    "occurred_on": "2026-10-20",
    "counterparty": "Colmado Ensayo Demo (registrada)",
}
ACCOUNT = {"nickname": "Cuenta Ensayo DOP", "type": "checking", "currency": "DOP"}

READ_ONLY_POSTS = ("/api/v1/business/reports/query",)
DUPLICATE_REPLY = ("Ya lo teníamos", "We already had this one")

PLANNED_WRITES = {
    "0": [
        "POST /business/receipt-reading (only when reading is off)",
        "POST /business/accounts (only when there is no DOP checking account)",
    ],
    "2": [
        "POST /business/captures (the cash note)",
        "PATCH /business/drafts/{id}/review (informal receipt, owner funds)",
        "POST /business/drafts/{id}/approve",
        "PATCH /business/month-close/documents/{activity} (pagado, efectivo)",
    ],
    "3": [
        "POST /business/receipts (03-farmacia-recibo.png)",
        "POST /business/drafts/{id}/personal",
        "PATCH /business/drafts/{id}/review",
        "POST /business/drafts/{id}/approve",
    ],
    "1": [
        "staging: none until the phone's document arrives; local: signed webhooks",
        "PATCH /business/drafts/{id}/review (funding, business share)",
        "POST /business/drafts/{id}/approve",
    ],
    "4": [
        "POST /business/bank/imports (the statement, sent twice with one key)",
        "POST /business/bank/suggestions/{id}/confirm (sent twice with one key)",
    ],
    "5": ["none: one GET /business/exports, skipped under --dry-run"],
}

FIX_1417 = "merge #1417 (personal separation): personal rows leave Registros totals, records.csv and the 606; personal.csv carries them"


def outbound_replies(log: Path) -> list[str]:
    """The reply texts serve-api's scripted Meta host recorded, oldest first."""

    if not log.exists():
        return []
    return [json.loads(line)["text"] for line in log.read_text().splitlines() if line]


def media_id(digest: str, attempt: int) -> str:
    """Graph media ids are digits; a resend gets a new id for the same bytes."""

    return f"{int(digest[:12], 16)}{attempt:02d}"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def require_loopback(url: str, what: str) -> None:
    if urlsplit(url.replace("postgresql://", "http://", 1)).hostname not in LOOPBACK:
        raise SystemExit(f"refusing: {what} is not a loopback address")


def require_staging_host(url: str, what: str) -> None:
    """Staging runs write real rows: only the staging services, over https."""

    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:
        port = -1
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or port not in (None, 443)
        or not host.endswith("-staging.onrender.com")
        or host == "-staging.onrender.com"
    ):
        raise SystemExit(
            f"refusing: {what} must be https://<service>-staging.onrender.com (got host {host or 'none'})"
        )


def pack_files(receipts_dir: Path) -> dict[str, bytes]:
    files = {}
    for key, (name, _, digest) in PACK.items():
        content = (receipts_dir / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise SystemExit(f"{name} is not the synthetic pack file (sha256 differs)")
        files[key] = content
    return files


def money(value: Any) -> str:
    return f"{float(value):.2f}" if value not in (None, "") else ""


# ---------------------------------------------------------------- serve-api


def serve_api(args: argparse.Namespace) -> None:
    env = load_env_file(args.env_file)
    for name in ("SUPABASE_URL", "DATABASE_URL", "SUPABASE_POSTGRES_SESSION_POOLER_URL"):
        require_loopback(env[name], name)
    os.environ.update(env)
    sys.path[:0] = [str(REPO / "src"), str(REPO / "web"), str(REPO)]

    import httpx
    import uvicorn

    files = pack_files(args.receipts_dir)
    by_prefix = {media_id(PACK[k][2], 0)[:-2]: (files[k], PACK[k][1]) for k in PACK}

    def found(mid: str) -> tuple[bytes, str] | None:
        return by_prefix.get(mid[:-2]) if mid.isdigit() else None

    def graph(request: httpx.Request) -> httpx.Response:
        # Local stand-in for graph.facebook.com and its media CDN; nothing leaves the host.
        path = request.url.path
        if request.url.host == "graph.facebook.com" and path.endswith("/messages"):
            if args.outbound_log:
                try:
                    sent = json.loads(request.content)["text"]["body"]
                except (ValueError, KeyError, TypeError):
                    sent = ""
                with args.outbound_log.open("a") as log:
                    log.write(json.dumps({"text": sent}, ensure_ascii=False) + "\n")
            return httpx.Response(200, json={"messages": [{"id": "wamid.LOCAL"}]})
        if request.url.host == "graph.facebook.com":
            mid = path.rsplit("/", 1)[-1]
            item = found(mid)
            if item is None:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "url": f"https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid={mid}",
                    "mime_type": item[1],
                    "file_size": len(item[0]),
                    "id": mid,
                },
            )
        if request.url.host == "lookaside.fbsbx.com":
            item = found(request.url.params.get("mid", ""))
            return httpx.Response(200, content=item[0]) if item else httpx.Response(404)
        return httpx.Response(599)

    import argus.api.whatsapp as whatsapp_api

    class _LocalGraphHttpx:
        @staticmethod
        def AsyncClient(*_a: Any, **_k: Any) -> httpx.AsyncClient:  # noqa: N802
            return httpx.AsyncClient(transport=httpx.MockTransport(graph))

    whatsapp_api.httpx = _LocalGraphHttpx

    if args.extractor == "real":
        if not args.openrouter_key_file:
            raise SystemExit("--extractor real needs --openrouter-key-file")
        key = load_env_file(args.openrouter_key_file).get("OPENROUTER_API_KEY", "")
        if not key or key == "local-qa-disabled":
            raise SystemExit("no OPENROUTER_API_KEY in --openrouter-key-file")
        os.environ["OPENROUTER_API_KEY"] = key
    if args.extractor == "stub":
        import argus.api.documents as documents_api
        from argus.domain.ingestion.documents.models import DocumentExtractionError

        from tests.business.receipt_stub import ReceiptStub

        printed_by_digest = {
            **{PACK[k][2]: PRINTED[k] for k in PACK},
            **{ALIVE_PACK[k][2]: PRINTED[k] for k in ALIVE_PACK if k in PRINTED},
        }
        rows_by_digest = {ALIVE_PACK[k][2]: PRINTED_ROWS[k] for k in PRINTED_ROWS}

        class PrintedReceiptReader:
            """The product projection (batch_from_result) over a fixed read of each pack file."""

            def __init__(self, *_a: Any, **_k: Any) -> None:
                pass

            async def extract(self, *, content: bytes, **kwargs: Any) -> Any:
                digest = hashlib.sha256(content).hexdigest()
                if digest in rows_by_digest:
                    stub = ReceiptStub()
                    stub.details = None
                    stub.rows = [
                        {
                            "page": 1,
                            "row": index,
                            "evidence": "transaction",
                            "status": "posted",
                            "amount": amount,
                            "currency": "DOP",
                            "occurred_on": day,
                            "direction": "outflow",
                            "kind_hint": "expense",
                            "merchant": merchant,
                        }
                        for index, (day, merchant, amount) in enumerate(
                            rows_by_digest[digest], start=1
                        )
                    ]
                    return await stub.extract(content=content, **kwargs)
                printed = printed_by_digest.get(digest)
                if printed is None:
                    raise DocumentExtractionError("document_unreadable")
                purchase = {
                    "page": 1,
                    "row": 1,
                    "evidence": "transaction",
                    "status": "posted",
                    "amount": printed["total"],
                    "currency": "DOP",
                    "occurred_on": printed["occurred_on"],
                    "direction": "outflow",
                    "kind_hint": "expense",
                    "merchant": printed["merchant"],
                }
                details = {
                    "payment_status": "paid",
                    "merchant": printed["merchant"],
                    "occurred_on": printed["occurred_on"],
                    "currency": "DOP",
                    "subtotal": printed["subtotal"],
                    "itbis": printed["itbis"],
                    "total": printed["total"],
                    "rnc": printed["rnc"],
                    "ncf": printed["ncf"],
                }
                return await ReceiptStub(purchase, details).extract(
                    content=content, **kwargs
                )

        documents_api.DocumentExtractor = PrintedReceiptReader

    from argus.api.main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


# ---------------------------------------------------------------- HTTP


@dataclass
class Resp:
    status: int
    body: Any
    raw: bytes
    request_id: str | None
    headers: dict[str, str]


class Api:
    def __init__(self, base: str, origin: str) -> None:
        import httpx

        self.base = base.rstrip("/")
        self.origin = origin
        self.http = httpx.Client(timeout=120)
        self.token: str | None = None
        self.grant: str | None = None
        self.dry_run = False
        self.log: list[dict[str, Any]] = []

    def call(self, method: str, path: str, *, ok: bool = True, **kw: Any) -> Resp:
        if (
            self.dry_run
            and method.upper() not in ("GET", "HEAD")
            and path not in READ_ONLY_POSTS
        ):
            raise AssertionError(f"dry-run: refused {method} {path.split('?')[0]}")
        headers = {"Origin": self.origin, **kw.pop("headers", {})}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.grant and path.startswith("/api/v1/business"):
            headers["X-Business-Grant"] = self.grant
        response = self.http.request(method, self.base + path, headers=headers, **kw)
        try:
            body = response.json()
        except ValueError:
            body = None
        rid = response.headers.get("x-request-id") or (
            body.get("request_id") if isinstance(body, dict) else None
        )
        self.log.append(
            {
                "method": method,
                "path": path.split("?")[0],
                "status": response.status_code,
                "request_id": rid,
            }
        )
        result = Resp(
            response.status_code, body, response.content, rid, dict(response.headers)
        )
        if ok and not 200 <= response.status_code < 300:
            code = body.get("code") if isinstance(body, dict) else response.text[:120]
            raise AssertionError(
                f"{method} {path.split('?')[0]} answered {response.status_code} {code} (request {rid})"
            )
        return result

    def get(self, path: str, **kw: Any) -> Any:
        return self.call("GET", "/api/v1" + path, **kw).body

    def send(
        self, method: str, path: str, body: Any = None, key: str | None = None, **kw: Any
    ) -> Any:
        headers = kw.pop("headers", {})
        if key:
            headers["Idempotency-Key"] = key
        return self.call(method, "/api/v1" + path, json=body, headers=headers, **kw).body


# ---------------------------------------------------------------- steps


class Untested(Exception):
    pass


def expect(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@dataclass
class StepResult:
    case: str
    step: str
    outcome: str
    expected: str
    observed: dict[str, Any] = field(default_factory=dict)
    failing_hop: str | None = None
    fix: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)


class Recorder:
    def __init__(self, api: Api, out: Path) -> None:
        self.api, self.out = api, out
        self.results: list[StepResult] = []
        (out / "steps").mkdir(parents=True, exist_ok=True)

    @contextmanager
    def step(
        self,
        case: str,
        name: str,
        expected: str,
        fix: str | None = None,
        hop: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        observed: dict[str, Any] = {}
        start = len(self.api.log)
        outcome = "PASS"
        try:
            yield observed
        except Untested as reason:
            outcome, observed["untested"] = "UNTESTED", str(reason)
        except AssertionError as failure:
            outcome, observed["failure"] = "FAIL", str(failure)
        except Exception as error:  # noqa: BLE001
            outcome = "FAIL"
            observed["failure"] = f"{type(error).__name__}: {error}"
            observed["trace"] = traceback.format_exc(limit=3)[-1200:]
        calls = self.api.log[start:]
        if outcome == "FAIL" and calls and hop is None:
            last = calls[-1]
            hop = f"{last['method']} {last['path']} -> {last['status']}"
        hop = hop if outcome == "FAIL" else None
        result = StepResult(
            case,
            name,
            outcome,
            expected,
            observed,
            hop,
            fix if outcome == "FAIL" else None,
            calls,
        )
        self.results.append(result)
        (self.out / "steps" / f"{case}-{name}.json").write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=1, default=str)
        )
        print(
            f"  {outcome:<9} case {case} {name}"
            + (
                f"  ({observed.get('failure') or observed.get('untested')})"
                if outcome != "PASS"
                else ""
            ),
            flush=True,
        )


def need(state: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if state.get(k) is None]
    if missing:
        raise Untested(f"needs {', '.join(missing)} from an earlier step")


def known(value: Any) -> dict[str, Any]:
    return {"state": "known", "value": value}


def fact(dossier: dict[str, Any], name: str) -> Any:
    item = (dossier.get("facts") or {}).get(name) or {}
    return item.get("value") if item.get("state") == "known" else None


def blocker_fields(dossier: dict[str, Any]) -> list[str]:
    names = []
    for blocker in dossier.get("blockers") or []:
        names.extend(
            blocker.get("fields") or [blocker.get("field") or blocker.get("code")]
        )
    return sorted(str(n) for n in names)


# ---------------------------------------------------------------- reads


class Books:
    """The places a total lives, read together so a step can diff before/after."""

    def __init__(self, api: Api) -> None:
        self.api = api

    def expenses(self) -> list[dict[str, Any]]:
        return self.api.get(f"/business/expenses?from={PERIOD[0]}&to={PERIOD[1]}")[
            "items"
        ]

    def month_close(self) -> dict[str, Any]:
        return self.api.get(f"/business/month-close?month={MONTH}")

    def snapshot(self) -> dict[str, Any]:
        overview = self.api.get(f"/business/overview?from={PERIOD[0]}&to={PERIOD[1]}")
        close = self.month_close()
        dop = next((c for c in close.get("currencies", []) if c["currency"] == "DOP"), {})
        open_items = self.api.get("/business/open-items")
        report = self.api.send("POST", "/business/reports/query", {})
        card = next(
            (
                t
                for t in report.get("totals", [])
                if t["basis"] == "document_family_amount"
                and t["kind"] == "expense"
                and t["currency"] == "DOP"
            ),
            {},
        )
        return {
            "overview_dop": next(
                (
                    t["amount"]
                    for t in overview.get("totals", [])
                    if t["currency"] == "DOP"
                ),
                "0.00",
            ),
            "close_expense_dop": dop.get("expense_before_itbis", "0.00"),
            "close_payables_dop": dop.get("cuentas_por_pagar", "0.00"),
            "close_receipts": dop.get("by_status", {}).get("receipts"),
            "open_payables": open_items["cuentas_por_pagar"]["count"],
            # The Registros card's figure: the full total, or the known part it
            # shows as partial while a matching row's amount is unknown.
            "registros_gastos_dop": card.get("known_amount"),
            "registros_complete": card.get("complete"),
            "registros_personal_excluded": report.get("excluded_personal", {}).get(
                "expense"
            ),
            "expense_ids": sorted(e["id"] for e in self.expenses()),
        }

    def receipts(self) -> list[dict[str, Any]]:
        body = self.api.get("/business/receipts?view=all")
        return body["items"] if isinstance(body, dict) else body


def wait_for(read, done, timeout: float = 90, every: float = 1.5) -> Any:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    value = read()
    while not done(value) and time.monotonic() < deadline:
        time.sleep(every)
        value = read()
    return value


def upload(
    api: Api, content: bytes, name: str, media_type: str, key: str
) -> dict[str, Any]:
    return api.call(
        "POST",
        "/api/v1/business/receipts",
        content=content,
        headers={
            "Content-Type": media_type,
            "Idempotency-Key": key,
            "X-Document-Filename": name,
            "X-Extraction-Consent": "true",
        },
    ).body


def read_receipt(api: Api, receipt_id: str) -> dict[str, Any]:
    return wait_for(
        lambda: api.get(f"/business/receipts/{receipt_id}"),
        lambda r: r.get("status") not in ("preparing", "reading", "queued")
        and not r.get("read_pending"),
    )


# ---------------------------------------------------------------- sign-in


BROWSER_JS = r"""
import { chromium } from "@playwright/test";
const job = JSON.parse(await new Promise(r => { let s = ""; process.stdin.on("data", c => s += c); process.stdin.on("end", () => r(s)); }));
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "es-419" });
const page = await context.newPage();
let token = null;
page.on("request", req => { const h = req.headers()["authorization"]; if (h && h.startsWith("Bearer ") && req.url().startsWith(job.api)) token = h.slice(7); });
const out = { shots: [], errors: [] };
const CODES = ["email_step_failed", "password_step_failed", "login_rejected", "timeout", "consent_required", "shot_on_auth_page"];
const fail = (code) => { throw new Error(code); };
const onAuth = () => { const u = new URL(page.url()); return /\/(auth|login)(\/|\?|$)/.test(u.pathname + "/") || u.searchParams.has("auth") || u.pathname === "/"; };
async function fillChecked(selector, allowed, value, code) {
  const field = page.locator(selector).first();
  try {
    await field.waitFor({ state: "visible", timeout: 15000 });
    const type = (await field.evaluate(el => el.type)) || "text";
    if (!allowed.includes(type)) fail(code);
    await field.fill(value);
  } catch (e) { if (e.message === code) throw e; fail(code); }
}
try {
  await page.goto(job.web + "/login", { waitUntil: "domcontentloaded" });
  await fillChecked('input[type="email"]:visible, input[type="text"]:visible', ["email", "text"], job.email, "email_step_failed");
  try { await page.getByRole("button", { name: /^(Continuar|Continue)$/i }).first().click({ timeout: 15000 }); } catch { fail("email_step_failed"); }
  await fillChecked('input[type="password"]:visible', ["password"], job.password, "password_step_failed");
  await page.locator('input[type="password"]:visible').first().press("Enter");
  const deadline = Date.now() + 60000;
  while (onAuth()) {
    if (Date.now() > deadline) fail("timeout");
    if (await page.locator('[role="alert"]:not(#__next-route-announcer__):visible', { hasText: /\S/ }).count() > 0) fail("login_rejected");
    await page.waitForTimeout(250);
  }
  await page.waitForLoadState("networkidle").catch(() => {});
  const gate = page.getByRole("checkbox").first();
  if (await gate.waitFor({ state: "visible", timeout: 8000 }).then(() => true, () => false)) {
    if (!job.accept_consent) fail("consent_required");
    await gate.check();
    await page.getByRole("button", { name: /Continuar|Continue/ }).click();
    await gate.waitFor({ state: "hidden", timeout: 20000 });
  }
  for (const shot of job.shots) {
    try {
      await page.goto(job.web + shot.path, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
      if (onAuth()) fail("shot_on_auth_page");
      if (shot.text) await page.getByText(shot.text, { exact: false }).first().waitFor({ timeout: 20000 });
      await page.waitForTimeout(800);
      await page.screenshot({ path: `${job.out}/${shot.name}.png`, fullPage: false });
      out.shots.push(shot.name);
    } catch (e) { out.errors.push(`${shot.name}: ${CODES.includes(e.message) ? e.message : "shot_failed"}`); }
  }
  for (let i = 0; i < 20 && !token; i++) await page.waitForTimeout(500);
} catch (e) {
  out.errors.push(`login: ${CODES.includes(e.message) ? e.message : "login_failed"}`);
}
await browser.close();
out.signed_in = Boolean(token);
if (job.want_token) out.token = token;
process.stdout.write(JSON.stringify(out));
"""


def error_name(stderr: str) -> str:
    """Only the error's name: a browser failure must not echo what was typed."""

    found = re.search(r"\b(\w*Error|ERR_[A-Z_]+)\b", stderr)
    return found.group(1) if found else "unknown"


def browser(
    web: str,
    api: str,
    email: str,
    password: str,
    shots: list[dict[str, str]],
    out: Path,
    want_token: bool,
) -> dict[str, Any]:
    """Headless web sign-in; credentials go over stdin, the token comes back over stdout.

    The first-use consent screen is accepted only for a loopback web (a synthetic local owner)."""

    out.mkdir(parents=True, exist_ok=True)
    job = {
        "web": web,
        "api": api,
        "email": email,
        "password": password,
        "shots": shots,
        "out": str(out),
        "want_token": want_token,
        "accept_consent": urlsplit(web).hostname in LOOPBACK,
    }
    result = subprocess.run(
        ["node", "--input-type=module", "-e", BROWSER_JS],
        cwd=REPO / "web",
        input=json.dumps(job),
        capture_output=True,
        text=True,
        timeout=600,
    )
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {
            "errors": [
                f"browser exited {result.returncode}: {error_name(result.stderr)}"
            ],
            "shots": [],
            "signed_in": False,
        }


def staging_account(path: Path, entry: str) -> tuple[str, str]:
    """The entry as ``{entry: {email: password}}`` (the accounts file), ``{entry:
    {email, password}}``, or a list item named by name/label/id. Values never print."""

    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        raise SystemExit("accounts file unreadable") from None
    if isinstance(data, dict):
        items = data.items()
    else:
        items = (
            (i.get("name") or i.get("label") or i.get("id"), i)
            for i in data
            if isinstance(i, dict)
        )
    for name, item in items:
        if name != entry or not isinstance(item, dict):
            continue
        email, password = item.get("email"), item.get("password")
        if isinstance(email, str) and isinstance(password, str) and email and password:
            return email, password
        if len(item) == 1:
            email, password = next(iter(item.items()))
            if "@" in email and isinstance(password, str) and password:
                return email, password
    raise SystemExit(f"account entry {entry!r} not found as an email and password pair")


def local_owner(
    env: dict[str, str], api: Api, account_file: Path | None
) -> tuple[str, str, bool]:
    import httpx

    if account_file and account_file.exists():
        data = json.loads(account_file.read_text())
        return data["email"], data["password"], False
    email = f"jose-ensayo-{secrets.token_hex(3)}@rehearsal.local"
    password = secrets.token_urlsafe(18)
    key = env["SUPABASE_SERVICE_ROLE_KEY"]
    created = httpx.post(
        f"{env['SUPABASE_URL']}/auth/v1/admin/users",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        json={"email": email, "password": password, "email_confirm": True},
        timeout=30,
    )
    expect(
        created.status_code == 200,
        f"local auth admin create answered {created.status_code}",
    )
    if account_file:
        old = os.umask(0o177)
        account_file.write_text(json.dumps({"email": email, "password": password}))
        os.umask(old)
    return email, password, True


# ---------------------------------------------------------------- WhatsApp (local only)


class LocalWhatsApp:
    def __init__(self, api: Api, env: dict[str, str]) -> None:
        self.api, self.secret = api, env["CUADRAO_WHATSAPP_APP_SECRET"].encode()
        self.number_id = env["CUADRAO_WHATSAPP_NUMBER_ID"]
        # One synthetic phone per run: a phone links to one owner, and every local run makes a new owner.
        self.phone = f"1555{secrets.randbelow(10**7):07d}"

    def deliver(self, message: dict[str, Any]) -> Resp:
        body = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "900000000000001",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15550009999",
                                    "phone_number_id": self.number_id,
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Ensayo José"},
                                        "wa_id": self.phone,
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": self.phone,
                                        "id": f"wamid.ENSAYO{secrets.token_hex(6).upper()}",
                                        "timestamp": str(int(time.time())),
                                        **message,
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
        raw = json.dumps(body).encode()
        signature = "sha256=" + hmac.new(self.secret, raw, hashlib.sha256).hexdigest()
        return self.api.call(
            "POST",
            "/api/v1/webhooks/whatsapp",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
            },
            ok=False,
        )


# ---------------------------------------------------------------- export


def xlsx_sheets(content: bytes) -> dict[str, list[list[str]]]:
    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    book = zipfile.ZipFile(io.BytesIO(content))
    shared = []
    if "xl/sharedStrings.xml" in book.namelist():
        for si in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall(
            "m:si", ns
        ):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
    rels = {
        r.get("Id"): r.get("Target")
        for r in ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    }
    sheets = {}
    for sheet in ElementTree.fromstring(book.read("xl/workbook.xml")).find(
        "m:sheets", ns
    ):
        target = rels[sheet.get(f"{{{ns['r']}}}id")].lstrip("/").removeprefix("xl/")
        rows = []
        for row in ElementTree.fromstring(book.read(f"xl/{target}")).iter(
            f"{{{ns['m']}}}row"
        ):
            values = []
            for c in row.findall("m:c", ns):
                v = c.find("m:v", ns)
                text = c.find("m:is/m:t", ns)
                value = (
                    text.text if text is not None else (v.text if v is not None else "")
                )
                values.append(
                    shared[int(value)] if c.get("t") == "s" and value else value or ""
                )
            rows.append(values)
        sheets[sheet.get("name")] = rows
    return sheets


def csv_rows(content: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


# ---------------------------------------------------------------- cases


class Rehearsal:
    def __init__(
        self,
        api: Api,
        rec: Recorder,
        args: argparse.Namespace,
        files: dict[str, bytes],
        env: dict[str, str],
    ) -> None:
        self.api, self.rec, self.args, self.files, self.env = api, rec, args, files, env
        self.books = Books(api)
        self.state: dict[str, Any] = {"run": secrets.token_hex(4)}

    def key(self, name: str) -> str:
        return f"jose-rehearse-{self.state['run']}-{name}"

    def setup(self) -> None:
        api, state = self.api, self.state
        with self.rec.step(
            "0", "receipt-reading-on", "receipt reading enabled for the Business"
        ):
            reading = api.get("/business/receipt-reading?language=es-419")
            if not reading["enabled"]:
                api.send(
                    "POST",
                    "/business/receipt-reading",
                    {
                        "enabled": True,
                        "scope_version": reading["scope_version"],
                        "disclosure_token": reading["disclosure_token"],
                        "language": "es-419",
                    },
                    key=self.key("reading"),
                )
            expect(
                api.get("/business/receipt-reading?language=es-419")["enabled"],
                "reading still off",
            )
        with self.rec.step(
            "0", "bank-account", "one DOP checking account for the Business"
        ) as obs:
            state["account_id"] = ensure_account(api, self.key("account"))
            obs["account_id"] = state["account_id"]
        with self.rec.step("0", "baseline", "books read before any case") as obs:
            state["base"] = self.books.snapshot()
            state["base_receipts"] = {r["id"] for r in self.books.receipts()}
            obs.update(state["base"])

    def plan(self) -> dict[str, Any]:
        """--dry-run: read the Business, print every write a real run would make."""

        api = self.api
        reading = api.get("/business/receipt-reading?language=es-419")
        accounts = [
            a
            for a in api.get("/business/workspace")["accounts"]
            if a.get("currency") == "DOP"
            and a.get("type", "checking") in ("checking", "savings")
        ]
        baseline = self.books.snapshot()
        print(
            f"  reads    reading enabled: {reading['enabled']}; DOP accounts: {len(accounts)}; baseline {json.dumps(baseline, default=str)[:300]}"
        )
        plan = {c: PLANNED_WRITES[c] for c in ("0", *self.args.cases)}
        for case, writes in plan.items():
            for write in writes:
                print(f"  plan     case {case}: {write}")
        return {
            "reading_enabled": reading["enabled"],
            "dop_accounts": len(accounts),
            "baseline": baseline,
            "planned": plan,
        }

    def case2(self) -> None:
        api, state, rec = self.api, self.state, self.rec
        with rec.step(
            "2",
            "note-captured",
            "a note makes an open draft; only currency DOP (default) is known",
        ) as obs:
            draft = api.send(
                "POST",
                "/business/captures",
                {"text": CASE2_NOTE, "document_type": "recibo"},
                key=self.key("note"),
            )
            state["c2_draft"] = draft["draft_id"]
            obs.update(
                draft_id=draft["draft_id"],
                review_state=draft["review_state"],
                amount=fact(draft, "amount"),
            )
            expect(
                draft["review_state"] == "open" and fact(draft, "amount") is None,
                "note draft is not an open draft without facts",
            )
        with rec.step(
            "2",
            "reviewed-informal",
            "facts set by hand; receipt_state informal_receipt; no RNC/NCF/ITBIS anywhere; no blockers",
        ) as obs:
            need(state, "c2_draft")
            draft = api.send(
                "PATCH",
                f"/business/drafts/{state['c2_draft']}/review",
                {
                    "version": 1,
                    "facts": {
                        "kind": known("expense"),
                        "amount": known(CASE2_FACTS["amount"]),
                        "currency": known("DOP"),
                        "occurred_on": known(CASE2_FACTS["occurred_on"]),
                        "counterparty": known(CASE2_FACTS["counterparty"]),
                        "funding": known({"kind": "owner_funds"}),
                        "business_share": known({"kind": "all"}),
                        "receipt_state": known("informal_receipt"),
                    },
                },
                key=self.key("note-review"),
            )
            dossier = api.get(f"/business/drafts/{state['c2_draft']}/dossier")
            obs.update(
                version=dossier["version"],
                blockers=dossier["blockers"],
                fiscal=(dossier["facts"] or {}).get("fiscal"),
                dgii=dossier.get("dgii"),
                sin_comprobante=dossier.get("sin_comprobante"),
                receipt_state=fact(dossier, "receipt_state"),
            )
            state["c2_version"] = draft["version"]
            expect(dossier["blockers"] == [], f"blockers left: {dossier['blockers']}")
            expect(
                (dossier["facts"] or {}).get("fiscal") is None
                and dossier.get("dgii") is None,
                "a fiscal value appeared on a note",
            )
            expect(
                fact(dossier, "receipt_state") == "informal_receipt",
                "receipt_state not saved",
            )
        with rec.step(
            "2",
            "approved",
            "exactly one new expense DOP 450.00 on 2026-10-27, no fiscal number",
        ) as obs:
            need(state, "c2_version")
            before = {e["id"] for e in self.books.expenses()}
            approved = api.send(
                "POST",
                f"/business/drafts/{state['c2_draft']}/approve",
                {"version": state["c2_version"], "action": "record_expense"},
                key=self.key("note-approve"),
            )
            state["c2_activity"] = approved["approval_result"]["activity_id"]
            new = [e for e in self.books.expenses() if e["id"] not in before]
            obs.update(activity_id=state["c2_activity"], new=new)
            expect(
                len(new) == 1
                and new[0]["amount"] == "450.00"
                and new[0]["currency"] == "DOP"
                and new[0]["occurred_on"] == "2026-10-27",
                f"expected one new 450.00 DOP expense, saw {new}",
            )
        with rec.step(
            "2",
            "month-close-informal",
            "counted in October expenses, not in missing_ncf, payable 450.00 until settled",
        ) as obs:
            need(state, "c2_activity")
            close = self.books.month_close()
            payable = [
                p
                for p in close["cuentas_por_pagar"]
                if p["activity_id"] == state["c2_activity"]
            ]
            missing = [
                m
                for m in close.get("missing_ncf", [])
                if state["c2_activity"] in json.dumps(m)
            ]
            obs.update(payable=payable, missing_ncf=missing)
            expect(not missing, "informal purchase listed as missing NCF")
            expect(
                len(payable) == 1
                and payable[0]["total"] == "450.00"
                and payable[0]["status"] == "pendiente",
                "not a 450.00 pending payable",
            )
        with rec.step(
            "2",
            "settled-cash",
            "month close PATCH pagado efectivo; payable gone, receipts pagado +1",
        ) as obs:
            need(state, "c2_activity")
            before = self.books.snapshot()
            settled = api.send(
                "PATCH",
                f"/business/month-close/documents/{state['c2_activity']}",
                {
                    "status": "pagado",
                    "settled_on": "2026-10-27",
                    "payment_method": "efectivo",
                },
            )
            after = self.books.snapshot()
            obs.update(
                settled=settled,
                before=before["close_receipts"],
                after=after["close_receipts"],
            )
            expect(
                settled["status"] == "pagado" and settled["payment_method"] == "efectivo",
                "settlement not stored",
            )
            expect(
                not [
                    p
                    for p in self.books.month_close()["cuentas_por_pagar"]
                    if p["activity_id"] == state["c2_activity"]
                ],
                "still a payable",
            )
        with rec.step(
            "2", "reload", "dossier reread: same version, same facts, accepted"
        ) as obs:
            need(state, "c2_activity")
            dossier = api.get(f"/business/drafts/{state['c2_draft']}/dossier")
            obs.update(
                version=dossier["version"],
                review_state=dossier["review_state"],
                amount=fact(dossier, "amount"),
            )
            expect(
                dossier["review_state"] == "accepted"
                and money(fact(dossier, "amount")) == "450.00",
                "dossier changed after reload",
            )

    def case3(self) -> None:
        api, state, rec = self.api, self.state, self.rec
        name, media_type, _ = PACK["P"]
        state["c3_before"] = self.books.snapshot()
        with rec.step(
            "3",
            "uploaded-read",
            "03-farmacia saved, read: FARMACIA SAN RAFAEL 548.70 DOP 2026-10-09",
        ) as obs:
            receipt = upload(
                api, self.files["P"], name, media_type, self.key("upload-03")
            )
            state["c3_receipt"] = receipt["id"]
            receipt = read_receipt(api, receipt["id"])
            state["c3_draft"] = receipt.get("draft_id")
            obs.update(
                {
                    k: receipt.get(k)
                    for k in (
                        "id",
                        "status",
                        "merchant",
                        "amount",
                        "currency",
                        "occurred_on",
                        "draft_id",
                    )
                }
            )
            expect(
                receipt.get("draft_id"),
                f"no draft after read (status {receipt.get('status')})",
            )
            expect(
                receipt.get("merchant") == PRINTED["P"]["merchant"]
                and money(receipt.get("amount")) == "548.70",
                "read differs from the printed receipt",
            )
            state["c3_read"] = self.books.snapshot()
        with rec.step(
            "3",
            "marked-personal",
            "Personal mark: business_share none, owner_stated; funding owner_funds; approvable",
        ) as obs:
            need(state, "c3_draft")
            draft = api.get(f"/business/drafts/{state['c3_draft']}/dossier")
            draft = api.send(
                "POST",
                f"/business/drafts/{state['c3_draft']}/personal",
                {"version": draft["version"], "personal": True},
                key=self.key("personal"),
            )
            draft = api.send(
                "PATCH",
                f"/business/drafts/{state['c3_draft']}/review",
                {
                    "version": draft["version"],
                    "facts": {"funding": known({"kind": "owner_funds"})},
                },
                key=self.key("personal-funding"),
            )
            dossier = api.get(f"/business/drafts/{state['c3_draft']}/dossier")
            state["c3_version"] = dossier["version"]
            obs.update(
                personal=dossier["personal"],
                share=fact(dossier, "business_share"),
                blockers=dossier["blockers"],
            )
            expect(
                dossier["personal"] is True
                and fact(dossier, "business_share") == {"kind": "none"},
                "personal mark not stored",
            )
            expect(dossier["blockers"] == [], f"blockers left: {dossier['blockers']}")
        with rec.step(
            "3",
            "approved",
            "approved as a personal record; books compared with the reads before the upload",
        ) as obs:
            need(state, "c3_version")
            approved = api.send(
                "POST",
                f"/business/drafts/{state['c3_draft']}/approve",
                {"version": state["c3_version"], "action": "record_expense"},
                key=self.key("personal-approve"),
            )
            state["c3_activity"] = (approved.get("approval_result") or {}).get(
                "activity_id"
            )
            state["c3_after"] = self.books.snapshot()
            obs.update(approval=approved.get("approval_result"))
            expect(approved["review_state"] == "accepted", "not accepted")
        for place, label, fix in (
            ("overview_dop", "out-of-overview", None),
            ("close_expense_dop", "out-of-month-close", None),
            ("close_payables_dop", "out-of-payables", None),
            ("open_payables", "out-of-open-items", None),
        ):
            with rec.step(
                "3", label, f"{place} unchanged by the personal purchase", fix=fix
            ) as obs:
                need(state, "c3_activity")
                before, after = state["c3_before"][place], state["c3_after"][place]
                obs.update(before=before, after=after)
                expect(before == after, f"{place} moved {before} -> {after}")
        with rec.step(
            "3",
            "out-of-registros-card",
            "Registros gastos DOP: counts the open 548.70 draft after the read, drops"
            " exactly 548.70 once it is approved personal; one more personal exclusion",
            fix=FIX_1417 + " (gap 3a, reporting_query.py document_family_amount)",
            hop="POST /api/v1/business/reports/query totals[document_family_amount]",
        ) as obs:
            need(state, "c3_read", "c3_activity")
            read, after = state["c3_read"], state["c3_after"]
            obs.update(
                read=read["registros_gastos_dop"],
                after=after["registros_gastos_dop"],
                complete=[read["registros_complete"], after["registros_complete"]],
                personal_excluded=[
                    read["registros_personal_excluded"],
                    after["registros_personal_excluded"],
                ],
            )
            expect(
                read["registros_gastos_dop"] is not None
                and after["registros_gastos_dop"] is not None,
                "no Registros gastos DOP total in the report",
            )
            delta = round(
                float(read["registros_gastos_dop"])
                - float(after["registros_gastos_dop"]),
                2,
            )
            obs["delta"] = money(delta)
            expect(delta == 548.70, f"Registros gastos DOP moved by {delta}, not 548.70")
            expect(
                after["registros_personal_excluded"]
                == (read["registros_personal_excluded"] or 0) + 1,
                "the personal purchase is not counted as excluded",
            )
        with rec.step(
            "3", "original-kept", "the original opens (200, image bytes)"
        ) as obs:
            need(state, "c3_receipt")
            source = api.call(
                "GET", f"/api/v1/business/receipts/{state['c3_receipt']}/source"
            )
            obs.update(
                content_type=source.headers.get("content-type"),
                bytes=len(source.raw),
                sha256=hashlib.sha256(source.raw).hexdigest(),
            )
            expect(
                source.raw
                and source.headers.get("content-type", "").startswith("image/"),
                "original did not open as an image",
            )

    def case1(self) -> None:
        api, state, rec = self.api, self.state, self.rec
        local = self.args.target == "local"
        wa = LocalWhatsApp(api, self.env) if local else None
        name, media_type, digest = PACK["R"]
        with rec.step(
            "1",
            "phone-linked",
            "link code sent from the phone; /whatsapp/link linked:true",
        ) as obs:
            link = api.get("/whatsapp/link")
            if not link["linked"]:
                if not local:
                    raise Untested("phone not linked; staging link is Lucas's action")
                code = api.send("POST", "/whatsapp/link-codes", {"language": "es-419"})
                sent = wa.deliver(
                    {"type": "text", "text": {"body": code["message_text"]}}
                )
                obs["webhook_status"] = sent.status
                link = wait_for(
                    lambda: api.get("/whatsapp/link"),
                    lambda value: value["linked"],
                    timeout=20,
                )
            obs.update(linked=link["linked"], last4=link.get("last4"))
            expect(link["linked"], "phone not linked")
            state["c1_linked"] = True
        with rec.step(
            "1",
            "arrived-in-business",
            "one new Bandeja row: channel whatsapp, the R file, in this Business",
        ) as obs:
            need(state, "c1_linked")
            known_ids = {r["id"] for r in self.books.receipts()}
            if local:
                sent = wa.deliver(
                    {
                        "type": "document",
                        "document": {
                            "filename": name,
                            "mime_type": media_type,
                            "sha256": "",
                            "id": media_id(digest, 1),
                        },
                    }
                )
                obs["webhook_status"] = sent.status
                expect(sent.status == 200, f"webhook answered {sent.status}")
            timeout = 60 if local else self.args.whatsapp_wait
            if not local and timeout <= 0:
                raise Untested(
                    "staging case 1 needs a live WhatsApp document (--whatsapp-wait)"
                )
            rows = wait_for(
                self.books.receipts,
                lambda rs: any(
                    r["id"] not in known_ids and r.get("channel") == "whatsapp"
                    for r in rs
                ),
                timeout=timeout,
                every=3,
            )
            new = [
                r
                for r in rows
                if r["id"] not in known_ids and r.get("channel") == "whatsapp"
            ]
            obs["new"] = [
                {k: r.get(k) for k in ("id", "channel", "filename", "status", "replayed")}
                for r in new
            ]
            expect(len(new) == 1, f"expected one new WhatsApp row, saw {len(new)}")
            state["c1_receipt"] = new[0]["id"]
        with rec.step(
            "1",
            "read-fields",
            "review_ready; merchant, date, total, subtotal, ITBIS, RNC, NCF as printed; blockers funding + business_share only",
        ) as obs:
            need(state, "c1_receipt")
            receipt = read_receipt(api, state["c1_receipt"])
            state["c1_draft"] = receipt.get("draft_id")
            need(state, "c1_draft")
            dossier = api.get(f"/business/drafts/{state['c1_draft']}/dossier")
            fiscal = (dossier["facts"] or {}).get("fiscal") or {}
            seen = {
                "merchant": fact(dossier, "counterparty"),
                "occurred_on": fact(dossier, "occurred_on"),
                "total": money(fact(dossier, "amount")),
                "currency": fact(dossier, "currency"),
                "fiscal": fiscal,
                "dgii": dossier.get("dgii"),
                "blockers": blocker_fields(dossier),
                "duplicates": dossier.get("duplicate_candidates"),
            }
            obs.update(status=receipt.get("status"), **seen)
            state["c1_version"] = dossier["version"]
            misread = [
                k
                for k in ("merchant", "occurred_on", "total")
                if str(seen[k]) != PRINTED["R"][k]
            ]
            obs["misread"] = misread
            expect(not misread, f"misread: {misread}")
            fiscal_read = {
                k: (fiscal.get(k) or {}).get("value") for k in ("rnc", "ncf", "itbis")
            }
            fiscal_read["itbis"] = money(fiscal_read["itbis"])
            expect(
                fiscal_read == {k: PRINTED["R"][k] for k in ("rnc", "ncf", "itbis")},
                f"fiscal read differs: {fiscal_read}",
            )
            expect(
                set(blocker_fields(dossier)) <= {"funding", "business_share"},
                f"unexpected blockers {blocker_fields(dossier)}",
            )
        with rec.step(
            "1",
            "original-opens",
            "Recibo original opens: 200 image (images are re-encoded; hash recorded, not compared)",
        ) as obs:
            need(state, "c1_receipt")
            source = api.call(
                "GET", f"/api/v1/business/receipts/{state['c1_receipt']}/source"
            )
            obs.update(
                content_type=source.headers.get("content-type"),
                bytes=len(source.raw),
                sha256=hashlib.sha256(source.raw).hexdigest(),
                sent_sha256=digest,
            )
            expect(
                source.headers.get("content-type", "").startswith("image/")
                and len(source.raw) > 1000,
                "original did not open",
            )
        with rec.step(
            "1",
            "dossier-channel",
            "the dossier names WhatsApp as the channel of the original",
            hop="GET /api/v1/business/drafts/{id}/dossier sources[].channel",
            fix="prepare_attachment (actions/mutations.py) stores every attachment source as"
            " channel 'web'; overlay 'whatsapp' for connections in BusinessService.captured()"
            " beside with_email_sources (api/business_drafts.py)",
        ) as obs:
            need(state, "c1_draft")
            dossier = api.get(f"/business/drafts/{state['c1_draft']}/dossier")
            obs["sources"] = [
                {k: s.get(k) for k in ("id", "kind", "channel", "filename")}
                for s in dossier.get("sources") or []
            ]
            files = [s for s in obs["sources"] if s.get("kind") != "message"]
            expect(files, "no file source on the dossier")
            expect(
                all(s.get("channel") == "whatsapp" for s in files),
                f"source channels {[s.get('channel') for s in files]}",
            )
        with rec.step(
            "1",
            "corrected",
            "funding = the Business bank account, business_share all; no blockers",
        ) as obs:
            need(state, "c1_version", "account_id")
            api.send(
                "PATCH",
                f"/business/drafts/{state['c1_draft']}/review",
                {
                    "version": state["c1_version"],
                    "facts": {
                        "funding": known(
                            {
                                "kind": "business_account",
                                "account_id": state["account_id"],
                            }
                        ),
                        "business_share": known({"kind": "all"}),
                    },
                },
                key=self.key("r-review"),
            )
            dossier = api.get(f"/business/drafts/{state['c1_draft']}/dossier")
            state["c1_version"] = dossier["version"]
            obs.update(version=dossier["version"], blockers=dossier["blockers"])
            expect(dossier["blockers"] == [], f"blockers left: {dossier['blockers']}")
        with rec.step(
            "1", "approved", "one new expense DOP 2,826.10 on 2026-10-10"
        ) as obs:
            need(state, "c1_version")
            before = {e["id"] for e in self.books.expenses()}
            approved = api.send(
                "POST",
                f"/business/drafts/{state['c1_draft']}/approve",
                {"version": state["c1_version"], "action": "record_expense"},
                key=self.key("r-approve"),
            )
            state["c1_activity"] = approved["approval_result"]["activity_id"]
            new = [e for e in self.books.expenses() if e["id"] not in before]
            obs.update(activity_id=state["c1_activity"], new=new)
            expect(
                len(new) == 1
                and new[0]["amount"] == "2826.10"
                and new[0]["occurred_on"] == "2026-10-10",
                f"saw {new}",
            )
        with rec.step(
            "1", "reload", "fresh session: same dossier version, facts and expense"
        ) as obs:
            need(state, "c1_activity")
            fresh = self.fresh_api()
            dossier = fresh.get(f"/business/drafts/{state['c1_draft']}/dossier")
            obs.update(
                version=dossier["version"],
                review_state=dossier["review_state"],
                amount=fact(dossier, "amount"),
            )
            expect(
                dossier["review_state"] == "accepted"
                and money(fact(dossier, "amount")) == "2826.10",
                "dossier differs in a fresh session",
            )
            expect(
                any(e["id"] == state["c1_activity"] for e in Books(fresh).expenses()),
                "expense missing in a fresh session",
            )
        with rec.step(
            "1",
            "duplicate-resend",
            "same bytes again: the API replies that it already had it; no new receipt, draft, expense or read",
        ) as obs:
            need(state, "c1_activity")
            if not local:
                raise Untested("staging resend is Lucas's phone action")
            log = self.args.outbound_log
            if log is None:
                raise Untested(
                    "no dedupe signal without --outbound-log (serve-api --outbound-log)"
                )
            replies_before = len(outbound_replies(log))
            receipts_before = {r["id"] for r in self.books.receipts()}
            version_before = api.get(f"/business/drafts/{state['c1_draft']}/dossier")[
                "version"
            ]
            expenses_before = {e["id"] for e in self.books.expenses()}
            sent = wa.deliver(
                {
                    "type": "document",
                    "document": {
                        "filename": name,
                        "mime_type": media_type,
                        "sha256": "",
                        "id": media_id(digest, 2),
                    },
                }
            )
            expect(sent.status == 200, f"webhook answered {sent.status}")
            replies = wait_for(
                lambda: outbound_replies(log)[replies_before:],
                lambda new: any(d in text for text in new for d in DUPLICATE_REPLY),
                timeout=60,
                every=1,
            )
            rows = self.books.receipts()
            again = next((r for r in rows if r["id"] == state["c1_receipt"]), {})
            obs.update(
                webhook_status=sent.status,
                duplicate_reply=any(d in t for t in replies for d in DUPLICATE_REPLY),
                replies_after_resend=len(replies),
                new_receipts=sorted({r["id"] for r in rows} - receipts_before),
                new_expenses=sorted(
                    {e["id"] for e in self.books.expenses()} - expenses_before
                ),
                replayed=again.get("replayed"),
            )
            expect(
                obs["duplicate_reply"],
                "no 'already had it' reply within 60s: the resend was not seen as a duplicate",
            )
            obs["draft_version"] = [
                version_before,
                api.get(f"/business/drafts/{state['c1_draft']}/dossier")["version"],
            ]
            expect(
                not obs["new_receipts"] and not obs["new_expenses"],
                "the resend made a new record",
            )
            expect(
                obs["draft_version"][0] == obs["draft_version"][1],
                "the resend changed the draft (a second read)",
            )

    def case4(self) -> None:
        api, state, rec = self.api, self.state, self.rec
        with rec.step(
            "4",
            "statement-imported",
            "S.csv (sandbox_csv): 201, inserted + unchanged 3 (a seeded Business already"
            " holds the lines); same key + bytes 200 created:false, inserted 0",
        ) as obs:
            need(state, "account_id")
            first = import_statement(
                api, state["account_id"], STATEMENT, self.key("import")
            )
            again = import_statement(
                api, state["account_id"], STATEMENT, self.key("import")
            )
            obs.update(
                first={
                    k: first.body.get(k)
                    for k in ("inserted_count", "unchanged_count", "created")
                },
                first_status=first.status,
                again={k: again.body.get(k) for k in ("inserted_count", "created")},
                again_status=again.status,
            )
            expect(
                first.status == 201
                and first.body["inserted_count"] + first.body["unchanged_count"] == 3,
                "first import did not account for 3 lines",
            )
            expect(
                again.status == 200
                and again.body["created"] is False
                and again.body["inserted_count"] == 0,
                "replayed import was not a replay",
            )
            state["c4_imported"] = True
        with rec.step(
            "4",
            "suggestion-offered",
            "the L1 line (FERRETERÍA EL TORNILLO -2826.10) offers the case 1 expense as a suggestion",
        ) as obs:
            need(state, "c4_imported", "c1_activity")
            line, suggestion = find_suggestion(api, "2826.10", state["c1_activity"])
            obs.update(
                line_state=line.get("state") if line else None, suggestion=suggestion
            )
            expect(suggestion, "no suggestion of the case 1 expense on L1")
            state["c4_suggestion"] = suggestion["id"]
        with rec.step(
            "4",
            "confirmed",
            "confirm: line igualada, settlement pagado, no new expense, payables -2,826.10; same key replays",
        ) as obs:
            need(state, "c4_suggestion")
            before = self.books.snapshot()
            first = api.call(
                "POST",
                f"/api/v1/business/bank/suggestions/{state['c4_suggestion']}/confirm",
                headers={"Idempotency-Key": self.key("confirm")},
            )
            again = api.call(
                "POST",
                f"/api/v1/business/bank/suggestions/{state['c4_suggestion']}/confirm",
                headers={"Idempotency-Key": self.key("confirm")},
            )
            after = self.books.snapshot()
            close = self.books.month_close()
            settled = [
                p
                for p in close["cuentas_por_pagar"]
                if p["activity_id"] == state["c1_activity"]
            ]
            obs.update(
                first_status=first.status,
                again_status=again.status,
                same=first.body == again.body,
                expenses_added=sorted(
                    set(after["expense_ids"]) - set(before["expense_ids"])
                ),
                payables_before=before["close_payables_dop"],
                payables_after=after["close_payables_dop"],
                receipts_after=after["close_receipts"],
            )
            expect(not obs["expenses_added"], "confirm wrote an expense")
            expect(not settled, "case 1 still a payable after the match")
            expect(
                round(
                    float(before["close_payables_dop"])
                    - float(after["close_payables_dop"]),
                    2,
                )
                == 2826.10,
                "payables did not drop by 2,826.10",
            )
            expect(first.body == again.body, "confirm replay differs")
            line, _ = find_suggestion(api, "2826.10", state["c1_activity"])
            obs["line_state"] = line.get("state") if line else None
            expect(line and line.get("state") == "igualada", "line not igualada")

    def case5(self) -> None:
        api, state, rec = self.api, self.state, self.rec
        with rec.step(
            "5", "export-downloaded", "GET /business/exports for October answers a ZIP"
        ) as obs:
            response = api.call(
                "GET", f"/api/v1/business/exports?start={PERIOD[0]}&end={PERIOD[1]}"
            )
            book = zipfile.ZipFile(io.BytesIO(response.raw))
            state["zip"] = {n: book.read(n) for n in book.namelist()}
            (self.rec.out / "export-2026-10.zip").write_bytes(response.raw)
            obs["files"] = sorted(state["zip"])
        z = state.get("zip") or {}
        rows = csv_rows(z["records.csv"]) if "records.csv" in z else []
        manifest = json.loads(z["manifest.json"]) if "manifest.json" in z else {}

        def row_for(total: str) -> list[dict[str, str]]:
            return [r for r in rows if money(r.get("Total")) == total]

        with rec.step(
            "5",
            "case2-row",
            "450.00 row: RNC, NCF, ITBIS, Subtotal empty; Estado excluded; Pago pagado",
        ) as obs:
            need(state, "zip", "c2_activity")
            found = row_for("450.00")
            obs["rows"] = found
            expect(len(found) == 1, f"{len(found)} rows of 450.00")
            row = found[0]
            expect(
                not any(row.get(c) for c in ("RNC", "NCF", "ITBIS", "Subtotal")),
                "fiscal cells filled on an informal purchase",
            )
            expect(
                row.get("Estado") == "excluded" and row.get("Pago") == "pagado",
                f"Estado/Pago {row.get('Estado')}/{row.get('Pago')}",
            )
        with rec.step(
            "5",
            "case1-row",
            "2,826.10 row: NCF B0100000456, Subtotal 2395.00, ITBIS 431.10, DOP, Pago pagado",
        ) as obs:
            need(state, "zip", "c1_activity")
            found = row_for("2826.10")
            obs["rows"] = found
            expect(len(found) == 1, f"{len(found)} rows of 2826.10")
            row = found[0]
            expect(
                row.get("NCF") == PRINTED["R"]["ncf"]
                and money(row.get("Subtotal")) == "2395.00"
                and money(row.get("ITBIS")) == "431.10",
                "fiscal cells differ",
            )
            expect(
                row.get("Moneda") == "DOP" and row.get("Pago") == "pagado",
                f"Moneda/Pago {row.get('Moneda')}/{row.get('Pago')}",
            )
        with rec.step(
            "5",
            "rows-match-saved",
            "every records.csv row is a saved October expense with the same amount and date",
        ) as obs:
            need(state, "zip")
            saved = {
                (e["occurred_on"], money(e["amount"])) for e in self.books.expenses()
            }
            listed = [(r.get("Fecha"), money(r.get("Total"))) for r in rows]
            obs.update(saved=sorted(saved), listed=listed)
            expect(
                set(listed) <= saved,
                f"rows not among saved expenses: {set(listed) - saved}",
            )
        with rec.step(
            "5",
            "personal-out-of-records",
            "the 548.70 personal row is not in records.csv",
            fix=FIX_1417 + " (gap 3b)",
            hop="GET /api/v1/business/exports records.csv",
        ) as obs:
            need(state, "zip", "c3_activity")
            obs["rows"] = row_for("548.70")
            expect(not obs["rows"], "personal purchase listed as a business row")
        with rec.step(
            "5",
            "personal-csv",
            "personal.csv holds the 548.70 row with its original",
            fix=FIX_1417,
            hop="GET /api/v1/business/exports personal.csv",
        ) as obs:
            need(state, "zip", "c3_activity")
            expect("personal.csv" in z, "no personal.csv in the export")
            personal = csv_rows(z["personal.csv"])
            obs["rows"] = personal
            expect(
                any("548.7" in json.dumps(r) for r in personal),
                "548.70 not in personal.csv",
            )
        with rec.step(
            "5",
            "originals-and-manifest",
            "originals/ has the case 1 and 3 sources; manifest hashes match the files",
        ) as obs:
            need(state, "zip")
            originals = [n for n in z if n.startswith("originals/")]
            images = [
                n
                for n in originals
                if n.rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "pdf")
            ]
            wanted = sum(bool(state.get(k)) for k in ("c1_activity", "c3_activity"))
            files = manifest.get("files") or {}
            hashes = (
                files.items()
                if isinstance(files, dict)
                else [(f.get("path"), f.get("sha256")) for f in files]
            )
            bad = [
                p
                for p, h in hashes
                if p in z
                and hashlib.sha256(z[p]).hexdigest()
                != (h if isinstance(h, str) else (h or {}).get("sha256"))
            ]
            sources = manifest.get("sources") or []
            listed = {s.get("file"): s for s in sources}
            unlisted = [n for n in images if n not in listed]
            source_bad = [
                n
                for n, s in listed.items()
                if n in z and hashlib.sha256(z[n]).hexdigest() != s.get("sha256")
            ]
            obs.update(
                originals=originals,
                hash_mismatches=bad,
                source_hash_mismatches=source_bad,
                unlisted_originals=unlisted,
                availability=sorted({s.get("availability") for s in sources}),
            )
            expect(hashes and sources, "manifest lists no files or sources")
            expect(
                len(images) >= wanted,
                f"{len(images)} image originals for {wanted} receipt cases",
            )
            expect(not unlisted, f"originals missing from the manifest: {unlisted}")
            expect(not bad, f"manifest hash mismatch: {bad}")
            expect(not source_bad, f"manifest source hash mismatch: {source_bad}")
            expect(
                all(s.get("availability") == "included" for s in sources),
                "a source is not included",
            )
        with rec.step(
            "5",
            "606-not-filing-ready",
            "submitted false, official validation NOT RUN, no DGII_F_606 TXT",
        ) as obs:
            need(state, "zip")
            summary = json.loads(z.get("dgii/summary.json", b"{}"))
            text = json.dumps(manifest) + json.dumps(summary)
            txt = [n for n in z if n.startswith("dgii/DGII_F_606")]
            obs.update(
                txt=txt,
                submitted=re.findall(r'"submitted": (\w+)', text),
                period_status=summary.get("period_status"),
                forms={
                    k: v
                    for k, v in summary.items()
                    if k.startswith("606") or k == "forms"
                },
            )
            expect(not txt, "a 606 TXT was produced")
            expect(
                obs["submitted"] and set(obs["submitted"]) == {"false"},
                "submitted is not false everywhere",
            )
        with rec.step(
            "5",
            "personal-out-of-606",
            "the personal purchase is excluded from the DGII packet",
            fix=FIX_1417 + " (gap 3c)",
            hop="GET /api/v1/business/exports dgii/summary.json reconciliation",
        ) as obs:
            need(state, "zip", "c3_activity")
            summary = json.loads(z.get("dgii/summary.json", b"{}"))
            hits = [
                r
                for r in summary.get("reconciliation", [])
                if r.get("activity_id") == state["c3_activity"]
            ]
            obs.update(
                records=hits,
                purchase_gross=(summary.get("totals_dop") or {}).get(
                    "purchase_invoice_gross"
                ),
            )
            expect(
                len(hits) == 1, f"{len(hits)} packet records for the personal purchase"
            )
            expect(
                hits[0].get("disposition") == "excluded"
                and hits[0].get("reason") == "personal",
                f"packet disposition {hits[0].get('disposition')}/{hits[0].get('reason')}",
            )

    def fresh_api(self) -> Api:
        fresh = Api(self.api.base, self.api.origin)
        fresh.token, fresh.grant = self.state["sign_in"](), self.api.grant
        return fresh


def ensure_account(api: Api, key: str) -> str:
    accounts = api.get("/business/workspace")["accounts"]
    mine = [
        a
        for a in accounts
        if a.get("currency") == "DOP"
        and a.get("type", "checking") in ("checking", "savings")
    ]
    if mine:
        return mine[0]["id"]
    return api.send("POST", "/business/accounts", ACCOUNT, key=key)["id"]


def import_statement(api: Api, account_id: str, content: bytes, key: str) -> Resp:
    return api.call(
        "POST",
        "/api/v1/business/bank/imports",
        headers={"Idempotency-Key": key},
        files={"statement": ("estado-ensayo.csv", content, "text/csv")},
        data={"account_id": account_id, "reader_id": "sandbox_csv"},
    )


def find_suggestion(
    api: Api, amount: str, activity_id: str | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    body = api.get(
        f"/business/bank/movements?period_start={PERIOD[0]}&period_end={PERIOD[1]}&segment=todas"
    )
    for line in body.get("items", body.get("lines", [])):
        if money(abs(float(line.get("amount", 0)))) != amount:
            continue
        suggestions = line.get("suggestions") or []
        match = next(
            (
                s
                for s in suggestions
                if activity_id is None
                or (s.get("document") or {}).get("activity_id") == activity_id
            ),
            None,
        )
        return line, match
    return None, None


# ---------------------------------------------------------------- seed


class Seeder:
    """Ready-to-demo state for cases 2-5, found before it is written."""

    def __init__(
        self, api: Api, args: argparse.Namespace, files: dict[str, bytes]
    ) -> None:
        self.api, self.args, self.files = api, args, files
        self.created: list[dict[str, Any]] = []
        self.planned: list[str] = []
        self.budget = ReadBudget(
            args.read_cost_ceiling, args.spent_usd, args.reserve_reads
        )

    def act(self, what: str, write, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN001
        if self.args.dry_run:
            self.planned.append(what)
            print(f"  plan     {what}")
            return None
        value = write(*args, **kwargs)
        print(f"  wrote    {what}")
        return value

    def note(
        self,
        text: str,
        facts: dict[str, str],
        receipt_state: str | None,
        approve: bool,
        key: str,
        report: dict[str, Any],
    ) -> None:
        notes = self.api.get("/business/captures?view=all&limit=50")
        items = notes.get("items", notes) if isinstance(notes, dict) else notes
        existing = next(
            (
                n
                for n in items
                if (n.get("text") or (n.get("note") or {}).get("text")) == text
            ),
            None,
        )
        draft_id = existing and (
            existing.get("draft_id") or (existing.get("draft") or {}).get("draft_id")
        )
        if not draft_id:
            made = self.act(
                f"capture note {text!r}",
                lambda: self.api.send(
                    "POST",
                    "/business/captures",
                    {"text": text, "document_type": "recibo"},
                    key=key,
                ),
            )
            if made is None:
                return
            draft_id = made["draft_id"]
        dossier = self.api.get(f"/business/drafts/{draft_id}/dossier")
        report["draft_id"] = draft_id
        patch = {
            "kind": known("expense"),
            "amount": known(facts["amount"]),
            "currency": known("DOP"),
            "occurred_on": known(facts["occurred_on"]),
            "counterparty": known(facts["counterparty"]),
            "funding": known({"kind": "owner_funds"}),
            "business_share": known({"kind": "all"}),
        }
        if receipt_state:
            patch["receipt_state"] = known(receipt_state)
        if dossier["review_state"] == "open" and fact(dossier, "amount") is None:
            self.act(
                f"review facts on draft {draft_id}",
                lambda: self.api.send(
                    "PATCH",
                    f"/business/drafts/{draft_id}/review",
                    {"version": dossier["version"], "facts": patch},
                    key=f"{key}-review",
                ),
            )
            dossier = (
                self.api.get(f"/business/drafts/{draft_id}/dossier")
                if not self.args.dry_run
                else dossier
            )
        if approve and dossier["review_state"] == "open":
            result = self.act(
                f"approve draft {draft_id}",
                lambda: self.api.send(
                    "POST",
                    f"/business/drafts/{draft_id}/approve",
                    {"version": dossier["version"], "action": "record_expense"},
                    key=f"{key}-approve",
                ),
            )
            dossier = (
                self.api.get(f"/business/drafts/{draft_id}/dossier")
                if result
                else dossier
            )
        report.update(
            review_state=dossier["review_state"],
            blockers=dossier["blockers"],
            activity_id=(dossier.get("approval_result") or {}).get("activity_id"),
        )

    def receipt(
        self, key: str, idem: str, report: dict[str, Any]
    ) -> dict[str, Any] | None:
        name, media_type, digest = PACK[key]
        mine = [
            r
            for r in Books(self.api).receipts()
            if r.get("filename") == name and r.get("channel") == "web"
        ]
        if mine:
            found = mine[0]
        else:
            self.budget.take(f"reading {name}")
            found = self.act(
                f"upload {name}",
                lambda: upload(self.api, self.files[key], name, media_type, idem),
            )
            if found is None:
                return None
        found = read_receipt(self.api, found["id"])
        report.update(
            receipt_id=found["id"],
            draft_id=found.get("draft_id"),
            status=found.get("status"),
            merchant=found.get("merchant"),
            amount=found.get("amount"),
        )
        return found

    def run(self) -> dict[str, Any]:
        api = self.api
        out: dict[str, Any] = {"2": {}, "3": {}, "4": {}, "5": {}}
        name = api.get("/business/space/name")
        out["business_name"] = {
            "name": name.get("name"),
            "name_required": name.get("name_required"),
        }
        if name.get("name_required"):
            if not self.args.business_name:
                raise SystemExit(
                    "refusing: the Business needs a saved name; pass --business-name"
                )
            self.act(
                f"save Business name {self.args.business_name!r}",
                lambda: api.send(
                    "PATCH",
                    "/business/space/name",
                    {"space_id": name["id"], "name": self.args.business_name},
                ),
            )
        reading = api.get("/business/receipt-reading?language=es-419")
        out["reading"] = {"enabled_before": reading["enabled"]}
        if not reading["enabled"]:
            backlog = [
                r for r in Books(api).receipts() if r.get("status") in ("saved", "queued")
            ]
            out["reading"]["unread_backlog"] = len(backlog)
            # Turning reading on reads every saved, unread receipt of the Business.
            self.budget.take(
                "the unread backlog read when reading turns on", len(backlog)
            )
            if not self.args.enable_reading:
                raise SystemExit(
                    "refusing: receipt reading is off for this Business; pass --enable-reading to turn it on"
                )
            self.act(
                "turn receipt reading on",
                lambda: api.send(
                    "POST",
                    "/business/receipt-reading",
                    {
                        "enabled": True,
                        "scope_version": reading["scope_version"],
                        "disclosure_token": reading["disclosure_token"],
                        "language": "es-419",
                    },
                    key="jose-seed-v1-reading",
                ),
            )

        print(
            "case 2: informal cash purchase captured, facts filled, receipt state and approval left for the demo"
        )
        self.note(
            CASE2_NOTE, CASE2_FACTS, None, False, "jose-seed-v1-case2-note", out["2"]
        )

        print("case 3: 03-farmacia read, funding set, ready to mark personal")
        receipt = self.receipt("P", "jose-seed-v1-case3-upload", out["3"])
        if receipt and receipt.get("draft_id"):
            dossier = api.get(f"/business/drafts/{receipt['draft_id']}/dossier")
            if dossier["review_state"] == "open" and fact(dossier, "funding") is None:
                self.act(
                    f"set funding owner_funds on draft {receipt['draft_id']}",
                    lambda: api.send(
                        "PATCH",
                        f"/business/drafts/{receipt['draft_id']}/review",
                        {
                            "version": dossier["version"],
                            "facts": {"funding": known({"kind": "owner_funds"})},
                        },
                        key="jose-seed-v1-case3-funding",
                    ),
                )
                dossier = (
                    api.get(f"/business/drafts/{receipt['draft_id']}/dossier")
                    if not self.args.dry_run
                    else dossier
                )
            out["3"].update(
                personal=dossier.get("personal"),
                review_state=dossier["review_state"],
                blockers=blocker_fields(dossier),
            )
        elif self.args.dry_run:
            self.act(
                "after the read: set funding owner_funds on the 03 draft", lambda: None
            )

        print(
            "case 4: DOP account, statement imported, 01-colmado recorded and its match pending"
        )
        accounts = [
            a
            for a in api.get("/business/workspace")["accounts"]
            if a.get("currency") == "DOP"
        ]
        account_id = (
            accounts[0]["id"]
            if accounts
            else self.act(
                "create account Cuenta Ensayo DOP",
                lambda: api.send(
                    "POST", "/business/accounts", ACCOUNT, key="jose-seed-v1-account"
                )["id"],
            )
        )
        out["4"]["account_id"] = account_id
        receipt = self.receipt("C", "jose-seed-v1-case4-upload", out["4"])
        if receipt and receipt.get("draft_id") and account_id:
            draft_id = receipt["draft_id"]
            dossier = api.get(f"/business/drafts/{draft_id}/dossier")
            if dossier["review_state"] == "open":
                if blocker_fields(dossier):
                    self.act(
                        f"review 01-colmado draft {draft_id}: funding bank account, share all",
                        lambda: api.send(
                            "PATCH",
                            f"/business/drafts/{draft_id}/review",
                            {
                                "version": dossier["version"],
                                "facts": {
                                    "funding": known(
                                        {
                                            "kind": "business_account",
                                            "account_id": account_id,
                                        }
                                    ),
                                    "business_share": known({"kind": "all"}),
                                },
                            },
                            key="jose-seed-v1-case4-review",
                        ),
                    )
                    dossier = (
                        api.get(f"/business/drafts/{draft_id}/dossier")
                        if not self.args.dry_run
                        else dossier
                    )
                self.act(
                    f"approve 01-colmado draft {draft_id}",
                    lambda: api.send(
                        "POST",
                        f"/business/drafts/{draft_id}/approve",
                        {"version": dossier["version"], "action": "record_expense"},
                        key="jose-seed-v1-case4-approve",
                    ),
                )
                dossier = (
                    api.get(f"/business/drafts/{draft_id}/dossier")
                    if not self.args.dry_run
                    else dossier
                )
            out["4"]["activity_id"] = (dossier.get("approval_result") or {}).get(
                "activity_id"
            )
            # The status recorded at upload predates the approval above.
            out["4"]["status"] = api.get(f"/business/receipts/{receipt['id']}").get(
                "status"
            )
        elif self.args.dry_run:
            self.act(
                "after the read: review (funding bank account, share all) and approve the 01-colmado draft",
                lambda: None,
            )
        if not account_id and self.args.dry_run:
            self.act(
                "import seed statement (S.csv + COLMADO LA ESQUINA line)", lambda: None
            )
        if account_id and find_suggestion(api, "716.85", None)[0] is None:
            imported = self.act(
                "import seed statement (S.csv + COLMADO LA ESQUINA line)",
                lambda: import_statement(
                    api, account_id, SEED_STATEMENT, "jose-seed-v1-statement"
                ),
            )
            if imported is not None:
                out["4"]["import"] = {
                    "status": imported.status,
                    **{
                        k: imported.body.get(k)
                        for k in ("inserted_count", "unchanged_count", "created")
                    },
                }
        if account_id:
            line, suggestion = find_suggestion(api, "716.85", out["4"].get("activity_id"))
            out["4"].update(
                line_state=line and line.get("state"),
                suggestion_id=suggestion and suggestion.get("id"),
                suggestion_confidence=suggestion and suggestion.get("confidence"),
            )

        print(
            "case 5: one approved informal purchase in October beside the recorded 01-colmado"
        )
        self.note(
            SEED_INFORMAL_NOTE,
            SEED_INFORMAL_FACTS,
            "informal_receipt",
            True,
            "jose-seed-v1-case5-note",
            out["5"],
        )
        if self.args.profile == "alive":
            out["alive"] = Alive(self, account_id).run()
        out["read_budget"] = {
            "reads_caused": self.budget.reads,
            "reserved_reads": self.budget.reserve,
            "ceiling_usd_per_read": self.budget.ceiling,
            "already_spent_usd": self.budget.spent,
            "projected_usd": self.budget.projected(),
            "stop_usd": self.budget.stop,
        }
        if self.args.profile == "alive":
            out["planned_counts"] = planned_counts()
        if not self.args.dry_run:
            out["5"]["october_expenses"] = [
                {k: e[k] for k in ("id", "merchant", "amount", "occurred_on")}
                for e in Books(api).expenses()
            ]
            archive = zipfile.ZipFile(
                io.BytesIO(
                    api.call(
                        "GET",
                        f"/api/v1/business/exports?start={PERIOD[0]}&end={PERIOD[1]}",
                    ).raw
                )
            )
            out["5"]["export_rows"] = [
                {
                    k: r.get(k)
                    for k in (
                        "Fecha",
                        "Proveedor",
                        "NCF",
                        "Total",
                        "Moneda",
                        "Estado",
                        "Pago",
                    )
                }
                for r in csv_rows(archive.read("records.csv"))
            ]
        if self.args.profile == "alive" and not self.args.dry_run:
            out["screen_counts"] = screen_counts(api)
        out["planned"] = self.planned
        return out


# ---------------------------------------------------------------- seed --profile alive


@dataclass(frozen=True)
class AliveRow:
    """One synthetic operating record, entered by hand through a note.

    ``end``: open (note left in Notas en revisión), approved, personal.
    ``paid``: month-close payment method once settled; None stays pendiente.
    ``bank``: matched (statement line confirmed), suggested (left offered), None (no line)."""

    tag: str
    kind: str
    occurred_on: str
    counterparty: str
    amount: str
    currency: str = "DOP"
    funding: str = "owner"
    receipt_state: str | None = "informal_receipt"
    end: str = "approved"
    paid: str | None = None
    bank: str | None = None

    @property
    def marker(self) -> str:
        return f"(ensayo {self.tag})"

    @property
    def text(self) -> str:
        symbol = "US$" if self.currency == "USD" else "RD$"
        day = "/".join(reversed(self.occurred_on.split("-")))
        verb = "Cobro" if self.kind == "income" else "Pago"
        return f"{verb}: {self.counterparty}, {symbol} {float(self.amount):,.2f}, {day}. {self.marker}"


# Aug-Oct 2026 for an invented colmado. No real names, RNCs or NCFs; no fiscal
# fact on a hand-entered row. October avoids the demo totals (450.00, 2,826.10,
# 548.70, 716.85, 365.80) and income stays out of October so the rehearsal's
# records.csv-against-expenses check keeps its meaning.
ALIVE_ROWS = (
    AliveRow(
        "A01",
        "expense",
        "2026-08-02",
        "Distribuidora de Víveres El Progreso",
        "8450.00",
        funding="bank",
        bank="matched",
    ),
    AliveRow(
        "A02",
        "expense",
        "2026-08-05",
        "Panadería La Espiga Dorada",
        "1320.00",
        paid="efectivo",
    ),
    AliveRow(
        "A03",
        "expense",
        "2026-08-09",
        "Agua Purificada Manantial del Valle",
        "960.00",
        receipt_state="no_receipt",
        paid="efectivo",
    ),
    AliveRow(
        "A04",
        "income",
        "2026-08-12",
        "Ventas de la semana (cuadre de caja)",
        "18500.00",
        funding="bank",
        receipt_state=None,
    ),
    AliveRow(
        "A05",
        "expense",
        "2026-08-15",
        "Alquiler del local, agosto",
        "15000.00",
        funding="bank",
        receipt_state="no_receipt",
        bank="matched",
    ),
    AliveRow(
        "A06",
        "expense",
        "2026-08-20",
        "Embutidos y Lácteos Santa Clara",
        "6275.50",
        funding="bank",
        bank="matched",
    ),
    AliveRow(
        "A07",
        "expense",
        "2026-08-22",
        "Suscripción del programa de inventario",
        "29.00",
        currency="USD",
        receipt_state="no_receipt",
        paid="tarjeta",
    ),
    AliveRow(
        "A08",
        "income",
        "2026-08-26",
        "Ventas de la semana (cuadre de caja)",
        "21340.00",
        funding="bank",
        receipt_state=None,
    ),
    AliveRow(
        "A09",
        "expense",
        "2026-08-28",
        "Servicio de luz, agosto",
        "4850.00",
        funding="bank",
        receipt_state=None,
        bank="matched",
    ),
    AliveRow(
        "B01",
        "expense",
        "2026-09-01",
        "Distribuidora de Víveres El Progreso",
        "9120.00",
        funding="bank",
        bank="matched",
    ),
    AliveRow(
        "B02",
        "expense",
        "2026-09-04",
        "Panadería La Espiga Dorada",
        "1410.00",
        paid="efectivo",
    ),
    AliveRow(
        "B03",
        "income",
        "2026-09-08",
        "Ventas de la semana (cuadre de caja)",
        "19750.00",
        funding="bank",
        receipt_state=None,
    ),
    AliveRow(
        "B04",
        "expense",
        "2026-09-10",
        "Alquiler del local, septiembre",
        "15000.00",
        funding="bank",
        receipt_state="no_receipt",
        bank="matched",
    ),
    AliveRow(
        "B05",
        "expense",
        "2026-09-14",
        "Refrigeración Hermanos Ensayo, reparación de nevera",
        "3500.00",
        receipt_state=None,
    ),
    AliveRow(
        "B06",
        "expense",
        "2026-09-16",
        "Supermercado, compra de la casa",
        "2180.00",
        end="personal",
    ),
    AliveRow(
        "B07",
        "expense",
        "2026-09-18",
        "Embutidos y Lácteos Santa Clara",
        "5980.25",
        funding="bank",
        bank="suggested",
    ),
    AliveRow(
        "B08",
        "expense",
        "2026-09-22",
        "Suscripción del programa de inventario",
        "29.00",
        currency="USD",
        receipt_state="no_receipt",
        paid="tarjeta",
    ),
    AliveRow(
        "B09",
        "income",
        "2026-09-24",
        "Ventas de la semana (cuadre de caja)",
        "22610.00",
        funding="bank",
        receipt_state=None,
    ),
    AliveRow(
        "B10",
        "expense",
        "2026-09-27",
        "Servicio de luz, septiembre",
        "5120.00",
        funding="bank",
        receipt_state=None,
    ),
    AliveRow(
        "C01",
        "expense",
        "2026-10-02",
        "Distribuidora de Víveres El Progreso",
        "8990.00",
        funding="bank",
        bank="matched",
    ),
    AliveRow(
        "C02",
        "expense",
        "2026-10-05",
        "Panadería La Espiga Dorada",
        "1275.00",
        paid="efectivo",
    ),
    AliveRow(
        "C03",
        "expense",
        "2026-10-13",
        "Embutidos y Lácteos Santa Clara",
        "6410.75",
        funding="bank",
    ),
    AliveRow(
        "C04",
        "income",
        "2026-10-14",
        "Ventas de la semana (cuadre de caja)",
        "20880.00",
        funding="bank",
        receipt_state=None,
        end="open",
    ),
    AliveRow(
        "C05",
        "expense",
        "2026-10-22",
        "Alojamiento de la tienda en línea",
        "12.00",
        currency="USD",
        receipt_state="no_receipt",
    ),
    AliveRow(
        "C06",
        "expense",
        "2026-10-24",
        "Gas propano para la cocina",
        "1850.00",
        paid="efectivo",
    ),
    AliveRow(
        "C07",
        "expense",
        "2026-10-25",
        "Fundas y envases desechables",
        "980.00",
        end="open",
    ),
)
# Statement lines beside the rows: income deposits and monthly bank charges.
ALIVE_BANK_EXTRA = (
    ("2026-08-12", "DEPOSITO VENTAS ENSAYO", "18500.00", "open"),
    ("2026-08-26", "DEPOSITO VENTAS ENSAYO", "21340.00", "open"),
    ("2026-08-31", "COMISION MANEJO CUENTA ENSAYO", "-175.00", "cargo_banco"),
    ("2026-09-08", "DEPOSITO VENTAS ENSAYO", "19750.00", "open"),
    ("2026-09-24", "DEPOSITO VENTAS ENSAYO", "22610.00", "open"),
    ("2026-09-30", "COMISION MANEJO CUENTA ENSAYO", "-175.00", "cargo_banco"),
    ("2026-10-14", "DEPOSITO VENTAS ENSAYO", "20880.00", "open"),
)
# Numbered pack files the alive profile uploads (each is one model read).
# 02 is never uploaded: case 1 sends it live over WhatsApp.
ALIVE_PACK = {
    "U": (
        "07-compra-unica.csv",
        "text/csv",
        "a0b36853fce90f4ff376f778ade0147dbdbed6577529d8b778a44af29fbda146",
        "approve",
    ),
    "G": (
        "04-gasolinera-foto-rotada.jpg",
        "image/jpeg",
        "40dd76246a2f00b42b6b20f64c712620c4d450e0fd3e23f17cfae5dc6d78c852",
        "review",
    ),
    "V": (
        "08-varias-compras.csv",
        "text/csv",
        "cfe572e744451d256440f06b429b44becf29db98b4d045914957426ba10661b3",
        "attention",
    ),
    "B": (
        "13-borroso-ilegible.jpg",
        "image/jpeg",
        "a54dbd80c6d974418c4ba1a018fadb95f984ee3cc0c9c26dc40a4ecc5cff44e6",
        "attention",
    ),
}
PRINTED.update(
    {
        "U": {
            "merchant": "Ferretería El Tornillo",
            "occurred_on": "2026-10-06",
            "subtotal": "1180.00",
            "itbis": "212.40",
            "total": "1392.40",
            "rnc": "1-23-45678-9",
            "ncf": "B0100000111",
        },
        "G": {
            "merchant": "GASOLINERA DEL ESTE",
            "occurred_on": "2026-10-11",
            "subtotal": "2550.00",
            "itbis": "459.00",
            "total": "3009.00",
            "rnc": "1-23-45678-9",
            "ncf": "B0100000321",
        },
    }
)
# 08 prints five purchases (LEEME: "varias compras"); 13 is unreadable.
PRINTED_ROWS = {
    "V": [
        ("2026-10-01", "Colmado La Esquina", "1260.50"),
        ("2026-10-03", "Gasolinera Del Este", "2000.00"),
        ("2026-10-05", "Farmacia San Rafael", "615.00"),
        ("2026-10-08", "Restaurante Doña Mery", "1485.00"),
        ("2026-10-10", "Ferretería El Tornillo", "2395.00"),
    ]
}
ALIVE_CUSTOMERS = (
    ("Cafetería Ensayo Los Robles", "compras@cafeteria-ensayo.example.com"),
    ("Hotel Ensayo Brisas del Mar", "cuentas@hotel-ensayo.example.com"),
    ("Colegio Ensayo San Marcos", "administracion@colegio-ensayo.example.com"),
)
# Incomplete on purpose (no date, or an item without price): nothing is prepared or issued.
ALIVE_INVOICES = (
    ("F01", 0, [("1", "Bandejas de picadera para 40 personas", "2", "3500.00")], ""),
    ("F02", 1, [("1", "Desayunos del personal, octubre", "30", "")], "2026-10-20"),
)
ALIVE_KEY = "jose-seed-alive-v1"


def alive_statement() -> bytes:
    lines = [("date", "name", "amount", "iso_currency_code", "pending")]
    for row in ALIVE_ROWS:
        if row.bank:
            name = row.counterparty.upper().replace(",", "")
            lines.append((row.occurred_on, name, f"-{row.amount}", "DOP", "false"))
    for day, name, amount, _ in ALIVE_BANK_EXTRA:
        lines.append((day, name, amount, "DOP", "false"))
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(lines)
    return out.getvalue().encode()


@dataclass
class ReadBudget:
    """Model reads cost money and the API does not report their price, so each
    read the seed causes is counted at a ceiling price and refused past the stop."""

    ceiling: float
    spent: float
    reserve: int
    stop: float = 0.75
    reads: int = 0

    def projected(self, more: int = 0) -> float:
        return round(self.spent + (self.reads + more + self.reserve) * self.ceiling, 4)

    def take(self, what: str, count: int = 1) -> None:
        if self.projected(count) > self.stop:
            raise SystemExit(
                f"refusing: {what} would bring projected read spend to ${self.projected(count):.2f} (stop ${self.stop:.2f})"
            )
        self.reads += count


class Alive:
    """Three months of believable history on top of the demo seed. Every write
    is found first (note marker, pack filename, statement line, customer name,
    invoice note), so a rerun writes nothing."""

    def __init__(self, seeder: Seeder, account_id: str | None) -> None:
        self.s, self.api, self.account_id = seeder, seeder.api, account_id
        self.out: dict[str, Any] = {
            "rows": {},
            "uploads": {},
            "bank": {},
            "invoicing": {},
        }

    def key(self, name: str) -> str:
        return f"{ALIVE_KEY}-{name}"

    def dossier(self, draft_id: str) -> dict[str, Any]:
        return self.api.get(f"/business/drafts/{draft_id}/dossier")

    def find_note(self, row: AliveRow) -> str | None:
        page = self.api.get(
            "/business/captures", params={"q": row.marker, "view": "all", "limit": 50}
        )
        return next(
            (n["draft_id"] for n in page.get("items", []) if n.get("text") == row.text),
            None,
        )

    def facts(self, row: AliveRow) -> dict[str, Any]:
        funding = (
            {"kind": "business_account", "account_id": self.account_id}
            if row.funding == "bank"
            else {"kind": "owner_funds"}
        )
        patch = {
            "kind": known(row.kind),
            "amount": known(row.amount),
            "currency": known(row.currency),
            "occurred_on": known(row.occurred_on),
            "counterparty": known(row.counterparty),
            "funding": known(funding),
            "business_share": known({"kind": "all"}),
        }
        if row.receipt_state:
            patch["receipt_state"] = known(row.receipt_state)
        return patch

    def row(self, row: AliveRow) -> None:
        report: dict[str, Any] = {"end": row.end}
        self.out["rows"][row.tag] = report
        draft_id = self.find_note(row)
        if not draft_id:
            made = self.s.act(
                f"note {row.tag} {row.text!r}",
                self.api.send,
                "POST",
                "/business/captures",
                {"text": row.text, "document_type": "recibo"},
                key=self.key(f"{row.tag}-note"),
            )
            if made is None:
                for step in (
                    "review facts",
                    "mark personal" if row.end == "personal" else None,
                    None if row.end == "open" else "approve",
                    f"settle pagado {row.paid}" if row.paid else None,
                ):
                    if step:
                        self.s.act(f"{step} {row.tag}", lambda: None)
                return
            draft_id = made["draft_id"]
        report["draft_id"] = draft_id
        dossier = self.dossier(draft_id)
        if dossier["review_state"] == "open" and fact(dossier, "amount") is None:
            if row.funding == "bank" and not self.account_id:
                raise SystemExit("refusing: a bank-funded row needs the Business account")
            self.s.act(
                f"review {row.tag} facts",
                self.api.send,
                "PATCH",
                f"/business/drafts/{draft_id}/review",
                {"version": dossier["version"], "facts": self.facts(row)},
                key=self.key(f"{row.tag}-review"),
            )
            dossier = self.dossier(draft_id)
        if (
            row.end == "personal"
            and dossier["review_state"] == "open"
            and not dossier.get("personal")
        ):
            self.s.act(
                f"mark {row.tag} personal",
                self.api.send,
                "POST",
                f"/business/drafts/{draft_id}/personal",
                {"version": dossier["version"], "personal": True},
                key=self.key(f"{row.tag}-personal"),
            )
            dossier = self.dossier(draft_id)
        if row.end != "open" and dossier["review_state"] == "open":
            self.s.act(
                f"approve {row.tag}",
                self.api.send,
                "POST",
                f"/business/drafts/{draft_id}/approve",
                {
                    "version": dossier["version"],
                    "action": "record_income"
                    if row.kind == "income"
                    else "record_expense",
                },
                key=self.key(f"{row.tag}-approve"),
            )
            dossier = self.dossier(draft_id)
        report.update(
            review_state=dossier["review_state"],
            blockers=blocker_fields(dossier),
            activity_id=(dossier.get("approval_result") or {}).get("activity_id"),
        )

    def settle(self, rows: list[tuple[AliveRow, str | None]]) -> None:
        """Cash and card purchases paid in month close; bank-matched ones are settled by the match."""

        for month in sorted({row.occurred_on[:7] for row, _ in rows}):
            payables = {
                p["activity_id"]: p
                for p in self.api.get(f"/business/month-close?month={month}")[
                    "cuentas_por_pagar"
                ]
            }
            for row, activity_id in rows:
                if row.occurred_on[:7] != month or activity_id not in payables:
                    continue
                if payables[activity_id].get("status") != "pendiente":
                    continue
                self.s.act(
                    f"settle {row.tag} pagado {row.paid}",
                    self.api.send,
                    "PATCH",
                    f"/business/month-close/documents/{activity_id}",
                    {
                        "status": "pagado",
                        "settled_on": row.occurred_on,
                        "payment_method": row.paid,
                    },
                )

    def uploads(self) -> None:
        receipts = Books(self.api).receipts()
        for key, (name, media_type, digest, end) in ALIVE_PACK.items():
            report: dict[str, Any] = {"end": end}
            self.out["uploads"][name] = report
            found = next(
                (
                    r
                    for r in receipts
                    if r.get("filename") == name and r.get("channel") == "web"
                ),
                None,
            )
            if found is None:
                content = (self.s.args.receipts_dir / name).read_bytes()
                if hashlib.sha256(content).hexdigest() != digest:
                    raise SystemExit(
                        f"{name} is not the synthetic pack file (sha256 differs)"
                    )
                self.s.budget.take(f"reading {name}")
                found = self.s.act(
                    f"upload {name} (one model read)",
                    self.upload,
                    content,
                    name,
                    media_type,
                    self.key(f"upload-{key}"),
                )
                if found is None:
                    continue
            found = read_receipt(self.api, found["id"])
            report.update(
                receipt_id=found["id"],
                status=found.get("status"),
                draft_id=found.get("draft_id"),
            )
            if end != "approve" or not found.get("draft_id"):
                continue
            draft_id = found["draft_id"]
            dossier = self.dossier(draft_id)
            if dossier["review_state"] == "open" and blocker_fields(dossier):
                self.s.act(
                    f"review {name}: funding owner, share all",
                    self.api.send,
                    "PATCH",
                    f"/business/drafts/{draft_id}/review",
                    {
                        "version": dossier["version"],
                        "facts": {
                            "funding": known({"kind": "owner_funds"}),
                            "business_share": known({"kind": "all"}),
                        },
                    },
                    key=self.key(f"upload-{key}-review"),
                )
                dossier = self.dossier(draft_id)
            if dossier["review_state"] == "open" and not blocker_fields(dossier):
                self.s.act(
                    f"approve {name}",
                    self.api.send,
                    "POST",
                    f"/business/drafts/{draft_id}/approve",
                    {"version": dossier["version"], "action": "record_expense"},
                    key=self.key(f"upload-{key}-approve"),
                )
                dossier = self.dossier(draft_id)
            activity_id = (dossier.get("approval_result") or {}).get("activity_id")
            report.update(review_state=dossier["review_state"], activity_id=activity_id)
            if activity_id:
                printed = PRINTED[key]
                self.settle(
                    [
                        (
                            AliveRow(
                                key,
                                "expense",
                                printed["occurred_on"],
                                name,
                                printed["total"],
                                paid="efectivo",
                            ),
                            activity_id,
                        )
                    ]
                )

    def upload(self, content: bytes, name: str, media_type: str, key: str) -> Any:
        """Document POSTs are limited to five a minute per person: wait out a 429."""

        headers = {
            "Content-Type": media_type,
            "Idempotency-Key": key,
            "X-Document-Filename": name,
        }
        for _ in range(4):
            sent = self.api.call(
                "POST",
                "/api/v1/business/receipts",
                content=content,
                headers=dict(headers),
                ok=False,
            )
            if sent.status != 429:
                break
            wait = int(sent.headers.get("retry-after") or 60) + 1
            print(f"  wait     {wait}s for the upload rate limit")
            time.sleep(wait)
        expect(200 <= sent.status < 300, f"upload {name} answered {sent.status}")
        return sent.body

    def movements(self, month: str) -> list[dict[str, Any]]:
        start = f"{month}-01"
        end = f"{month}-{31 if month.endswith(('08', '10')) else 30}"
        return self.api.get(
            f"/business/bank/movements?period_start={start}&period_end={end}&segment=todas"
        ).get("items", [])

    def bank(self) -> None:
        if not self.account_id:
            self.s.act(
                "import the alive statement (after the account exists)", lambda: None
            )
            return
        first = ALIVE_ROWS[0]
        present = any(
            line.get("occurred_on") == first.occurred_on
            and line.get("amount") == f"-{first.amount}"
            for line in self.movements(first.occurred_on[:7])
        )
        if not present:
            imported = self.s.act(
                f"import the alive statement ({len(alive_statement().splitlines()) - 1} lines, Aug-Oct)",
                import_statement,
                self.api,
                self.account_id,
                alive_statement(),
                self.key("statement"),
            )
            if imported is None:
                return
            self.out["bank"]["import"] = {
                "status": imported.status,
                **{
                    k: imported.body.get(k)
                    for k in ("inserted_count", "unchanged_count", "created")
                },
            }
        activities = {tag: r.get("activity_id") for tag, r in self.out["rows"].items()}
        for month in ("2026-08", "2026-09", "2026-10"):
            lines = self.movements(month)
            for row in ALIVE_ROWS:
                if row.bank != "matched" or row.occurred_on[:7] != month:
                    continue
                for line in lines:
                    suggestion = next(
                        (
                            s
                            for s in line.get("suggestions") or []
                            if (s.get("document") or {}).get("activity_id")
                            == activities.get(row.tag)
                        ),
                        None,
                    )
                    if suggestion and line.get("state") == "sugerencia":
                        self.s.act(
                            f"confirm the statement match for {row.tag}",
                            self.api.call,
                            "POST",
                            f"/api/v1/business/bank/suggestions/{suggestion['id']}/confirm",
                            headers={"Idempotency-Key": self.key(f"{row.tag}-confirm")},
                        )
            for day, _name, amount, end in ALIVE_BANK_EXTRA:
                if end != "cargo_banco" or day[:7] != month:
                    continue
                line = next(
                    (
                        x
                        for x in lines
                        if x.get("occurred_on") == day
                        and x.get("amount") == amount
                        and x.get("state") == "falta_comprobante"
                    ),
                    None,
                )
                if line:
                    self.s.act(
                        f"mark the {day} bank charge as no receipt needed (cargo_banco)",
                        self.api.call,
                        "PUT",
                        f"/api/v1/business/bank/movements/{line['id']}/disposition",
                        json={"reason": "cargo_banco"},
                        headers={"Idempotency-Key": self.key(f"charge-{day}")},
                    )

    def invoicing(self) -> None:
        listed = self.api.call(
            "GET", "/api/v1/business/customers?page_size=100", ok=False
        )
        if listed.status == 404:
            self.out["invoicing"] = {
                "skipped": "invoicing is off on this API (business_invoicing_unavailable)"
            }
            print("  skip     customers and invoice drafts: invoicing is off on this API")
            return
        expect(listed.status == 200, f"customers answered {listed.status}")
        have = {c["data"]["name"]: c["id"] for c in listed.body["items"]}
        ids = []
        for index, (name, email) in enumerate(ALIVE_CUSTOMERS):
            if name not in have:
                made = self.s.act(
                    f"customer {name!r}",
                    self.api.send,
                    "POST",
                    "/business/customers",
                    {"data": {"name": name, "email": email}},
                    key=self.key(f"customer-{index}"),
                )
                have[name] = made and made["id"]
            ids.append(have[name])
        invoices = self.api.get("/business/invoices?page_size=100")["items"]
        notes = {i["data"].get("notes") for i in invoices}
        for tag, customer, items, issued_on in ALIVE_INVOICES:
            note = f"Borrador de prueba (ensayo {tag})"
            if note in notes or ids[customer] is None:
                continue
            self.s.act(
                f"incomplete invoice draft {tag} (never prepared or issued)",
                self.api.send,
                "POST",
                "/business/invoices",
                {
                    "data": {
                        "customer_id": ids[customer],
                        "customer_input": {
                            "name": ALIVE_CUSTOMERS[customer][0],
                            "email": ALIVE_CUSTOMERS[customer][1],
                        },
                        "currency": "DOP",
                        "issued_on": issued_on,
                        "items": [
                            {"id": i, "description": d, "quantity": q, "price": p}
                            for i, d, q, p in items
                        ],
                        "notes": note,
                    }
                },
                key=self.key(f"invoice-{tag}"),
            )
        self.out["invoicing"] = {"customers": len(ids), "drafts": len(ALIVE_INVOICES)}

    def run(self) -> dict[str, Any]:
        print("alive: Aug-Oct 2026 notes entered by hand, approved, settled")
        for row in ALIVE_ROWS:
            self.row(row)
        self.settle(
            [
                (row, self.out["rows"][row.tag].get("activity_id"))
                for row in ALIVE_ROWS
                if row.paid and row.funding == "owner"
            ]
        )
        print(
            "alive: numbered pack uploads (07 approved, 04 to review, 08 and 13 need attention)"
        )
        self.uploads()
        print("alive: Aug-Oct statement, matches confirmed, bank charges marked")
        self.bank()
        print("alive: invoicing customers and incomplete drafts")
        self.invoicing()
        return self.out


def planned_counts() -> dict[str, Any]:
    """What the alive profile adds, by screen, from its own table."""

    rows = ALIVE_ROWS
    recorded = [r for r in rows if r.end != "open"]
    by_month: dict[str, dict[str, int]] = {}
    for r in recorded:
        cell = by_month.setdefault(
            r.occurred_on[:7], {"expense": 0, "income": 0, "personal": 0}
        )
        cell["personal" if r.end == "personal" else r.kind] += 1
    statement = alive_statement().splitlines()[1:]
    return {
        "bandeja": {
            "notes_open": sum(r.end == "open" for r in rows),
            "uploads": {v[0]: v[3] for v in ALIVE_PACK.values()},
        },
        "registros_recorded_by_month": by_month,
        "registros_usd_rows": sum(r.currency == "USD" for r in recorded),
        "month_close": {
            "settled_by_hand": sum(bool(r.paid) for r in recorded) + 1,
            "settled_by_bank_match": sum(r.bank == "matched" for r in recorded),
            "left_pendiente": sum(
                r.kind == "expense"
                and r.end == "approved"
                and not r.paid
                and r.bank != "matched"
                for r in recorded
            ),
            "without_receipt_state": sum(
                r.receipt_state is None and r.kind == "expense" for r in recorded
            ),
        },
        "bank_lines": {
            "total": len(statement),
            "matched": sum(r.bank == "matched" for r in rows),
            "suggested": sum(r.bank == "suggested" for r in rows),
            "cargo_banco": sum(e[3] == "cargo_banco" for e in ALIVE_BANK_EXTRA),
            "open_deposits": sum(e[3] == "open" for e in ALIVE_BANK_EXTRA),
        },
        "facturacion": {
            "customers": len(ALIVE_CUSTOMERS),
            "incomplete_drafts": len(ALIVE_INVOICES),
        },
        "model_reads": len(ALIVE_PACK),
    }


def screen_counts(api: Api) -> dict[str, Any]:
    """The Business as each screen reads it, from the server."""

    receipts = Books(api).receipts()
    statuses: dict[str, int] = {}
    for r in receipts:
        statuses[r.get("status")] = statuses.get(r.get("status"), 0) + 1
    notes = api.get("/business/captures", params={"view": "inbox", "limit": 50})
    months = {}
    for month, last in (("2026-08", "31"), ("2026-09", "30"), ("2026-10", "31")):
        close = api.get(f"/business/month-close?month={month}")
        payables = close.get("cuentas_por_pagar", [])
        overview = api.get(f"/business/overview?from={month}-01&to={month}-{last}")
        moves = api.get(
            f"/business/bank/movements?period_start={month}-01&period_end={month}-{last}&segment=todas"
        ).get("counts", {})
        months[month] = {
            "expenses": len(
                api.get(f"/business/expenses?from={month}-01&to={month}-{last}")["items"]
            ),
            "overview_totals": overview.get("totals"),
            "payables_pendiente": len(payables),
            "receipts_by_status": [
                c.get("by_status", {}).get("receipts")
                for c in close.get("currencies", [])
            ],
            "bank": {
                k: moves.get(k)
                for k in (
                    "movimientos",
                    "igualadas",
                    "sugerencias",
                    "falta_comprobante",
                    "no_lleva_comprobante",
                )
            },
        }
    open_items = api.get("/business/open-items")
    activity = api.call("GET", "/api/v1/business/activity?limit=100", ok=False)
    customers = api.call("GET", "/api/v1/business/customers?page_size=100", ok=False)
    invoices = api.call("GET", "/api/v1/business/invoices?page_size=100", ok=False)
    return {
        "bandeja": {
            "receipts_by_status": statuses,
            "notes_in_review": len(notes.get("items", [])),
        },
        "months": months,
        "open_items": {
            k: v.get("count")
            for k, v in open_items.items()
            if isinstance(v, dict) and "count" in v
        },
        "actividad_items": len((activity.body or {}).get("items", []))
        if activity.status == 200
        else f"status {activity.status}",
        "facturacion": {
            "customers": customers.body.get("total")
            if customers.status == 200
            else f"status {customers.status}",
            "invoices": invoices.body.get("total")
            if invoices.status == 200
            else f"status {invoices.status}",
        },
    }


# ---------------------------------------------------------------- run


def run(args: argparse.Namespace) -> None:
    if args.target == "staging":
        require_staging_host(args.api, "--api")
        require_staging_host(args.web, "--web")
    out = args.evidence.resolve()
    out.mkdir(parents=True, exist_ok=True)
    local = args.target == "local"
    env: dict[str, str] = {}
    if local:
        env = load_env_file(args.env_file)
        for value, what in (
            (args.api, "--api"),
            (args.web, "--web"),
            (env["SUPABASE_URL"], "SUPABASE_URL"),
        ):
            require_loopback(value, what)
    files = pack_files(args.receipts_dir)
    api = Api(args.api, args.web)
    api.dry_run = args.dry_run and not local
    health = api.call("GET", "/health").body
    sha = health.get("git_sha") or (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
        ).stdout.strip()
        + " (local HEAD)"
    )
    print(f"{args.target} {args.mode} at {sha}")

    if local:
        email, password, fresh = local_owner(env, api, args.local_account)

        def sign_in() -> str:
            # Supabase password grant: the product's /auth/login rate limit counts every local run from one IP.
            response = api.http.post(
                f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
                headers={"apikey": env["SUPABASE_ANON_KEY"]},
                json={"email": email, "password": password},
            )
            expect(
                response.status_code == 200,
                f"local sign-in answered {response.status_code}",
            )
            return response.json()["access_token"]
    else:
        email, password = staging_account(args.accounts_file, args.account)
        fresh = False

        def sign_in() -> str:
            result = browser(
                args.web, args.api, email, password, [], out / "screens", want_token=True
            )
            if not result.get("token"):
                raise SystemExit(
                    f"staging sign-in failed headless: {result.get('errors')}"
                )
            return result["token"]

    api.token = sign_in()
    spaces = api.get("/business/spaces")["spaces"]
    if not spaces and local:
        # Seed meets an unnamed Business, as on staging, so its name step is exercised.
        api.send(
            "POST",
            "/business/space",
            {
                "name": "Ensayo José Demo" if args.mode == "rehearse" else None,
                "language": "es-419",
                "country": "DO",
            },
        )
        spaces = api.get("/business/spaces")["spaces"]
    prefix = args.expect_business or ""
    chosen = [
        s for s in spaces if str(s.get("space_id") or s.get("id")).startswith(prefix)
    ]
    if len(chosen) != 1:
        owned = (
            ", ".join(
                f"{str(x.get('space_id') or x.get('id'))[:8]} {x.get('name')!r}"
                for x in spaces
            )
            or "none"
        )
        raise SystemExit(
            f"refusing: signed-in account has no single Business"
            f"{' with id prefix ' + prefix if prefix else ''} (it has: {owned})"
        )
    space = chosen[0]
    api.dry_run = args.dry_run
    api.grant = space.get("grant_id")
    space_id = str(space.get("space_id") or space.get("id"))
    print(
        f"Business {space.get('name')!r} {space_id}"
        + (" (fresh local owner)" if fresh else "")
    )
    meta = {
        "target": args.target,
        "mode": args.mode,
        "sha": sha,
        "business_id": space_id,
        "business_name": space.get("name"),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    if args.mode == "seed":
        result = Seeder(api, args, files).run()
        if args.screens and not args.dry_run:
            shots = [
                {"name": "seed-inicio", "path": "/biz?view=overview"},
                {"name": "seed-bandeja", "path": "/biz?view=inbox"},
                {"name": "seed-registros", "path": "/biz?view=transactions"},
            ]
            if args.profile == "alive":
                shots += [
                    {"name": "seed-facturacion", "path": "/biz?view=invoicing"},
                    {"name": "seed-actividad", "path": "/biz?view=activity"},
                ]
            for name, case, key, param in (
                ("seed-case2-note", "2", "draft_id", "draft"),
                ("seed-case3-ready-personal", "3", "receipt_id", "receipt"),
            ):
                if result[case].get(key):
                    shots.append(
                        {"name": name, "path": f"/biz?{param}={result[case][key]}"}
                    )
            shot = browser(
                args.web,
                args.api,
                email,
                password,
                shots,
                out / "screens",
                want_token=False,
            )
            meta["screens"] = {"taken": shot.get("shots"), "errors": shot.get("errors")}
        report = {**meta, "dry_run": args.dry_run, "seeded": result}
        (out / "seed.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1, default=str)
        )
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
        (out / "calls.json").write_text(json.dumps(api.log, indent=1))
        return

    rec = Recorder(api, out)
    rehearsal = Rehearsal(api, rec, args, files, env)
    rehearsal.state["sign_in"] = sign_in
    if args.dry_run:
        report = {**meta, "dry_run": True, **rehearsal.plan()}
        (out / "plan.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1, default=str)
        )
        (out / "calls.json").write_text(json.dumps(api.log, indent=1))
        return
    rehearsal.setup()
    for case in args.cases:
        print(f"case {case}")
        getattr(rehearsal, f"case{case}")()
    if args.screens:
        s = rehearsal.state
        shots = [
            {"name": "inicio", "path": "/biz?view=overview"},
            {"name": "bandeja", "path": "/biz?view=inbox"},
            {"name": "registros", "path": "/biz?view=transactions"},
        ]
        for name, key, param in (
            ("case1-whatsapp-dossier", "c1_receipt", "receipt"),
            ("case2-note-dossier", "c2_draft", "draft"),
            ("case3-personal-dossier", "c3_receipt", "receipt"),
        ):
            if s.get(key):
                shots.append({"name": name, "path": f"/biz?{param}={s[key]}"})
        shot = browser(
            args.web, args.api, email, password, shots, out / "screens", want_token=False
        )
        meta["screens"] = {"taken": shot.get("shots"), "errors": shot.get("errors")}
    counts = {
        o: sum(r.outcome == o for r in rec.results) for o in ("PASS", "FAIL", "UNTESTED")
    }
    summary = {
        **meta,
        "counts": counts,
        "steps": [
            {k: v for k, v in asdict(r).items() if k != "calls"} for r in rec.results
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str)
    )
    (out / "calls.json").write_text(json.dumps(api.log, indent=1))
    print(f"\n{counts}  evidence {out}")
    for r in rec.results:
        print(
            f"{r.outcome:<9} {r.case}.{r.step}"
            + (f"  hop: {r.failing_hop}  fix: {r.fix}" if r.outcome == "FAIL" else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    receipts = Path.home() / "Documents/projects/cuadrao/cuadrao-test-receipts"
    serve = sub.add_parser(
        "serve-api", help="local API with the stub reader and a scripted Meta media host"
    )
    serve.add_argument("--env-file", type=Path, required=True)
    serve.add_argument("--port", type=int, default=57741)
    serve.add_argument("--receipts-dir", type=Path, default=receipts)
    serve.add_argument("--extractor", choices=("stub", "real"), default="stub")
    serve.add_argument(
        "--outbound-log",
        type=Path,
        help="append each WhatsApp reply the API sends to this JSONL file",
    )
    serve.add_argument(
        "--openrouter-key-file",
        type=Path,
        default=Path(
            subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=REPO,
                capture_output=True,
                text=True,
            ).stdout.strip()
            or REPO / ".git"
        ).parent
        / ".env",
        help="real: env file whose OPENROUTER_API_KEY is read inside this process"
        " (default: the main checkout .env)",
    )
    serve.set_defaults(handler=serve_api)
    go = sub.add_parser("run", help="rehearse the cases or seed them ready to demo")
    go.add_argument("--target", choices=("local", "staging"), required=True)
    go.add_argument("--mode", choices=("rehearse", "seed"), default="rehearse")
    go.add_argument("--api", required=True)
    go.add_argument("--web", required=True)
    go.add_argument("--evidence", type=Path, required=True)
    go.add_argument("--env-file", type=Path, help="local: the env file serve-api uses")
    go.add_argument(
        "--local-account",
        type=Path,
        help="local: JSON {email,password}; created when absent",
    )
    go.add_argument("--account", help="staging: entry name in the accounts file")
    common = Path(
        subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=REPO,
            capture_output=True,
            text=True,
        ).stdout.strip()
        or REPO / ".git"
    ).parent
    go.add_argument(
        "--accounts-file", type=Path, default=common / "temp/staging-walk-accounts.json"
    )
    go.add_argument(
        "--expect-business",
        help="refuse unless the signed-in Business id starts with this",
    )
    go.add_argument("--receipts-dir", type=Path, default=receipts)
    go.add_argument(
        "--cases",
        nargs="+",
        default=["2", "3", "1", "4", "5"],
        choices=["1", "2", "3", "4", "5"],
    )
    go.add_argument(
        "--whatsapp-wait",
        type=int,
        default=0,
        help="staging: seconds to wait for Lucas's WhatsApp document",
    )
    go.add_argument(
        "--dry-run",
        action="store_true",
        help="read and print the planned writes, write nothing (seed and rehearse)",
    )
    go.add_argument(
        "--business-name", help="seed: saved only when the server reports name_required"
    )
    go.add_argument(
        "--enable-reading",
        action="store_true",
        help="seed: turn receipt reading on when it is off (model spend on staging)",
    )
    go.add_argument(
        "--profile",
        choices=("demo", "alive"),
        default="demo",
        help="seed: demo = cases 2-5 ready; alive = that plus Aug-Oct synthetic history",
    )
    go.add_argument(
        "--read-cost-ceiling",
        type=float,
        default=0.05,
        help="seed: USD counted per model read the seed causes (the API reports no price)",
    )
    go.add_argument(
        "--spent-usd",
        type=float,
        default=0.0,
        help="seed: read spend already made under the $1.00 cap (stop $0.75)",
    )
    go.add_argument(
        "--reserve-reads",
        type=int,
        default=1,
        help="seed: reads kept for the rehearsal (case 1 WhatsApp read)",
    )
    go.add_argument(
        "--outbound-log",
        type=Path,
        help="local: the file serve-api --outbound-log appends replies to (case 1 resend)",
    )
    go.add_argument("--no-screens", dest="screens", action="store_false")
    go.set_defaults(handler=run)
    args = parser.parse_args()
    if args.command == "run":
        args.cases = list(dict.fromkeys(args.cases))
        if args.target == "local" and not args.env_file:
            parser.error("--env-file is required for --target local")
        if args.target == "staging" and not args.account:
            parser.error("--account is required for --target staging")
        if (args.mode == "seed" or args.target == "staging") and not args.expect_business:
            parser.error(
                "--expect-business is required for seed and for --target staging"
            )
        if args.target == "staging" and len(args.expect_business) < 6:
            parser.error(
                "--expect-business needs at least 6 characters of the Business id"
            )
        if args.profile != "demo" and args.mode != "seed":
            parser.error("--profile is a seed option")
    args.handler(args)


if __name__ == "__main__":
    main()

"""The signed founder walkthrough. Opt in with the disposable DB and local Storage."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from argus.api import business_spaces, documents, financial_accounts, ingestion, whatsapp
from argus.api.main import app
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.documents import extractor
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.domain.ingestion.documents.objects import SupabaseSourceObjects, owner_prefix
from argus.domain.ingestion.documents.service import (
    DocumentOutcome,
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.email_intake.budget import business_day, next_business_day
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.held import HeldFile, held_files
from argus.domain.ingestion.whatsapp.replies import compose_reply, review_url
from faker import Faker
from loguru import logger
from psycopg_pool import ConnectionPool

from scripts.qa.whatsapp_walkthrough import Receipt, local_targets, media_server
from tests import test_financial_accounts_postgres as accounts
from tests.business_reading_support import ROUTE, turn_reading
from tests.document_extractor_support import admit
from tests.document_reads_support import read_receipt
from tests.ingestion.whatsapp_support import ENV, encode, fixture, sign
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_spaces_migration_postgres import owned_space
from workflows.document_job import postgres_documents_service
from workflows.read_resume import ReadResume

LINK = "/api/v1/whatsapp/link"
RECEIPTS = "/api/v1/business/receipts"
C_NAME = "Taller privado de prueba"
APP_ORIGIN = "https://app.example.test"


@pytest.fixture
def reads_finish_inside_the_request() -> None:
    """The walkthrough takes the receipt's real queued attempt after the HTTP 200."""


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class WalkthroughDesk:
    pool: ConnectionPool
    service: DocumentsService
    auth: dict[str, str]
    ana: str
    users: dict[str, str]
    clock: Clock
    spaces: dict[str, str]
    grants: dict[str, str]
    rnc: dict[str, str]


@pytest.fixture
def desk(monkeypatch: pytest.MonkeyPatch) -> Iterator[WalkthroughDesk]:
    dsn, url = local_targets()
    for key, value in {
        **ENV,
        "CUADRAO_DOCUMENT_EXTRACTION_ENABLED": "true",
        "CUADRAO_WHATSAPP_OUTBOUND_ENABLED": "true",
        "CUADRAO_APP_ORIGIN": APP_ORIGIN,
        "CUADRAO_WHATSAPP_SENDER_KEY": str(uuid4()),
        "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
        "CUADRAO_FINANCIAL_ACCOUNTS_ENABLED": "true",
        "CUADRAO_INGESTION_ENABLED": "true",
        "CUADRAO_BUSINESS_READS_PER_DAY": "3",
        "CUADRAO_MOCK_AUTH": "false",
        "NEXT_PUBLIC_MOCK_AUTH": "false",
        "POSTHOG_PROJECT_TOKEN": "",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    gateway = local_supabase_gateway()
    objects = SupabaseSourceObjects(gateway.client.storage)
    clock = Clock()
    with ConnectionPool(dsn, min_size=0, max_size=8) as pool:
        with pool.connection() as db:
            users = accounts._create_users(db, ("A", False), ("B", False), ("C", False))
        try:
            email = f"ana-{uuid4().hex}@example.test"
            password = uuid4().hex
            ana = gateway.client.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                }
            ).user.id
            users["Ana"] = ana
            with httpx.Client(base_url=url, trust_env=False) as client:
                session = client.post(
                    "/auth/v1/token?grant_type=password",
                    headers={"apikey": os.environ["ARGUS_LOCAL_SUPABASE_ANON_KEY"]},
                    json={"email": email, "password": password},
                )
                session.raise_for_status()
                auth = {"Authorization": "Bearer " + session.json()["access_token"]}

            service = postgres_documents_service(pool, objects)
            service.hub.clock = clock
            service.hub.box = SecretBox(b"q" * 32)
            spaces, grants = {}, {}
            faker = Faker()
            rnc = {
                key: faker.unique.numerify("1########")
                for key in ("A", "B", "C", "X", "vendor")
            }
            for key in ("A", "B", "C"):
                with pool.connection() as db:
                    space = spaces[key] = owned_space(db, users[key])
                    db.execute(
                        "update public.spaces set name=%s, business_rnc=%s, business_tax_id_type='rnc' where id=%s",
                        (C_NAME if key == "C" else f"Negocio {key}", rnc[key], space),
                    )
                    if key != "C":
                        grants[key] = db.execute(
                            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities)"
                            " values(%s,%s,%s,'editor',array['read','prepare']) returning id::text",
                            (space, ana, users[key]),
                        ).fetchone()[0]
                turn_reading(service.business_receipt_consent, space, users[key])
            with pool.connection() as db:
                assert not db.execute(
                    "select 1 from public.spaces where business_rnc=%s", (rnc["X"],)
                ).fetchone()

            for module, name, value in (
                (documents, "_service", service),
                (ingestion, "_hub", service.hub),
                (business_spaces, "_access", PostgresAccessStore(pool)),
                (business_spaces, "_spaces", PostgresSpaceStore(pool)),
                (financial_accounts, "_service", service.hub.sink.money.accounts),
                (whatsapp.api_state, "supabase_gateway", gateway),
                (whatsapp.api_state, "DATABASE_URL", dsn),
                (whatsapp.api_state, "PERSISTENCE_MODE", "supabase"),
            ):
                monkeypatch.setattr(module, name, value)
            monkeypatch.setattr(app.state, "financial_accounts_pool", pool, raising=False)
            yield WalkthroughDesk(
                pool=pool,
                service=service,
                auth=auth,
                ana=ana,
                users=users,
                clock=clock,
                spaces=spaces,
                grants=grants,
                rnc=rnc,
            )
        finally:
            with pool.connection() as db:
                for owner in users.values():
                    objects.delete(owner_prefix(owner))
                accounts._delete_users(db, users)


class SignedForward:
    def __init__(
        self, desk: WalkthroughDesk, client: httpx.AsyncClient, replies: list[str]
    ) -> None:
        self.desk, self.client, self.replies = desk, client, replies
        self.reads = Counter()
        self.media, self.receipts = {}, {}
        self.responses: list[str] = []
        self.proof: list[str] = []

    async def request(self, method: str, path: str, **options: Any) -> dict:
        response = await self.client.request(method, path, **options)
        self.responses.append(response.text)
        assert response.is_success, (path, response.status_code, response.text)
        return response.json()

    async def post(self, body: dict) -> None:
        raw = encode(body, self.desk.clock.now)
        result = await self.request(
            "POST",
            whatsapp.WEBHOOK_PATH,
            content=raw,
            headers={"X-Hub-Signature-256": sign(raw)},
        )
        assert result == {"received": True}

    async def link(self) -> None:
        status = await self.request("GET", LINK, headers=self.desk.auth)
        code = await self.request(
            "POST",
            LINK + "-codes",
            headers=self.desk.auth,
            json={"disclosure_token": status["disclosure_token"]},
        )
        await self.post(fixture("text_link_code.json", text=code["message_text"]))
        linked = await self.request("GET", LINK, headers=self.desk.auth)
        assert linked["linked"]
        assert {b["space_id"]: b["tax_id"] for b in linked["receiving_businesses"]} == {
            self.desk.spaces[key]: {"type": "rnc", "value": self.desk.rnc[key]}
            for key in ("A", "B")
        }

    async def provider(
        self,
        *,
        document_sha256: str,
        before_request: Callable[[], Awaitable[None]],
        **_: Any,
    ) -> ExtractionResult:
        await admit(before_request)
        receipt = self.receipts[document_sha256]
        self.reads[receipt.name] += 1
        return ExtractionResult.model_validate(
            {
                "readable": True,
                "complete": True,
                "pages_read": [1],
                "observations": [
                    {
                        "page": 1,
                        "row": 1,
                        "evidence": "transaction",
                        "direction": "outflow",
                        "kind_hint": "expense",
                        "merchant": receipt.name,
                        "amount": "250.50",
                        "currency": "DOP",
                    }
                ],
                "receipt": {
                    "merchant": receipt.name,
                    "payment_status": "paid",
                    "total": "250.50",
                    "currency": "DOP",
                    "rnc": receipt.issuer,
                    "buyer_rnc": receipt.buyer,
                },
            }
        )

    async def forward(self, *receipts: Receipt) -> list[str]:
        body = fixture("document_forwarded.json")
        messages = body["entry"][0]["changes"][0]["value"]["messages"]
        original = messages.pop()
        ids = []
        for receipt in receipts:
            key = str(100000000000000 + len(self.media))
            message_id = f"wamid.W9.{key}"
            ids.append(message_id)
            content = self.media[key] = receipt.png()
            self.receipts[sha256(content).hexdigest()] = receipt
            messages.append(
                {
                    **original,
                    "id": message_id,
                    "document": {
                        "mime_type": "image/png",
                        "id": key,
                        "filename": receipt.name + ".png",
                    },
                }
            )
        await self.post(body)
        connections = []
        intake = whatsapp.whatsapp_runtime().intake
        for message in ids:
            inbound = intake.store.inbound(intake.keys.message(message))
            assert inbound is not None and inbound.connection_id, (
                "200 without a saved file",
                inbound.status if inbound else None,
                inbound.error_code if inbound else None,
            )
            connections.append(inbound.connection_id)
        return connections

    async def read(self, connection_id: str) -> str | None:
        service = self.desk.service
        owner = service.store.owner(connection_id=connection_id)
        return await read_receipt(service, owner, connection_id)

    async def inbox(self, key: str) -> dict[str, dict]:
        result = await self.request(
            "GET",
            RECEIPTS,
            headers={
                **self.desk.auth,
                "X-Business-Grant": self.desk.grants[key],
            },
        )
        assert all(row["channel"] == "whatsapp" for row in result["items"])
        return {row["filename"]: row for row in result["items"]}

    def usage(self) -> tuple[int, int, int, int]:
        d = self.desk
        day = business_day(d.clock())
        with d.pool.connection() as db:
            business = dict(
                db.execute(
                    "select business_id::text, reads from public.business_read_daily_usage"
                    " where day=%s and business_id=any(%s::uuid[])",
                    (day, list(d.spaces.values())),
                ).fetchall()
            )
            held = db.execute(
                "select coalesce(sum(reads),0) from public.whatsapp_held_read_usage"
                " where day=%s and user_id=%s",
                (day, d.ana),
            ).fetchone()[0]
        return (
            sum(self.reads.values()),
            business.get(d.spaces["A"], 0),
            business.get(d.spaces["B"], 0),
            int(held),
        )

    def evidence(self, step: str, expected: tuple[int, int, int, int]) -> None:
        actual = self.usage()
        assert actual == expected, (step, actual, expected)
        provider, a, b, held = actual
        self.proof.append(f"{step} | provider={provider} A={a} B={b} held_reads={held}")

    def row_counts(self) -> tuple[int, ...]:
        with self.desk.pool.connection() as db:
            return tuple(
                db.execute(
                    f"select count(*) from public.{table} where user_id=any(%s::uuid[])",
                    (list(self.desk.users.values()),),
                ).fetchone()[0]
                for table in ("financial_document_extractions", "whatsapp_held_files")
            )

    def held(self) -> list[HeldFile]:
        return [
            row
            for row in held_files(self.desk.service.store).list_for_user(self.desk.ana)
            if row.state == "held"
        ]


@pytest.mark.asyncio
async def test_signed_founder_walkthrough(
    desk: WalkthroughDesk,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    record_property,
) -> None:
    replies, downloads = [], []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        w = SignedForward(desk, client, replies)
        with media_server(w.media, downloads, replies) as transport:
            async with httpx.AsyncClient(transport=transport, trust_env=False) as media:
                monkeypatch.setattr(
                    whatsapp, "httpx", SimpleNamespace(AsyncClient=lambda: media)
                )
                monkeypatch.setattr(
                    extractor.DocumentExtractor,
                    "_provider",
                    lambda self: ("fixture", "fixture"),
                )
                monkeypatch.setattr(
                    extractor, "invoke_openrouter_json_schema", w.provider
                )
                monkeypatch.setattr(whatsapp, "_runtime", None)
                whatsapp.start_whatsapp(app)
                await w.link()
                captured = StringIO()
                sink = logger.add(captured, format="{message} {extra}")
                try:
                    with caplog.at_level(logging.INFO):
                        await run_cases(w)
                finally:
                    logger.remove(sink)
    assert Counter(downloads) == Counter(w.media.keys())
    public = "\n".join([*w.responses, *replies, captured.getvalue(), caplog.text])
    for private in (C_NAME, desk.spaces["C"]):
        assert (
            private not in public
        ), "An inaccessible Business appeared in a response or log"
    w.proof.append(
        "Privacy | inaccessible Business name and ID absent from HTTP, replies and logs"
    )
    for line in w.proof:
        record_property("walkthrough", line)


async def run_cases(w: SignedForward) -> None:
    d, r = w.desk, w.desk.rnc
    sales = [Receipt(f"Venta-{n}", r["A"], None) for n in (1, 2)]
    purchases = [Receipt(f"Compra-{n}", r["vendor"], r["B"]) for n in (1, 2)]
    unplaced = [
        Receipt("Sin-comprador", r["vendor"], None),
        Receipt("Compra-3", r["vendor"], r["C"]),
        Receipt("Compra-4", r["vendor"], r["X"]),
    ]
    for cid in await w.forward(*sales, *purchases, *unplaced):
        assert await w.read(cid) == "prepared"
    assert w.reads == Counter(receipt.name for receipt in [*sales, *purchases, *unplaced])
    for key, expected, kind in (("A", sales, "venta"), ("B", purchases, "recibo")):
        rows = await w.inbox(key)
        assert {k: row["document_type"] for k, row in rows.items()} == {
            receipt.name + ".png": kind for receipt in expected
        }
    by_file = {
        d.service.store.draft(
            user_id=d.ana, connection_id=item.connection_id
        ).filename: item
        for item in w.held()
    }
    assert {name: row.reason for name, row in by_file.items()} == {
        "Sin-comprador.png": "no_buyer_rnc",
        "Compra-3.png": "no_match",
        "Compra-4.png": "no_match",
    }
    assert (await w.request("GET", LINK, headers=d.auth))["held_count"] == 3
    w.evidence(
        "1 | A=2 ventas, B=2 compras | held=no_buyer_rnc,no_match,no_match", (7, 2, 2, 3)
    )

    before = w.row_counts()
    sale = sales[0]
    original = (await w.inbox("A"))[sale.name + ".png"]["id"]
    [duplicate] = await w.forward(sale)
    assert duplicate == original, "Resending the file should refer to A's existing sale"
    assert w.replies[-1] == compose_reply(
        "duplicate", language="es-419", link=review_url(APP_ORIGIN, original)
    )
    assert await w.read(duplicate) is None
    assert w.row_counts() == before
    w.evidence(
        "6 | duplicate links to A’s original sale | new drafts=0 new held rows=0",
        (7, 2, 2, 3),
    )

    def assign(name: str, key: str) -> DocumentOutcome:
        return d.service.adopt(
            user_id=d.ana, held_id=by_file[name].id, business_id=d.spaces[key]
        )

    assigned = assign("Sin-comprador.png", "A")
    assert (await w.inbox("A"))["Sin-comprador.png"]["id"] == assigned.connection_id
    assert await w.read(assigned.connection_id) is None
    assert len(w.held()) == 2
    w.evidence("2 | assigned to A with room | channel=whatsapp", (7, 3, 2, 2))
    assigned = assign("Compra-3.png", "A")
    assert (await w.inbox("A"))["Compra-3.png"]["id"] == assigned.connection_id
    assert await w.read(assigned.connection_id) is None
    assert len(w.held()) == 1
    w.evidence("2 | assigned at A's cap | channel=whatsapp", (7, 3, 2, 2))

    PostgresAccessStore(d.pool).revoke_grant(d.spaces["B"], d.users["B"], d.grants["B"])
    with pytest.raises(DocumentServiceError, match="business_permission_denied"):
        assign("Compra-4.png", "B")
    status = await w.request("GET", LINK, headers=d.auth)
    assert [row["space_id"] for row in status["receiving_businesses"]] == [d.spaces["A"]]
    assert status["held_count"] == 1
    w.evidence(
        "3 | revoked B absent from picker | assignment=business_permission_denied",
        (7, 3, 2, 2),
    )

    single = Receipt("Directo", r["vendor"], None)
    before = w.row_counts()
    [direct] = await w.forward(single)
    assert w.row_counts() == (before[0] + 1, before[1])
    assert await w.read(direct) == "business_read_budget_day"
    row = (await w.inbox("A"))["Directo.png"]
    assert (row["id"], row["attention"]) == (direct, "read_budget_day")
    resume = ReadResume(d.service)
    assert await asyncio.to_thread(resume.run, d.clock()) == {"due": 0, "requeued": 0}
    w.evidence(
        "4 | one eligible, no buyer | new held rows=0 | Bandeja=read_budget_day",
        (7, 3, 2, 2),
    )
    d.clock.now = next_business_day(d.clock()) + timedelta(seconds=1)
    assert await asyncio.to_thread(resume.run, d.clock()) == {"due": 1, "requeued": 1}
    assert await w.read(direct) == "prepared"
    assert (await w.inbox("A"))["Directo.png"]["status"] == "review_ready"
    w.evidence("4 | next Santo Domingo day | resumed=1", (8, 1, 0, 0))

    with d.pool.connection() as db:
        triggers = db.execute(
            "select tgname from pg_trigger t join pg_proc p on p.oid=t.tgfoid"
            " where not tgisinternal and (tgname=any(%s) or p.proname=any(%s))",
            (
                ["fill_sender_link_space", "whatsapp_capture_same_space"],
                ["fill_sender_link_space", "require_whatsapp_capture_same_space"],
            ),
        ).fetchall()
    assert not triggers, triggers
    search = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            r"resolve_business_scope\|business_space_of",
            "--",
            "src/argus/api/whatsapp.py",
            "src/argus/domain/ingestion/whatsapp",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        check=False,
    )
    assert search.returncode == 1, search.stdout.decode() or search.stderr.decode()
    w.proof.append("7 | default lookup matches=0 | Business-pin triggers=0")

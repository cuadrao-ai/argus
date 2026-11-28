"""The signed founder walkthrough. Opt in with the disposable DB and local Storage."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
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
import pytest_asyncio
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
from argus.domain.ingestion.whatsapp import document_step, reply_groups_postgres
from argus.domain.ingestion.whatsapp.held import HeldFile, held_files
from argus.domain.ingestion.whatsapp.media import FetchedMedia
from argus.domain.ingestion.whatsapp.reply_groups import BatchOutcomes, ReplyGroup
from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups
from faker import Faker
from loguru import logger
from psycopg import Connection
from psycopg_pool import ConnectionPool

from scripts.qa.whatsapp_walkthrough import (
    Receipt,
    ToLocalMedia,
    local_targets,
    media_server,
)
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
BUSINESS_NAMES = {
    "A": "Colmado Doña Rosa",
    "B": "Taller Hermanos Peña",
    "D": "Farmacia San Miguel",
    "E": "Ferretería El Progreso",
    "F": "Cafetería La Esquina",
    "G": "Repuestos Don Julio",
    "H": "Papelería Central",
    "I": "Salón Caribe",
    "J": "Lavandería Brisa",
}
APP_ORIGIN = "https://app.example.test"


@pytest.fixture
def reads_finish_inside_the_request() -> None:
    """The walkthrough takes the receipt's real queued attempt after the HTTP 200."""


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc).replace(
            hour=21, minute=20, second=0, microsecond=0
        )

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
    private_business_name: str


@pytest.fixture
def read_limit() -> int:
    return 3


@pytest.fixture
def desk(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, read_limit: int
) -> Iterator[WalkthroughDesk]:
    dsn, url = local_targets()
    businesses = (*getattr(request, "param", ("A", "B")), "C")
    for key, value in {
        **ENV,
        "CUADRAO_DOCUMENT_EXTRACTION_ENABLED": "true",
        "CUADRAO_INGESTION_SECRET_KEY": ENV["ARGUS_INGESTION_SECRET_KEY"],
        "CUADRAO_WHATSAPP_OUTBOUND_ENABLED": "true",
        "CUADRAO_APP_ORIGIN": APP_ORIGIN,
        "CUADRAO_WHATSAPP_SENDER_KEY": str(uuid4()),
        "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
        "CUADRAO_FINANCIAL_ACCOUNTS_ENABLED": "true",
        "CUADRAO_INGESTION_ENABLED": "true",
        "CUADRAO_BUSINESS_READS_PER_DAY": str(read_limit),
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
            users = accounts._create_users(db, *((key, False) for key in businesses))
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
            service.hub.box = SecretBox.from_env()
            spaces, grants = {}, {}
            faker = Faker()
            private_business_name = faker.lexify("????????????")
            rnc = {
                key: faker.unique.numerify("1########")
                for key in (*businesses, "X", "vendor")
            }
            for key in businesses:
                with pool.connection() as db:
                    space = spaces[key] = owned_space(db, users[key])
                    db.execute(
                        "update public.spaces set name=%s, business_rnc=%s, business_tax_id_type='rnc' where id=%s",
                        (
                            private_business_name if key == "C" else BUSINESS_NAMES[key],
                            rnc[key],
                            space,
                        ),
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
                private_business_name=private_business_name,
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
        self.read_ids: list[str] = []
        self.reads = Counter()
        self.upkeep = document_step.FailureReplyUpkeep(
            PostgresReplyGroups(desk.pool), clock=desk.clock
        )
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
            for key in self.desk.grants
        }

    async def sweep(self, seconds: int = 60) -> None:
        self.desk.clock.now += timedelta(seconds=seconds)
        await asyncio.to_thread(self.upkeep.send_due)

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


@pytest_asyncio.fixture
async def signed(
    desk: WalkthroughDesk, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[SignedForward]:
    replies, downloads = [], []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://local",
    ) as client:
        w = SignedForward(desk, client, replies)
        with media_server(w.media, downloads, replies, w.read_ids) as transport:
            async with httpx.AsyncClient(transport=transport, trust_env=False) as media:
                monkeypatch.setattr(
                    whatsapp, "httpx", SimpleNamespace(AsyncClient=lambda: media)
                )
                monkeypatch.setattr(
                    document_step,
                    "httpx",
                    SimpleNamespace(
                        AsyncClient=lambda: httpx.AsyncClient(
                            transport=ToLocalMedia(transport.port), trust_env=False
                        )
                    ),
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
                [w.link_reply] = replies
                replies.clear()
                yield w
    assert Counter(downloads) == Counter(w.media.keys())


@pytest.mark.asyncio
async def test_signed_founder_walkthrough(
    signed: SignedForward,
    caplog: pytest.LogCaptureFixture,
    record_property,
) -> None:
    w, desk = signed, signed.desk
    captured = StringIO()
    sink = logger.add(captured, format="{message} {extra}")
    try:
        with caplog.at_level(logging.INFO):
            await run_cases(w)
    finally:
        logger.remove(sink)
    assert (
        w.link_reply
        == "Listo, este WhatsApp quedó conectado. Envía aquí la foto o el PDF de tus facturas."
    )
    public = "\n".join([*w.responses, *w.replies, captured.getvalue(), caplog.text])
    for private in (desk.private_business_name, desk.spaces["C"]):
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
    connections = await w.forward(*sales, *purchases, *unplaced)
    assert w.read_ids == [f"wamid.W9.{100000000000000+n}" for n in range(7)]
    assert w.replies == []
    for cid in connections:
        assert await w.read(cid) == "prepared"
    await w.sweep()
    assert w.replies == [
        "Recibimos 7 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 2\n• Taller Hermanos Peña: 2\n"
        "3 quedaron sin negocio. Te esperan en Cuadrao."
    ]
    w.proof.append("1 | 7 read receipts after save | one exact reply after 1 minute")
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
    assert len(w.read_ids) == 7 and len(w.replies) == 1
    await w.sweep()
    assert w.replies[1:] == ["Esta ya la teníamos, gracias. No se guardó dos veces."]
    assert await w.read(duplicate) is None
    assert w.row_counts() == before
    w.evidence(
        "6 | duplicate acknowledged once, without a link | new drafts=0 new held rows=0",
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


@pytest.mark.asyncio
@pytest.mark.parametrize("read_limit", [10])
async def test_mixed_ten_share_one_reply(signed: SignedForward) -> None:
    w, r = signed, signed.desk.rnc
    sales = [Receipt(f"Venta-{n}", r["A"], None) for n in range(4)]
    purchases = [Receipt(f"Compra-{n}", r["vendor"], r["B"]) for n in range(2)]
    saved = await w.forward(*sales, *purchases, Receipt("Sin-RNC", r["vendor"], None))
    for cid in saved:
        assert await w.read(cid) == "prepared"
    await w.forward(sales[0])
    for n in range(2):
        await w.post(
            fixture(
                "image_message.json",
                id=f"wamid.INVALID{n}",
                image={"id": f"99900000000000{n}", "mime_type": "image/gif"},
            )
        )
    assert len(w.read_ids) == 7
    assert w.replies == []
    await w.sweep()
    assert w.replies == [
        "Recibimos 10 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 4\n• Taller Hermanos Peña: 2\n"
        "1 quedó sin negocio. Te espera en Cuadrao.\n1 ya la teníamos.\n"
        "Disculpa, no pudimos recibir 2 archivos:\n• foto enviada a las 5:20 p. m.\n"
        "• foto enviada a las 5:20 p. m.\nEnvíalos como foto o PDF."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("desk", [tuple(BUSINESS_NAMES)], indirect=True)
@pytest.mark.parametrize("read_limit", [40])
async def test_forty_files_in_nine_businesses_name_five(signed: SignedForward) -> None:
    w, r = signed, signed.desk.rnc
    receipts = [
        Receipt(f"Venta-{key}-{n}", r[key], None)
        for key, count in zip(BUSINESS_NAMES, (8, 6, 5, 5, 4, 3, 3, 2, 2), strict=True)
        for n in range(count)
    ]
    receipts.extend(Receipt(f"Sin-{n}", r["vendor"], None) for n in range(2))
    for cid in await w.forward(*receipts):
        assert await w.read(cid) == "prepared"
    assert len(w.read_ids) == 40
    assert w.replies == []
    await w.sweep()
    assert w.replies == [
        "Recibimos 40 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 8\n• Taller Hermanos Peña: 6\n• Farmacia San Miguel: 5\n"
        "• Ferretería El Progreso: 5\n• Cafetería La Esquina: 4\n"
        "y 4 negocios más: 10 facturas\n2 quedaron sin negocio. Te esperan en Cuadrao."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("read_limit", [12])
async def test_slow_reads_close_at_three_minutes_without_followup(
    signed: SignedForward,
) -> None:
    w, r = signed, signed.desk.rnc
    receipts = [
        Receipt(f"Venta-{key}-{n}", r[key], None)
        for key, count in (("A", 6), ("B", 4))
        for n in range(count)
    ]
    receipts.extend(Receipt(f"Pendiente-{n}", r["A"], None) for n in range(2))
    connections = await w.forward(*receipts)
    for cid in connections[:-2]:
        assert await w.read(cid) == "prepared"
    for _ in range(2):
        await w.sweep()
        assert w.replies == []
    await w.sweep()
    expected = [
        "Recibimos 12 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 6\n• Taller Hermanos Peña: 4\n"
        "Las demás se están leyendo. Puedes seguirlas en Cuadrao."
    ]
    assert w.replies == expected
    for cid in connections[-2:]:
        assert await w.read(cid) == "prepared"
    await w.sweep()
    assert w.replies == expected


@pytest.mark.asyncio
async def test_failed_capture_commit_sends_no_status_or_reply(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = signed
    destination = whatsapp.whatsapp_runtime().intake.destination
    prepare = destination.prepare
    deferred = []

    def fail_at_commit(connection, *args, **kwargs):
        result = prepare(connection, *args, **kwargs)
        connection.execute(
            "create temp table failed_commit (id int primary key, parent int "
            "references failed_commit(id) deferrable initially deferred) on commit drop"
        )
        connection.execute("insert into failed_commit values (1, 2)")
        deferred.append(True)
        return result

    monkeypatch.setattr(destination, "prepare", fail_at_commit)
    key = "100000000000000"
    w.media[key] = Receipt("Sin-commit", w.desk.rnc["A"], None).png()
    message_id = "wamid.ROLLBACK"
    body = fixture(
        "image_message.json", id=message_id, image={"id": key, "mime_type": "image/png"}
    )
    raw = encode(body, w.desk.clock.now)
    errors = []
    sink = logger.add(
        lambda message: errors.append(message.record["extra"].get("failure_mode"))
    )
    try:
        response = await w.client.post(
            whatsapp.WEBHOOK_PATH, content=raw, headers={"X-Hub-Signature-256": sign(raw)}
        )
    finally:
        logger.remove(sink)
    assert response.status_code == 503 and "ForeignKeyViolation" in errors
    assert deferred == [True]
    intake = whatsapp.whatsapp_runtime().intake
    inbound = intake.store.inbound(intake.keys.message(message_id))
    assert inbound.status == "received" and inbound.connection_id is None
    await w.sweep(180)
    assert w.read_ids == w.replies == []


@pytest.mark.asyncio
async def test_daily_failure_cap_keeps_saved_file_counts(
    signed: SignedForward,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = signed
    monkeypatch.setenv("CUADRAO_WHATSAPP_REPLY_DAILY_LIMIT", "2")

    async def unsupported(n: int) -> None:
        await w.post(
            fixture(
                "image_message.json",
                id=f"wamid.INVALID{n}",
                image={"id": f"99900000000000{n}", "mime_type": "image/gif"},
            )
        )

    await unsupported(1)
    await w.sweep()
    assert w.replies == [
        "Disculpa, no pudimos recibir este archivo.\n• foto enviada a las 5:20 p. m.\n"
        "Envíalo como foto o PDF."
    ]
    await unsupported(2)
    await w.sweep()
    assert w.replies[1:] == [
        "Por hoy no avisaremos más sobre archivos que no podamos recibir. Las facturas válidas siguen entrando."
    ]
    await unsupported(3)
    [cid] = await w.forward(Receipt("Cada-válida", w.desk.rnc["A"], None))
    assert await w.read(cid) == "prepared"
    await w.sweep()
    assert w.replies[2:] == [
        "Recibimos 2 facturas, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1"
    ]
    await unsupported(4)
    await w.sweep()
    assert len(w.replies) == 3


@pytest.mark.asyncio
async def test_window_elapsed_before_worker_runs(signed: SignedForward) -> None:
    w = signed
    [cid] = await w.forward(Receipt("Con-ventana", w.desk.rnc["A"], None))
    assert await w.read(cid) == "prepared"
    assert len(w.read_ids) == 1
    await w.sweep(24 * 60 * 60)
    assert w.replies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("delay_seconds", [0.5, 1])
async def test_window_during_final_database_authorization(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch, delay_seconds: float
) -> None:
    w = signed
    [cid] = await w.forward(Receipt("Último-segundo", w.desk.rnc["A"], None))
    assert await w.read(cid) == "prepared"
    checked_at = []
    outcomes = reply_groups_postgres._outcomes

    def read_outcomes(db: Connection, group: ReplyGroup) -> BatchOutcomes:
        result = outcomes(db, group)
        # Claim reads outcomes before inserting the attempt. Authorization reads them
        # again with that committed attempt locked, immediately before dispatch.
        if db.execute(
            "select 1 from public.whatsapp_reply_attempts where sender_hash=%s",
            (group.sender_hash,),
        ).fetchone():
            checked_at.append(w.desk.clock.now - group.last_sent_at)
            w.desk.clock.now += timedelta(seconds=delay_seconds)
        return result

    monkeypatch.setattr(reply_groups_postgres, "_outcomes", read_outcomes)
    await w.sweep(24 * 60 * 60 - 1)
    assert checked_at == [timedelta(hours=24, seconds=-1)]
    await w.sweep()
    assert w.replies == (
        ["Recibimos tu factura, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1"]
        if delay_seconds < 1 else []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("link_in_envelope", [False, True])
async def test_same_envelope_files_share_arrival_before_second_claim(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch, link_in_envelope: bool
) -> None:
    w = signed
    intake = whatsapp.whatsapp_runtime().intake
    send = intake.transport.send
    first_saved, resume = asyncio.Event(), asyncio.Event()
    first_id, second_id = (f"wamid.W9.{100000000000000 + i}" for i in range(2))
    if link_in_envelope:
        w.desk.clock.now += timedelta(days=1)  # A fresh daily linking-reply allowance.
        assert (await w.client.delete(LINK, headers=w.desk.auth)).status_code == 204
        status = await w.request("GET", LINK, headers=w.desk.auth)
        code = await w.request(
            "POST", LINK + "-codes", headers=w.desk.auth,
            json={"disclosure_token": status["disclosure_token"]},
        )
        post = w.post

        async def link_then_forward(body: dict) -> None:
            link = fixture("text_link_code.json", id="wamid.SAME-LINK", text=code["message_text"])
            body["entry"][0]["changes"][0]["value"]["messages"][:0] = (
                link["entry"][0]["changes"][0]["value"]["messages"]
            )
            await post(body)

        monkeypatch.setattr(w, "post", link_then_forward)

    arrival = w.desk.clock.now

    async def after_read_receipt(payload: dict[str, Any]) -> None:
        await send(payload)
        if payload.get("message_id") == first_id:
            first_saved.set()
            await resume.wait()

    monkeypatch.setattr(intake.transport, "send", after_read_receipt)
    delivery = asyncio.create_task(
        w.forward(
            Receipt("Primera-en-sobre", w.desk.rnc["A"], None),
            Receipt("Segunda-en-sobre", w.desk.rnc["B"], None),
        )
    )
    try:
        await asyncio.wait_for(first_saved.wait(), timeout=5)
        if link_in_envelope:
            assert w.replies == [w.link_reply]
            w.replies.clear()
        first = intake.store.inbound(intake.keys.message(first_id))
        second = intake.store.inbound(intake.keys.message(second_id))
        assert await w.read(first.connection_id) == "prepared"
        await w.sweep(60)
        early = list(w.replies)
    finally:
        resume.set()
        connections = await delivery
    assert await w.read(connections[1]) == "prepared"
    await w.sweep(60)
    await w.sweep(60)
    assert early == []
    assert w.replies == [
        "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    ]
    assert second is not None and second.received_at == first.received_at == arrival
    assert second.status == "received" and second.claim_until is None
    assert second.connection_id is None and w.read_ids == [first_id, second_id]


@pytest.mark.asyncio
async def test_grant_revoked_before_reply_hides_business(signed: SignedForward) -> None:
    w, d = signed, signed.desk
    [cid] = await w.forward(Receipt("Revocado", d.rnc["vendor"], d.rnc["B"]))
    assert await w.read(cid) == "prepared"
    PostgresAccessStore(d.pool).revoke_grant(d.spaces["B"], d.users["B"], d.grants["B"])
    await w.sweep()
    assert w.replies == [
        "Recibimos tu factura, gracias.\n1 quedó sin negocio. Te espera en Cuadrao."
    ]


@pytest.mark.asyncio
async def test_text_audio_and_video_get_one_daily_reply(signed: SignedForward) -> None:
    w = signed
    await w.post(fixture("text_message.json", text="Buenas"))
    w.desk.clock.now += timedelta(seconds=60)
    await w.post(fixture("audio_message.json"))
    await w.sweep(0)
    assert w.replies == []
    await w.post(
        fixture(
            "audio_message.json",
            id="wamid.VIDEO",
            type="video",
            video={"id": "700000000000003"},
        )
    )
    assert w.read_ids == w.replies == []
    await w.sweep()
    greeting = "Hola. Por aquí no respondemos mensajes, solo recibimos facturas. Envía aquí la foto o el PDF de tus facturas."
    assert w.replies == [greeting]
    await w.post(fixture("audio_message.json", id="wamid.GUIDANCE3"))
    await w.sweep()
    assert w.replies == [greeting]


@pytest.mark.asyncio
@pytest.mark.parametrize("read_limit", [1])
async def test_three_files_wait_for_tomorrows_read_budget(signed: SignedForward) -> None:
    w, d = signed, signed.desk
    PostgresAccessStore(d.pool).revoke_grant(d.spaces["B"], d.users["B"], d.grants["B"])
    [first] = await w.forward(Receipt("Primera", d.rnc["A"], None))
    assert await w.read(first) == "prepared"
    await w.sweep()
    assert w.replies == [
        "Recibimos tu factura, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1"
    ]
    for cid in await w.forward(
        *(Receipt(f"Mañana-{n}", d.rnc["A"], None) for n in range(3))
    ):
        assert await w.read(cid) == "business_read_budget_day"
    assert len(w.read_ids) == 4
    await w.sweep()
    assert w.replies[1:] == [
        "Recibimos 3 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 3\n"
        "Hoy llegamos al límite de lecturas. 3 se leerán mañana y no hace falta enviarlas de nuevo."
    ]


@asynccontextmanager
async def pause_download(
    w: SignedForward, receipt: Receipt, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[asyncio.Task[list[str]]]:
    started, release = asyncio.Event(), asyncio.Event()
    media = whatsapp.whatsapp_runtime().intake.media
    fetch = media.fetch

    async def delayed(media_id: str) -> FetchedMedia:
        started.set()
        await release.wait()
        return await fetch(media_id)

    with monkeypatch.context() as patch:
        patch.setattr(media, "fetch", delayed)
        delivery = asyncio.create_task(w.forward(receipt))
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            yield delivery
        finally:
            release.set()
            await delivery


@pytest.mark.asyncio
async def test_read_finishes_during_next_files_download(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = signed
    [first] = await w.forward(Receipt("Venta-primera", w.desk.rnc["A"], None))
    await w.sweep(60)
    assert w.replies == []

    w.desk.clock.now += timedelta(seconds=30)
    async with pause_download(
        w, Receipt("Venta-segunda", w.desk.rnc["A"], None), monkeypatch
    ) as second:
        w.desk.clock.now += timedelta(seconds=20)
        assert await w.read(first) == "prepared"
        await w.sweep(10)
        assert w.replies == []
    [pending] = await second
    assert await w.read(pending) == "prepared"
    await w.sweep(60)
    expected = [
        "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 2"
    ]
    assert w.replies == expected
    await w.sweep(60)
    assert w.replies == expected


@pytest.mark.asyncio
async def test_inflight_second_file_extends_first_files_deadline(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch
) -> None:
    w, clock = signed, signed.desk.clock
    [first] = await w.forward(Receipt("Pendiente-A", w.desk.rnc["A"], None))
    await w.sweep(60)
    await w.sweep(60)
    assert w.replies == []

    intake = whatsapp.whatsapp_runtime().intake
    clock.now += timedelta(seconds=20)
    arrival = clock.now
    async with pause_download(
        w, Receipt("Pendiente-B", w.desk.rnc["B"], None), monkeypatch
    ) as second:
        # The signed webhook has committed B's inbound claim but has no file to count yet.
        key = intake.keys.message("wamid.W9.100000000000001")
        inbound = intake.store.inbound(key)
        assert inbound.status == "received" and inbound.connection_id is None
        assert inbound.received_at == arrival
        clock.now += timedelta(seconds=30)
        assert await w.read(first) == "prepared"
        await w.sweep(10)  # t=180, 40 seconds after B arrived
        early = list(w.replies)
        clock.now += timedelta(seconds=20)
        assert clock.now < inbound.claim_until
    [last] = await second
    assert await w.read(last) == "prepared"
    w.upkeep = document_step.FailureReplyUpkeep(
        PostgresReplyGroups(w.desk.pool), clock=clock
    )
    await w.sweep(40)  # t=240, 100 seconds after B arrived
    completed = list(w.replies)
    await w.sweep(60)
    await w.sweep(60)
    summary = "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    assert (early, completed, w.replies) == ([], [summary], [summary])


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_second", [179, 180.5])
async def test_off_phase_read_finishes_either_side_of_last_worker_tick(
    signed: SignedForward, finish_second: float
) -> None:
    w, clock = signed, signed.desk.clock
    start = clock.now
    await w.sweep(0)
    clock.now = start + timedelta(seconds=1)
    first, second = await w.forward(
        Receipt("Lista", w.desk.rnc["A"], None),
        Receipt("Ultima", w.desk.rnc["B"], None),
    )
    assert await w.read(first) == "prepared"
    await w.sweep(59)  # t=60, less than one minute quiet
    assert w.replies == []
    await w.sweep(60)  # t=120, second file still reading
    assert w.replies == []
    if finish_second < 180:
        clock.now = start + timedelta(seconds=finish_second)
        assert await w.read(second) == "prepared"
    clock.now = start + timedelta(seconds=180)
    await w.sweep(0)
    at_last_tick = list(w.replies)
    if finish_second > 180:
        clock.now = start + timedelta(seconds=finish_second)
        assert await w.read(second) == "prepared"
    clock.now = start + timedelta(seconds=181)  # the sender's exact three-minute cutoff
    at_deadline = list(w.replies)
    await w.sweep(59)
    w.upkeep = document_step.FailureReplyUpkeep(
        PostgresReplyGroups(w.desk.pool), clock=clock
    )
    await w.sweep(60)
    summary = "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    assert (at_last_tick, at_deadline, w.replies) == (
        [summary] if finish_second < 180 else [],
        [summary],
        [summary],
    )


@pytest.mark.asyncio
async def test_off_phase_slow_reply_stays_within_quiet_and_deadline_bounds(
    signed: SignedForward,
) -> None:
    w, clock = signed, signed.desk.clock
    await w.sweep(0)
    clock.now += timedelta(seconds=1)
    arrival = clock.now
    [slow] = await w.forward(Receipt("Lectura-lenta", w.desk.rnc["B"], None))
    observations = []
    for seconds in (59, 60, 60, 60):
        await w.sweep(seconds)
        if w.replies:
            observations.append(((clock.now - arrival).total_seconds(), list(w.replies)))
    sent_at, sent = observations[0]
    assert 60 <= sent_at <= 180
    assert sent == [
        "Recibimos tu factura, gracias.\nLa otra se está leyendo. Puedes seguirla en Cuadrao."
    ]
    assert await w.read(slow) == "prepared"
    w.upkeep = document_step.FailureReplyUpkeep(
        PostgresReplyGroups(w.desk.pool), clock=clock
    )
    await w.sweep()
    assert w.replies == sent


@pytest.mark.asyncio
async def test_delayed_worker_pass_still_sends_by_the_three_minute_deadline(
    signed: SignedForward,
) -> None:
    w, clock = signed, signed.desk.clock
    arrival = clock.now
    [slow] = await w.forward(Receipt("Barrido-tardío", w.desk.rnc["A"], None))
    await w.sweep(60)
    await w.sweep(60)
    assert w.replies == []
    clock.now += timedelta(seconds=60)
    by_deadline = list(w.replies)  # The worker's next pass is five seconds late.
    await w.sweep(5)
    assert (clock.now - arrival).total_seconds() == 185
    [reply] = w.replies
    assert reply.endswith("La otra se está leyendo. Puedes seguirla en Cuadrao.")
    assert await w.read(slow) == "prepared"
    await w.sweep()
    assert by_deadline == w.replies == [reply]


@pytest.mark.asyncio
async def test_file_saved_after_its_own_deadline_never_starts_another_reply(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch, record_property
) -> None:
    w, clock = signed, signed.desk.clock
    [first] = await w.forward(Receipt("Ya-guardada", w.desk.rnc["A"], None))
    assert await w.read(first) == "prepared"
    receipt = Receipt("Pendiente-de-descargar", w.desk.rnc["B"], None)
    media_id, message_id = "100000000000001", "wamid.OWN-DEADLINE"
    content = w.media[media_id] = receipt.png()
    w.receipts[sha256(content).hexdigest()] = receipt
    raw = encode(
        fixture(
            "image_message.json",
            id=message_id,
            image={"id": media_id, "mime_type": "image/png"},
        ),
        clock.now,
    )

    async def deliver() -> httpx.Response:
        return await w.client.post(
            whatsapp.WEBHOOK_PATH, content=raw, headers={"X-Hub-Signature-256": sign(raw)}
        )

    # The first process stops after admitting B. The provider repeats the identical signed delivery.
    intake = whatsapp.whatsapp_runtime().intake
    fetch = intake.media.fetch

    async def interrupted(media_id: str) -> FetchedMedia:
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(intake.media, "fetch", interrupted)
        try:
            failed = await deliver()
        except asyncio.CancelledError:
            pass
        else:
            assert failed.status_code >= 500

    key = intake.keys.message(message_id)
    inbound = intake.store.inbound(key)
    assert inbound.status == "received" and inbound.connection_id is None
    await w.sweep(60)
    assert w.replies == []
    clock.now += timedelta(seconds=55)
    assert clock.now > inbound.claim_until
    fetching, release = asyncio.Event(), asyncio.Event()

    async def retry_download(media_id: str) -> FetchedMedia:
        fetching.set()
        await release.wait()
        return await fetch(media_id)

    with monkeypatch.context() as patch:
        patch.setattr(intake.media, "fetch", retry_download)
        retry = asyncio.create_task(deliver())
        try:
            await asyncio.wait_for(fetching.wait(), timeout=5)
            await w.sweep(5)
            await w.sweep(60)
            before_save = list(w.replies)
            assert (clock.now - inbound.received_at).total_seconds() == 180
            assert intake.store.inbound(key).connection_id is None
            clock.now += timedelta(seconds=5)
            assert clock.now < intake.store.inbound(key).claim_until
        finally:
            release.set()
            result = await retry
    assert result.status_code == 200
    assert w.read_ids[-1] == message_id
    assert await w.read(intake.store.inbound(key).connection_id) == "prepared"
    w.upkeep = document_step.FailureReplyUpkeep(
        PostgresReplyGroups(w.desk.pool), clock=clock
    )
    await w.sweep(55)
    await w.sweep(60)
    assert w.replies == before_save
    assert len(before_save) == 1
    record_property(
        "walkthrough",
        f"Uncommitted at 180 s, saved at 185 s | replies by deadline={len(before_save)} | follow-ups=0",
    )

"""Signed intake, disposable storage and controlled document-worker clock for the walkthrough."""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
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
from argus.domain.ingestion.documents import extractor, jobs
from argus.domain.ingestion.documents.models import ExtractionResult
from argus.domain.ingestion.documents.objects import SupabaseSourceObjects, owner_prefix
from argus.domain.ingestion.documents.service import (
    DocumentsService,
)
from argus.domain.ingestion.email_intake.budget import business_day
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp import document_step
from argus.domain.ingestion.whatsapp.held import HeldFile, held_files
from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups
from faker import Faker
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
from workflows import document_worker
from workflows.document_job import postgres_documents_service

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

    async def link(self, language: str) -> None:
        status = await self.request("GET", LINK, headers=self.desk.auth, params={"language": language})
        code = await self.request(
            "POST",
            LINK + "-codes",
            headers=self.desk.auth,
            json={"disclosure_token": status["disclosure_token"], "language": language},
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


@pytest.fixture
def reply_language() -> str:
    return "es-419"


@pytest_asyncio.fixture
async def signed(
    desk: WalkthroughDesk, monkeypatch: pytest.MonkeyPatch, reply_language: str
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
                await w.link(reply_language)
                [w.link_reply] = replies
                replies.clear()
                yield w
    assert Counter(downloads) == Counter(w.media.keys())


class ScheduledSweeps:
    """Advance time through each sleep requested by the production worker."""

    def __init__(self, clock: Clock) -> None:
        self.clock, self.start = clock, clock()
        self.sleeps: asyncio.Queue[tuple[datetime, asyncio.Event]] = asyncio.Queue()

    async def sleep(self, seconds: float) -> None:
        wake = asyncio.Event()
        self.sleeps.put_nowait((self.clock() + timedelta(seconds=seconds), wake))
        await wake.wait()

    async def wait_for_sleep(self) -> None:
        self.wake_at, self.release = await asyncio.wait_for(self.sleeps.get(), timeout=10)
        assert self.wake_at > self.clock()

    async def advance(self, second: float) -> None:
        target = self.start + timedelta(seconds=second)
        assert self.clock() <= target
        while self.wake_at <= target:
            self.clock.now = self.wake_at
            self.release.set()
            await self.wait_for_sleep()
        self.clock.now = target


@pytest.fixture
def sweep_interval() -> int:
    return 30


@pytest_asyncio.fixture
async def scheduler(
    signed: SignedForward, sweep_interval: int, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ScheduledSweeps]:
    desk = signed.desk
    driver = ScheduledSweeps(desk.clock)
    monkeypatch.setenv("CUADRAO_DOCUMENT_JOBS_SWEEP_SECONDS", str(sweep_interval))
    clocked_asyncio = SimpleNamespace(**vars(asyncio))
    clocked_asyncio.sleep = driver.sleep
    clocked_asyncio.get_running_loop = lambda: SimpleNamespace(
        time=lambda: (desk.clock() - driver.start).total_seconds()
    )
    monkeypatch.setattr(jobs, "asyncio", clocked_asyncio)
    dsn, _ = local_targets()
    monkeypatch.setattr(document_worker, "require_database_url", lambda: dsn)
    monkeypatch.setattr(
        document_worker, "storage_source_objects", lambda: desk.service.store.objects
    )
    monkeypatch.setattr(
        document_worker, "postgres_documents_service", lambda *_: desk.service
    )
    # Each scenario takes the queued read at its specified time through read_receipt.
    monkeypatch.setattr(desk.service.store, "pull", lambda **_: None)
    stops = []
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "add_signal_handler",
        lambda _signal, stop: stops.append(stop),
    )
    worker = asyncio.create_task(document_worker.serve())
    try:
        await driver.wait_for_sleep()
        yield driver
    finally:
        if stops:
            stops[0]()
        else:
            worker.cancel()
        await worker

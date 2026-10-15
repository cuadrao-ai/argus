"""Personal and Business never see each other's records, on real Postgres.

The isolation matrix of docs/specs/lanes/cuadrao-business-space-slice-plan.md
section 5 for slices S1 to S3. Two owners, A and B, each hold a Personal and a
Business side, seeded with the same receipt bytes and the same purchase, so any
reader that loses its scope returns a literal id from the wrong side.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest
from argus.api.whatsapp import DocumentsDestination
from argus.domain import financial_search
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.service import BusinessService
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.household.repository import FinancialAccountLookup
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.documents.jobs import PreparationJobs, run_attempt
from argus.domain.ingestion.documents.objects import owner_prefix
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile.model import EventNotFound, ReconcileError
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.ingestion.whatsapp.store import Settlement
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from argus.domain.owner_scope import PERSONAL, OwnerScope
from argus.domain.planning import storage
from argus.domain.planning.service import PlanService
from argus.domain.recording import canonical_groups
from argus.domain.recording.errors import AccountNotFound, IdempotencyConflict
from argus.domain.recording.money_postgres import load_owner
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.postgres_repository import (
    PostgresFinancialAccountRepository,
)
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import ReceiptStub
from tests.business_reading_support import reading_setting, turn_reading
from tests.document_sources_support import LOCAL_STORAGE, source_objects

pytestmark = pytest.mark.skipif(
    not (shared.DSN and LOCAL_STORAGE),
    reason="ARGUS_DISPOSABLE_DATABASE_URL and the local Supabase stack are required",
)
RECEIPT = (
    Path(__file__).parent / "document_extraction_fixtures/receipt-dop.png"
).read_bytes()
ZONE = "America/Santo_Domingo"
DAY = date(2026, 10, 6)
SIDES = ("personal", "business")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class World:
    """Services over one pool, plus each owner's two scopes and seeded ids."""

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool
        self.spaces = PostgresSpaceStore(pool)
        self.connections = PostgresConnectionRepository(pool)
        self.repository = PostgresFinancialAccountRepository(pool)
        self.accounts = FinancialAccountService(self.repository, _now)
        self.money = MoneyService(self.accounts)
        self.imports = ReconciliationService(
            PostgresImportStore(pool), self.money, _now, connections=self.connections
        )
        self.hub = IngestionHub(self.connections, box=None, sink=self.imports, clock=_now)
        self.objects = source_objects()
        self.documents = DocumentsService(
            self.hub, PostgresDocumentStore(pool, self.objects), ReceiptStub()
        )
        self.documents.business_receipt_consent = reading_setting(pool)
        self.business = BusinessService(
            self.documents, self.imports, lambda _: frozenset()
        )
        self.people: dict[str, str] = {}
        self.scope: dict[tuple[str, str], OwnerScope] = {}
        self.biz: dict[str, BusinessScope] = {}
        self.account: dict[tuple[str, str], str] = {}
        self.expense: dict[tuple[str, str], str] = {}
        self.receipt: dict[tuple[str, str], str] = {}

    def side(self, who: str, side: str) -> tuple[str, OwnerScope]:
        return self.people[who], self.scope[(who, side)]


def _seed(world: World, who: str, side: str) -> None:
    person, scope = world.side(who, side)
    account = world.accounts.create(
        user_id=person,
        idempotency_key=f"{who}-{side}-account",
        request=CreateFinancialAccountRequest(
            type="checking", currency="DOP", nickname=f"{who} {side}"
        ),
        scope=scope,
    ).stored.account.id
    expense = world.money.write_entered(
        user_id=person,
        request=MoneyRequest(
            kind="expense",
            account_id=account,
            amount="250.50",
            occurred_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
            time_zone=ZONE,
            note="Colmado",
            category_id=None,
        ),
        idempotency_key=f"{who}-{side}-expense",
        scope=scope,
    )["activity"]["activity_id"]
    receipt = asyncio.run(
        world.documents.upload(
            user_id=person,
            content=RECEIPT,
            filename="recibo.png",
            media_type="image/png",
            consent=False,
            scope=scope,
        )
    ).connection_id
    asyncio.run(world.documents.enter(user_id=person, connection_id=receipt, scope=scope))
    world.account[(who, side)] = account
    world.expense[(who, side)] = expense
    world.receipt[(who, side)] = receipt


@pytest.fixture
def world() -> Iterator[World]:
    pool = ConnectionPool(shared.DSN, min_size=0, max_size=8, open=True)
    world = World(pool)
    with pool.connection() as connection:
        for who in ("a", "b"):
            person = str(uuid4())
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (person, f"spaces-{who}-{person}@example.test"),
            )
            world.people[who] = person
    try:
        for who, person in world.people.items():
            world.spaces.create(person, "Mi negocio")
            scope = resolve_business_scope(world.spaces, person)
            assert scope is not None
            world.biz[who] = scope
            world.scope[(who, "personal")] = PERSONAL
            world.scope[(who, "business")] = scope.owner
            for side in SIDES:
                _seed(world, who, side)
        yield world
    finally:
        for person in world.people.values():
            world.objects.delete(owner_prefix(person))
        with pool.connection() as connection:
            connection.execute(
                "delete from auth.users where id = any(%s)",
                (list(world.people.values()),),
            )
        pool.close()


QUADRANTS = [(who, side) for who in ("a", "b") for side in SIDES]


@pytest.mark.parametrize(("who", "side"), QUADRANTS)
def test_every_reader_returns_exactly_its_own_side(
    world: World, who: str, side: str
) -> None:
    person, scope = world.side(who, side)
    account, receipt = world.account[(who, side)], world.receipt[(who, side)]
    # R1, R2
    assert [
        s.account.id for s in world.accounts.list_accounts(user_id=person, scope=scope)
    ] == [account]
    others = [world.account[q] for q in QUADRANTS if q != (who, side)]
    for other in others:
        assert (
            world.repository.get_account(user_id=person, account_id=other, scope=scope)
            is None
        )
    # R3, R4
    with world.pool.connection() as connection:
        assert [
            s.account.id
            for s in load_owner(world.repository, connection, person, scope=scope)
        ] == [account]
        canonical = canonical_groups.load(
            world.repository, connection, {person}, scope=scope
        )
    assert set(canonical.current) == {world.expense[(who, side)]}
    # R5, R6
    assert [c.id for c in world.connections.list(user_id=person, scope=scope)] == [
        receipt
    ]
    for other in (world.receipt[q] for q in QUADRANTS if q != (who, side)):
        with pytest.raises(ConnectionNotFound):
            world.connections.get(user_id=person, connection_id=other, scope=scope)
    # R7, R8: the event the receipt created is the only one in scope.
    [event] = world.imports.list(user_id=person, states=("open",), scope=scope)
    assert [o["connection_id"] for o in event["observations"]] == [receipt]
    with world.imports.store.transaction(person, scope=scope) as tx:
        assert [e.id for e in tx.events(("open",))] == [event["id"]]
        assert tx.event(event["id"]).id == event["id"]
    for q in QUADRANTS:
        if q == (who, side):
            continue
        other_person, other_scope = world.side(*q)
        [foreign] = world.imports.list(
            user_id=other_person, states=("open",), scope=other_scope
        )
        with pytest.raises(EventNotFound):
            world.imports.detail(user_id=person, event_id=foreign["id"], scope=scope)
    # R9: review and confirm accept only this side's accounts.
    with pytest.raises(ReconcileError) as refused:
        world.imports.resolve(
            user_id=person,
            event_id=event["id"],
            version=event["version"],
            changes={
                "account_id": world.account[
                    (who, "business" if side == "personal" else "personal")
                ]
            },
            scope=scope,
        )
    assert refused.value.code == "financial_account_not_found"


def test_business_routes_reach_only_their_own_space(world: World) -> None:
    a, b = world.biz["a"], world.biz["b"]
    service = world.business
    before = {
        quadrant: world.accounts.list_accounts(
            user_id=world.people[quadrant[0]], scope=world.scope[quadrant]
        )
        for quadrant in QUADRANTS
    }
    assert [r.id for r in service.receipts(a)] == [world.receipt[("a", "business")]]
    assert [x["id"] for x in service.accounts_for_expenses(a)] == [
        world.account[("a", "business")]
    ]
    for forged in (world.receipt[("b", "business")], world.receipt[("a", "personal")]):
        with pytest.raises(ConnectionNotFound):
            service.receipt(a, forged)
        with pytest.raises(ConnectionNotFound):
            service.source(a, forged)
    entered = {
        "account_id": world.account[("a", "personal")],
        "amount": "10.00",
        "occurred_on": DAY,
        "merchant": "Ferretería",
        "category_id": None,
    }
    for account in (entered["account_id"], world.account[("b", "business")]):
        with pytest.raises(ReconcileError) as refused:
            service.record_expense(a, {**entered, "account_id": account}, "direct-entry")
        assert refused.value.code == "human_approval_required"
        with pytest.raises(AccountNotFound):
            world.money.write_entered(
                user_id=a.person_id,
                request=MoneyRequest(
                    kind="expense",
                    account_id=account,
                    amount=entered["amount"],
                    occurred_at=datetime.combine(
                        DAY, datetime.min.time(), ZoneInfo(ZONE)
                    ),
                    time_zone=ZONE,
                    note=entered["merchant"],
                    category_id=None,
                ),
                idempotency_key=f"forged-{account}",
                scope=a.owner,
            )
    for quadrant, original in before.items():
        assert (
            world.accounts.list_accounts(
                user_id=world.people[quadrant[0]], scope=world.scope[quadrant]
            )
            == original
        )
    expenses = service.expenses(a, date(2026, 10, 1), date(2026, 10, 31))
    assert [e["id"] for e in expenses] == [world.expense[("a", "business")]]
    assert (
        service.expenses(b, date(2026, 10, 1), date(2026, 10, 31))[0]["id"]
        == (world.expense[("b", "business")])
    )


def test_personal_keeps_working_after_a_business_expense(world: World) -> None:
    person = world.people["a"]
    a = world.biz["a"]
    original_personal = world.accounts.list_accounts(user_id=person, scope=PERSONAL)
    world.money.write_entered(
        user_id=person,
        request=MoneyRequest(
            kind="expense",
            account_id=world.account[("a", "business")],
            amount="99.00",
            occurred_at=datetime.combine(DAY, datetime.min.time(), ZoneInfo(ZONE)),
            time_zone=ZONE,
            note="Proveedor",
            category_id=None,
        ),
        idempotency_key="second-business-expense",
        scope=a.owner,
    )
    state, accounts = storage.read(world.repository, person)
    assert accounts == original_personal
    assert [s.account.id for s in accounts] == [world.account[("a", "personal")]]
    assert set(state["_canonical_groups"].current) == {world.expense[("a", "personal")]}
    hits = financial_search.search(world.accounts, person, q="").items
    account_hits = {h.account.id for h in hits if h.kind == "account"}
    activity_hits = {h.activity.activity_id for h in hits if h.kind == "activity"}
    assert account_hits == {world.account[("a", "personal")]}
    assert activity_hits == {world.expense[("a", "personal")]}
    today = datetime.now(ZoneInfo(ZONE)).date()
    overview = PlanService(world.accounts).read(person, today, today + timedelta(days=30))
    [dop] = overview["home"]["currencies"]
    assert dop["known_accounts"] + dop["unknown_accounts"] == 1
    assert {a["account_id"] for a in overview["home"]["recent_activity"]} == {
        world.account[("a", "personal")]
    }
    second = world.money.write_entered(
        user_id=person,
        request=MoneyRequest(
            kind="expense",
            account_id=world.account[("a", "personal")],
            amount="12.00",
            occurred_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            time_zone=ZONE,
            note="Farmacia",
            category_id=None,
        ),
        idempotency_key="personal-after-business",
        scope=PERSONAL,
    )
    assert second["replayed"] is False
    personal = world.accounts.list_accounts(user_id=person, scope=PERSONAL)
    assert len(canonical_ids(personal)) == 2


def canonical_ids(accounts: list) -> set[str]:  # noqa: ANN001
    return set(accounts.canonical.current)


def test_the_same_file_in_both_spaces_is_two_documents(world: World) -> None:
    person = world.people["a"]
    personal, business = (
        world.receipt[("a", "personal")],
        world.receipt[("a", "business")],
    )
    assert personal != business
    digest = hashlib.sha256(RECEIPT).hexdigest()
    with world.pool.connection() as connection:
        refs = dict(
            connection.execute(
                "select id::text, external_ref from public.financial_source_connections"
                " where user_id = %s",
                (person,),
            ).fetchall()
        )
    assert refs[personal] == hashlib.sha256(f"{person}:{digest}".encode()).hexdigest()
    assert (
        refs[business]
        == hashlib.sha256(
            f"{person}:{world.biz['a'].owner.space_id}:{digest}".encode()
        ).hexdigest()
    )
    for receipt, scope in ((personal, PERSONAL), (business, world.biz["a"].owner)):
        draft = world.documents.get(user_id=person, connection_id=receipt, scope=scope)
        assert draft.sha256 == digest


def _candidate(connection_id: str, external_id: str) -> ImportCandidate:
    return ImportCandidate.model_validate(
        {
            "source": {
                "source": "statement",
                "connection_id": connection_id,
                "external_id": external_id,
                "observed_at": _now(),
            },
            "evidence": "transaction",
            "amount": "777.00",
            "currency": "DOP",
            "occurred_on": DAY,
            "merchant": "FERRETERIA LA ESQUINA",
            "direction": "outflow",
            "kind_hint": "expense",
        }
    )


def test_import_matching_never_crosses_spaces(world: World) -> None:
    person = world.people["a"]
    personal, business = PERSONAL, world.biz["a"].owner
    made = {}
    for name, scope in (("p1", personal), ("b1", business)):
        made[name] = world.connections.create(
            user_id=person,
            source="statement",
            external_ref=f"match-{name}-{uuid4()}",
            label=None,
            now=_now(),
            scope=scope,
        ).id
    world.imports.submit(
        user_id=person,
        connection_id=made["b1"],
        candidates=[_candidate(made["b1"], "x")],
        scope=business,
    )
    world.imports.submit(
        user_id=person,
        connection_id=made["p1"],
        candidates=[_candidate(made["p1"], "x")],
        scope=personal,
    )
    matching = [
        e
        for e in world.imports.list(user_id=person, states=("open",), scope=business)
        if e["observations"][0]["connection_id"] == made["b1"]
    ]
    assert [e["possible_duplicates"] for e in matching] == [[]]
    [personal_event] = [
        e
        for e in world.imports.list(user_id=person, states=("open",), scope=personal)
        if e["observations"][0]["connection_id"] == made["p1"]
    ]
    assert personal_event["possible_duplicates"] == []
    # Duplicate matching reads only the transaction's own side.
    window = (DAY - timedelta(days=3), DAY + timedelta(days=3))
    with world.imports.store.transaction(person, scope=personal) as tx:
        assert [e.id for e in tx.nearby(*window)] == [personal_event["id"]]
    with world.imports.store.transaction(person, scope=business) as tx:
        assert [e.id for e in tx.nearby(*window)] == [matching[0]["id"]]
    # M5: a Business observation forced onto a Personal event is refused.
    with pytest.raises(
        psycopg.errors.RaiseException, match="import_observation_space_mismatch"
    ):
        with world.imports.store.transaction(person, scope=personal) as tx:
            [observation] = tx.observations(personal_event["id"])
            tx.put_observation(
                replace(
                    observation,
                    id=str(uuid4()),
                    connection_id=made["b1"],
                    external_id="forced",
                )
            )


def test_whatsapp_links_and_captures_into_the_business_space(world: World) -> None:
    person, business = world.people["a"], world.biz["a"].owner
    store = PostgresWhatsAppStore(world.pool)
    sender, code, now = bytes(range(32)), hashlib.sha256(uuid4().bytes).digest(), _now()
    store.issue_code(
        destination_owner_id=person,
        code_digest=code,
        reply_language="es-419",
        now=now,
        expires_at=now + timedelta(minutes=10),
    )
    assert (
        store.redeem_code(
            code_digest=code, sender_hash=sender, last4="1234", now=now
        ).destination_owner_id
        == person
    )
    with world.pool.connection() as connection:
        [(space,)] = connection.execute(
            "select destination_space_id::text from public.whatsapp_sender_links"
            " where destination_owner_id = %s and status = 'active'",
            (person,),
        ).fetchall()
    assert space == business.space_id
    destination = DocumentsDestination(world.documents, world.spaces)
    captured = asyncio.run(
        destination.capture(
            owner_id=person,
            content=RECEIPT + b"wa",
            filename="wa.png",
            media_type="image/png",
        )
    )
    assert world.connections.get(
        user_id=person, connection_id=captured.connection_id, scope=business
    )
    with pytest.raises(ConnectionNotFound):
        world.connections.get(
            user_id=person, connection_id=captured.connection_id, scope=PERSONAL
        )
    key = hashlib.sha256(uuid4().bytes).digest()
    claim = store.claim(
        provider_message_key=key,
        sender_hash=sender,
        now=now,
        claim_until=now + timedelta(seconds=90),
    )
    settled = store.settle(
        provider_message_key=key,
        claim_until=claim.record.claim_until,
        settlement=Settlement("captured", person, captured.connection_id),
        now=now,
    )
    assert settled == Settlement("captured", person, captured.connection_id)
    # M7: a Personal connection on a captured row is refused by the database.
    forged = hashlib.sha256(uuid4().bytes).digest()
    claim = store.claim(
        provider_message_key=forged,
        sender_hash=sender,
        now=now,
        claim_until=now + timedelta(seconds=90),
    )
    with pytest.raises(
        psycopg.errors.RaiseException, match="whatsapp_capture_space_mismatch"
    ):
        store.settle(
            provider_message_key=forged,
            claim_until=claim.record.claim_until,
            settlement=Settlement("captured", person, world.receipt[("a", "personal")]),
            now=now,
        )


def test_a_job_for_a_business_receipt_keeps_its_space(world: World) -> None:
    person, a = world.people["a"], world.biz["a"]
    turn_reading(world.documents.business_receipt_consent, a.owner.space_id, person)
    dispatched: list[tuple[str, str]] = []
    jobs = PreparationJobs(
        world.documents, lambda cid, aid: dispatched.append((cid, aid))
    )
    receipt = asyncio.run(
        world.documents.upload(
            user_id=person,
            content=RECEIPT + b"job",
            filename="job.png",
            media_type="image/png",
            consent=True,
            scope=a.owner,
        )
    ).connection_id
    jobs.start(user_id=person, connection_id=receipt)
    [(connection_id, attempt)] = dispatched
    assert asyncio.run(run_attempt(world.documents, connection_id, attempt)) == "prepared"
    assert receipt in {r.id for r in world.business.receipts(a)}
    assert world.business.receipt(a, receipt).status == "review_ready"
    personal_events = world.imports.list(user_id=person, states=("open",), scope=PERSONAL)
    assert receipt not in {
        o["connection_id"] for e in personal_events for o in e["observations"]
    }
    assert receipt not in {
        c.id for c in world.connections.list(user_id=person, scope=PERSONAL)
    }


def test_a_business_account_never_reaches_a_household(world: World) -> None:
    """create_grant refuses an account owned_account cannot find; M8 backs it up."""

    lookup = FinancialAccountLookup(world.repository)
    person = world.people["a"]
    assert (
        lookup.owned_account(user_id=person, account_id=world.account[("a", "business")])
        is None
    )
    assert (
        lookup.owned_account(user_id=person, account_id=world.account[("a", "personal")])
        is not None
    )


def test_an_account_key_replayed_from_the_other_side_conflicts(world: World) -> None:
    person = world.people["a"]
    request = CreateFinancialAccountRequest(type="cash", currency="DOP", nickname="Caja")
    first = world.accounts.create(
        user_id=person, idempotency_key="shared-key", request=request, scope=PERSONAL
    )
    replay = world.accounts.create(
        user_id=person, idempotency_key="shared-key", request=request, scope=PERSONAL
    )
    assert (replay.created, replay.stored.account.id) == (False, first.stored.account.id)
    with pytest.raises(IdempotencyConflict):
        world.accounts.create(
            user_id=person,
            idempotency_key="shared-key",
            request=request,
            scope=world.biz["a"].owner,
        )


def test_starting_a_space_is_idempotent_under_concurrency_and_owned_by_one_person(
    world: World,
) -> None:
    person = str(uuid4())
    with world.pool.connection() as connection:
        connection.execute(
            "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
            (person, f"spaces-race-{person}@example.test"),
        )
    try:
        with ThreadPoolExecutor(8) as pool:
            results = list(
                pool.map(lambda _: world.spaces.create(person, "Mi negocio"), range(8))
            )
        assert len({space.id for space, _ in results}) == 1
        assert sum(created for _, created in results) == 1
        with world.pool.connection() as connection:
            assert connection.execute(
                "select count(*) from public.spaces where created_by = %s", (person,)
            ).fetchone() == (1,)
        assert world.spaces.rename(person, "Taller").name == "Taller"
        assert world.spaces.open_space(world.people["a"]).name == "Mi negocio"
        assert resolve_business_scope(world.spaces, str(uuid4())) is None
    finally:
        with world.pool.connection() as connection:
            connection.execute("delete from auth.users where id = %s", (person,))

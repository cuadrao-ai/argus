"""Business receipts on real PostgreSQL and local Supabase Storage: one confirm
records one expense under concurrency, and image downloads retain their original.

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` plus ``ARGUS_LOCAL_SUPABASE_URL``,
``ARGUS_LOCAL_SUPABASE_ANON_KEY`` and ``ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY``
to run locally.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from argus.domain import financial_search
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from argus.domain.business.service import BusinessService
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.objects import SourceObjects, owner_prefix
from argus.domain.ingestion.documents.service import (
    DocumentServiceError,
    DocumentsService,
)
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.postgres_repository import (
    PostgresFinancialAccountRepository,
)
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import PURCHASE, ReceiptStub
from tests.business_reading_support import reading_setting, turn_reading
from tests.document_sources_support import LOCAL_STORAGE, source_objects, stored_paths

pytestmark = pytest.mark.skipif(
    not (shared.DSN and LOCAL_STORAGE),
    reason="ARGUS_DISPOSABLE_DATABASE_URL and the local Supabase stack are required",
)
RECEIPT = (
    Path(__file__).parent / "document_extraction_fixtures/receipt-dop.png"
).read_bytes()
OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def rig() -> Iterator[dict]:
    pool = ConnectionPool(shared.DSN, min_size=0, max_size=8, open=True)
    owner, other = str(uuid4()), str(uuid4())
    with pool.connection() as connection:
        for user in (owner, other):
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (user, f"business-{user}@example.test"),
            )
    objects = source_objects()
    spaces = PostgresSpaceStore(pool)
    try:
        yield {
            "pool": pool,
            "owner": _started(spaces, owner),
            "other": _started(spaces, other),
            "service": _service(pool, objects),
            # A new process over the same database and storage.
            "restart": lambda: _service(pool, objects),
        }
    finally:
        for user in (owner, other):
            objects.delete(owner_prefix(user))
        with pool.connection() as connection:
            connection.execute(
                "delete from auth.users where id = any(%s)", ([owner, other],)
            )
        pool.close()


def _service(pool: ConnectionPool, objects: SourceObjects) -> BusinessService:
    connections = PostgresConnectionRepository(pool)
    accounts = FinancialAccountService(PostgresFinancialAccountRepository(pool), _now)
    imports = ReconciliationService(
        PostgresImportStore(pool), MoneyService(accounts), _now, connections=connections
    )
    hub = IngestionHub(connections, box=None, sink=imports, clock=_now)
    documents = DocumentsService(hub, PostgresDocumentStore(pool, objects), ReceiptStub())
    documents.business_receipt_consent = reading_setting(pool)
    return BusinessService(documents, imports, lambda _: frozenset())


def _started(spaces: PostgresSpaceStore, person: str) -> BusinessScope:
    spaces.create(person, "Mi negocio")
    scope = resolve_business_scope(spaces, person)
    assert scope is not None
    return scope


def _prepared(rig: dict) -> str:
    service, scope = rig["service"], rig["owner"]
    turn_reading(
        service.documents.business_receipt_consent,
        scope.owner.space_id,
        scope.person_id,
    )
    receipt = asyncio.run(
        service.upload(
            scope,
            content=RECEIPT,
            filename="recibo.png",
            media_type="image/png",
            consent=True,
        )
    )
    asyncio.run(
        service.documents.resume(
            user_id=scope.person_id, connection_id=receipt.id, scope=scope.owner
        )
    )
    return receipt.id


def _reviewed(rig: dict) -> tuple[str, int]:
    service, scope = rig["service"], rig["owner"]
    receipt_id = _prepared(rig)
    account, _ = service.create_account(
        scope,
        CreateFinancialAccountRequest(type="checking", currency="DOP", nickname="Ops"),
        "acct",
    )
    reviewed = service.review(
        scope,
        receipt_id,
        service.receipt(scope, receipt_id).version,
        {"account_id": account["id"], "merchant": "Ferretería La Esquina"},
    )
    return receipt_id, reviewed.version


def _written(rig: dict) -> int:
    with rig["pool"].connection() as connection:
        return connection.execute(
            "select count(distinct activity_id) from public.financial_activity_receipts"
            " where user_id = %s",
            (rig["owner"].person_id,),
        ).fetchone()[0]


def test_an_interrupted_claim_is_finished_once_by_another_key(
    rig: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, scope = rig["service"], rig["owner"]
    receipt_id, version = _reviewed(rig)
    write = MoneyService.write

    def crash_after_claim(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
        raise RuntimeError("process died after the claim")

    monkeypatch.setattr(MoneyService, "write", crash_after_claim)
    with pytest.raises(RuntimeError):
        service.confirm(scope, receipt_id, version, "tab-a")
    assert _written(rig) == 0
    monkeypatch.setattr(MoneyService, "write", write)

    other_tab = service.confirm(scope, receipt_id, version, "tab-b")
    first_tab = service.confirm(scope, receipt_id, version, "tab-a")
    later = service.confirm(scope, receipt_id, version, "later")
    assert {(r.status, r.review.expense_id) for r in (other_tab, first_tab, later)} == {
        ("confirmed", other_tab.review.expense_id)
    }
    [expense] = service.expenses(scope, *OCTOBER)
    assert {
        key: expense[key] for key in ("merchant", "amount", "currency", "receipt_id")
    } == {
        "merchant": "Ferretería La Esquina",
        "amount": "3450.00",
        "currency": "DOP",
        "receipt_id": receipt_id,
    }
    assert _written(rig) == 1


def test_concurrent_confirms_in_any_order_record_one_expense(rig: dict) -> None:
    service, scope = rig["service"], rig["owner"]
    receipt_id, version = _reviewed(rig)
    keys = ["double-click", "double-click", "double-click", "other-tab"]
    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        results = list(
            pool.map(lambda key: service.confirm(scope, receipt_id, version, key), keys)
        )
    assert {(r.status, r.review.expense_id) for r in results} == {
        ("confirmed", results[0].review.expense_id)
    }
    assert _written(rig) == 1


def test_source_is_the_stored_object_and_only_its_owner_reads_it(rig: dict) -> None:
    service = rig["service"]
    receipt_id = _prepared(rig)
    media_type, content = service.source(rig["owner"], receipt_id)
    assert media_type == "image/jpeg" and content.startswith(b"\xff\xd8")
    assert content != RECEIPT
    owner = rig["owner"].person_id
    assert service.documents.store.source(user_id=owner, connection_id=receipt_id) == RECEIPT
    with rig["pool"].connection() as connection:
        sealed = stored_paths(connection, f"sealed/{owner}/")
        rebuilt = stored_paths(connection, f"rebuilt/{owner}/")
    assert len(sealed) == len(rebuilt) == 1
    assert sealed[0].rsplit("/", 1)[1] == rebuilt[0].rsplit("/", 1)[1]
    assert service.source(rig["owner"], receipt_id) == (media_type, content)
    with pytest.raises(ConnectionNotFound):
        service.source(rig["other"], receipt_id)
    with pytest.raises(ConnectionNotFound):
        service.receipt(rig["other"], receipt_id)


def test_a_receipt_entered_by_hand_is_saved_once_and_linked(rig: dict) -> None:
    service, scope = rig["service"], rig["owner"]
    receipt = asyncio.run(
        service.upload(
            scope,
            content=RECEIPT,
            filename="whatsapp-image",
            media_type="image/png",
            consent=False,
        )
    )
    account, _ = service.create_account(
        scope,
        CreateFinancialAccountRequest(type="cash", currency="DOP", nickname="Caja"),
        "acct",
    )
    version = asyncio.run(service.start_entry(scope, receipt.id, 0))
    entered = service.review(
        scope,
        receipt.id,
        version,
        {
            "merchant": "Colmado Don Pedro",
            "occurred_on": "2026-10-07",
            "amount": "706.10",
            "currency": "DOP",
            "account_id": account["id"],
        },
    )
    assert (entered.missing_fields, entered.detail()["evidence"]) == ([], None)
    first = service.confirm(scope, receipt.id, entered.version, "by-hand")
    second = service.confirm(scope, receipt.id, entered.version, "other-tab")
    assert first.review.expense_id == second.review.expense_id
    [expense] = service.expenses(scope, *OCTOBER)
    assert (expense["receipt_id"], expense["amount"], expense["merchant"]) == (
        receipt.id,
        "706.10",
        "Colmado Don Pedro",
    )
    with pytest.raises(DocumentServiceError) as refused:
        service.queue(scope, receipt.id)
    assert refused.value.code == "document_entered_by_owner"
    with rig["pool"].connection() as connection:
        events = connection.execute(
            "select count(*) from public.financial_import_events where user_id = %s",
            (scope.person_id,),
        ).fetchone()[0]
    assert (events, _written(rig)) == (1, 1)
    media_type, content = service.source(scope, receipt.id)
    assert media_type == "image/jpeg" and content.startswith(b"\xff\xd8")
    assert content != RECEIPT
    assert service.documents.store.source(user_id=scope.person_id, connection_id=receipt.id) == RECEIPT


def test_entry_by_hand_after_a_read_records_one_expense_across_tabs_and_a_restart(
    rig: dict,
) -> None:
    service, scope = rig["service"], rig["owner"]
    service.documents.extractor.rows = [
        PURCHASE,
        {**PURCHASE, "row": 2, "evidence": "payment_notice", "amount": "100.00"},
    ]
    receipt_id = _prepared(rig)
    read = service.receipt(scope, receipt_id)
    assert (read.attention, read.enterable, read.preparable, read.version) == (
        "several_purchases",
        True,
        False,
        0,
    )
    account, _ = service.create_account(
        scope,
        CreateFinancialAccountRequest(type="cash", currency="DOP", nickname="Caja"),
        "acct",
    )

    def enter(_: int) -> int:
        return asyncio.run(service.start_entry(scope, receipt_id, 0))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(enter, range(2)))
    current = service.receipt(scope, receipt_id)
    entered = service.review(
        scope,
        receipt_id,
        current.version,
        {
            "merchant": "Ferretería La Esquina",
            "occurred_on": "2026-10-06",
            "amount": "3450.00",
            "currency": "DOP",
            "account_id": account["id"],
        },
    )
    assert (entered.status, entered.attention, entered.missing_fields) == (
        "review_ready",
        None,
        [],
    )
    assert entered.detail()["evidence"]["total"] == "3450.00"

    restarted = rig["restart"]()
    assert asyncio.run(restarted.start_entry(scope, receipt_id, 0)) == 0
    first = restarted.confirm(scope, receipt_id, entered.version, "by-hand")
    second = rig["restart"]().confirm(scope, receipt_id, entered.version, "other-tab")
    assert first.review.expense_id == second.review.expense_id
    [expense] = restarted.expenses(scope, *OCTOBER)
    assert (expense["receipt_id"], expense["amount"]) == (receipt_id, "3450.00")
    with rig["pool"].connection() as connection:
        states = connection.execute(
            "select state, count(*) from public.financial_import_events"
            " where user_id = %s group by state order by state",
            (scope.person_id,),
        ).fetchall()
    assert (states, _written(rig)) == ([("accepted", 1), ("dismissed", 2)], 1)


def test_search_finds_the_business_expense_and_its_source_never_personal(
    rig: dict,
) -> None:
    service, scope = rig["service"], rig["owner"]
    accounts = service.accounts
    personal = accounts.create(
        user_id=scope.person_id,
        idempotency_key="personal-acct",
        request=CreateFinancialAccountRequest(
            type="checking", currency="DOP", nickname="Casa"
        ),
        scope=PERSONAL,
    ).stored.account
    zone = "America/Santo_Domingo"
    personal_expense = service.imports.money.write_entered(
        user_id=scope.person_id,
        request=MoneyRequest(
            kind="expense",
            account_id=personal.id,
            amount="99.00",
            occurred_at=datetime(2026, 10, 6, 9, 0, tzinfo=ZoneInfo(zone)),
            time_zone=zone,
            note="Ferretería La Esquina",
        ),
        idempotency_key="personal-expense",
        scope=PERSONAL,
    )["activity"]["activity_id"]
    receipt_id, version = _reviewed(rig)
    expense_id = service.confirm(scope, receipt_id, version, "k").review.expense_id

    found = service.search(scope, "ferreteria", 5)

    assert [(e["id"], e["receipt_id"]) for e in found["expenses"]] == [
        (expense_id, receipt_id)
    ]
    assert (found["receipts"], found["accounts"]) == ([], [])
    media_type, content = service.source(scope, receipt_id)
    assert media_type == "image/jpeg" and content.startswith(b"\xff\xd8")
    assert content != RECEIPT
    assert service.documents.store.source(user_id=scope.person_id, connection_id=receipt_id) == RECEIPT
    assert [r["id"] for r in service.search(scope, "recibo", 5)["receipts"]] == [
        receipt_id
    ]
    assert [a["nickname"] for a in service.search(scope, "ops", 5)["accounts"]] == ["Ops"]
    assert service.search(rig["other"], "ferreteria", 5) == {
        "expenses": [],
        "receipts": [],
        "accounts": [],
    }
    personal_hits = financial_search.search(
        accounts, scope.person_id, q="ferreteria"
    ).items
    assert [hit.activity.activity_id for hit in personal_hits] == [personal_expense]

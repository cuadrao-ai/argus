"""The owner-scope rule and the required ``scope`` keyword on every scoped reader and writer.

``scope`` has no default anywhere in the plan's section 2 table, so a caller
that forgets it fails at the call instead of reading the other side's rows.
The in-memory twins apply the same null rule as Postgres.
"""

import hashlib
import inspect
from datetime import datetime, timezone

import pytest
from argus.domain.ingestion.connections import (
    ConnectionNotFound,
    ConnectionRepository,
    InMemoryConnectionRepository,
)
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService, document_ref
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile import intake
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent
from argus.domain.ingestion.reconcile.recording import Recording
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store import ImportStore, InMemoryImportStore
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.ingestion.sink import CandidateSink
from argus.domain.owner_scope import (
    PERSONAL,
    BusinessSpace,
    holds,
    scope_of,
    space_id,
    sql_predicate,
)
from argus.domain.recording import canonical_groups, money_postgres, money_storage
from argus.domain.recording.errors import AccountNotFound, IdempotencyConflict
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
from argus.domain.recording.repository import (
    FinancialAccountRepository,
    InMemoryFinancialAccountRepository,
    NewAccount,
)
from argus.domain.recording.service import FinancialAccountService

SHOP = BusinessSpace("7c1d2f9e-0000-4000-8000-000000000001")
OTHER_SHOP = BusinessSpace("7c1d2f9e-0000-4000-8000-000000000002")
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

SCOPED = [
    *(
        getattr(cls, name)
        for cls in (
            FinancialAccountRepository,
            PostgresFinancialAccountRepository,
            InMemoryFinancialAccountRepository,
        )
        for name in (
            "create",
            "list_accounts",
            "get_account",
            "update_account",
            "write_opening",
            "mutate",
            "write_asset_details",
        )
    ),
    PostgresFinancialAccountRepository._load,
    money_postgres.load_owner,
    money_postgres.transact_postgres,
    money_storage.transact,
    canonical_groups.load,
    *(
        getattr(cls, name)
        for cls in (
            ConnectionRepository,
            PostgresConnectionRepository,
            InMemoryConnectionRepository,
        )
        for name in ("create", "get", "list")
    ),
    IngestionHub.list,
    IngestionHub.disconnect,
    ImportStore.transaction,
    PostgresImportStore.transaction,
    InMemoryImportStore.transaction,
    CandidateSink.submit,
    CandidateSink.forget_connection,
    intake.submit,
    intake.forget,
    *(
        getattr(ReconciliationService, name)
        for name in (
            "submit",
            "forget_connection",
            "list",
            "detail",
            "resolve",
            "merge",
            "dismiss",
            "reopen",
            "acknowledge",
        )
    ),
    *(
        getattr(Recording, name)
        for name in (
            "preview",
            "accept",
            "accept_batch",
            "accept_reviewed",
            "link_activity",
        )
    ),
    *(
        getattr(FinancialAccountService, name)
        for name in ("create", "list_accounts", "get", "edit", "write_opening")
    ),
    *(
        getattr(MoneyService, name)
        for name in (
            "preview",
            "write",
            "write_entered",
            "detail",
            "history",
            "purchases",
        )
    ),
    *(
        getattr(DocumentsService, name)
        for name in (
            "get",
            "source_bytes",
            "update_proposal",
            "upload",
            "outcome",
            "queue",
            "enter",
            "resume",
            "background_prepare",
        )
    ),
]


@pytest.mark.parametrize("function", SCOPED, ids=lambda f: f.__qualname__)
def test_scope_is_a_required_keyword_with_no_default(function) -> None:  # noqa: ANN001
    parameter = inspect.signature(function).parameters["scope"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_the_null_rule_has_one_owner() -> None:
    assert sql_predicate(PERSONAL, "a.owner_space_id") == ("a.owner_space_id is null", ())
    assert sql_predicate(SHOP, "owner_space_id") == (
        "owner_space_id = %s",
        ("7c1d2f9e-0000-4000-8000-000000000001",),
    )
    assert space_id(PERSONAL) is None
    assert space_id(SHOP) == "7c1d2f9e-0000-4000-8000-000000000001"
    assert scope_of(None) == PERSONAL
    assert scope_of("7c1d2f9e-0000-4000-8000-000000000001") == SHOP
    assert holds(PERSONAL, None) and not holds(PERSONAL, SHOP.space_id)
    assert holds(SHOP, SHOP.space_id) and not holds(SHOP, None)
    assert not holds(SHOP, OTHER_SHOP.space_id)


def test_personal_document_reference_is_the_original_formula() -> None:
    digest = hashlib.sha256(b"receipt").hexdigest()
    original = hashlib.sha256(f"person-1:{digest}".encode()).hexdigest()
    assert document_ref("person-1", PERSONAL, digest) == original
    business = document_ref("person-1", SHOP, digest)
    assert (
        business
        == hashlib.sha256(f"person-1:{SHOP.space_id}:{digest}".encode()).hexdigest()
    )
    assert business != original


def _account(repository: InMemoryFinancialAccountRepository, key: str, scope) -> str:  # noqa: ANN001
    return repository.create(
        user_id="person-1",
        idempotency_key=key,
        identity_hash="same-body",
        account=NewAccount("checking", "DOP", key, 10_000),
        opening=None,
        scope=scope,
    ).stored.account.id


def test_in_memory_accounts_stay_on_their_side() -> None:
    repository = InMemoryFinancialAccountRepository(lambda: NOW)
    personal = _account(repository, "personal", PERSONAL)
    business = _account(repository, "business", SHOP)
    listed = {
        scope: [
            s.account.id
            for s in repository.list_accounts(user_id="person-1", scope=scope)
        ]
        for scope in (PERSONAL, SHOP, OTHER_SHOP)
    }
    assert listed == {PERSONAL: [personal], SHOP: [business], OTHER_SHOP: []}
    assert (
        repository.get_account(user_id="person-1", account_id=business, scope=PERSONAL)
        is None
    )
    with pytest.raises(AccountNotFound):
        repository.update_account(
            user_id="person-1",
            account_id=personal,
            expected_version=1,
            changes={"nickname": "moved"},
            scope=SHOP,
        )


def test_in_memory_create_key_replayed_from_the_other_side_conflicts() -> None:
    repository = InMemoryFinancialAccountRepository(lambda: NOW)
    first = _account(repository, "one-key", PERSONAL)
    assert _account(repository, "one-key", PERSONAL) == first
    with pytest.raises(IdempotencyConflict):
        _account(repository, "one-key", SHOP)


def test_in_memory_connections_stay_on_their_side() -> None:
    repository = InMemoryConnectionRepository()
    rows = {
        scope: repository.create(
            user_id="person-1",
            source="statement",
            external_ref=f"ref-{label}",
            label="Document",
            now=NOW,
            scope=scope,
        )
        for label, scope in (("p", PERSONAL), ("b", SHOP))
    }
    assert [r.id for r in repository.list(user_id="person-1", scope=SHOP)] == [
        rows[SHOP].id
    ]
    assert [r.id for r in repository.list(user_id="person-1", scope=PERSONAL)] == [
        rows[PERSONAL].id
    ]
    with pytest.raises(ConnectionNotFound):
        repository.get(user_id="person-1", connection_id=rows[SHOP].id, scope=PERSONAL)
    found = repository.get_any_scope(user_id="person-1", connection_id=rows[SHOP].id)
    assert found.scope == SHOP


def _event(event_id: str) -> ImportEvent:
    return ImportEvent(
        id=event_id,
        user_id="person-1",
        state="open",
        evidence="transaction",
        anchor_on=NOW.date(),
        attention=None,
        attention_detail=None,
        possible_duplicates=(),
        resolution={},
        activity_id=None,
        accept_key=None,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )


def test_in_memory_import_events_stay_on_their_side() -> None:
    store = InMemoryImportStore()
    with store.transaction("person-1", scope=SHOP) as tx:
        tx.put_event(_event("business-event"))
    with store.transaction("person-1", scope=PERSONAL) as tx:
        tx.put_event(_event("personal-event"))
        assert [e.id for e in tx.events(("open",))] == ["personal-event"]
        assert [e.id for e in tx.nearby(NOW.date(), NOW.date())] == ["personal-event"]
        with pytest.raises(EventNotFound):
            tx.event("business-event")
    with store.transaction("person-1", scope=SHOP) as tx:
        assert [e.id for e in tx.events(("open",))] == ["business-event"]

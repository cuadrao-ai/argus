from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ProposeActivity
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore

from tests import test_business_actions_postgres as shared

users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark
create = shared.create
prepare = shared.prepare
ready = shared.ready


@pytest.fixture
def production_sink(actions, monkeypatch):
    from argus.api import ingestion
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository

    service, _, _ = actions
    monkeypatch.setattr(ingestion.api_state, "PERSISTENCE_MODE", "supabase")
    monkeypatch.setattr(
        ingestion, "financial_accounts_service", lambda: service.imports.money.accounts
    )
    sink = ingestion._reconciliation(
        service.authority.pool, PostgresConnectionRepository(service.authority.pool)
    )
    assert isinstance(sink.store, PostgresImportStore)
    return sink


@pytest.mark.parametrize("typed_first", [True, False])
def test_atomic_store_guard_blocks_distinct_legacy_and_typed_receipt_candidates(
    actions, typed_first, production_sink
):
    from argus.domain.business.contracts.dossier import AttachmentSource

    from tests.ingestion.reconcile_cases import cand
    from tests.test_business_spaces_migration_postgres import connection

    service, context, _ = actions
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
    source_id = service.record_source(
        context,
        "atomic-receipt",
        AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=datetime.now(timezone.utc),
            connection_id=receipt,
            filename="receipt.png",
            media_type="image/png",
        ),
    )
    key, lease = prepare(
        service,
        context,
        [
            ProposeActivity(
                facts=BusinessFactPatch(amount={"state": "unknown"}),
                source_ids=(source_id,),
            )
        ],
    )
    legacy = production_sink

    def deliver():
        legacy.submit(
            user_id=context.owner_id,
            connection_id=receipt,
            candidates=[
                cand(receipt, "one", source="statement", amount="25", currency="DOP")
            ],
            scope=context.scope,
        )

    if typed_first:
        assert service.execute(context, key, 0, lease=lease).outcome == "applied"
        with pytest.raises(ActionError, match="business_action_required"):
            deliver()
    else:
        deliver()
        assert (
            service.execute(context, key, 0, lease=lease).code
            == "business_legacy_conversion_unsupported"
        )
    with service.authority.pool.connection() as db:
        remaining = db.execute(
            "select id from public.financial_import_events where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchall()
    assert len(remaining) == 1
    from argus.domain.business.actions.receipts import draft_for_receipt
    from argus.domain.business.transactions import transaction

    expected = remaining[0][0]
    with transaction(service.authority, context) as tx:
        assert draft_for_receipt(
            tx, UUID(receipt), None if typed_first else expected
        ) == (expected, False)


def test_raw_factory_rejects_strong_match_into_typed_history(actions, production_sink):
    from argus.domain.ingestion.reconcile.model import AccountLink

    from tests.ingestion.reconcile_cases import cand
    from tests.test_business_spaces_migration_postgres import connection

    service, context, _ = actions
    draft = ready(service, context)
    before = service.dossier(context, draft)
    account_id = str(before.facts.funding.value.account_id)
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
    with production_sink.store.transaction(context.owner_id, scope=context.scope) as tx:
        tx.put_link(
            AccountLink(
                context.owner_id,
                receipt,
                "id:bank",
                account_id,
                datetime.now(timezone.utc),
            )
        )
    with pytest.raises(ActionError, match="business_action_required"):
        production_sink.submit(
            user_id=context.owner_id,
            connection_id=receipt,
            scope=context.scope,
            candidates=[
                cand(
                    receipt,
                    "strong",
                    source="statement",
                    amount="850",
                    currency="DOP",
                    occurred_on="2026-10-01",
                    direction="outflow",
                    account={"external_account_id": "bank"},
                )
            ],
        )
    after = service.dossier(context, draft)
    assert after.version == before.version
    assert after.history == before.history
    assert after.facts == before.facts
    with production_sink.store.transaction(context.owner_id, scope=context.scope) as tx:
        assert tx.observations(str(draft)) == []


def test_raw_factory_forget_preserves_existing_typed_candidate(actions, production_sink):
    from tests.test_business_spaces_migration_postgres import connection, observation

    service, context, _ = actions
    draft, version = create(service, context)
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
        observation(db, context.owner_id, str(draft), receipt)
    before = service.dossier(context, draft)
    with pytest.raises(ActionError, match="business_action_required"):
        production_sink.forget_connection(
            user_id=context.owner_id, connection_id=receipt, scope=context.scope
        )
    after = service.dossier(context, draft)
    assert after.version == version
    assert after.history == before.history
    assert after.sources == before.sources
    with production_sink.store.transaction(context.owner_id, scope=context.scope) as tx:
        assert len(tx.observations(str(draft))) == 1


def test_raw_factory_personal_intake_and_forget_unchanged(actions, production_sink):
    from argus.domain.owner_scope import PERSONAL

    from tests.ingestion.reconcile_cases import cand
    from tests.test_business_spaces_migration_postgres import connection

    service, context, _ = actions
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id)
    result = production_sink.submit(
        user_id=context.owner_id,
        connection_id=receipt,
        scope=PERSONAL,
        candidates=[
            cand(receipt, "personal", source="statement", amount="25", currency="DOP")
        ],
    )
    assert result.recorded == 1
    assert (
        production_sink.forget_connection(
            user_id=context.owner_id, connection_id=receipt, scope=PERSONAL
        )
        == 1
    )
    with production_sink.store.transaction(context.owner_id, scope=PERSONAL) as tx:
        assert tx.events(("open",)) == []

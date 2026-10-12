"""On real Postgres through the C0 bridge: a receipt whose read shows two
purchases becomes one open draft with real blockers, approval stays closed
while the amount is unknown, one approval records exactly one purchase, the
dossier keeps saying what the receipt still leaves unrecorded until a person
settles it, and a repeated preparation replays instead of making a second
draft."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ReviewDraft,
    SettleRemainder,
)
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from argus.domain.recording.money_reads import current_activities
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_financial_accounts_postgres as accounts
from tests.test_business_spaces_migration_postgres import connection

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


@pytest.fixture
def two_purchases(actions):  # noqa: ANN001
    return saved_two_purchases(actions)


def saved_two_purchases(actions):  # noqa: ANN001
    """A saved document whose read shows two purchases of one receipt."""

    service, context, grant = actions
    content = b"synthetic receipt with two purchases"
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    with service.authority.pool.connection() as db:
        cid = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=cid,
            filename="dos-compras.txt",
            media_type="text/plain",
            sha256=digest,
            size_bytes=len(content),
            consent=True,
            created_at=now,
            updated_at=now,
        )
        result = ExtractionResult.model_validate(
            dict(
                complete=True,
                readable=True,
                pages_read=[1],
                observations=[
                    dict(
                        page=1,
                        row=row,
                        evidence="transaction",
                        amount=amount,
                        currency="DOP",
                        direction="outflow",
                        kind_hint="expense",
                        merchant="Colmado La Esquina",
                        occurred_on="2026-10-11",
                    )
                    for row, amount in ((1, "245.00"), (2, "95.00"))
                ],
                receipt=dict(total="340.00", currency="DOP"),
            )
        )
        batch = batch_from_result(result, digest, cid, now, 1)
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=draft.media_type,
            size_bytes=len(content),
            filename=draft.filename,
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest},
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
            }
        )
        db.execute(
            "insert into public.financial_document_extractions"
            " (connection_id,user_id,draft,source_bytes,batch) values (%s,%s,%s,%s,%s)",
            (
                cid,
                context.owner_id,
                Jsonb(draft.model_dump(mode="json")),
                content,
                Jsonb(batch.model_dump(mode="json")),
            ),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s,"
            " lease_until=%s where id=%s",
            (holder, now + timedelta(minutes=3), cid),
        )
    return service, context, grant, cid, holder, batch


def _drafts(service, context) -> int:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        return db.execute(
            "select count(*) from public.financial_import_events where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchone()[0]


def _account(service, context):  # noqa: ANN001
    from argus.domain.recording.repository import NewAccount

    return service.imports.money.repository.create(
        user_id=context.owner_id,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        account=NewAccount(
            type="cash", currency="DOP", nickname="Till", ownership_share_bps=10000
        ),
        opening=accounts._opening(1000000),
        scope=context.scope,
    ).stored.account.id


def test_two_purchases_record_one_expense_and_keep_asking_for_the_rest(
    two_purchases,
) -> None:  # noqa: ANN001
    service, context, _, _, _, _ = two_purchases
    bridge.bind(two_purchases)
    first = bridge.finish(two_purchases)
    assert first.outcome == "applied", first
    view = service.dossier(context, first.draft_id)
    codes = [(b.code, b.field) for b in view.blockers]
    assert ("fact_required", "amount") in codes
    assert view.approval_available is False
    assert view.facts.amount.state == "unknown"
    assert view.facts.counterparty.value == "Colmado La Esquina"
    assert [(p.index, Decimal(p.amount)) for p in view.read_purchases] == [
        (1, Decimal("245")),
        (2, Decimal("95")),
    ]
    assert (view.read_total, view.unrecorded_purchases) == ("340.00", 2)
    # Preparing the same receipt again replays the first draft; no second draft.
    again = bridge.finish(two_purchases)
    assert again.draft_id == first.draft_id
    assert _drafts(service, context) == 1
    # Approval stays closed while the amount is unknown, even with the rest filled.
    account = _account(service, context)
    filled = service.review(
        context,
        first.draft_id,
        ReviewDraft(
            version=view.version,
            facts=BusinessFactPatch.model_validate(
                {
                    "funding": {
                        "state": "known",
                        "value": {"kind": "business_account", "account_id": account},
                    },
                    "business_share": {"state": "known", "value": {"kind": "all"}},
                }
            ),
        ),
        "fill",
    )
    assert filled.outcome == "applied", filled
    refused = service.approve(
        context,
        first.draft_id,
        ApproveExpense(version=filled.version, action="record_expense"),
        "too-early",
    )
    assert refused.outcome != "applied", refused
    assert service.dossier(context, first.draft_id).approval_available is False
    # One purchase chosen, one approval, exactly one expense recorded.
    chosen = service.review(
        context,
        first.draft_id,
        ReviewDraft(
            version=filled.version,
            facts=BusinessFactPatch.model_validate(
                {"amount": {"state": "known", "value": "245.00"}}
            ),
        ),
        "choose",
    )
    assert chosen.outcome == "applied", chosen
    recorded = service.approve(
        context,
        first.draft_id,
        ApproveExpense(version=chosen.version, action="record_expense"),
        "approve",
    )
    assert recorded.outcome == "applied", recorded
    accounts = service.imports.money.accounts.list_accounts(
        user_id=context.owner_id, scope=context.scope
    )
    activities = current_activities(accounts)
    assert len(activities) == 1
    assert activities[0]["amount_minor"] == 24500
    after = service.dossier(context, first.draft_id)
    assert after.review_state == "accepted"
    assert (after.read_total, after.unrecorded_purchases) == ("340.00", 1)
    assert len(after.read_purchases) == 2
    # A person settles the rest; the ledger holds that decision once.
    settled = service.settle_remainder(
        context, first.draft_id, SettleRemainder(version=after.version), "settle"
    )
    assert settled.outcome == "applied", settled
    # The same key again replays the stored outcome; nothing is written twice.
    assert (
        service.settle_remainder(
            context, first.draft_id, SettleRemainder(version=after.version), "settle"
        )
        == settled
    )
    done = service.dossier(context, first.draft_id)
    assert (done.unrecorded_purchases, done.review_state) == (0, "accepted")
    assert done.facts.amount.value in ("245.00", "245")
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts"
                " where space_id=%s and command->>'action'='settle_remainder'",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 1
        )
    assert current_activities(accounts) == activities
    twice = service.settle_remainder(
        context, first.draft_id, SettleRemainder(version=done.version), "settle-2"
    )
    assert twice.outcome == "invalid_input" and twice.code == "business_remainder_none"

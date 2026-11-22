from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest
from argus.domain.business.actions import document_ledger
from argus.domain.business.actions.document_purge import DocumentExpiry
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ApproveExpense, ApproveRefund
from argus.domain.business.contracts.deletion import PURGE_AFTER
from argus.domain.business.month_close import Settlement
from argus.domain.business.month_close_store import settle_document
from psycopg import Connection

from tests import test_business_declaration_after_approval_postgres as recording
from tests import test_business_document_delete_postgres as deleting
from tests import test_business_document_purge_postgres as purging
from tests import test_financial_accounts_postgres as shared
from tests.business_accept_support import seen_gaps
from tests.document_sources_support import source_objects
from tests.test_business_dgii_postgres import cash_account

actions = deleting.actions
users = deleting.users
pytestmark = deleting.pytestmark


def _refused(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


@pytest.mark.parametrize("recorded", [False, True])
def test_credit_note_link_prevents_delete_in_both_directions(actions, recorded):
    service, owner, _ = actions
    cash = recording.account_funding(cash_account(service, owner))
    purchase, version = recording.captured(service, owner, "B0100005901", cash)
    original = recording.approved(service, owner, purchase, version).approval_result
    credit, version = recording.captured(
        service,
        owner,
        "B0400005901",
        cash,
        recording.blank_declaration(
            actual_refund=True,
            purchase_activity_id=original.activity_id,
        ),
        amount="118.00",
        itbis="18.00",
        kind="refund",
        occurred_on="2026-09-10",
    )
    if recorded:
        result = service.approve_refund(
            owner,
            credit,
            ApproveRefund(
                version=version,
                action="record_refund",
                accept_gaps=seen_gaps(service, owner, credit),
            ),
            str(uuid4()),
        )
        assert result.outcome == "applied", result

    client = deleting._client(service, owner)
    targets = (purchase, credit) if recorded else (purchase,)
    for target in targets:
        before = service.dossier(owner, target)
        _refused(deleting._act(client, target, "delete"), 422, "business_document_linked")
        after = service.dossier(owner, target)
        assert before == after and not after.delete_available


def test_record_with_a_payment_settlement_cannot_be_deleted(actions):
    service, owner, _ = actions
    draft = deleting._captured_purchase(service, owner, approve=True)
    approved = service.dossier(owner, draft).approval_result.activity_id
    settle_document(
        service.authority,
        owner,
        str(approved),
        Settlement("pagado", date(2026, 9, 4), "efectivo"),
    )

    _refused(
        deleting._act(deleting._client(service, owner), draft, "delete"),
        422,
        "business_document_linked",
    )
    dossier = service.dossier(owner, draft)
    assert dossier.review_state == "accepted" and not dossier.delete_available


def test_document_linked_to_an_independently_recorded_activity_cannot_be_deleted(actions):
    service, owner, _ = actions
    draft = deleting._captured_purchase(service, owner, approve=True)
    # Persist the shape of an independently linked record from legacy import.
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events set accept_key=null,"
            " resolution=resolution - 'approval_receipt' - 'accepted_request' where id=%s",
            (draft,),
        )

    _refused(
        deleting._act(deleting._client(service, owner), draft, "delete"),
        422,
        "business_document_linked",
    )
    assert not service.dossier(owner, draft).delete_available


def test_settlement_waits_for_delete_then_cannot_target_the_hidden_record(
    actions, monkeypatch
):
    service, owner, _ = actions
    draft = deleting._captured_purchase(service, owner, approve=True)
    activity = service.dossier(owner, draft).approval_result.activity_id
    reached, finish = Event(), Event()
    set_reversed = document_ledger.set_reversed
    backend = []

    def pause(tx, activity, at):
        set_reversed(tx, activity, at)
        backend.append(tx.connection.info.backend_pid)
        reached.set()
        assert finish.wait(10)

    def settle():
        with pytest.raises(ActionError) as refused:
            settle_document(
                service.authority,
                owner,
                str(activity),
                Settlement("pagado", date(2026, 9, 4), "efectivo"),
            )
        assert refused.value.code == "business_record_not_found"

    monkeypatch.setattr(document_ledger, "set_reversed", pause)
    with ThreadPoolExecutor(2) as pool:
        deleted = pool.submit(
            deleting._act, deleting._client(service, owner), draft, "delete"
        )
        try:
            assert reached.wait(5)
            settled = pool.submit(settle)
            # Observe the competing connection queued on the transaction lock.
            with Connection.connect(shared.DSN, autocommit=True) as db:
                until = datetime.now(timezone.utc) + timedelta(seconds=3)
                waited = False
                while not settled.done() and datetime.now(timezone.utc) < until:
                    (waited,) = db.execute(
                        "select exists (select 1 from pg_stat_activity where wait_event='advisory'"
                        " and %s=any(pg_blocking_pids(pid)))",
                        (backend[0],),
                    ).fetchone()
                    if waited:
                        break
            assert waited and not settled.done()
        finally:
            finish.set()
        assert deleted.result(timeout=5).status_code == 200
        settled.result(timeout=5)


def test_live_restore_window_reserves_a_recorded_comprobante(actions):
    service, owner, _ = actions
    cash = recording.account_funding(cash_account(service, owner))
    target, version = recording.captured(service, owner, "B0100005902", cash)
    recording.approved(service, owner, target, version)
    client = deleting._client(service, owner)
    response = deleting._act(client, target, "delete")
    assert response.status_code == 200, response.text
    copy, version = recording.captured(service, owner, "B0100005902", cash)
    result = service.approve(
        owner,
        copy,
        ApproveExpense(
            version=version,
            action="record_expense",
            accept_gaps=seen_gaps(service, owner, copy),
        ),
        str(uuid4()),
    )
    assert result.outcome == "invalid_input", result
    assert result.code == "duplicate_comprobante" and result.existing_record_id == target
    assert deleting._act(client, target, "restore").status_code == 200


def test_approval_waiting_to_record_cannot_recreate_money_after_purge(actions, monkeypatch):
    service, owner, _ = actions
    draft = deleting._captured_purchase(service, owner)
    approval = ApproveExpense(
        action="record_expense",
        version=service.dossier(owner, draft).version,
        accept_gaps=seen_gaps(service, owner, draft),
    )
    claim_key = str(uuid4())
    reached, resume = Event(), Event()
    write = service.imports._write

    def pause_first(*args, **kwargs):
        if not reached.is_set():
            reached.set()
            assert resume.wait(15)
        return write(*args, **kwargs)

    monkeypatch.setattr(service.imports, "_write", pause_first)
    client = deleting._client(service, owner)
    with ThreadPoolExecutor(1) as executor:
        delayed = executor.submit(service.approve, owner, draft, approval, claim_key)
        try:
            assert reached.wait(5)
            winner = service.approve(owner, draft, approval, claim_key)
            assert winner.outcome == "applied", winner
            delete = deleting._act(client, draft, "delete")
            assert delete.status_code == 200, delete.text
            purge = deleting._act(client, draft, "purge")
            assert purge.status_code == 200, purge.text
        finally:
            resume.set()
        late = delayed.result(timeout=10)

    with Connection.connect(shared.DSN) as db:
        assert db.execute(
            "select count(*) from public.financial_activity_groups where user_id=%s",
            (owner.owner_id,),
        ).fetchone() == (0,)
        assert db.execute(
            "select count(*) from public.financial_activity_receipts where user_id=%s",
            (owner.owner_id,),
        ).fetchone() == (0,)
    assert late.outcome == "not_found" and late.code == "business_record_not_found"


@pytest.mark.parametrize("reason", ["owner", "expiry"])
def test_accepted_document_purge_removes_its_money_and_revisions(actions, reason):
    service, owner, _ = actions
    target = deleting._captured_purchase(service, owner, approve=True)
    other = deleting._captured_purchase(service, owner, approve=True)
    activity = service.dossier(owner, target).approval_result.activity_id
    other_activity = service.dossier(owner, other).approval_result.activity_id
    client = deleting._client(service, owner)
    with Connection.connect(shared.DSN) as db:
        (record,) = db.execute(
            "select record_id from public.financial_activity_memberships where activity_id=%s",
            (activity,),
        ).fetchone()
    deleted = deleting._act(client, target, "delete")
    assert deleted.status_code == 200, deleted.text
    marker = service.dossier(owner, target).deleted
    expiry = DocumentExpiry(
        service.authority.pool, source_objects(), every=timedelta(hours=1)
    )
    if reason == "owner":
        purged = deleting._act(client, target, "purge")
        assert purged.status_code == 200, purged.text
    else:
        expiry.run(marker.at + PURGE_AFTER - timedelta(seconds=1))
        assert service.dossier(owner, target).deleted == marker
        expiry.run(marker.at + PURGE_AFTER)

    _refused(deleting._act(client, target, "restore"), 404, "business_document_purged")
    assert deleting._act(client, target, "purge").status_code == 200
    with Connection.connect(shared.DSN) as db:
        for table, field, value in (
            ("financial_import_events", "id", target),
            ("business_draft_revisions", "draft_id", target),
            ("financial_activity_groups", "id", activity),
            ("financial_activity_revisions", "activity_id", activity),
            ("financial_records", "id", record),
            ("financial_record_revisions", "record_id", record),
        ):
            assert (
                db.execute(
                    f"select 1 from public.{table} where {field}=%s", (value,)
                ).fetchone()
                is None
            ), table
        assert db.execute(
            "select reversed_at from public.financial_activity_groups where id=%s",
            (other_activity,),
        ).fetchone() == (None,)
    action = f"{'purge' if reason == 'owner' else 'expire'}_document"
    [entry] = purging._purges(service, owner, action)
    assert entry.object is None


@pytest.mark.parametrize("attachment", [False, True])
def test_restore_stops_at_the_retention_deadline_before_expiry_runs(actions, attachment):
    if attachment:
        service, owner, receipt, draft, web = deleting._ready(actions)
        result = service.approve(
            owner,
            draft,
            ApproveExpense(
                version=service.dossier(owner, draft).version,
                action="record_expense",
                accept_gaps=seen_gaps(service, owner, draft),
            ),
            str(uuid4()),
        )
        assert result.outcome == "applied", result
    else:
        service, owner, _ = actions
        draft = deleting._captured_purchase(service, owner, approve=True)
    client = deleting._client(service, owner)
    deleted = deleting._act(client, draft, "delete")
    assert deleted.status_code == 200, deleted.text
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events"
            " set resolution=jsonb_set(resolution,'{deleted,at}',to_jsonb(%s::timestamptz))"
            " where id=%s",
            (datetime.now(timezone.utc) - PURGE_AFTER, draft),
        )

    _refused(
        deleting._act(client, draft, "restore"), 422, "business_document_restore_expired"
    )
    dossier = service.dossier(owner, draft)
    assert dossier.review_state == "dismissed" and not dossier.restore_available
    if attachment:
        shown = deleting.receipt_detail(web, web.service.receipt(web.scope, receipt))
    else:
        [shown] = service.captures(owner, view="eliminados")
    assert shown["deleted"] is not None and shown["restore_available"] is False

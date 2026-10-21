from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    ProposeActivity,
)
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.repository import NewAccount
from argus.domain.recording.schemas import account_response

from tests import test_business_actions_postgres as shared

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


def _income(service, context, *, omitted=(), unknown=(), funding=None, share=None):
    account = service.imports.money.repository.create(
        user_id=context.owner_id,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        account=NewAccount(
            type="cash", currency="DOP", nickname="Income till", ownership_share_bps=10000
        ),
        opening=shared.shared._opening(1000000),
        scope=context.scope,
    ).stored.account.id
    evidence = shared.source(service, context, "Me pagaron 5000 por la reparación")
    values = {
        "kind": "income",
        "amount": "5000",
        "currency": "DOP",
        "occurred_on": "2026-10-09",
        "funding": funding or {"kind": "business_account", "account_id": account},
        "business_share": share or {"kind": "all"},
    }
    patch = {
        name: {"state": "known", "value": value}
        for name, value in values.items()
        if name not in omitted
    }
    patch.update({name: {"state": "unknown"} for name in unknown})
    facts = BusinessFactPatch.model_validate(patch)
    key, lease = shared.prepare(
        service, context, [ProposeActivity(facts=facts, source_ids=(evidence,))]
    )
    outcome = service.execute(context, key, 0, lease=lease)
    assert outcome.outcome == "applied", outcome
    return outcome.draft_id, account, evidence


def _account(service, context, account):
    stored = service.imports.money.accounts.get(
        user_id=context.owner_id, account_id=str(account), scope=context.scope
    )
    return account_response(stored)


@pytest.mark.owner_acts
def test_member_approves_income_once_with_real_account_credit(actions):
    service, context, grant = actions
    draft, account, evidence = _income(service, context)
    personal = service.imports.money.repository.create(
        user_id=context.owner_id,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        account=NewAccount(
            type="cash",
            currency="DOP",
            nickname="Personal cash",
            ownership_share_bps=10000,
        ),
        opening=shared.shared._opening(200000),
        scope=PERSONAL,
    ).stored.account.id
    personal_before = account_response(
        service.imports.money.accounts.get(
            user_id=context.owner_id, account_id=personal, scope=PERSONAL
        )
    )
    before = _account(service, context, account)
    assert before.balance.state == "known"
    request = ApproveIncome(version=1, action="record_income")
    assert service.dossier(context, draft).approval_available
    result = service.approve_income(context, draft, request, "income-approval")
    assert result.outcome == "applied"
    assert result.version == 1 and result.activity_id is not None
    assert service.approve_income(context, draft, request, "income-approval") == result
    after = _account(service, context, account)
    assert after.balance.amount_minor - before.balance.amount_minor == 500000
    assert after.version > before.version
    assert (
        account_response(
            service.imports.money.accounts.get(
                user_id=context.owner_id, account_id=personal, scope=PERSONAL
            )
        )
        == personal_before
    )
    view = service.dossier(context, draft)
    assert view.version == 3 and view.approval_result.activity_id == result.activity_id
    assert view.approval_result.reviewed_version == 1
    assert view.approval_result.actor.actor_id == context.actor.actor_id
    assert view.approval_result.actor.grant_id == grant
    assert view.history[0].source_ids == (evidence,)
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.financial_records"
                " where user_id=%s and record_kind='income' and account_id=%s",
                (context.owner_id, str(account)),
            ).fetchone()[0]
            == 1
        )
        receipt = db.execute(
            "select actor,command,outcome,turn_key,action_index"
            " from public.business_action_receipts"
            " where space_id=%s and actor_id=%s and idempotency_key=%s",
            (context.actor.space_id, context.actor.actor_id, "income-approval"),
        ).fetchone()
        assert receipt[0]["grant_id"] == str(grant)
        assert receipt[1] == {
            "action": "approve_income",
            "draft_id": str(draft),
            "request": {"version": 1, "action": "record_income"},
        }
        assert receipt[2]["outcome"] == "applied"
        assert receipt[3:] == (None, None)


@pytest.mark.owner_acts
def test_income_requires_current_kind_and_complete_sourced_facts(actions):
    service, context, _ = actions
    request = ApproveIncome(version=1, action="record_income")
    for omitted, unknown in (
        (("funding",), ()),
        (("occurred_on",), ()),
        (("amount",), ()),
        ((), ("currency",)),
    ):
        draft, account, _ = _income(service, context, omitted=omitted, unknown=unknown)
        before = _account(service, context, account)
        result = service.approve_income(context, draft, request, str(uuid4()))
        assert result.outcome == "invalid_input" and result.code == "fact_required"
        assert _account(service, context, account) == before
        assert service.dossier(context, draft).version == 1
    for funding, share, expected in (
        ({"kind": "owner_funds"}, None, "business_funding_unsupported"),
        (None, {"kind": "partial", "amount": "100"}, "business_allocation_unsupported"),
    ):
        draft, account, _ = _income(service, context, funding=funding, share=share)
        before = _account(service, context, account)
        result = service.approve_income(context, draft, request, str(uuid4()))
        assert result.outcome == "invalid_input" and result.code == expected
        assert _account(service, context, account) == before
    draft, _, _ = _income(service, context)
    assert (
        service.approve(
            context,
            draft,
            ApproveExpense(version=1, action="record_expense"),
            "wrong-kind",
        ).code
        == "activity_kind_unsupported"
    )
    expense = shared.ready(service, context)
    assert service.approve_income(context, expense, request, "wrong-income").code == (
        "activity_kind_unsupported"
    )


@pytest.mark.owner_acts
def test_income_dossier_blocks_nonliquid_business_account_without_money_write(actions):
    service, context, _ = actions
    for account_type in ("credit_card", "other_debt"):
        account = service.imports.money.repository.create(
            user_id=context.owner_id,
            idempotency_key=str(uuid4()),
            identity_hash=uuid4().hex,
            account=NewAccount(
                type=account_type,
                currency="DOP",
                nickname=f"Income {account_type}",
                ownership_share_bps=10000,
            ),
            opening=None,
            scope=context.scope,
        ).stored.account.id
        draft, _, _ = _income(
            service,
            context,
            funding={"kind": "business_account", "account_id": account},
        )
        before = _account(service, context, account)
        view = service.dossier(context, draft)
        assert not view.approval_available
        assert [(item.code, item.field) for item in view.blockers] == [
            ("account_ineligible", "funding")
        ]
        result = service.approve_income(
            context,
            draft,
            ApproveIncome(version=view.version, action="record_income"),
            f"blocked-{account_type}",
        )
        assert result.outcome == "invalid_input" and result.code == "account_ineligible"
        assert _account(service, context, account) == before
        with service.authority.pool.connection() as db:
            assert (
                db.execute(
                    "select count(*) from public.financial_records"
                    " where user_id=%s and record_kind='income' and account_id=%s",
                    (context.owner_id, str(account)),
                ).fetchone()[0]
                == 0
            )


@pytest.mark.owner_acts
def test_income_stale_version_and_changed_command_never_post(actions):
    service, context, _ = actions
    draft, account, _ = _income(service, context)
    before = _account(service, context, account)
    stale = service.approve_income(
        context, draft, ApproveIncome(version=2, action="record_income"), "stale"
    )
    assert stale.outcome == "stale_version"
    assert _account(service, context, account) == before
    request = ApproveIncome(version=1, action="record_income")
    first = service.approve_income(context, draft, request, "approved")
    assert first.outcome == "applied"
    changed = service.approve_income(
        context, draft, ApproveIncome(version=2, action="record_income"), "approved"
    )
    assert changed.outcome == "idempotency_conflict"
    assert _account(service, context, account).balance.amount_minor == (
        before.balance.amount_minor + 500000
    )


def test_agent_cannot_approve_income_or_create_human_receipt(actions):
    service, context, _ = actions
    draft, account, _ = _income(service, context)
    agent = service.resolve_actor(
        context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    before = _account(service, context, account)
    result = service.approve_income(
        agent, draft, ApproveIncome(version=1, action="record_income"), "agent-income"
    )
    assert result.outcome == "permission_denied"
    assert _account(service, context, account) == before
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts"
                " where space_id=%s and idempotency_key=%s",
                (context.actor.space_id, "agent-income"),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.owner_acts
def test_income_lost_acknowledgement_reuses_one_money_activity(actions, monkeypatch):
    service, context, _ = actions
    draft, account, _ = _income(service, context)
    request = ApproveIncome(version=1, action="record_income")
    original = service.imports._write

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError("Synthetic lost acknowledgement after Money commit")

    monkeypatch.setattr(service.imports, "_write", interrupted)
    assert service.approve_income(context, draft, request, "lost-income").outcome == (
        "outcome_unknown"
    )
    monkeypatch.setattr(service.imports, "_write", original)
    recovered = service.approve_income(context, draft, request, "lost-income")
    assert recovered.outcome == "applied"
    assert service.approve_income(context, draft, request, "lost-income") == recovered
    assert _account(service, context, account).balance.amount_minor == 1500000
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.financial_records"
                " where user_id=%s and record_kind='income' and account_id=%s",
                (context.owner_id, str(account)),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.owner_acts
def test_concurrent_same_income_approval_records_one_activity(actions):
    service, context, _ = actions
    draft, account, _ = _income(service, context)
    request = ApproveIncome(version=1, action="record_income")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: service.approve_income(context, draft, request, "same-income"),
                range(2),
            )
        )
    assert all(result.outcome == "applied" for result in results)
    assert results[0].activity_id == results[1].activity_id
    assert _account(service, context, account).balance.amount_minor == 1500000

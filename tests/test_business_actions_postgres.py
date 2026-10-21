from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ProposeActivity, ReviewDraft, TurnPlan
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import MessageSource
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.contracts.recovery import SenderLease
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
from argus.domain.recording.service import FinancialAccountService
from psycopg import Connection
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import space

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def actions(users, request):
    """An accountant (``other``) acting in the owner's Business through the
    grant the owner issued, as before. Approval is the owner's alone, so a test
    marked ``owner_acts`` runs the same flow as the owner through the owner's
    own grant."""

    owner_acts = request.node.get_closest_marker("owner_acts") is not None
    acting = users["owner"] if owner_acts else users["other"]
    # The database refuses approve on anyone's grant but the owner's.
    capabilities = ["read", "prepare", "approve"] if owner_acts else ["read", "prepare"]
    with Connection.connect(shared.DSN) as db:
        space_id = space(db, users["owner"])
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,%s) returning id",
            (space_id, acting, users["owner"], capabilities),
        ).fetchone()[0]
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as pool:
        money = MoneyService(
            FinancialAccountService(PostgresFinancialAccountRepository(pool))
        )
        imports = ReconciliationService(
            PostgresImportStore(pool), money, lambda: datetime.now(timezone.utc)
        )
        service = BusinessActions(pool, imports)
        context = service.resolve_actor(
            TrustedActor(actor_id=acting, actor_kind="member", space_id=space_id)
        )
        yield service, context, grant


def source(service, context, text="Paid 850 pesos"):
    evidence = MessageSource(
        id=uuid4(),
        kind="message",
        channel="whatsapp",
        received_at=datetime.now(timezone.utc),
        text=text,
    )
    return service.record_source(context, str(uuid4()), evidence)


def prepare(service, context, actions):
    key, sender = str(uuid4()), uuid4().hex + uuid4().hex
    lease = SenderLease(
        space_id=context.actor.space_id,
        sender_hash=sender,
        holder=uuid4(),
        fence=1,
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=3),
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_sender_leases(space_id,sender_hash,holder,fence,lease_until) values (%s,%s,%s,1,%s)",
            (lease.space_id, sender, lease.holder, lease.lease_until),
        )
        db.execute(
            "insert into public.business_turns(turn_key,space_id,sender_hash,actor_id,lease_fence) values(%s,%s,%s,%s,1)",
            (key, lease.space_id, sender, context.actor.actor_id),
        )
    plan = TurnPlan(actions=actions)
    assert service.persist_plan(context, key, plan, lease=lease) == plan
    return key, lease


def create(service, context):
    evidence = source(service, context)
    plan, lease = prepare(
        service,
        context,
        [
            ProposeActivity(
                facts=BusinessFactPatch(amount={"state": "known", "value": "850"}),
                source_ids=(evidence,),
            )
        ],
    )
    result = service.execute(context, plan, 0, lease=lease)
    assert result.outcome == "applied", result
    return result.draft_id, result.version


def test_create_history_web_provenance_and_exact_replay(actions):
    service, context, _ = actions
    draft, version = create(service, context)
    request = ReviewDraft(
        version=version, facts=BusinessFactPatch(amount={"state": "unknown"})
    )
    first = service.review(context, draft, request, "same-key")
    assert first.outcome == "applied"
    assert service.review(context, draft, request, "same-key") == first
    changed = request.model_copy(update={"version": version + 1})
    assert (
        service.review(context, draft, changed, "same-key").outcome
        == "idempotency_conflict"
    )
    view = service.dossier(context, draft)
    assert view.facts.amount.value is None
    assert len(view.history) == 2
    assert view.sources[-1].kind == "web_action"
    assert view.history[-1].actor.actor_id == context.actor.actor_id
    assert view.facts.amount.origin == "member_set"


def test_same_plan_references_follow_own_revisions(actions):
    service, context, _ = actions
    evidence = source(service, context)
    create_action = ProposeActivity(
        facts=BusinessFactPatch(amount={"state": "known", "value": "850"}),
        source_ids=(evidence,),
    )
    update = ProposeActivity(
        draft={"from_action": 0},
        facts=BusinessFactPatch(counterparty={"state": "known", "value": "Shop"}),
        source_ids=(evidence,),
    )
    final = ProposeActivity(
        draft={"from_action": 0},
        facts=BusinessFactPatch(amount={"state": "unknown"}),
        source_ids=(evidence,),
    )
    key, lease = prepare(service, context, [create_action, update, final])
    results = [service.execute(context, key, index, lease=lease) for index in range(3)]
    assert [r.version for r in results] == [1, 2, 3]
    assert service.execute(context, key, 2, lease=lease) == results[2]
    assert len(service.dossier(context, results[0].draft_id).history) == 3


def test_revocation_and_cross_client_non_disclosure(actions, users):
    service, context, grant = actions
    draft, _ = create(service, context)
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.context_for_draft(UUID(users["owner"]), draft)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.dossier(context, draft)


def test_concurrent_reviews_commit_one_revision(actions):
    service, context, _ = actions
    draft, version = create(service, context)
    request = ReviewDraft(
        version=version, facts=BusinessFactPatch(amount={"state": "unknown"})
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda key: service.review(context, draft, request, key),
                ["first", "second"],
            )
        )
    assert sorted(r.outcome for r in results) == ["applied", "stale_version"]
    assert len(service.dossier(context, draft).history) == 2


def test_reference_does_not_silently_take_later_human_version(actions):
    service, context, _ = actions
    evidence = source(service, context)
    first = ProposeActivity(
        facts=BusinessFactPatch(amount={"state": "known", "value": "850"}),
        source_ids=(evidence,),
    )
    next_action = ProposeActivity(
        draft={"from_action": 0},
        facts=BusinessFactPatch(amount={"state": "unknown"}),
        source_ids=(evidence,),
    )
    key, lease = prepare(service, context, [first, next_action])
    result = service.execute(context, key, 0, lease=lease)
    human = service.review(
        context,
        result.draft_id,
        ReviewDraft(
            version=1, facts=BusinessFactPatch(amount={"state": "known", "value": "900"})
        ),
        "human",
    )
    assert human.version == 2
    assert service.execute(context, key, 1, lease=lease).outcome == "stale_version"
    assert service.dossier(context, result.draft_id).facts.amount.value == "900"


def test_lease_loss_and_source_collision_do_not_write(actions):
    service, context, _ = actions
    evidence = MessageSource(
        id=uuid4(),
        kind="message",
        channel="whatsapp",
        text="Paid",
        received_at=datetime.now(timezone.utc),
    )
    assert service.record_source(context, "source", evidence) == evidence.id
    with pytest.raises(ActionError, match="source_identity_conflict"):
        service.record_source(
            context, "source", evidence.model_copy(update={"text": "Changed"})
        )
    action = ProposeActivity(
        facts=BusinessFactPatch(amount={"state": "unknown"}), source_ids=(evidence.id,)
    )
    key, lease = prepare(service, context, [action])
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_sender_leases set fence=fence+1 where space_id=%s and sender_hash=%s",
            (lease.space_id, lease.sender_hash),
        )
    result = service.execute(context, key, 0, lease=lease)
    assert result.code == "business_sender_lease_lost"
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where turn_key=%s",
                (key,),
            ).fetchone()[0]
            == 0
        )


def ready(service, context, *, owner_funds=False):
    from argus.domain.recording.repository import NewAccount

    account = service.imports.money.repository.create(
        user_id=context.owner_id,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        account=NewAccount(
            type="cash", currency="DOP", nickname="Till", ownership_share_bps=10000
        ),
        opening=shared._opening(1000000),
        scope=context.scope,
    ).stored.account.id
    evidence = source(service, context)
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "expense",
                "amount": "850",
                "currency": "DOP",
                "occurred_on": "2026-10-01",
                "funding": {"kind": "owner_funds"}
                if owner_funds
                else {"kind": "business_account", "account_id": account},
                "business_share": {"kind": "all"},
            }.items()
        }
    )
    key, lease = prepare(
        service, context, [ProposeActivity(facts=facts, source_ids=(evidence,))]
    )
    result = service.execute(context, key, 0, lease=lease)
    assert result.outcome == "applied"
    return result.draft_id


@pytest.mark.owner_acts
def test_human_approval_recovers_committed_money_once(actions, monkeypatch):
    from argus.domain.business.contracts.actions import ApproveExpense

    service, context, _ = actions
    draft = ready(service, context)
    request = ApproveExpense(version=1, action="record_expense")
    original = service.imports._write

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError("Synthetic lost acknowledgement after commit")

    monkeypatch.setattr(service.imports, "_write", interrupted)
    assert (
        service.approve(context, draft, request, "approve").outcome == "outcome_unknown"
    )
    monkeypatch.setattr(service.imports, "_write", original)
    result = service.approve(context, draft, request, "approve")
    assert result.outcome == "applied", result
    assert service.approve(context, draft, request, "approve") == result
    view = service.dossier(context, draft)
    assert view.approval_result.activity_id == result.activity_id
    assert view.approval_result.actor.actor_id == context.actor.actor_id
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.financial_records where user_id=%s and record_kind='expense'",
                (context.owner_id,),
            ).fetchone()[0]
            == 1
        )


def test_agent_cannot_approve_and_generic_review_cannot_bypass_history(actions):
    from argus.domain.business.contracts.actions import ApproveExpense
    from argus.domain.ingestion.reconcile.model import ReconcileError

    service, context, _ = actions
    draft = ready(service, context)
    agent = service.resolve_actor(
        context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    assert (
        service.approve(
            agent, draft, ApproveExpense(version=1, action="record_expense"), "agent"
        ).outcome
        == "permission_denied"
    )
    with pytest.raises(ReconcileError, match="business_action_required"):
        service.imports.resolve(
            user_id=context.owner_id,
            event_id=str(draft),
            version=1,
            changes={"amount": "1"},
            scope=context.scope,
        )
    assert service.dossier(context, draft).version == 1


def test_owner_uncertainty_escalates_question_without_inventing_answer(actions):
    from argus.domain.business.contracts.actions import Ask

    service, context, _ = actions
    evidence = source(service, context)
    create_action = ProposeActivity(
        facts=BusinessFactPatch(amount={"state": "unknown"}), source_ids=(evidence,)
    )
    question = Ask(
        draft={"from_action": 0},
        field="amount",
        asked_of="owner",
        prompt="How much was it?",
    )
    key, lease = prepare(service, context, [create_action, question])
    created = service.execute(context, key, 0, lease=lease)
    asked = service.execute(context, key, 1, lease=lease)
    assert asked.question_id
    service.review(
        context,
        created.draft_id,
        ReviewDraft(
            version=1, facts=BusinessFactPatch(amount={"state": "owner_does_not_know"})
        ),
        "uncertain",
    )
    view = service.dossier(context, created.draft_id)
    assert view.facts.amount.state == "owner_does_not_know"
    assert view.questions[0].asked_of == "accountant"
    assert view.questions[0].state == "owner_does_not_know"


@pytest.mark.owner_acts
def test_approval_rechecks_grant_after_preview_before_claim(actions, monkeypatch):
    from argus.domain.business.contracts.actions import ApproveExpense

    service, context, grant = actions
    draft = ready(service, context)
    preview = service.imports.money.preview

    def revoke_after_preview(**kwargs):
        result = preview(**kwargs)
        with service.authority.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        return result

    monkeypatch.setattr(service.imports.money, "preview", revoke_after_preview)
    result = service.approve(
        context, draft, ApproveExpense(version=1, action="record_expense"), "approve"
    )
    assert result.outcome == "not_found"
    with service.authority.pool.connection() as db:
        state, version = db.execute(
            "select state,version from public.financial_import_events where id=%s",
            (draft,),
        ).fetchone()
        assert (state, version) == ("open", 1)
        assert (
            db.execute(
                "select count(*) from public.financial_records where user_id=%s and record_kind='expense'",
                (context.owner_id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.owner_acts
def test_concurrent_approval_and_recorded_correction(actions):
    from argus.domain.business.contracts.actions import ApproveExpense

    service, context, _ = actions
    draft = ready(service, context)
    request = ApproveExpense(version=1, action="record_expense")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: service.approve(context, draft, request, "same"), range(2)
            )
        )
    assert all(r.outcome == "applied" for r in results), results
    assert results[0].activity_id == results[1].activity_id
    view = service.dossier(context, draft)
    correction = service.review(
        context,
        draft,
        ReviewDraft(
            version=view.version,
            facts=BusinessFactPatch(amount={"state": "known", "value": "99"}),
        ),
        "correct",
    )
    assert correction.code == "recorded_correction_unsupported"
    assert service.dossier(context, draft).history == view.history


def test_cross_client_source_and_account_are_not_found(actions, users):
    from tests.test_business_spaces_migration_postgres import account

    service, context, _ = actions
    with service.authority.pool.connection() as db:
        foreign_space = space(db, users["other"])
        foreign_account = account(db, users["other"], foreign_space)
        foreign_source = db.execute(
            "insert into public.business_sources(space_id,kind,channel,source_key,text_content,received_at) values(%s,'message','web',%s,'Other',now()) returning id",
            (foreign_space, str(uuid4())),
        ).fetchone()[0]
    evidence = source(service, context)
    bad_source = ProposeActivity(
        facts=BusinessFactPatch(amount={"state": "unknown"}), source_ids=(foreign_source,)
    )
    bad_account = ProposeActivity(
        facts=BusinessFactPatch(
            funding={
                "state": "known",
                "value": {"kind": "business_account", "account_id": foreign_account},
            }
        ),
        source_ids=(evidence,),
    )
    key, lease = prepare(service, context, [bad_source, bad_account])
    for index in range(2):
        assert service.execute(context, key, index, lease=lease).outcome == "not_found"
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.financial_import_events where owner_space_id=%s",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 0
        )


def test_replaced_grant_cannot_resume_saved_plan(actions):
    service, context, grant = actions
    evidence = source(service, context)
    key, lease = prepare(
        service,
        context,
        [
            ProposeActivity(
                facts=BusinessFactPatch(amount={"state": "unknown"}),
                source_ids=(evidence,),
            )
        ],
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,ARRAY['read','prepare'])",
            (context.actor.space_id, context.actor.actor_id, context.owner_id),
        )
    replacement = service.resolve_actor(context.actor)
    assert (
        service.execute(replacement, key, 0, lease=lease).code
        == "business_plan_authority_changed"
    )


def test_dossier_api_resolves_actual_client_and_rechecks_live_grant(actions, users):
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_drafts import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, context, grant = actions
    draft, _ = create(service, context)
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-actions"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id
    )
    with TestClient(app) as client:
        response = client.get(f"/business/drafts/{draft}/dossier")
        assert response.status_code == 200
        assert response.json()["space_id"] == str(context.actor.space_id)
        assert response.json()["version"] == 1
        reviewed = client.patch(
            f"/business/drafts/{draft}/review",
            headers={"Idempotency-Key": "browser"},
            json={
                "version": 1,
                "facts": {"amount": {"state": "unknown"}},
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["facts"]["amount"]["value"] is None
        with service.authority.pool.connection() as db:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
        assert client.get(f"/business/drafts/{draft}/dossier").status_code == 404


def test_receipt_bridge_uses_client_scope_and_live_prepare_transaction(actions):
    from types import SimpleNamespace

    from argus.api.business_drafts import scoped_legacy
    from fastapi import FastAPI
    from starlette.requests import Request

    from tests.test_business_spaces_migration_postgres import connection

    service, context, grant = actions
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
    app = FastAPI()
    app.state.financial_accounts_pool = service.authority.pool
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "PATCH",
            "path": f"/business/receipts/{receipt}/review",
            "path_params": {"receipt_id": receipt},
            "headers": [],
            "state": {"request_id": "synthetic"},
        }
    )
    hub = SimpleNamespace(sink=service.imports)
    documents = SimpleNamespace(hub=hub)
    bridged = scoped_legacy(request, documents, hub, str(context.actor.actor_id), None)
    assert bridged.scope.person_id == context.owner_id
    assert bridged.scope.owner == context.scope
    assert bridged.record_context.space_id == context.actor.space_id
    assert documents.hub is hub
    assert bridged.service.documents.hub.sink is bridged.service.imports
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    with pytest.raises(ActionError, match="business_record_not_found"):
        with bridged.service.imports.store.transaction(
            context.owner_id, scope=context.scope
        ):
            pytest.fail("revoked grant entered mutation")


def test_related_drafts_use_canonical_matching(actions):
    service, context, _ = actions
    first, _ = create(service, context)
    second, _ = create(service, context)
    request = ReviewDraft(
        version=1,
        facts=BusinessFactPatch(occurred_on={"state": "known", "value": "2026-10-01"}),
    )
    service.review(context, first, request, "first-date")
    service.review(context, second, request, "second-date")
    assert service.find_related(context, first)["draft_ids"] == [str(second)]


def test_saved_plan_read_does_not_reinterpret_unknown_model_boundary(actions):
    from argus.domain.business.contracts.actions import ReadContext

    service, context, _ = actions
    key, lease = prepare(service, context, [ReadContext()])
    assert service.plan_for_turn(context, key, lease=lease) == TurnPlan(
        actions=(ReadContext(),)
    )
    with service.authority.pool.connection() as db:
        unknown_key = str(uuid4())
        db.execute(
            "insert into public.business_turns(turn_key,space_id,sender_hash,actor_id,lease_fence,model_state) values(%s,%s,%s,%s,1,'unknown')",
            (unknown_key, lease.space_id, lease.sender_hash, context.actor.actor_id),
        )
    with pytest.raises(ActionError, match="business_model_outcome_unknown"):
        service.plan_for_turn(context, unknown_key, lease=lease)


@pytest.mark.parametrize(
    "legacy,typed_count,ambiguous",
    [(None, 1, False), ("same", 1, False), (None, 2, True), ("different", 1, True)],
)
def test_receipt_candidate_bridge_preserves_ambiguity(
    actions, legacy, typed_count, ambiguous
):
    from argus.domain.business.actions.receipts import draft_for_receipt
    from argus.domain.business.contracts.dossier import AttachmentSource
    from argus.domain.business.transactions import transaction

    from tests.test_business_spaces_migration_postgres import connection

    service, context, _ = actions
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
    evidence = AttachmentSource(
        id=uuid4(),
        channel="web",
        received_at=datetime.now(timezone.utc),
        connection_id=receipt,
        filename="synthetic.png",
        media_type="image/png",
    )
    source_id = service.record_source(context, "attachment", evidence)
    drafts = []
    for _ in range(typed_count):
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
        drafts.append(service.execute(context, key, 0, lease=lease).draft_id)
    from tests.test_business_spaces_migration_postgres import event, observation

    legacy_id = None
    if legacy is not None:
        with service.authority.pool.connection() as db:
            legacy_id = (
                drafts[0]
                if legacy == "same"
                else UUID(event(db, context.owner_id, str(context.actor.space_id)))
            )
            observation(db, context.owner_id, str(legacy_id), receipt)
    with transaction(service.authority, context) as tx:
        selected, actual_ambiguity = draft_for_receipt(tx, UUID(receipt), legacy_id)
    assert actual_ambiguity is ambiguous
    assert selected == (None if ambiguous else drafts[0])


def test_legacy_projection_is_derived_without_a_second_current_store(actions):
    service, context, _ = actions
    draft, _ = create(service, context)
    request = ReviewDraft(
        version=1,
        facts=BusinessFactPatch(
            counterparty={"state": "known", "value": "Supplier"},
            category_id={"state": "known", "value": "supplies"},
        ),
    )
    service.review(context, draft, request, "details")
    detail = service.imports.detail(
        user_id=context.owner_id, event_id=str(draft), scope=context.scope
    )
    assert detail["resolution"]["note"] == "Supplier"
    assert detail["resolution"]["category_id"] == "supplies"
    with service.authority.pool.connection() as db:
        stored = db.execute(
            "select resolution from public.financial_import_events where id=%s", (draft,)
        ).fetchone()[0]
    assert set(stored) == {"business"}


def test_changed_issuer_cannot_replace_plan_authority(actions):
    from argus.domain.business.contracts.actions import ReadContext

    service, context, grant = actions
    key, lease = prepare(service, context, [ReadContext()])
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set issuer_id=grantee_id where id=%s",
            (grant,),
        )
    assert (
        service.execute(context, key, 0, lease=lease).code
        == "business_plan_authority_changed"
    )
    with pytest.raises(ActionError, match="business_plan_authority_changed"):
        service.plan_for_turn(context, key, lease=lease)


def test_closed_window_marks_only_same_turn_owner_questions(actions):
    from argus.domain.business.contracts.actions import Ask

    service, context, _ = actions
    evidence = source(service, context)
    first = ProposeActivity(
        facts=BusinessFactPatch(amount={"state": "unknown"}), source_ids=(evidence,)
    )
    key, lease = prepare(
        service,
        context,
        [
            first,
            Ask(
                draft={"from_action": 0},
                field="amount",
                asked_of="owner",
                prompt="Amount?",
            ),
            Ask(
                draft={"from_action": 0},
                field="currency",
                asked_of="accountant",
                prompt="Currency?",
            ),
        ],
    )
    results = [service.execute(context, key, index, lease=lease) for index in range(3)]
    service.mark_turn_waiting_for_window(context, key, lease=lease)
    service.mark_turn_waiting_for_window(context, key, lease=lease)
    questions = {
        q.field: q for q in service.dossier(context, results[0].draft_id).questions
    }
    assert questions["amount"].state == "waiting_for_window"
    assert questions["currency"].state == "open"


def test_legacy_hand_entry_cannot_create_another_candidate_for_typed_receipt(actions):
    from types import SimpleNamespace

    from argus.api.business import BusinessContext
    from argus.api.business_drafts import require_legacy_receipt_write
    from argus.domain.business.contracts.dossier import AttachmentSource
    from argus.domain.business.scope import BusinessScope
    from argus.domain.business.transactions import GrantImportStore

    from tests.test_business_spaces_migration_postgres import connection

    service, context, _ = actions
    with service.authority.pool.connection() as db:
        receipt = connection(db, context.owner_id, str(context.actor.space_id))
    source_id = service.record_source(
        context,
        "receipt",
        AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=datetime.now(timezone.utc),
            connection_id=receipt,
            filename="source.png",
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
    assert service.execute(context, key, 0, lease=lease).outcome == "applied"
    imports = SimpleNamespace(
        store=GrantImportStore(service.authority, context, "prepare")
    )
    business = BusinessContext(
        BusinessScope(context.owner_id, context.scope), SimpleNamespace(imports=imports)
    )
    with pytest.raises(ActionError, match="business_action_required"):
        require_legacy_receipt_write(business, receipt)


@pytest.mark.owner_acts
def test_owner_funds_approval_recovers_without_bank_movement(actions, monkeypatch):
    from argus.domain.business.contracts.actions import ApproveExpense
    from argus.domain.recording.money_reads import current_activities
    from argus.domain.recording.schemas import account_response

    service, context, _ = actions
    draft = ready(service, context, owner_funds=True)
    money = service.imports.money
    before = [
        account_response(row)
        for row in money.accounts.list_accounts(
            user_id=context.owner_id, scope=context.scope
        )
    ]
    assert service.dossier(context, draft).approval_available
    request = ApproveExpense(version=1, action="record_expense")
    original = money.write

    def interrupted(**kwargs):
        result = original(**kwargs)
        assert result["activity"]["funding"] == "owner_funds"
        assert result["activity"]["legs"] == []
        raise ConnectionError("Synthetic lost acknowledgement after MoneyService commit")

    monkeypatch.setattr(money, "write", interrupted)
    assert (
        service.approve(context, draft, request, "owner-paid").outcome
        == "outcome_unknown"
    )
    unsettled = service.dossier(context, draft)
    assert unsettled.review_state == "accepting"
    assert unsettled.approval_result.status == "outcome_unknown"
    monkeypatch.setattr(money, "write", original)
    result = service.approve(context, draft, request, "owner-paid")
    assert result.outcome == "applied", result
    assert service.approve(context, draft, request, "owner-paid") == result
    accounts = money.accounts.list_accounts(user_id=context.owner_id, scope=context.scope)
    assert [account_response(row) for row in accounts] == before
    activities = current_activities(accounts)
    assert len(activities) == 1
    assert activities[0]["activity_id"] == str(result.activity_id)
    assert activities[0]["funding"] == "owner_funds"
    assert activities[0]["legs"] == []
    assert activities[0]["amount_minor"] == 85000
    view = service.dossier(context, draft)
    assert view.approval_result.reviewed_version == 1
    assert view.approval_result.actor.actor_id == context.actor.actor_id
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select account_id,funding,currency from public.financial_records"
            " where user_id=%s and record_kind='expense'",
            (context.owner_id,),
        ).fetchall() == [(None, "owner_funds", "DOP")]
        assert (
            db.execute(
                "select count(*) from public.financial_activity_receipts where user_id=%s",
                (context.owner_id,),
            ).fetchone()[0]
            == 1
        )


def test_owner_workspace_read_never_grants_draft_authority(actions, monkeypatch):
    from types import SimpleNamespace

    from argus.api.business import require_business_surface
    from argus.api.documents import require_saved_documents
    from argus.api.ingestion import require_ingestion_context
    from argus.api.routers.business import router
    from argus.domain.business.spaces import PostgresSpaceStore
    from argus.domain.owner_scope import PERSONAL
    from argus.domain.recording.repository import NewAccount
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, context, _ = actions
    repository = service.imports.money.repository
    account_ids = []
    for person, scope in (
        (context.owner_id, context.scope),
        (context.owner_id, PERSONAL),
        (str(context.actor.actor_id), PERSONAL),
    ):
        account_ids.append(
            repository.create(
                user_id=person,
                idempotency_key=str(uuid4()),
                identity_hash=uuid4().hex,
                account=NewAccount(
                    type="cash",
                    currency="DOP",
                    nickname="Till",
                    ownership_share_bps=10000,
                ),
                opening=shared._opening(1000),
                scope=scope,
            ).stored.account.id
        )
    spaces = PostgresSpaceStore(service.authority.pool)
    monkeypatch.setattr("argus.api.business.business_spaces", lambda: spaces)
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "false")
    hub = SimpleNamespace(sink=service.imports)
    documents = SimpleNamespace(hub=hub)
    app = FastAPI()
    app.state.financial_accounts_pool = service.authority.pool
    app.include_router(router)
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_saved_documents] = lambda: documents

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "workspace-authority"
        return await call_next(request)

    def acting_as(person):
        app.dependency_overrides[require_ingestion_context] = lambda: SimpleNamespace(
            hub=hub, user_id=person
        )

    with TestClient(app) as client:
        acting_as(context.owner_id)
        response = client.get("/business/workspace")
        assert response.status_code == 200, response.text
        assert set(response.json()) == {
            "country",
            "currency",
            "accounts",
            "currencies",
            "assistant_available",
            "chat_available",
            "receipt_limits",
            "logo_url",
        }
        assert response.json()["chat_available"] is False
        assert [a["id"] for a in response.json()["accounts"]] == [account_ids[0]]
        assert response.headers["cache-control"] == "no-store"
        receipts = client.get("/business/receipts")
        assert receipts.status_code == 404
        assert receipts.json()["detail"]["code"] == "business_record_not_found"
        for person in (str(context.actor.actor_id), str(uuid4())):
            acting_as(person)
            refused = client.get("/business/workspace")
            assert refused.status_code == 404
            assert refused.json()["detail"]["code"] == "business_space_missing"
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.resolve_actor(
            TrustedActor(
                actor_id=context.owner_id,
                actor_kind="member",
                space_id=context.actor.space_id,
            )
        )

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from argus.domain.business.actions import BusinessActions, mutations, plans
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    CaptureCommand,
    CaptureNote,
    OutcomeUnknown,
    ReviewDraft,
)
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.transactions import transaction
from psycopg_pool import ConnectionPool

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import space

users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark


def note(service, context, text="  Pagué algo; falta el detalle.\n", key="note"):
    return service.capture(context, CaptureNote(text=text), key)


def counts(service, context):
    with service.authority.pool.connection() as db:
        return tuple(
            db.execute(
                f"select count(*) from public.{table} where {column}=%s", (value,)
            ).fetchone()[0]
            for table, column, value in (
                ("business_sources", "space_id", context.actor.space_id),
                ("business_draft_revisions", "space_id", context.actor.space_id),
                ("financial_import_events", "owner_space_id", context.actor.space_id),
                ("financial_records", "user_id", context.owner_id),
            )
        )


def test_capture_original_unknown_facts_and_restart_replay(actions):
    service, context, _ = actions
    before_accounts = service.imports.money.accounts.list_accounts(
        user_id=context.owner_id, scope=context.scope
    )
    result = note(service, context)
    assert result.outcome == "applied"
    assert result.version == 1
    view = service.dossier(context, result.draft_id)
    assert view.sources[0].text == "  Pagué algo; falta el detalle.\n"
    assert (view.sources[0].kind, view.sources[0].channel) == ("message", "web")
    assert len(view.history) == 1
    assert view.history[0].before is None
    assert view.history[0].source_ids == (view.sources[0].id,)
    assert view.history[0].actor.actor_id == context.actor.actor_id
    assert view.history[0].actor.grant_id == context.grant_id
    assert view.facts.currency.value == "DOP"
    assert view.facts.currency.origin == "default"
    assert not view.facts.currency.verified
    for field in (
        "kind",
        "amount",
        "occurred_on",
        "counterparty",
        "funding",
        "business_share",
        "receipt_state",
        "category_id",
    ):
        assert getattr(view.facts, field).state == "unknown"
        assert getattr(view.facts, field).value is None
    assert view.facts.fiscal is None
    assert not view.approval_available
    with ConnectionPool(shared.shared.DSN, min_size=0, max_size=2) as pool:
        resumed = BusinessActions(pool, service.imports)
        assert note(resumed, context) == result
        listed = resumed.captures(context)
    assert len(listed) == 1
    assert listed[0]["source_id"] == view.sources[0].id
    assert listed[0]["draft_id"] == result.draft_id
    assert counts(service, context) == (1, 1, 1, 0)
    assert (
        service.imports.money.accounts.list_accounts(
            user_id=context.owner_id, scope=context.scope
        )
        == before_accounts
    )


def test_append_preserves_facts_and_uses_exact_revision_source(actions):
    service, context, _ = actions
    created = note(service, context, "First source")
    service.review(
        context,
        created.draft_id,
        ReviewDraft(
            version=1, facts=BusinessFactPatch(amount={"state": "known", "value": "850"})
        ),
        "review",
    )
    before = service.dossier(context, created.draft_id)
    request = CaptureNote(
        text="  Extra original note\n", draft={"draft_id": created.draft_id, "version": 2}
    )
    result = service.capture(context, request, "append")
    assert result.outcome == "applied" and result.version == 3
    after = service.dossier(context, created.draft_id)
    assert after.facts == before.facts
    assert after.history[-1].before == after.history[-1].after == before.facts
    assert len(after.history[-1].source_ids) == 1
    assert after.sources[-1].text == request.text
    assert service.capture(context, request, "append") == result
    entries = service.captures(context)
    assert len(entries) == 2
    assert {row["source_id"] for row in entries} == {
        after.sources[0].id,
        after.sources[-1].id,
    }
    assert {row["version"] for row in entries} == {3}
    # Each note names the revision it created, the number the history lists.
    assert {(row["source_id"], row["revision"]) for row in entries} == {
        (after.sources[0].id, 1),
        (after.sources[-1].id, 3),
    }
    assert counts(service, context)[-1] == 0


def test_capture_drift_stale_and_concurrent_replay(actions):
    service, context, _ = actions
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _: note(service, context), range(2)))
    assert outcomes[0] == outcomes[1]
    assert counts(service, context) == (1, 1, 1, 0)
    assert note(service, context, "Changed text").outcome == "idempotency_conflict"
    draft = outcomes[0].draft_id
    request = CaptureNote(text="Add", draft={"draft_id": draft, "version": 1})
    assert service.capture(context, request, "append").version == 2
    stale = service.capture(context, request, "stale")
    assert stale.outcome == "stale_version"
    assert service.capture(context, request, "stale") == stale
    assert counts(service, context) == (2, 2, 1, 0)


def test_capture_refuses_agent_read_only_and_revoked_authority(actions):
    service, context, grant = actions
    agent = service.resolve_actor(
        context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    assert note(service, agent).code == "business_human_command_required"
    assert counts(service, context) == (0, 0, 0, 0)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read'] where id=%s",
            (grant,),
        )
    assert note(service, context).code == "business_permission_denied"
    assert service.captures(context) == []
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    assert note(service, context).outcome == "not_found"
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.captures(context)


def test_foreign_candidate_is_not_found_and_leaves_no_source(actions, users):
    service, context, _ = actions
    with service.authority.pool.connection() as db:
        foreign_space = space(db, users["other"])
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,ARRAY['read','prepare'])",
            (foreign_space, users["owner"], users["other"]),
        )
    foreign = service.resolve_actor(
        TrustedActor(actor_id=users["owner"], actor_kind="member", space_id=foreign_space)
    )
    foreign_note = note(service, foreign, "Private foreign text")
    request = CaptureNote(
        text="Attempt", draft={"draft_id": foreign_note.draft_id, "version": 1}
    )
    assert service.capture(context, request, "foreign").outcome == "not_found"
    assert service.captures(context) == []
    assert counts(service, context) == (0, 0, 0, 0)
    assert len(service.captures(foreign)) == 1


@pytest.mark.owner_acts
def test_original_note_search_is_literal_and_survives_record_state(actions):
    service, context, _ = actions
    first = note(service, context, "Compra 100%_ ORIGINAL", "literal")
    note(service, context, "Compra 10000 unrelated", "second")
    found = service.captures(context, query="100%_")
    assert [row["draft_id"] for row in found] == [first.draft_id]
    assert (
        service.captures(context, query="original")[0]["text"] == "Compra 100%_ ORIGINAL"
    )
    assert counts(service, context) == (2, 2, 2, 0)
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "expense",
                "amount": "850",
                "currency": "DOP",
                "occurred_on": "2026-10-01",
                "funding": {"kind": "owner_funds"},
                "business_share": {"kind": "all"},
            }.items()
        }
    )
    reviewed = service.review(
        context, first.draft_id, ReviewDraft(version=1, facts=facts), "review"
    )
    assert reviewed.outcome == "applied"
    approved = service.approve(
        context,
        first.draft_id,
        ApproveExpense(version=2, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied"
    assert service.captures(context, query="ORIGINAL")[0]["review_state"] == "accepted"
    denied = service.capture(
        context,
        CaptureNote(
            text="later",
            draft={
                "draft_id": first.draft_id,
                "version": service.dossier(context, first.draft_id).version,
            },
        ),
        "accepted",
    )
    assert denied.code == "recorded_correction_unsupported"
    assert counts(service, context) == (3, 3, 2, 1)


def test_capture_failure_rolls_back_source_candidate_and_receipt(actions, monkeypatch):
    service, context, _ = actions
    original = mutations.save_revision

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic transaction failure")

    monkeypatch.setattr(mutations, "save_revision", interrupted)
    with pytest.raises(RuntimeError, match="synthetic transaction failure"):
        note(service, context)
    assert counts(service, context) == (0, 0, 0, 0)
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_action_receipts where space_id=%s",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 0
        )
    monkeypatch.setattr(mutations, "save_revision", original)
    assert note(service, context).outcome == "applied"


@pytest.mark.parametrize("settled", [False, True], ids=["unset", "unknown"])
def test_capture_unknown_outcome_is_not_reset(actions, settled):
    service, context, _ = actions
    request = CaptureNote(text="Original pending note")
    command = CaptureCommand(request=request)
    expected = OutcomeUnknown(
        code="synthetic_unknown" if settled else "business_action_unsettled"
    )
    with transaction(service.authority, context, "prepare") as tx:
        plans.start_receipt(tx, "note", command)
        if settled:
            plans.finish_receipt(tx, "note", expected)
        original = plans.receipt(tx, "note", command)
    for _ in range(2):
        assert service.capture(context, request, "note") == expected
        assert counts(service, context) == (0, 0, 0, 0)
        with transaction(service.authority, context) as tx:
            assert plans.receipt(tx, "note", command) == original


def test_capture_api_owner_scope_and_accountant_append(actions, users):
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, require_drafts, stored_drafts
    from argus.api.routers.business_manual import router
    from argus.domain.business.spaces import PostgresSpaceStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service, accountant, _ = actions
    actor = UUID(users["owner"])
    app = FastAPI()
    app.include_router(router)
    spaces = PostgresSpaceStore(service.authority.pool)
    context = DraftContext(service, actor)
    app.dependency_overrides[require_drafts] = lambda: context
    app.dependency_overrides[stored_drafts] = lambda: context
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(actor), spaces
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "manual-pg"
        return await call_next(request)

    with TestClient(app) as client:
        body, headers = {"text": "Owner original"}, {"Idempotency-Key": "web"}
        assert (
            client.post("/business/captures", json=body, headers=headers).status_code
            == 404
        )
        with service.authority.pool.connection() as db:
            db.execute(
                "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values(%s,%s,%s,ARRAY['read','prepare'])",
                (accountant.actor.space_id, actor, users["owner"]),
            )
        response = client.post("/business/captures", json=body, headers=headers)
        assert response.status_code == 200, response.text
        draft = response.json()["draft_id"]
        assert response.json()["facts"]["amount"]["state"] == "unknown"
        actor = accountant.actor.actor_id
        assert (
            client.post(
                "/business/captures", json={"text": "No selected client"}, headers=headers
            ).status_code
            == 404
        )
        appended = client.post(
            "/business/captures",
            json={
                "text": "Accountant original",
                "draft": {"draft_id": draft, "version": 1},
            },
            headers={"Idempotency-Key": "append"},
        )
        assert appended.status_code == 200, appended.text
        assert appended.json()["version"] == 2
        assert len(appended.json()["sources"]) == 2
        assert client.get("/business/captures").status_code == 404
        actor = UUID(users["owner"])
        replay = client.post("/business/captures", json=body, headers=headers)
        assert replay.status_code == 200 and replay.json()["version"] == 2
        assert replay.json()["draft_id"] == draft
        assert len(client.get("/business/captures").json()["items"]) == 2


def test_capture_replay_never_substitutes_a_replacement_grant(actions):
    service, context, grant = actions
    first = note(service, context)
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
    assert replacement.grant_id != context.grant_id
    assert note(service, replacement).outcome == "idempotency_conflict"
    assert service.dossier(replacement, first.draft_id).version == 1
    assert counts(service, context) == (1, 1, 1, 0)

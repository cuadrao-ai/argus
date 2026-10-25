"""A person's same-Business duplicate decision opens only the named pair."""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests import test_business_attachment_preparation_postgres as preparation
from tests import test_business_duplicates_postgres as receipts

actions = receipts.actions
users = receipts.users
pytestmark = receipts.pytestmark


def pair(actions):
    prepared = []
    for content in (b"Synthetic purchase one", b"Synthetic purchase two"):
        receipt = receipts._receipt(actions, content)
        preparation.bind(receipt)
        prepared.append(preparation.finish(receipt).draft_id)
    return prepared


def request_for(service, context, draft_id, other_id):
    from argus.domain.business.contracts.actions import ResolveDuplicate

    return ResolveDuplicate(
        version=service.dossier(context, draft_id).version,
        other_draft_id=other_id,
        other_version=service.dossier(context, other_id).version,
        decision="different_purchase",
    )


@pytest.mark.owner_acts
def test_explicit_decision_clears_duplicate_only_and_is_durable(actions):
    service, context, _ = actions
    first, second = pair(actions)
    before = service.dossier(context, second)
    assert "possible_duplicate" in {b.code for b in before.blockers}
    request = request_for(service, context, second, first)
    key = str(uuid4())
    decided = service.resolve_duplicate(context, second, request, key)
    assert decided.outcome == "applied", decided
    after = service.dossier(context, second)
    assert "possible_duplicate" not in {b.code for b in after.blockers}
    assert after.version == before.version + 1
    assert len(after.history) == len(before.history) + 1
    assert "fact_required" in {b.code for b in after.blockers}
    assert after.approval_available is False
    assert service.resolve_duplicate(context, second, request, key) == decided
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.financial_records where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchone() == (0,)


@pytest.mark.parametrize("field", ["version", "other_version"])
def test_both_captured_versions_are_required(actions, field):
    service, context, _ = actions
    first, second = pair(actions)
    request = request_for(service, context, second, first)
    request = request.model_copy(update={field: getattr(request, field) + 1})
    result = service.resolve_duplicate(context, second, request, str(uuid4()))
    assert result.outcome == "stale_version", result
    assert "possible_duplicate" in {
        b.code for b in service.dossier(context, second).blockers
    }


def test_prepare_member_can_decide_and_conflicting_replay_is_refused(actions):
    service, context, _ = actions
    first, second = pair(actions)
    request = request_for(service, context, second, first)
    key = str(uuid4())
    result = service.resolve_duplicate(context, second, request, key)
    assert result.outcome == "applied", result
    assert service.resolve_duplicate(context, second, request, key) == result
    changed = request.model_copy(update={"other_version": request.other_version + 1})
    assert (
        service.resolve_duplicate(context, second, changed, key).outcome
        == "idempotency_conflict"
    )
    assert service.dossier(context, second).approval_available is False


@pytest.mark.parametrize("change", ["read_only", "revoked", "expired", "closed"])
@pytest.mark.parametrize("replay", [False, True])
def test_current_authority_is_required_even_on_replay(actions, change, replay):
    service, context, grant = actions
    first, second = pair(actions)
    request = request_for(service, context, second, first)
    key = str(uuid4())
    if replay:
        assert (
            service.resolve_duplicate(context, second, request, key).outcome == "applied"
        )
    with service.authority.pool.connection() as db:
        if change == "read_only":
            db.execute(
                "update public.business_client_grants set business_role='viewer' where id=%s",
                (grant,),
            )
        elif change == "closed":
            db.execute(
                "update public.spaces set closed_at=now() where id=%s",
                (context.actor.space_id,),
            )
        else:
            assignment = (
                "revoked_at=now()"
                if change == "revoked"
                else "created_at=now()-interval '2 minutes', expires_at=now()-interval '1 second'"
            )
            db.execute(
                f"update public.business_client_grants set {assignment} where id=%s",
                (grant,),
            )
    result = service.resolve_duplicate(context, second, request, key)
    assert result.outcome in {"permission_denied", "not_found"}, result


def test_nonhuman_actor_cannot_decide(actions):
    from dataclasses import replace

    service, context, _ = actions
    first, second = pair(actions)
    request = request_for(service, context, second, first)
    machine = replace(
        context, actor=context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    result = service.resolve_duplicate(machine, second, request, str(uuid4()))
    assert result.code == "business_human_command_required"


def test_only_selected_pair_is_cleared_and_new_receipt_still_warns(actions):
    service, context, _ = actions
    first, second = pair(actions)
    third_receipt = receipts._receipt(actions, b"Synthetic purchase three")
    preparation.bind(third_receipt)
    third = preparation.finish(third_receipt).draft_id
    view = service.dossier(context, third)
    assert {c.draft_id for c in view.duplicate_candidates} == {first, second}
    result = service.resolve_duplicate(
        context, third, request_for(service, context, third, first), str(uuid4())
    )
    assert result.outcome == "applied", result
    view = service.dossier(context, third)
    assert {c.draft_id for c in view.duplicate_candidates} == {second}
    assert "possible_duplicate" in {b.code for b in view.blockers}
    assert "possible_duplicate" in {
        b.code for b in service.dossier(context, second).blockers
    }


@pytest.mark.owner_acts
@pytest.mark.parametrize("side", ["target", "comparison"])
def test_changed_read_evidence_reopens_guard_and_invalidates_replay(actions, side):
    from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft

    service, context, _ = actions
    first, second = pair(actions)
    ready = service.review(
        context,
        second,
        ReviewDraft(
            version=1,
            facts={
                "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                "business_share": {"state": "known", "value": {"kind": "all"}},
            },
        ),
        str(uuid4()),
    )
    assert ready.outcome == "applied"
    request = request_for(service, context, second, first)
    key = str(uuid4())
    assert service.resolve_duplicate(context, second, request, key).outcome == "applied"
    assert service.dossier(context, second).approval_available is True
    changed = second if side == "target" else first
    from argus.domain.business.contracts.actions import ExistingDraft

    added = receipts._receipt(actions, b"Synthetic new receipt evidence")
    preparation.bind(
        added,
        ExistingDraft(
            draft_id=changed, version=service.dossier(context, changed).version
        ),
    )
    prepared = preparation.finish(added)
    assert prepared.outcome == "applied", prepared
    view = service.dossier(context, second)
    assert "possible_duplicate" in {b.code for b in view.blockers}
    assert {c.draft_id for c in view.duplicate_candidates} == {first}
    refused = service.approve(
        context,
        second,
        ApproveExpense(version=view.version, action="record_expense"),
        str(uuid4()),
    )
    assert refused.code == "possible_duplicate", refused
    assert (
        service.resolve_duplicate(context, second, request, key).code
        == "duplicate_evidence_changed"
    )


def test_ordinary_review_and_retry_keep_decision(actions):
    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.business.duplicates import flag_receipt_duplicates
    from argus.domain.business.transactions import transaction

    service, context, _ = actions
    first, second = pair(actions)
    result = service.resolve_duplicate(
        context, second, request_for(service, context, second, first), str(uuid4())
    )
    reviewed = service.review(
        context,
        second,
        ReviewDraft(
            version=result.version,
            facts={"funding": {"state": "known", "value": {"kind": "owner_funds"}}},
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed
    from argus.domain.business.actions.duplicate_resolution import attachment_signature

    with transaction(service.authority, context) as tx:
        assert (
            flag_receipt_duplicates(
                tx.imports,
                str(second),
                lambda event_id: attachment_signature(tx, event_id),
            )
            == ()
        )
        assert (
            flag_receipt_duplicates(
                tx.imports,
                str(first),
                lambda event_id: attachment_signature(tx, event_id),
            )
            == ()
        )
    assert "possible_duplicate" not in {
        b.code for b in service.dossier(context, second).blockers
    }


def post_resolution(service, context, draft_id, body, key=None):
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_drafts import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "duplicate-resolution"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, str(context.actor.space_id), context.grant_id
    )
    with TestClient(app) as client:
        return client.post(
            f"/business/drafts/{draft_id}/duplicate-resolution",
            json=body,
            headers={"Idempotency-Key": key or str(uuid4())},
        )


def test_api_resolves_current_pair_and_replays(actions):
    service, context, _ = actions
    first, second = pair(actions)
    body = request_for(service, context, second, first).model_dump(mode="json")
    key = str(uuid4())
    result = post_resolution(service, context, second, body, key)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert "possible_duplicate" not in {b["code"] for b in result.json()["blockers"]}
    replay = post_resolution(service, context, second, body, key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["version"] == result.json()["version"]


@pytest.mark.parametrize("foreign", ["same_owner_business", "other_owner", "personal"])
@pytest.mark.parametrize("target", [False, True])
def test_foreign_pair_ids_are_missing_over_api(actions, users, foreign, target):
    from psycopg.types.json import Jsonb

    from tests.test_business_spaces_migration_postgres import space

    service, context, _ = actions
    first, second = pair(actions)
    body = request_for(service, context, second, first).model_dump(mode="json")
    foreign_id = uuid4()
    owner = context.owner_id if foreign != "other_owner" else users["other"]
    with service.authority.pool.connection() as db:
        if foreign == "same_owner_business":
            other_space = db.execute(
                "insert into public.spaces(kind,name,created_by,current_owner_id,closed_at) values('business','Synthetic other Business',%s,%s,now()) returning id",
                (owner, owner),
            ).fetchone()[0]
        elif foreign == "other_owner":
            other_space = space(db, owner)
        else:
            other_space = None
        event = db.execute(
            "select resolution from public.financial_import_events where id=%s", (first,)
        ).fetchone()[0]
        if foreign == "personal":
            event = {}
        db.execute(
            "insert into public.financial_import_events(id,user_id,owner_space_id,state,evidence,resolution,version,created_at,updated_at) values(%s,%s,%s,'open','transaction',%s,1,now(),now())",
            (foreign_id, owner, other_space, Jsonb(event)),
        )
    if target:
        second = foreign_id
    else:
        body["other_draft_id"] = str(foreign_id)
    result = post_resolution(service, context, second, body)
    assert result.status_code == 404, result.text
    assert result.json()["detail"]["code"] == "business_record_not_found"


@pytest.mark.owner_acts
def test_accepted_comparison_and_financial_record_stay_unchanged(actions):
    from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft

    service, context, _ = actions
    first, second = pair(actions)
    ready = service.review(
        context,
        first,
        ReviewDraft(
            version=1,
            facts={
                "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                "business_share": {"state": "known", "value": {"kind": "all"}},
            },
        ),
        str(uuid4()),
    )
    approved = service.approve(
        context,
        first,
        ApproveExpense(version=ready.version, action="record_expense"),
        str(uuid4()),
    )
    assert approved.outcome == "applied", approved
    before = service.dossier(context, first)
    with service.authority.pool.connection() as db:
        money_before = db.execute(
            "select to_jsonb(r) from public.financial_records r where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchall()
    decided = service.resolve_duplicate(
        context, second, request_for(service, context, second, first), str(uuid4())
    )
    assert decided.outcome == "applied", decided
    assert service.dossier(context, first) == before
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select to_jsonb(r) from public.financial_records r where owner_space_id=%s",
                (context.actor.space_id,),
            ).fetchall()
            == money_before
        )
    assert len(money_before) == 1


@pytest.mark.parametrize("wrong", ["self", "unrelated", "bank_warning", "source_warning"])
def test_only_an_existing_receipt_fact_pair_can_be_decided(actions, wrong):
    service, context, _ = actions
    first, second = pair(actions)
    request = request_for(service, context, second, first)
    if wrong == "self":
        request = request.model_copy(update={"other_draft_id": second})
    elif wrong == "unrelated":
        added = receipts._receipt(
            actions, b"Different merchant receipt", merchant="Synthetic other merchant"
        )
        preparation.bind(added)
        third = preparation.finish(added).draft_id
        request = request.model_copy(update={"other_draft_id": third})
    else:
        attention = "ambiguous_match" if wrong == "bank_warning" else "source_changed"
        with service.authority.pool.connection() as db:
            db.execute(
                "update public.financial_import_events set attention=%s where id=%s",
                (attention, second),
            )
    result = service.resolve_duplicate(context, second, request, str(uuid4()))
    assert result.code == "duplicate_pair_not_available", result
    assert service.dossier(context, second).approval_available is False


@pytest.mark.parametrize(
    "command", ["review_draft", "capture_note", "resolve_duplicate", "unknown_command"]
)
def test_migration_preserves_known_commands_and_refuses_unknown(actions, command):
    from argus.domain.business.transactions import transaction
    from psycopg.errors import CheckViolation
    from psycopg.types.json import Jsonb

    service, context, _ = actions
    with transaction(service.authority, context) as tx:
        params = (
            context.actor.space_id,
            context.actor.actor_id,
            Jsonb(tx.authorization.provenance.model_dump(mode="json")),
            str(uuid4()),
            "a" * 64,
            Jsonb({"action": command}),
        )
        sql = "insert into public.business_action_receipts(space_id,actor_id,actor,idempotency_key,input_hash,command) values(%s,%s,%s,%s,%s,%s)"
        if command == "unknown_command":
            with pytest.raises(CheckViolation) as error, tx.connection.transaction():
                tx.connection.execute(sql, params)
            assert (
                error.value.diag.constraint_name
                == "business_action_receipts_unplanned_command"
            )
        else:
            tx.connection.execute(sql, params)


def test_model_facing_view_does_not_expose_unmeasured_duplicate_controls(actions):
    service, context, _ = actions
    _, second = pair(actions)
    view = service.dossier(context, second)
    assert len(view.duplicate_candidates) == 1
    assert "duplicate_candidates" not in view.model_facing()


@pytest.mark.owner_acts
def test_owner_reviews_resolved_receipt_then_approves_once(actions):
    from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft

    service, context, _ = actions
    first, second = pair(actions)
    resolved = service.resolve_duplicate(
        context, second, request_for(service, context, second, first), str(uuid4())
    )
    reviewed = service.review(
        context,
        second,
        ReviewDraft(
            version=resolved.version,
            facts={
                "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                "business_share": {"state": "known", "value": {"kind": "all"}},
            },
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed
    assert service.dossier(context, second).approval_available is True
    command = ApproveExpense(version=reviewed.version, action="record_expense")
    key = str(uuid4())
    approved = service.approve(context, second, command, key)
    assert approved.outcome == "applied", approved
    assert service.approve(context, second, command, key) == approved
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.financial_records where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchone() == (1,)


def test_api_denies_read_only_and_reports_stale_both_versions(actions):
    service, context, grant = actions
    first, second = pair(actions)
    command = request_for(service, context, second, first).model_dump(mode="json")
    for field in ("version", "other_version"):
        response = post_resolution(
            service, context, second, {**command, field: command[field] + 1}
        )
        assert response.status_code == 409, response.text
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set business_role='viewer' where id=%s",
            (grant,),
        )
    response = post_resolution(service, context, second, command)
    assert response.status_code == 403, response.text

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from argus.domain.business.actions import BusinessActions, plans
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import (
    Ask,
    BoundDraft,
    ProposeActivity,
    ProposeAllocation,
    ReviewDraft,
    TurnPlan,
    canonical_input_hash,
)
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.transactions import transaction
from faker import Faker

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import space

fake = Faker()
users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark


def change(target: BoundDraft, evidence: UUID) -> ProposeActivity:
    return ProposeActivity(
        draft=target,
        facts=BusinessFactPatch(counterparty={"state": "known", "value": fake.company()}),
        source_ids=(evidence,),
    )


def question(target: BoundDraft) -> Ask:
    return Ask(draft=target, field="funding", asked_of="owner", prompt=fake.sentence())


def test_existing_draft_binding_survives_each_action_restart_and_replay(actions):
    service, context, _ = actions
    draft, version = shared.create(service, context)
    before = service.review(
        context,
        draft,
        ReviewDraft(
            version=version,
            facts=BusinessFactPatch(
                funding={"state": "known", "value": {"kind": "owner_funds"}}
            ),
        ),
        fake.uuid4(),
    )
    agent = service.resolve_actor(
        context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    target = BoundDraft(draft_id=draft, base_version=before.version)
    evidence = shared.source(service, agent)
    date = fake.date_object()
    commands = [
        ProposeActivity(
            draft=target,
            facts=BusinessFactPatch(occurred_on={"state": "known", "value": date}),
            source_ids=(evidence,),
        ),
        ProposeAllocation(
            draft=target,
            funding={"state": "known", "value": {"kind": "owner_funds"}},
            business_share={"state": "known", "value": {"kind": "all"}},
            source_ids=(evidence,),
        ),
        Ask(draft=target, field="counterparty", asked_of="owner", prompt=fake.sentence()),
    ]
    key, lease = shared.prepare(service, agent, commands)
    results = []
    for index in range(len(commands)):
        restarted = BusinessActions(service.authority.pool, service.imports)
        saved = restarted.plan_for_turn(agent, key, lease=lease)
        assert saved == TurnPlan(actions=commands)
        result = restarted.execute(agent, key, index, lease=lease)
        assert result.outcome == "applied", result
        assert restarted.execute(agent, key, index, lease=lease) == result
        results.append(result)
    assert [result.version for result in results] == [3, 4, 4]
    view = service.dossier(context, draft)
    assert view.version == 4
    assert len(view.history) == 4
    assert len(view.questions) == 1
    assert view.facts.occurred_on.value == date
    assert view.facts.business_share.value.kind == "all"
    with service.authority.pool.connection() as db:
        receipts = db.execute(
            "select command,input_hash from public.business_action_receipts"
            " where turn_key=%s order by action_index",
            (key,),
        ).fetchall()
        assert len(receipts) == len(commands)
        for (command, input_hash), expected in zip(receipts, commands, strict=True):
            assert command["draft"] == target.model_dump(mode="json")
            assert input_hash == canonical_input_hash(expected)
        assert (
            db.execute(
                "select count(*) from public.financial_records where user_id=%s",
                (context.owner_id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("interleave_after_first", [False, True])
def test_bound_reference_does_not_absorb_concurrent_human_revision(
    actions, interleave_after_first: bool
):
    service, context, _ = actions
    draft, version = shared.create(service, context)
    target = BoundDraft(draft_id=draft, base_version=version)
    evidence = shared.source(service, context)
    commands = [change(target, evidence), question(target)]
    key, lease = shared.prepare(service, context, commands)
    if interleave_after_first:
        assert service.execute(context, key, 0, lease=lease).version == version + 1
        version += 1
    human = service.review(
        context,
        draft,
        ReviewDraft(
            version=version, facts=BusinessFactPatch(amount={"state": "unknown"})
        ),
        fake.uuid4(),
    )
    assert human.outcome == "applied"
    index = 1 if interleave_after_first else 0
    refused = service.execute(context, key, index, lease=lease)
    assert refused.outcome == "stale_version"
    assert service.execute(context, key, index, lease=lease) == refused
    if not interleave_after_first:
        assert (
            service.execute(context, key, 1, lease=lease).code
            == "business_prior_action_not_applied"
        )
    view = service.dossier(context, draft)
    assert view.version == human.version
    assert view.facts.amount.state == "unknown"
    assert not view.questions


def test_two_bound_plans_racing_same_base_commit_one_revision(actions):
    service, context, _ = actions
    draft, version = shared.create(service, context)
    target = BoundDraft(draft_id=draft, base_version=version)
    evidence = shared.source(service, context)
    turns = [
        shared.prepare(service, context, [change(target, evidence)]) for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda turn: service.execute(context, turn[0], 0, lease=turn[1]), turns
            )
        )
    assert sorted(result.outcome for result in results) == ["applied", "stale_version"]
    assert service.dossier(context, draft).version == version + 1


def test_bound_target_cannot_inherit_another_draft_or_turn_revision(actions):
    service, context, _ = actions
    first, version = shared.create(service, context)
    second, _ = shared.create(service, context)
    target = BoundDraft(draft_id=first, base_version=version)
    other = BoundDraft(draft_id=second, base_version=version)
    evidence = shared.source(service, context)
    key, lease = shared.prepare(
        service, context, [change(other, evidence), change(target, evidence)]
    )
    assert service.execute(context, key, 0, lease=lease).version == 2
    assert service.execute(context, key, 1, lease=lease).version == 2
    later_key, later_lease = shared.prepare(service, context, [change(target, evidence)])
    assert (
        service.execute(context, later_key, 0, lease=later_lease).outcome
        == "stale_version"
    )
    assert service.dossier(context, first).version == 2
    assert service.dossier(context, second).version == 2


def test_bound_target_keeps_cross_client_not_found(actions, users):
    service, context, _ = actions
    with service.authority.pool.connection() as db:
        other_space = space(db, users["other"])
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare','approve'])",
            (other_space, users["other"], users["other"]),
        )
    other = service.resolve_actor(
        TrustedActor(
            actor_id=UUID(users["other"]), actor_kind="member", space_id=UUID(other_space)
        )
    )
    foreign, version = shared.create(service, other)
    evidence = shared.source(service, context)
    command = change(BoundDraft(draft_id=foreign, base_version=version), evidence)
    key, lease = shared.prepare(service, context, [command])
    result = service.execute(context, key, 0, lease=lease)
    assert result.outcome == "not_found"
    assert result.code == "business_record_not_found"
    assert service.dossier(other, foreign).version == version


def test_bound_target_unknown_receipt_blocks_later_work(actions):
    service, context, _ = actions
    draft, version = shared.create(service, context)
    target = BoundDraft(draft_id=draft, base_version=version)
    command = change(target, shared.source(service, context))
    key, lease = shared.prepare(service, context, [command, question(target)])
    with transaction(service.authority, context, "prepare", lease) as tx:
        plans.start_receipt(tx, plans.action_key(key, 0), command, turn_key=key, index=0)
    assert service.execute(context, key, 0, lease=lease).outcome == "outcome_unknown"
    assert (
        service.execute(context, key, 1, lease=lease).code
        == "business_prior_action_unsettled"
    )
    assert service.dossier(context, draft).version == version
    assert not service.dossier(context, draft).questions


def test_bound_plan_identity_is_immutable_and_revocation_stops_resume(actions):
    service, context, grant = actions
    draft, version = shared.create(service, context)
    target = BoundDraft(draft_id=draft, base_version=version)
    command = change(target, shared.source(service, context))
    key, lease = shared.prepare(service, context, [command, question(target)])
    assert service.execute(context, key, 0, lease=lease).outcome == "applied"
    altered = command.model_copy(
        update={"draft": target.model_copy(update={"base_version": version + 1})}
    )
    with pytest.raises(ActionError, match="business_plan_conflict"):
        service.persist_plan(
            context,
            key,
            TurnPlan(actions=[altered, question(altered.draft)]),
            lease=lease,
        )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (grant,),
        )
    assert service.execute(context, key, 1, lease=lease).outcome == "not_found"
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_questions where draft_id=%s",
                (draft,),
            ).fetchone()[0]
            == 0
        )

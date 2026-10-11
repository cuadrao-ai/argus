from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.agent_runtime.business.binding import (
    BusinessBindingError,
    capture_business_snapshot,
    compile_business_plan,
)
from argus.agent_runtime.business.interpretation import (
    BusinessInterpretation,
    BusinessRecordIntent,
)
from argus.domain.business.contracts.actions import TurnPlan
from pydantic import ValidationError


def snapshot(draft_id=None, *, version=2, questions=()):
    return {
        "drafts": [] if draft_id is None else [{"id": str(draft_id), "version": version}],
        "questions": list(questions),
    }


def question(draft_id, *, field="funding", asked_of="owner", state="open"):
    return {
        "id": str(uuid4()),
        "draft_id": str(draft_id),
        "field": field,
        "asked_of": asked_of,
        "state": state,
        "channel": "whatsapp" if asked_of == "owner" else "web",
        "prompt": "How was it paid?",
        "allowed_answers": ["known", "owner_does_not_know"],
        "answer_source_id": str(uuid4()) if state != "open" else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def compile_records(*records, context=None, source_id=None, read_context=False):
    return compile_business_plan(
        BusinessInterpretation(records=records, read_context=read_context),
        snapshot=capture_business_snapshot(context or snapshot()),
        source_id=source_id or uuid4(),
    )


def test_semantic_wire_schema_does_not_expose_execution_or_authority_fields():
    schema = json.dumps(BusinessInterpretation.model_json_schema())
    for field in (
        "from_action",
        "base_version",
        "source_ids",
        "answers_question_id",
        "grant_id",
        "actor_id",
        "space_id",
    ):
        assert field not in schema
    assert "TurnPlan" not in schema
    assert "ExistingDraft" not in schema
    assert "BoundDraft" not in schema


@pytest.mark.parametrize(
    "field", ["version", "base_version", "source_ids", "from_action", "grant_id"]
)
def test_semantic_record_rejects_model_execution_binding(field):
    with pytest.raises(ValidationError):
        BusinessRecordIntent.model_validate({field: 1})


def test_create_references_are_server_generated_and_scoped_to_each_record_group():
    records = tuple(
        BusinessRecordIntent(
            facts={"amount": {"state": "known", "value": str(amount)}},
            question={
                "field": "funding",
                "asked_of": "owner",
                "prompt": "How was it paid?",
            },
        )
        for amount in (17, 29)
    )
    source_id = uuid4()
    plan = compile_records(*records, source_id=source_id, read_context=True)
    assert [action.action for action in plan.actions] == [
        "business_read_context",
        "business_propose_activity",
        "business_ask",
        "business_propose_activity",
        "business_ask",
    ]
    assert plan.actions[1].draft is plan.actions[3].draft is None
    assert plan.actions[2].draft.from_action == 1
    assert plan.actions[4].draft.from_action == 3
    assert plan.actions[1].source_ids == plan.actions[3].source_ids == (source_id,)


def test_existing_update_allocation_and_question_share_captured_base_version():
    draft_id, source_id = uuid4(), uuid4()
    record = BusinessRecordIntent(
        target_draft_id=draft_id,
        facts={"occurred_on": {"state": "known", "value": "2026-10-09"}},
        allocation={
            "funding": {"state": "known", "value": {"kind": "owner_funds"}},
            "business_share": {"state": "known", "value": {"kind": "all"}},
        },
        question={
            "field": "counterparty",
            "asked_of": "owner",
            "prompt": "Who supplied the materials?",
        },
    )
    plan = compile_records(record, context=snapshot(draft_id), source_id=source_id)
    assert len(plan.actions) == 3
    assert all(
        action.draft.model_dump(mode="json")
        == {"draft_id": str(draft_id), "base_version": 2}
        for action in plan.actions
    )
    assert plan.actions[0].source_ids == plan.actions[1].source_ids == (source_id,)
    rejected_legacy = plan.model_dump(mode="json")
    rejected_legacy["actions"][0]["draft"] = {
        "draft_id": str(draft_id),
        "version": 2,
    }
    for action in rejected_legacy["actions"][1:]:
        action["draft"] = {"from_action": 0}
    with pytest.raises(ValidationError, match="draft creation"):
        TurnPlan.model_validate(rejected_legacy)
    with pytest.raises(ValidationError):
        BusinessInterpretation.model_validate({"plan": rejected_legacy})


def test_binding_snapshot_is_captured_before_model_and_cannot_follow_changed_payload():
    draft_id = uuid4()
    pending = question(draft_id)
    raw = snapshot(draft_id, questions=[pending])
    captured = capture_business_snapshot(raw)
    raw["drafts"][0]["version"] = 30
    pending["asked_of"] = "accountant"
    proposal = BusinessInterpretation(
        records=(
            BusinessRecordIntent(
                target_draft_id=draft_id,
                facts={"funding": {"state": "owner_does_not_know"}},
                question={
                    "field": "funding",
                    "asked_of": "accountant",
                    "prompt": "Please review the payment source.",
                },
            ),
        )
    )
    plan = compile_business_plan(proposal, snapshot=captured, source_id=uuid4())
    assert plan.actions[0].draft.base_version == 2
    assert plan.actions[0].answers_question_id == captured.questions[0].id
    assert plan.actions[1].asked_of == "accountant"


@pytest.mark.parametrize("version", [0, -1, True, "2"])
def test_binding_rejects_malformed_canonical_version(version):
    with pytest.raises(BusinessBindingError, match="context_draft_invalid"):
        capture_business_snapshot(snapshot(uuid4(), version=version))


def test_binding_rejects_duplicate_canonical_targets():
    raw = snapshot(uuid4())
    raw["drafts"].append(dict(raw["drafts"][0]))
    with pytest.raises(BusinessBindingError, match="context_draft_invalid"):
        capture_business_snapshot(raw)


def test_unknown_mutable_target_never_selects_another_supplied_draft():
    unknown = uuid4()
    with pytest.raises(BusinessBindingError, match="target_not_in_context"):
        compile_records(
            BusinessRecordIntent(
                target_draft_id=unknown,
                facts={"amount": {"state": "known", "value": "83"}},
            ),
            context=snapshot(uuid4()),
        )


def test_contradictory_groups_for_same_target_are_not_merged():
    draft_id = uuid4()
    records = tuple(
        BusinessRecordIntent(
            target_draft_id=draft_id,
            facts={"amount": {"state": "known", "value": str(amount)}},
        )
        for amount in (17, 29)
    )
    with pytest.raises(BusinessBindingError, match="target_repeated"):
        compile_records(*records, context=snapshot(draft_id))


def test_foreign_read_uses_canonical_action_refusal_without_binding_write_authority():
    foreign_id = uuid4()
    plan = compile_records(
        BusinessRecordIntent(target_draft_id=foreign_id, explain_status=True)
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "business_explain_status"
    assert plan.actions[0].draft_id == foreign_id


@pytest.mark.parametrize(
    "asked_of,state", [("accountant", "open"), ("owner", "answered")]
)
def test_owner_patch_does_not_answer_accountant_or_closed_question(asked_of, state):
    draft_id = uuid4()
    plan = compile_records(
        BusinessRecordIntent(
            target_draft_id=draft_id,
            facts={"funding": {"state": "known", "value": {"kind": "owner_funds"}}},
        ),
        context=snapshot(
            draft_id, questions=[question(draft_id, asked_of=asked_of, state=state)]
        ),
    )
    assert plan.actions[0].answers_question_id is None


def test_multiple_matching_owner_questions_refuse_ambiguous_answer_binding():
    draft_id = uuid4()
    with pytest.raises(BusinessBindingError, match="answer_question_ambiguous"):
        compile_records(
            BusinessRecordIntent(
                target_draft_id=draft_id,
                facts={"funding": {"state": "owner_does_not_know"}},
            ),
            context=snapshot(
                draft_id, questions=[question(draft_id), question(draft_id)]
            ),
        )


def test_generated_action_limit_is_enforced_before_persistence():
    records = tuple(
        BusinessRecordIntent(
            facts={"amount": {"state": "known", "value": "17"}},
            question={
                "field": "funding",
                "asked_of": "owner",
                "prompt": "How was it paid?",
            },
        )
        for _ in range(5)
    )
    with pytest.raises(ValidationError, match="at most 8"):
        compile_records(*records)


def test_overlapping_fact_and_allocation_intents_are_not_normalized():
    draft_id = uuid4()
    with pytest.raises(BusinessBindingError, match="allocation_overlaps_facts"):
        compile_records(
            BusinessRecordIntent(
                target_draft_id=draft_id,
                facts={"funding": {"state": "known", "value": {"kind": "owner_funds"}}},
                allocation={
                    "funding": {"state": "unknown"},
                    "business_share": {"state": "known", "value": {"kind": "all"}},
                },
            ),
            context=snapshot(draft_id),
        )


def test_model_context_keeps_semantic_facts_without_execution_bindings():
    from argus.agent_runtime.business.binding import model_business_context

    draft_id, source_id = uuid4(), uuid4()
    pending = question(draft_id)
    raw = snapshot(draft_id, questions=[pending])
    raw["drafts"][0]["facts"] = {
        "currency": {
            "state": "known",
            "value": "DOP",
            "origin": "default",
            "verified": False,
            "source_ids": [],
        },
        "fiscal": {"rnc": {"state": "known", "value": "123", "source_ids": [source_id]}},
    }
    projected = model_business_context(raw)
    assert projected["drafts"][0]["id"] == str(draft_id)
    assert projected["drafts"][0]["facts"]["currency"] == {
        "state": "known",
        "value": "DOP",
        "origin": "default",
        "verified": False,
    }
    encoded = json.dumps(projected, default=str)
    for name in (
        "source_ids",
        "answer_source_id",
        "version",
        "from_action",
        "base_version",
    ):
        assert name not in encoded
    assert str(pending["id"]) not in encoded
    assert str(source_id) not in encoded
    assert raw["drafts"][0]["version"] == 2
    assert raw["questions"][0]["id"] == pending["id"]


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"question": {"field": "funding", "asked_of": "owner", "prompt": "How paid?"}},
        {"explain_status": True},
    ],
)
def test_unselected_record_never_implicitly_uses_the_latest_draft(record):
    with pytest.raises(BusinessBindingError, match="new_target_requires_facts"):
        compile_records(
            BusinessRecordIntent.model_validate(record), context=snapshot(uuid4())
        )


def test_semantic_target_must_be_a_valid_supplied_uuid_shape():
    with pytest.raises(ValidationError):
        BusinessRecordIntent(target_draft_id="latest", explain_status=True)

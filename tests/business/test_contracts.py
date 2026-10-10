from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from argus.domain.business.contracts.actions import (
    MAX_TURN_ACTIONS,
    ApprovalCommand,
    BusinessAction,
    ProposeActivity,
    TurnPlan,
    canonical_input_hash,
)
from argus.domain.business.contracts.dossier import (
    BusinessDossier,
    ReviewQuestion,
    SourceEvidence,
)
from argus.domain.business.contracts.facts import (
    BusinessFactPatch,
    BusinessFacts,
    Known,
    legacy_projection,
)
from argus.domain.business.contracts.recovery import ActionReceipt, DurableTurn
from faker import Faker
from pydantic import TypeAdapter, ValidationError

fake = Faker()
FIXTURE = Path(__file__).parent / "fixtures" / "hosted_business_dossier.json"


@pytest.fixture
def dossier() -> BusinessDossier:
    return BusinessDossier.model_validate_json(FIXTURE.read_text())


def test_dossier_retains_uncertainty_and_separates_receipt_time(
    dossier: BusinessDossier,
) -> None:
    assert dossier.facts.funding.state == "owner_does_not_know"
    assert dossier.history[0].before.funding.state == "unknown"
    assert dossier.history[0].after == dossier.facts
    assert dossier.questions[0].asked_of == "accountant"
    assert dossier.sources[0].received_at.date() != dossier.facts.occurred_on.value
    assert not dossier.approval_available
    assert dossier.facts.currency.origin == "default"
    assert not dossier.facts.currency.verified
    assert BusinessDossier.model_validate_json(dossier.model_dump_json()) == dossier


@pytest.mark.parametrize("field", ["kind", "occurred_on", "funding", "amount"])
def test_only_currency_can_default(field: str) -> None:
    values = {
        "kind": "expense",
        "occurred_on": "2026-10-09",
        "funding": {"kind": "owner_funds"},
        "amount": "100",
    }
    with pytest.raises(ValidationError, match="only DOP currency"):
        BusinessFacts.model_validate(
            {
                field: {
                    "state": "known",
                    "value": values[field],
                    "origin": "default",
                    "source_ids": [],
                }
            }
        )


@pytest.mark.parametrize("change", [{"verified": True}, {"value": "USD"}])
def test_dop_default_cannot_be_verified_or_other_currency(change: dict) -> None:
    fact = {"state": "known", "value": "DOP", "origin": "default", "source_ids": []}
    with pytest.raises(ValidationError):
        BusinessFacts.model_validate({"currency": {**fact, **change}})


@pytest.mark.parametrize("state", ["unknown", "owner_does_not_know"])
@pytest.mark.parametrize("extra", [{"value": "250"}, {"verified": True}])
def test_uncertainty_cannot_hide_value_or_claim_verification(
    state: str, extra: dict
) -> None:
    with pytest.raises(ValidationError):
        BusinessFacts.model_validate(
            {
                "amount": {
                    "state": state,
                    "value": None,
                    "origin": "owner_stated",
                    "source_ids": [fake.uuid4()],
                    **extra,
                }
            }
        )


def test_projection_masks_older_extraction_and_never_debits_owner_funds() -> None:
    source = UUID(fake.uuid4())
    facts = BusinessFacts(
        funding=Known(
            value={"kind": "owner_funds"},
            origin="owner_stated",
            source_ids=(source,),
        )
    )
    extracted = {
        "amount": "250",
        "account_id": fake.uuid4(),
        "kind": "expense",
        "direction": "outflow",
    }
    projected = {**extracted, **legacy_projection(facts)}
    assert projected["amount"] is None
    assert projected["account_id"] is None
    assert projected["kind"] is None
    assert projected["direction"] is None


@pytest.mark.parametrize("value", ["income", "expense"])
def test_kind_preserves_the_proposal(value: str) -> None:
    facts = BusinessFacts.model_validate(
        {
            "kind": {
                "state": "known",
                "value": value,
                "origin": "owner_stated",
                "source_ids": [fake.uuid4()],
            }
        }
    )
    assert legacy_projection(facts)["kind"] == value


@pytest.mark.parametrize(
    "fields", [{}, {"amount": None}, {"kind": {"state": "known", "value": "other"}}]
)
def test_patch_rejects_missing_or_untyped_facts(fields: dict) -> None:
    with pytest.raises(ValidationError):
        BusinessFactPatch.model_validate(fields)


@pytest.mark.parametrize(
    "field", ["actor_id", "space_id", "grant_id", "fiscal", "approve"]
)
def test_model_action_cannot_claim_trusted_authority_or_tax_decision(field: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(BusinessAction).validate_python(
            {
                "action": "business_propose_activity",
                "source_ids": [fake.uuid4()],
                "facts": {"amount": {"state": "known", "value": "10"}},
                field: fake.uuid4(),
            }
        )


def test_model_cannot_emit_human_approval() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(BusinessAction).validate_python(
            {"action": "record_expense", "version": 1}
        )


def test_plan_references_only_prior_draft_creation() -> None:
    create = {
        "action": "business_propose_activity",
        "source_ids": [fake.uuid4()],
        "facts": {"kind": {"state": "known", "value": "expense"}},
    }
    ask = {
        "action": "business_ask",
        "draft": {"from_action": 0},
        "field": "funding",
        "asked_of": "owner",
        "prompt": "¿Cómo lo pagaste?",
    }
    assert len(TurnPlan.model_validate({"actions": [create, ask]}).actions) == 2
    with pytest.raises(ValidationError, match="earlier action"):
        TurnPlan.model_validate({"actions": [ask, create]})
    with pytest.raises(ValidationError, match="draft creation"):
        TurnPlan.model_validate({"actions": [{"action": "business_read_context"}, ask]})


def test_normalized_hash_matches_defaults_and_decimal_spelling() -> None:
    source = fake.uuid4()
    first = ProposeActivity.model_validate(
        {
            "source_ids": [source],
            "facts": {"amount": {"state": "known", "value": "1850.00"}},
        }
    )
    second = ProposeActivity.model_validate(
        {
            "action": "business_propose_activity",
            "draft": None,
            "source_ids": [source],
            "facts": {"amount": {"state": "known", "value": "1850"}},
        }
    )
    assert canonical_input_hash(first) == canonical_input_hash(second)
    assert canonical_input_hash(first) != canonical_input_hash(
        ProposeActivity.model_validate(
            {
                "source_ids": [source],
                "facts": {"amount": {"state": "known", "value": "1851"}},
            }
        )
    )


def test_approval_hash_binds_canonical_target_and_version() -> None:
    target = fake.uuid4()
    base = ApprovalCommand.model_validate(
        {"draft_id": target, "request": {"version": 1, "action": "record_expense"}}
    )
    other = ApprovalCommand.model_validate(
        {"draft_id": fake.uuid4(), "request": {"version": 1, "action": "record_expense"}}
    )
    newer = ApprovalCommand.model_validate(
        {"draft_id": target, "request": {"version": 2, "action": "record_expense"}}
    )
    assert len({canonical_input_hash(item) for item in (base, other, newer)}) == 3


def test_exact_decimal_normalization_does_not_round() -> None:
    amount = "123456789012345678901234567890.120000"
    patch = BusinessFactPatch.model_validate(
        {"amount": {"state": "known", "value": amount}}
    )
    assert patch.amount.value == amount.rstrip("0")


def test_owner_uncertainty_cannot_reopen_owner_question(dossier: BusinessDossier) -> None:
    value = dossier.questions[0].model_dump(mode="json")
    with pytest.raises(ValidationError, match="accountant"):
        ReviewQuestion.model_validate({**value, "asked_of": "owner"})
    with pytest.raises(ValidationError, match="answer source"):
        ReviewQuestion.model_validate({**value, "answer_source_id": None})


def test_completed_turn_needs_persisted_plan(dossier: BusinessDossier) -> None:
    value = {
        "space_id": fake.uuid4(),
        "actor_id": dossier.history[0].actor.actor_id,
        "sender_hash": fake.sha256(),
        "turn_key": fake.sha256(),
        "arrival_sequence": 1,
        "phase": "turn_done",
        "model_state": "completed",
    }
    with pytest.raises(ValidationError, match="persisted plan"):
        DurableTurn.model_validate(value)
    with pytest.raises(ValidationError, match="actor provenance"):
        DurableTurn.model_validate({**value, "plan": {"actions": []}})
    saved = {**value, "plan": {"actions": []}, "plan_actor": dossier.history[0].actor}
    assert DurableTurn.model_validate(saved).plan is not None
    with pytest.raises(ValidationError, match="actual actor"):
        DurableTurn.model_validate({**saved, "actor_id": fake.uuid4()})
    with pytest.raises(ValidationError, match="actor provenance"):
        DurableTurn.model_validate({**saved, "plan": None, "model_state": "running"})


def test_plan_rejects_more_than_the_executor_can_run() -> None:
    action = {"action": "business_read_context"}
    assert (
        len(TurnPlan.model_validate({"actions": [action] * MAX_TURN_ACTIONS}).actions)
        == MAX_TURN_ACTIONS
    )
    with pytest.raises(ValidationError):
        TurnPlan.model_validate({"actions": [action] * (MAX_TURN_ACTIONS + 1)})


def test_persisted_plan_round_trips_partial_patch_without_inventing_edits() -> None:
    plan = TurnPlan.model_validate(
        {
            "actions": [
                {
                    "action": "business_propose_activity",
                    "source_ids": [fake.uuid4()],
                    "facts": {
                        "amount": {"state": "known", "value": "1850"},
                        "funding": {"state": "owner_does_not_know", "value": None},
                    },
                }
            ]
        }
    )
    restored = TurnPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    assert restored.actions[0].facts.model_fields_set == {"amount", "funding"}


def test_known_facts_require_evidence_and_amount_requires_exact_string() -> None:
    with pytest.raises(ValidationError, match="require a source"):
        BusinessFacts.model_validate(
            {
                "amount": {
                    "state": "known",
                    "value": "10",
                    "origin": "extracted",
                    "source_ids": [],
                }
            }
        )
    with pytest.raises(ValidationError):
        BusinessFactPatch.model_validate({"amount": {"state": "known", "value": 0.1}})


def test_web_action_source_preserves_human_command_and_rejects_whatsapp(
    dossier: BusinessDossier,
) -> None:
    payload = {
        "id": fake.uuid4(),
        "kind": "web_action",
        "channel": "web",
        "received_at": dossier.sources[0].received_at,
        "text": '{"facts":{"funding":{"state":"known","value":{"kind":"owner_funds"}}},"version":1}',
    }
    adapter = TypeAdapter(SourceEvidence)
    source = adapter.validate_python(payload)
    assert source.text == payload["text"]
    assert adapter.validate_json(adapter.dump_json(source)) == source
    with pytest.raises(ValidationError):
        adapter.validate_python({**payload, "channel": "whatsapp"})


def test_receipt_provenance_is_required_and_bound_to_actual_actor(
    dossier: BusinessDossier,
) -> None:
    actor = dossier.history[0].actor
    payload = {
        "space_id": dossier.space_id,
        "actor_id": actor.actor_id,
        "actor": actor,
        "idempotency_key": fake.sha256(),
        "input_hash": fake.sha256(),
        "command": {
            "action": "review_draft",
            "draft_id": dossier.draft_id,
            "request": {
                "version": dossier.version,
                "facts": {"amount": {"state": "unknown"}},
            },
        },
        "created_at": dossier.sources[0].received_at,
    }
    receipt = ActionReceipt.model_validate(payload)
    assert receipt.turn_key is None and receipt.actor == actor
    with pytest.raises(ValidationError, match="actual actor"):
        ActionReceipt.model_validate({**payload, "actor_id": fake.uuid4()})
    del payload["actor"]
    with pytest.raises(ValidationError):
        ActionReceipt.model_validate(payload)


def test_agent_receipt_requires_a_persisted_turn(dossier: BusinessDossier) -> None:
    actor = dossier.history[0].actor
    payload = {
        "space_id": dossier.space_id,
        "actor_id": actor.actor_id,
        "actor": actor,
        "idempotency_key": fake.sha256(),
        "input_hash": fake.sha256(),
        "command": {"action": "business_read_context"},
        "created_at": dossier.sources[0].received_at,
    }
    with pytest.raises(ValidationError, match="persisted turn plan"):
        ActionReceipt.model_validate(payload)
    receipt = ActionReceipt.model_validate(
        {**payload, "turn_key": fake.sha256(), "action_index": 0}
    )
    assert receipt.action_index == 0

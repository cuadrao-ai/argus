from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from argus.domain.business.contracts.actions import (
    MAX_TURN_ACTIONS,
    ApprovalCommand,
    ApproveIncome,
    AttachmentPreparationBinding,
    BusinessAction,
    CaptureNote,
    Command,
    IncomeApprovalCommand,
    PrepareAttachmentCommand,
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
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
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


def test_patch_schema_requires_a_fact_without_requiring_every_field() -> None:
    schema = BusinessFactPatch.model_json_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert len(schema["properties"]) == 9
    assert not schema.get("required")
    assert all("default" not in field for field in schema["properties"].values())
    with pytest.raises(JsonSchemaValidationError):
        validator.validate({})
    with pytest.raises(ValidationError, match="at least one fact"):
        BusinessFactPatch.model_validate({})
    payload = {"amount": {"state": "known", "value": "850"}}
    validator.validate(payload)
    patch = BusinessFactPatch.model_validate(payload)
    assert patch.model_fields_set == {"amount"}
    assert patch.currency is None
    assert patch.model_dump(mode="json") == payload


@pytest.mark.parametrize("field", tuple(BusinessFactPatch.model_fields))
def test_patch_schema_matches_explicit_uncertainty_and_rejects_outer_null(
    field: str,
) -> None:
    validator = Draft202012Validator(BusinessFactPatch.model_json_schema())
    payload = {field: None}
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(payload)
    with pytest.raises(ValidationError, match="explicit unknown state"):
        BusinessFactPatch.model_validate(payload)
    for state in ("unknown", "owner_does_not_know"):
        payload = {field: {"state": state, "value": None}}
        validator.validate(payload)
        patch = BusinessFactPatch.model_validate(payload)
        assert patch.model_fields_set == {field}
        assert patch.model_dump(mode="json") == payload


def test_turn_plan_schema_retains_nonnullable_patch_boundary() -> None:
    validator = Draft202012Validator(TurnPlan.model_json_schema())
    payload = {
        "actions": [
            {
                "action": "business_propose_activity",
                "facts": {"amount": {"state": "unknown", "value": None}},
                "source_ids": [fake.uuid4()],
            }
        ]
    }
    validator.validate(payload)
    TurnPlan.model_validate(payload)
    for invalid in ({}, {"amount": None}):
        payload["actions"][0]["facts"] = invalid
        with pytest.raises(JsonSchemaValidationError):
            validator.validate(payload)
        with pytest.raises(ValidationError):
            TurnPlan.model_validate(payload)


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
    for version_field in ("version", "base_version"):
        revise = {**create, "draft": {"draft_id": fake.uuid4(), version_field: 2}}
        with pytest.raises(ValidationError, match="draft creation"):
            TurnPlan.model_validate({"actions": [revise, ask]})


def test_legacy_exact_references_keep_explicit_versions_and_serialization() -> None:
    draft_id = fake.uuid4()
    actions = [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": draft_id, "version": version},
            "source_ids": [fake.uuid4()],
            "facts": {"amount": {"state": "unknown", "value": None}},
        }
        for version in (2, 3)
    ]
    plan = TurnPlan.model_validate({"actions": actions})
    assert [action.draft.version for action in plan.actions] == [2, 3]
    assert [
        action.model_dump(mode="json", exclude_none=True)["draft"]
        for action in plan.actions
    ] == [action["draft"] for action in actions]
    assert TurnPlan.model_validate_json(plan.model_dump_json()) == plan


def test_bound_draft_plan_retains_one_captured_revision_and_round_trips() -> None:
    target = {"draft_id": fake.uuid4(), "base_version": 2}
    action = {
        "action": "business_propose_activity",
        "draft": target,
        "source_ids": [fake.uuid4()],
        "facts": {"amount": {"state": "unknown"}},
    }
    ask = {
        "action": "business_ask",
        "draft": target,
        "field": "funding",
        "asked_of": "owner",
        "prompt": fake.sentence(),
    }
    plan = TurnPlan.model_validate({"actions": [action, ask]})
    assert plan.schema_version == 1
    assert plan.actions[0].draft == plan.actions[1].draft
    assert TurnPlan.model_validate_json(plan.model_dump_json()) == plan
    assert canonical_input_hash(plan.actions[0]) == canonical_input_hash(
        TurnPlan.model_validate_json(plan.model_dump_json()).actions[0]
    )


@pytest.mark.parametrize("change", [{"base_version": 3}, {"version": 2}])
@pytest.mark.parametrize("reverse", [False, True])
def test_bound_draft_plan_rejects_rebinding_or_mixed_exact_references(
    change: dict, reverse: bool
) -> None:
    draft_id = fake.uuid4()
    first = {
        "action": "business_propose_activity",
        "draft": {"draft_id": draft_id, "base_version": 2},
        "source_ids": [fake.uuid4()],
        "facts": {"amount": {"state": "unknown"}},
    }
    second = {**first, "draft": {"draft_id": draft_id, **change}}
    actions = [second, first] if reverse else [first, second]
    with pytest.raises(ValidationError, match="one captured draft binding"):
        TurnPlan.model_validate({"actions": actions})


@pytest.mark.parametrize("version", [0, -1, True, "2", 2.5])
def test_bound_draft_rejects_malformed_captured_versions(version: object) -> None:
    with pytest.raises(ValidationError):
        ProposeActivity.model_validate(
            {
                "draft": {"draft_id": fake.uuid4(), "base_version": version},
                "source_ids": [fake.uuid4()],
                "facts": {"amount": {"state": "unknown"}},
            }
        )


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


@pytest.mark.parametrize("target", [False, True])
def test_manual_capture_preserves_original_text_and_exact_target(target: bool) -> None:
    text = f" \t{fake.sentence()}\n"
    request = {"text": text}
    if target:
        request["draft"] = {"draft_id": fake.uuid4(), "version": 3}
    payload = {"action": "capture_note", "request": request}
    adapter = TypeAdapter(Command)
    command = adapter.validate_python(payload)
    assert command.request.text == text
    assert adapter.validate_json(adapter.dump_json(command)) == command
    assert (command.request.draft is not None) == target
    if target:
        assert command.request.draft.model_dump(mode="json") == request["draft"]
    changed = adapter.validate_python(
        {**payload, "request": {**request, "text": text.strip()}}
    )
    assert canonical_input_hash(command) != canonical_input_hash(changed)
    with pytest.raises(ValidationError):
        TypeAdapter(BusinessAction).validate_python(payload)
    with pytest.raises(ValidationError):
        TurnPlan.model_validate({"actions": [payload]})


@pytest.mark.parametrize("text", ["", " \t\r\n\f\v\u00a0", "a" * 20001])
def test_manual_capture_rejects_empty_blank_or_oversized_text(text: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Command).validate_python(
            {"action": "capture_note", "request": {"text": text}}
        )


@pytest.mark.parametrize("length", [1, 20000])
def test_manual_capture_accepts_text_length_boundaries(length: int) -> None:
    assert CaptureNote(text="a" * length).text == "a" * length


@pytest.mark.parametrize(
    "draft",
    [
        {"from_action": 0},
        {"draft_id": fake.uuid4(), "base_version": 1},
        {"draft_id": fake.uuid4(), "version": 0},
        {"draft_id": "not-a-record", "version": 1},
    ],
)
def test_manual_capture_requires_an_exact_existing_target(draft: dict) -> None:
    with pytest.raises(ValidationError):
        CaptureNote(text=fake.sentence(), draft=draft)


@pytest.mark.parametrize("version", [True, False, "1", "3", 1.0, 3.0, 1.5])
def test_manual_capture_rejects_coercible_json_target_versions(version: object) -> None:
    payload = {
        "text": fake.sentence(),
        "draft": {"draft_id": fake.uuid4(), "version": version},
    }
    with pytest.raises(
        ValidationError, match="capture target version must be an integer"
    ):
        CaptureNote.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("text", ["\x00", "original\x00text", "\x00 nota \r\n"])
def test_manual_capture_rejects_nul_without_rewriting_text(text: str) -> None:
    with pytest.raises(ValidationError, match="capture text must not contain NUL"):
        CaptureNote.model_validate_json(json.dumps({"text": text}))


@pytest.mark.parametrize("version", [1, 3])
def test_manual_capture_retains_valid_json_integer_and_original_unicode(
    version: int,
) -> None:
    payload = {
        "text": f"\t{fake.sentence()} Café\r\n",
        "draft": {"draft_id": fake.uuid4(), "version": version},
    }
    note = CaptureNote.model_validate_json(json.dumps(payload))
    assert note.model_dump(mode="json") == payload
    assert isinstance(note.draft.version, int) and not isinstance(
        note.draft.version, bool
    )


@pytest.mark.parametrize("field", ["actor_id", "space_id", "grant_id", "source_ids"])
def test_manual_capture_rejects_caller_authority_and_sources(field: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Command).validate_python(
            {
                "action": "capture_note",
                "request": {"text": fake.sentence(), field: fake.uuid4()},
            }
        )


@pytest.mark.parametrize("actor_kind", ["member", "owner_via_agent", "extractor"])
@pytest.mark.parametrize("with_turn", [False, True])
def test_manual_capture_receipt_requires_human_without_turn(
    dossier: BusinessDossier, actor_kind: str, with_turn: bool
) -> None:
    actor = dossier.history[0].actor.model_copy(update={"actor_kind": actor_kind})
    payload = {
        "space_id": dossier.space_id,
        "actor_id": actor.actor_id,
        "actor": actor,
        "idempotency_key": fake.sha256(),
        "input_hash": fake.sha256(),
        "command": {"action": "capture_note", "request": {"text": fake.sentence()}},
        "created_at": dossier.sources[0].received_at,
        "turn_key": fake.sha256() if with_turn else None,
        "action_index": 0 if with_turn else None,
    }
    if actor_kind == "member" and not with_turn:
        receipt = ActionReceipt.model_validate(payload)
        assert receipt.actor == actor
        assert receipt.command.action == "capture_note"
    else:
        with pytest.raises(
            ValidationError, match="capture requires a human command without a turn"
        ):
            ActionReceipt.model_validate(payload)


@pytest.mark.parametrize("version", [True, False, "1", 1.0, 1.5, 0, -1, None])
def test_income_approval_requires_exact_positive_integer_version(version):
    with pytest.raises(ValidationError):
        ApproveIncome.model_validate({"action": "record_income", "version": version})


def test_income_human_command_round_trips_and_hashes_distinctly_from_expense():
    draft_id = UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    income = IncomeApprovalCommand(
        draft_id=draft_id, request=ApproveIncome(action="record_income", version=3)
    )
    adapter = TypeAdapter(Command)
    assert adapter.validate_json(income.model_dump_json()) == income
    changed_target = income.model_copy(update={"draft_id": UUID(fake.uuid4())})
    changed_version = IncomeApprovalCommand(
        draft_id=draft_id, request=ApproveIncome(action="record_income", version=4)
    )
    expense = ApprovalCommand.model_validate(
        {"draft_id": str(draft_id), "request": {"action": "record_expense", "version": 3}}
    )
    assert (
        len(
            {
                canonical_input_hash(value)
                for value in (income, changed_target, changed_version, expense)
            }
        )
        == 4
    )
    assert canonical_input_hash(income) == canonical_input_hash(
        adapter.validate_json(income.model_dump_json())
    )
    assert income.model_dump(mode="json") == {
        "action": "approve_income",
        "draft_id": str(draft_id),
        "request": {"version": 3, "action": "record_income"},
    }


@pytest.mark.parametrize(
    "extra", ["actor_id", "space_id", "grant_id", "account_id", "facts", "amount"]
)
def test_income_approval_cannot_supply_authority_or_replace_reviewed_facts(extra):
    with pytest.raises(ValidationError):
        ApproveIncome.model_validate(
            {"action": "record_income", "version": 1, extra: fake.uuid4()}
        )


def test_income_approval_is_not_a_model_action_or_a_turn_plan():
    command = IncomeApprovalCommand(
        draft_id=UUID(fake.uuid4()),
        request=ApproveIncome(action="record_income", version=1),
    )
    for payload in (
        command.model_dump(mode="json"),
        command.request.model_dump(mode="json"),
    ):
        with pytest.raises(ValidationError):
            TypeAdapter(BusinessAction).validate_python(payload)
        with pytest.raises(ValidationError):
            TurnPlan.model_validate({"actions": [payload]})
    with pytest.raises(ValidationError):
        ApproveIncome(action="record_expense", version=1)


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        {"outcome": "outcome_unknown", "code": "business_recording_unsettled"},
        {"outcome": "applied", "version": 1},
        {"outcome": "replayed", "version": 1},
    ],
)
def test_income_receipt_retains_actual_human_authority_and_recovery(dossier, outcome):
    actor = dossier.history[0].actor.model_copy(update={"actor_kind": "member"})
    command = IncomeApprovalCommand(
        draft_id=dossier.draft_id,
        request=ApproveIncome(action="record_income", version=dossier.version),
    )
    payload = dict(
        space_id=dossier.space_id,
        actor_id=actor.actor_id,
        actor=actor,
        idempotency_key="income-human-review",
        input_hash=canonical_input_hash(command),
        command=command,
        created_at=dossier.sources[0].received_at,
        outcome=outcome,
    )
    receipt = ActionReceipt.model_validate(payload)
    assert receipt.actor == actor and receipt.turn_key is None
    assert ActionReceipt.model_validate_json(receipt.model_dump_json()) == receipt
    with pytest.raises(ValidationError, match="actual actor"):
        ActionReceipt.model_validate({**payload, "actor_id": fake.uuid4()})
    for kind in ("owner_via_agent", "extractor"):
        with pytest.raises(ValidationError, match="human command without a turn"):
            ActionReceipt.model_validate(
                {**payload, "actor": actor.model_copy(update={"actor_kind": kind})}
            )
    with pytest.raises(ValidationError, match="human command without a turn"):
        ActionReceipt.model_validate(
            {**payload, "turn_key": "invented-turn", "action_index": 0}
        )


@pytest.fixture
def attachment_binding(dossier: BusinessDossier) -> AttachmentPreparationBinding:
    return AttachmentPreparationBinding(
        binding_id=fake.uuid4(),
        space_id=dossier.space_id,
        owner_id=fake.uuid4(),
        connection_id=fake.uuid4(),
        source_sha256=fake.sha256(),
        actor=dossier.history[0].actor.model_copy(update={"actor_kind": "extractor"}),
        target=None,
        consent=True,
        captured_at=dossier.sources[0].received_at,
    )


def test_attachment_command_is_server_only_and_round_trips(attachment_binding):
    command = PrepareAttachmentCommand(
        binding=attachment_binding, batch_sha256=fake.sha256()
    )
    encoded = command.model_dump_json()
    assert TypeAdapter(Command).validate_json(encoded) == command
    with pytest.raises(ValidationError):
        TypeAdapter(BusinessAction).validate_json(encoded)
    with pytest.raises(ValidationError):
        TurnPlan(actions=(command,))
    assert canonical_input_hash(command) == canonical_input_hash(
        PrepareAttachmentCommand.model_validate_json(encoded)
    )


@pytest.mark.parametrize(
    "field",
    [
        "binding_id",
        "space_id",
        "owner_id",
        "connection_id",
        "source_sha256",
        "actor",
        "target",
        "consent",
        "captured_at",
    ],
)
def test_attachment_binding_requires_original_inputs(attachment_binding, field):
    payload = attachment_binding.model_dump(mode="json")
    del payload[field]
    with pytest.raises(ValidationError):
        AttachmentPreparationBinding.model_validate(payload)


@pytest.mark.parametrize("value", [False, None, 1, "true"])
def test_attachment_binding_consent_is_affirmative_boolean(attachment_binding, value):
    with pytest.raises(ValidationError):
        AttachmentPreparationBinding.model_validate(
            {**attachment_binding.model_dump(), "consent": value}
        )


@pytest.mark.parametrize("version", [True, False, "1", 1.0, 1.5, 0])
def test_attachment_binding_target_requires_exact_positive_integer(
    attachment_binding, version
):
    with pytest.raises(ValidationError):
        AttachmentPreparationBinding.model_validate(
            {
                **attachment_binding.model_dump(),
                "target": {"draft_id": fake.uuid4(), "version": version},
            }
        )


def test_attachment_binding_new_and_existing_targets_have_distinct_hashes(
    attachment_binding,
):
    command = PrepareAttachmentCommand(
        binding=attachment_binding, batch_sha256=fake.sha256()
    )
    payload = command.model_dump(mode="json")
    payload["binding"]["target"] = {"draft_id": fake.uuid4(), "version": 2}
    existing = PrepareAttachmentCommand.model_validate(payload)
    assert existing.binding.target.version == 2
    assert canonical_input_hash(existing) != canonical_input_hash(command)
    for field in ("source_sha256", "actor", "target"):
        changed = existing.model_dump(mode="json")
        if field == "actor":
            changed["binding"][field]["grant_id"] = fake.uuid4()
        elif field == "target":
            changed["binding"][field]["version"] = 3
        else:
            changed["binding"][field] = fake.sha256()
        assert canonical_input_hash(
            PrepareAttachmentCommand.model_validate(changed)
        ) != canonical_input_hash(existing)
    assert canonical_input_hash(
        command.model_copy(update={"batch_sha256": fake.sha256()})
    ) != canonical_input_hash(command)


@pytest.mark.parametrize("kind", ["member", "owner_via_agent"])
def test_attachment_binding_never_claims_human_approval(attachment_binding, kind):
    payload = attachment_binding.model_dump(mode="json")
    payload["actor"]["actor_kind"] = kind
    with pytest.raises(ValidationError):
        AttachmentPreparationBinding.model_validate(payload)


def test_attachment_receipt_pins_original_actor_space_and_no_turn(attachment_binding):
    command = PrepareAttachmentCommand(
        binding=attachment_binding, batch_sha256=fake.sha256()
    )
    payload = dict(
        space_id=attachment_binding.space_id,
        actor_id=attachment_binding.actor.actor_id,
        actor=attachment_binding.actor,
        idempotency_key=f"attachment:{attachment_binding.binding_id}",
        input_hash=canonical_input_hash(command),
        command=command,
        created_at=attachment_binding.captured_at,
    )
    receipt = ActionReceipt.model_validate(payload)
    assert ActionReceipt.model_validate_json(receipt.model_dump_json()) == receipt
    altered_actor = attachment_binding.actor.model_copy(update={"grant_id": fake.uuid4()})
    for change in (
        {"actor": altered_actor},
        {"space_id": fake.uuid4()},
        {"actor_id": fake.uuid4()},
        {"turn_key": fake.sha256(), "action_index": 0},
    ):
        with pytest.raises(ValidationError):
            ActionReceipt.model_validate({**payload, **change})

from typing import get_args

import pytest
from argus.agent_runtime.capabilities.contract import (
    CapabilityContract,
    CapabilityRange,
    FieldDescription,
    OptionalParameterSpec,
    SimplificationTemplate,
    UnsupportedCombination,
    ValidationRule,
    build_default_capability_contract,
)
from argus.agent_runtime.profile.response_profile import (
    resolve_effective_response_profile,
)
from argus.agent_runtime.state.models import (
    AmbiguousField,
    ArtifactActionRecoveryFacts,
    ConversationMessage,
    ExtractedFieldValue,
    ResolutionProvenance,
    ResponseProfileOverrides,
    RunState,
    SimplificationOption,
    StructuredActionContext,
    TaskSnapshot,
    ThreadState,
    UnsupportedConstraint,
    UserState,
    normalize_resolution_provenance_items,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    "intent", get_args(get_args(RunState.model_fields["intent"].annotation)[0])
)
def test_checkpoint_preserves_the_existing_interpreter_intent(intent: str) -> None:
    state = RunState(current_user_message="", intent=intent)
    restored = RunState.model_validate_json(state.model_dump_json())
    snapshot = TaskSnapshot(latest_task_type=restored.intent)

    assert restored.intent == intent
    assert (
        TaskSnapshot.model_validate_json(snapshot.model_dump_json()).latest_task_type
        == intent
    )


def make_valid_contract_kwargs() -> dict:
    return {
        "version": "test",
        "supported_intents": (
            "strategy_drafting",
            "backtest_execution",
        ),
        "supported_tool_families": ("backtest_tools",),
        "required_field_descriptions": {
            "strategy_thesis": FieldDescription(
                label="Strategy thesis",
                description="Plain-language summary of the idea.",
            ),
            "asset_universe": FieldDescription(
                label="Assets",
                description="Symbols included in the run.",
            ),
            "entry_logic": FieldDescription(
                label="Entry logic",
                description="What opens the position.",
            ),
            "exit_logic": FieldDescription(
                label="Exit logic",
                description="What closes the position.",
            ),
            "date_range": FieldDescription(
                label="Date range",
                description="Historical period used for testing.",
            ),
        },
        "optional_parameters": {
            "timeframe": OptionalParameterSpec(
                default_value="1D",
                description=FieldDescription(
                    label="Timeframe",
                    description="Bar interval used for the simulation.",
                ),
                allowed_range=CapabilityRange(
                    allowed_values=("1h", "2h", "4h", "6h", "12h", "1D")
                ),
            ),
            "slippage": OptionalParameterSpec(
                default_value=0.0,
                description=FieldDescription(
                    label="Slippage",
                    description="Execution slippage assumption.",
                ),
                allowed_range=CapabilityRange(minimum=0.0, maximum=0.05),
            ),
        },
        "validation_rules": (
            ValidationRule(
                field_name="asset_universe",
                rule_type="max_length",
                message="Backtests support up to 5 symbols per run.",
            ),
        ),
        "unsupported_combinations": (
            UnsupportedCombination(
                fields={"asset_universe": ["too_many_symbols"]},
                reason="Known unsupported asset-universe shape.",
            ),
        ),
    }


def test_resolution_provenance_normalizer_skips_invalid_legacy_items() -> None:
    normalized = normalize_resolution_provenance_items(
        [
            {
                "field": "asset_universe",
                "raw_text": "AAPL",
                "source": "user_mention",
                "candidate_kind": "asset",
                "canonical_symbol": "AAPL",
            },
            {
                "field": "asset_universe",
                "raw_text": "legacy asset",
                "source": "legacy_regex_router",
                "candidate_kind": "asset",
            },
            "not-a-provenance-dict",
        ]
    )

    assert normalized == [
        ResolutionProvenance(
            field="asset_universe",
            raw_text="AAPL",
            source="user_mention",
            candidate_kind="asset",
            canonical_symbol="AAPL",
        )
    ]


def test_effective_response_profile_prefers_turn_override() -> None:
    user = UserState(
        user_id="user-1",
        display_name="Sarah",
        language_preference="en",
        preferred_tone="concise",
        expertise_level="advanced",
        response_verbosity="low",
    )

    profile = resolve_effective_response_profile(
        user=user,
        explicit_overrides=ResponseProfileOverrides(
            tone="friendly",
            verbosity="high",
            expertise_mode="beginner",
        ),
    )

    assert profile.effective_tone == "friendly"
    assert profile.effective_verbosity == "high"
    assert profile.effective_expertise_mode == "beginner"


def test_response_profile_overrides_reject_unknown_values() -> None:
    with pytest.raises(ValidationError):
        ResponseProfileOverrides(verbosity="verbose")


def test_artifact_action_recovery_facts_reject_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ArtifactActionRecoveryFacts(
            action_type="retry_failed_action",
            status="retry_this_somehow",
        )


def test_structured_retry_action_exposes_canonical_failed_action_id() -> None:
    action = StructuredActionContext(
        type="retry_failed_action",
        payload={"failed_action_id": " failed-1 "},
    )

    assert action.failed_action_artifact_id == "failed-1"


def test_structured_action_does_not_infer_failed_action_id_for_other_actions() -> None:
    action = StructuredActionContext(
        type="run_backtest",
        payload={"failed_action_id": "failed-1"},
    )

    assert action.failed_action_artifact_id is None


def test_run_state_starts_fresh_but_thread_state_keeps_history() -> None:
    thread = ThreadState(
        thread_id="thread-1",
        message_history=[ConversationMessage(role="user", content="backtest Apple")],
        thread_metadata={"latest_task_type": "backtest_execution"},
        latest_task_snapshot=TaskSnapshot(latest_task_type="backtest_execution"),
        artifact_references=[],
    )

    state = RunState.new(
        current_user_message="now try Tesla",
        recent_thread_history=thread.message_history,
    )

    assert state.current_user_message == "now try Tesla"
    assert state.recent_thread_history == thread.message_history
    assert state.recent_thread_history is not thread.message_history
    assert state.recent_thread_history[0] is not thread.message_history[0]
    assert state.recent_thread_history[0].role == "user"
    assert state.tool_call_records == []
    assert state.confirmation_payload is None

    state.recent_thread_history[0].content = "backtest Tesla"
    state.recent_thread_history.append(
        ConversationMessage(role="assistant", content="Tesla draft prepared.")
    )

    assert len(state.recent_thread_history) == 2
    assert thread.message_history == [
        ConversationMessage(role="user", content="backtest Apple")
    ]


def test_extraction_models_capture_resolution_states() -> None:
    extracted = ExtractedFieldValue(
        raw_value="sell when RSI > 70",
        normalized_value="exit when RSI rises above 70",
        status="resolved",
    )
    ambiguous = AmbiguousField(
        field_name="exit_logic",
        raw_value="sell if RSI is not above 70",
        candidate_normalized_value="exit when RSI rises above 70",
        reason_code="negation_or_conditional_reversal",
    )
    unsupported = UnsupportedConstraint(
        category="unsupported_time_granularity",
        raw_value="sell at market open",
        explanation="Market-open execution timing is not supported in this runtime slice.",
        simplification_options=[
            SimplificationOption(
                label="Retry with daily bars",
                replacement_values={"timeframe": "1D"},
            ),
        ],
    )

    assert extracted.status == "resolved"
    assert extracted.normalized_value == "exit when RSI rises above 70"
    assert ambiguous.reason_code == "negation_or_conditional_reversal"
    assert unsupported.simplification_options[0].label == "Retry with daily bars"
    assert unsupported.simplification_options[0].replacement_values == {"timeframe": "1D"}


def test_simplification_option_serializes_nested_frozen_payloads() -> None:
    unsupported = UnsupportedConstraint(
        category="indicator",
        raw_value="ATR 14",
        explanation="ATR is not executable as a rule yet.",
        simplification_options=[
            SimplificationOption(
                label="Use moving-average crossover",
                replacement_values={
                    "strategy_type": "signal_strategy",
                    "entry_rule": {
                        "type": "moving_average_crossover",
                        "fast_indicator": "sma",
                        "fast_period": 50,
                    },
                },
            )
        ],
    )

    dumped = unsupported.model_dump(mode="python")

    assert dumped["simplification_options"][0]["replacement_values"] == {
        "strategy_type": "signal_strategy",
        "entry_rule": {
            "type": "moving_average_crossover",
            "fast_indicator": "sma",
            "fast_period": 50,
        },
    }


def test_capability_contract_exposes_required_and_optional_fields() -> None:
    contract = build_default_capability_contract()

    assert contract.version == "1.0"
    assert "backtest_execution" in contract.supported_intents
    assert "backtest_tools" in contract.supported_tool_families
    assert contract.required_fields == [
        "strategy_thesis",
        "asset_universe",
        "entry_logic",
        "exit_logic",
        "date_range",
    ]
    assert contract.optional_defaults["initial_capital"] == 1000.0
    assert contract.optional_defaults["timeframe"] == "1D"
    assert "engine_options" in contract.optional_defaults
    assert contract.get_optional_parameter("initial_capital").description.label == (
        "Initial capital"
    )
    assert contract.get_allowed_range("slippage").maximum == 0.05
    assert contract.get_optional_parameter("timeframe").default_value == "1D"
    assert contract.allowed_ranges["timeframe"].allowed_values == (
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1D",
    )
    assert set(contract.optional_defaults) == set(contract.optional_parameters)
    assert set(contract.required_fields).isdisjoint(contract.optional_parameters)
    assert contract.validation_rules[0].field_name == "asset_universe"
    assert contract.describe_field("strategy_thesis").label == "Strategy thesis"
    assert contract.describe_field("timeframe").label == "Timeframe"
    assert contract.unsupported_combinations == ()


def test_capability_contract_optional_defaults_are_mutation_safe() -> None:
    contract = build_default_capability_contract()

    defaults = contract.optional_defaults
    defaults["engine_options"]["mode"] = "mutated"

    assert contract.optional_defaults["engine_options"] == {}


def test_capability_contract_exposes_default_simplification_templates() -> None:
    contract = build_default_capability_contract()

    assert set(contract.simplification_templates) == {
        "unsupported_time_granularity",
        "unsupported_asset_mix",
        "unsupported_strategy_logic",
        "future_performance",
    }
    future_options = contract.get_simplification_options("future_performance")
    assert [
        option.replacement_values.get("requested_field") for option in future_options
    ] == ["date_range", "date_range"]
    options = contract.get_simplification_options("unsupported_time_granularity")

    assert options == [
        SimplificationOption(
            label="Retry with daily bars",
            replacement_values={"timeframe": "1D"},
        ),
        SimplificationOption(
            label="Retry with 1-hour bars",
            replacement_values={"timeframe": "1h"},
        ),
    ]
    assert contract.get_simplification_options("unknown_category") == []


def test_capability_contract_simplification_access_is_mutation_safe() -> None:
    contract = build_default_capability_contract()

    options = contract.get_simplification_options("unsupported_time_granularity")
    options[0] = SimplificationOption(
        label="Mutated",
        replacement_values={"timeframe": "4h"},
    )

    with pytest.raises(TypeError):
        contract.simplification_templates["unsupported_strategy_logic"] = (
            SimplificationTemplate(
                category="unsupported_strategy_logic",
                options=(
                    SimplificationOption(
                        label="Mutated",
                        replacement_values={"position_side": "short"},
                    ),
                ),
            )
        )

    with pytest.raises((TypeError, ValidationError)):
        contract.simplification_templates["unsupported_strategy_logic"].options += (
            SimplificationOption(
                label="Mutated",
                replacement_values={"position_side": "short"},
            ),
        )

    with pytest.raises((TypeError, ValidationError)):
        contract.simplification_templates["unsupported_time_granularity"].options[
            0
        ].label = "Mutated"

    with pytest.raises(TypeError):
        contract.simplification_templates["unsupported_time_granularity"].options[
            0
        ].replacement_values["timeframe"] = "mutated"

    assert contract.get_simplification_options("unsupported_time_granularity") == [
        SimplificationOption(
            label="Retry with daily bars",
            replacement_values={"timeframe": "1D"},
        ),
        SimplificationOption(
            label="Retry with 1-hour bars",
            replacement_values={"timeframe": "1h"},
        ),
    ]


def test_capability_contract_accessors_do_not_expose_live_mutable_internals() -> None:
    contract = build_default_capability_contract()

    optional_parameter = contract.get_optional_parameter("timeframe")
    allowed_range = contract.get_allowed_range("timeframe")
    described_field = contract.describe_field("strategy_thesis")
    derived_ranges = contract.allowed_ranges

    with pytest.raises((TypeError, ValidationError)):
        optional_parameter.allowed_range.allowed_values += ("mutated",)
    with pytest.raises((TypeError, ValidationError)):
        allowed_range.allowed_values += ("other",)
    with pytest.raises((TypeError, ValidationError)):
        described_field.label = "Mutated"
    with pytest.raises((TypeError, ValidationError)):
        derived_ranges["timeframe"].allowed_values += ("bad",)

    assert contract.get_optional_parameter("timeframe").allowed_range.allowed_values == (
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1D",
    )
    assert contract.describe_field("strategy_thesis").label == "Strategy thesis"


def test_capability_contract_rejects_overlapping_required_and_optional_fields() -> None:
    with pytest.raises(ValidationError):
        CapabilityContract(
            **{
                **make_valid_contract_kwargs(),
                "required_field_descriptions": {
                    **make_valid_contract_kwargs()["required_field_descriptions"],
                    "timeframe": FieldDescription(
                        label="Timeframe",
                        description="Conflicting duplicate field.",
                    ),
                },
            }
        )


def test_capability_contract_rejects_validation_rules_for_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CapabilityContract(
            **{
                **make_valid_contract_kwargs(),
                "validation_rules": [
                    *make_valid_contract_kwargs()["validation_rules"],
                    ValidationRule(
                        field_name="unknown_field",
                        rule_type="required_for_execution",
                        message="Unknown field should fail.",
                    ),
                ],
            }
        )


def test_capability_contract_rejects_unsupported_combinations_for_unknown_fields() -> (
    None
):
    with pytest.raises(ValidationError):
        CapabilityContract(
            **{
                **make_valid_contract_kwargs(),
                "unsupported_combinations": [
                    *make_valid_contract_kwargs()["unsupported_combinations"],
                    UnsupportedCombination(
                        fields={"unknown_field": ["bad"]},
                        reason="Unknown field should fail.",
                    ),
                ],
            }
        )


def test_capability_contract_rejects_optional_defaults_outside_numeric_range() -> None:
    with pytest.raises(ValidationError):
        CapabilityContract(
            **{
                **make_valid_contract_kwargs(),
                "optional_parameters": {
                    **make_valid_contract_kwargs()["optional_parameters"],
                    "slippage": OptionalParameterSpec(
                        default_value=0.1,
                        description=FieldDescription(
                            label="Slippage",
                            description="Invalid default outside allowed range.",
                        ),
                        allowed_range=CapabilityRange(minimum=0.0, maximum=0.05),
                    ),
                },
            }
        )


def test_capability_contract_rejects_optional_defaults_outside_allowed_values() -> None:
    with pytest.raises(ValidationError):
        CapabilityContract(
            **{
                **make_valid_contract_kwargs(),
                "optional_parameters": {
                    **make_valid_contract_kwargs()["optional_parameters"],
                    "timeframe": OptionalParameterSpec(
                        default_value="30m",
                        description=FieldDescription(
                            label="Timeframe",
                            description="Invalid enum default.",
                        ),
                        allowed_range=CapabilityRange(
                            allowed_values=("1h", "2h", "4h", "6h", "12h", "1D")
                        ),
                    ),
                },
            }
        )


def test_capability_contract_rejects_invalid_supported_intent_names() -> None:
    with pytest.raises(ValidationError):
        CapabilityContract(
            **{
                **make_valid_contract_kwargs(),
                "supported_intents": ["backtest_execution", "not_a_real_intent"],
            }
        )


def test_capability_contract_public_model_fields_are_immutable() -> None:
    contract = build_default_capability_contract()

    with pytest.raises((TypeError, ValidationError)):
        contract.supported_intents += ("strategy_drafting",)

    with pytest.raises(TypeError):
        contract.optional_parameters["timeframe"] = contract.get_optional_parameter(
            "timeframe"
        )

    with pytest.raises((TypeError, ValidationError)):
        contract.optional_parameters["timeframe"].allowed_range.allowed_values += ("bad",)


def test_capability_contract_nested_default_value_payload_is_immutable() -> None:
    contract = build_default_capability_contract()

    with pytest.raises(TypeError):
        contract.optional_parameters["engine_options"].default_value["mode"] = "mutated"


def test_capability_contract_unsupported_combination_fields_are_immutable() -> None:
    contract = CapabilityContract(**make_valid_contract_kwargs())

    with pytest.raises(TypeError):
        contract.unsupported_combinations[0].fields["asset_universe"] += ("other",)

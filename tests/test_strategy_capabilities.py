import pytest
from argus.domain.cadences import SUPPORTED_DCA_CADENCE_VALUES
from argus.domain.strategy_capabilities import (
    STRATEGY_CAPABILITIES,
    ResultChartExplorationSpec,
    resolve_result_chart_exploration_policy,
)


def test_registry_contains_all_alpha_templates():
    expected = {
        "buy_and_hold",
        "buy_the_dip",
        "rsi_mean_reversion",
        "moving_average_crossover",
        "dca_accumulation",
        "momentum_breakout",
        "trend_follow",
    }
    assert set(STRATEGY_CAPABILITIES.keys()) == expected


def test_dca_accumulation_has_cadence_parameter():
    dca = STRATEGY_CAPABILITIES["dca_accumulation"]
    assert "dca_cadence" in dca.parameters
    spec = dca.parameters["dca_cadence"]
    assert spec.policy == "clarify_if_missing"
    assert spec.default == "monthly"
    assert spec.allowed_values == list(SUPPORTED_DCA_CADENCE_VALUES)


def test_strategy_aliases_are_machine_identifiers():
    for cap in STRATEGY_CAPABILITIES.values():
        assert len(cap.aliases) > 0
        assert cap.display_name != ""
        for alias in cap.aliases:
            assert alias == alias.strip().casefold()
            assert " " not in alias
            assert "-" not in alias


def test_buy_and_hold_aliases_are_machine_compatibility_not_nlu():
    """Capability aliases are not the multilingual interpretation layer."""
    bah = STRATEGY_CAPABILITIES["buy_and_hold"]
    assert bah.display_name == "Buy and Hold"
    assert "lump_sum_investment" in bah.aliases
    assert "one_time_investment" in bah.aliases
    assert "buy and hold" not in bah.aliases
    assert "hold" not in bah.aliases
    assert "comprar y mantener" not in bah.aliases


def test_registry_aliases_are_not_orchestrator_nlu():
    """The registry exposes machine compatibility, not prose extraction."""
    import importlib.util

    assert importlib.util.find_spec("argus.domain.orchestrator") is None
    for capability in STRATEGY_CAPABILITIES.values():
        assert capability.display_name not in capability.aliases


def test_exploration_spec_defaults_are_the_safe_observation_only_policy():
    spec = ResultChartExplorationSpec()
    assert spec.minimum_visible_observations == 6
    assert spec.minimum_meaningful_duration is None
    assert spec.cycle_parameter is None
    assert spec.cycle_duration_by_value == {}
    assert spec.minimum_visible_cycles == 2


def test_buy_and_hold_resolves_one_month_chart_duration():
    assert resolve_result_chart_exploration_policy(
        {"template": "buy_and_hold", "parameters": {}}
    ) == {
        "minimum_visible_observations": 6,
        "minimum_meaningful_duration": "P1M",
    }


@pytest.mark.parametrize(
    ("cadence", "duration"),
    [
        ("daily", "P2D"),
        ("weekly", "P2W"),
        ("biweekly", "P4W"),
        ("monthly", "P2M"),
        ("quarterly", "P6M"),
    ],
)
def test_dca_resolves_two_typed_cadence_cycles(cadence, duration):
    assert resolve_result_chart_exploration_policy(
        {
            "template": "dca_accumulation",
            "parameters": {"dca_cadence": cadence},
        }
    ) == {
        "minimum_visible_observations": 6,
        "minimum_meaningful_duration": duration,
    }


def test_dca_with_unknown_cadence_degrades_to_observation_only():
    assert resolve_result_chart_exploration_policy(
        {
            "template": "dca_accumulation",
            "parameters": {"dca_cadence": "fortnightly"},
        }
    ) == {"minimum_visible_observations": 6}


def test_signal_capability_uses_observation_only_policy():
    assert resolve_result_chart_exploration_policy(
        {"template": "rsi_mean_reversion", "parameters": {}}
    ) == {"minimum_visible_observations": 6}


def test_unknown_capability_uses_safe_observation_only_policy():
    assert resolve_result_chart_exploration_policy(
        {"template": "future_strategy", "parameters": {"future_cycle": "fortnight"}}
    ) == {"minimum_visible_observations": 6}


def test_resolver_tolerates_missing_template_and_malformed_parameters():
    assert resolve_result_chart_exploration_policy({}) == {
        "minimum_visible_observations": 6
    }
    assert resolve_result_chart_exploration_policy(
        {"template": "dca_accumulation", "parameters": "monthly"}
    ) == {"minimum_visible_observations": 6}


def test_exploration_metadata_contains_no_display_or_provider_fields():
    forbidden = {"display_name", "label", "provider", "asset_class", "timeframe"}
    for capability in STRATEGY_CAPABILITIES.values():
        dumped = capability.result_chart_exploration.model_dump()
        assert forbidden.isdisjoint(dumped)


def test_registry_keeps_locale_phrases_out_of_execution_capabilities():
    """Execution capabilities are not the multilingual NLU layer."""
    if "dca_accumulation" not in STRATEGY_CAPABILITIES:
        pytest.skip("dca_accumulation not in registry")

    forbidden_fragments = {
        "compra",
        "comprar",
        "mantener",
        "semanal",
        "mensual",
        "diario",
        "quincenal",
        "trimestral",
        "tendencia",
        "ruptura",
    }
    all_aliases: list[str] = []
    for capability in STRATEGY_CAPABILITIES.values():
        all_aliases.extend(capability.aliases)
        assert capability.display_name not in capability.aliases
        for spec in capability.parameters.values():
            for aliases in spec.value_aliases.values():
                all_aliases.extend(aliases)

    leaked = [
        alias
        for alias in all_aliases
        if any(fragment in alias.casefold() for fragment in forbidden_fragments)
    ]
    assert leaked == []

    cap = STRATEGY_CAPABILITIES["dca_accumulation"]
    assert "dca_cadence" in cap.parameters
    spec = cap.parameters["dca_cadence"]
    assert set(spec.allowed_values) == {
        "daily",
        "weekly",
        "biweekly",
        "monthly",
        "quarterly",
    }

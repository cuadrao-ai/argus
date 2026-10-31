"""The $10 starting-capital floor on every path that sets or edits capital.

A recurring plan keeps its own seed and contribution rules, and a run whose
portfolio never reached $1,000 shows its money to the cent.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

import pytest
from argus.agent_runtime.artifact_edit_planner import (
    EditOperation,
    apply_edit_operations,
)
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.result_conversation import _run_sheet
from argus.agent_runtime.stages import confirm as confirm_module
from argus.agent_runtime.stages.clarify import clarify_stage
from argus.agent_runtime.stages.confirm import confirm_stage
from argus.agent_runtime.stages.interpret_internal.confirmation_artifact_edits import (
    apply_resolved_artifact_edit_to_strategy_summary,
)
from argus.agent_runtime.stages.launch_validation_recovery import (
    _validate_launch_envelope,
)
from argus.agent_runtime.state.models import RunState, StrategySummary
from argus.api.chat.confirmation import runtime_confirmation_card
from argus.api.chat.persistence import build_runtime_backtest_run
from argus.api.main import app
from argus.api.message_store import create_message
from argus.domain.backtesting.config import MAX_STARTING_CAPITAL, MIN_STARTING_CAPITAL
from argus.domain.dca_capital import DcaCapitalError, build_dca_capital_plan
from argus.domain.engine_launch.adapter import run_launch_backtest
from argus.domain.engine_launch.models import LaunchBacktestRequest
from argus.domain.result_money import (
    format_result_money,
    stored_currency_fraction_digits,
    with_currency_fraction_digits,
)
from argus.domain.result_readout_display_values import readout_display_value
from argus.domain.result_readout_headlines import (
    headline_readout_facts,
    headline_request_lines,
)
from argus.domain.result_readout_prompt_facts import readout_prompt_facts
from babel.numbers import format_decimal
from fastapi.testclient import TestClient

UNDER_THE_FLOOR = 9.99
LANGUAGES = ("en", "es-419")
CONFIRMATION_ID = "33333333-3333-4333-8333-333333333333"
SOURCE_RUN_ID = "5d6c1e0a-7b3f-4c2a-9e1d-2f3a4b5c6d7e"
_CLOSE = {"kind": "price", "field": "close"}
_EMA = {"kind": "indicator", "key": "ema", "period": 20}
# Every strategy type that runs on one bankroll. A recurring plan's money
# rules are its own and stay covered by test_dca_capital_semantics.
_ONE_BANKROLL_RULES: dict[str, dict[str, Any]] = {
    "buy_and_hold": {},
    "indicator_threshold": {
        "entry_rule": {"indicator": "rsi", "operator": "below", "threshold": 45},
        "exit_rule": {"indicator": "rsi", "operator": "above", "threshold": 55},
    },
    "signal_strategy": {
        "rule_spec": {
            "entry": {"conditions": [{"left": _CLOSE, "operator": "gt", "right": _EMA}]},
            "exit": {"conditions": [{"left": _CLOSE, "operator": "lt", "right": _EMA}]},
        }
    },
}


def _launch_request(
    strategy_type: str, capital: float, *, symbol: str = "AAPL"
) -> LaunchBacktestRequest:
    fields: dict[str, Any] = {
        "strategy_type": strategy_type,
        "symbol": symbol,
        "symbols": [symbol],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": {"start": "2024-01-02", "end": "2024-12-31"},
        "entry_rule": None,
        "exit_rule": None,
        "sizing_mode": "capital_amount",
        "capital_amount": capital,
        "position_size": None,
        "cadence": None,
        "parameters": {},
        "risk_rules": [],
        "benchmark_symbol": "SPY",
    }
    fields.update(_ONE_BANKROLL_RULES[strategy_type])
    return LaunchBacktestRequest.model_validate(fields)


def _rows(card: dict[str, Any]) -> dict[str, str]:
    return {row["key"]: row["value"] for row in card["rows"]}


def _draft(capital: float) -> StrategySummary:
    return StrategySummary(
        strategy_type="buy_and_hold",
        asset_universe=["NFLX"],
        asset_class="equity",
        date_range={"start": "2024-01-02", "end": "2024-12-31"},
        capital_amount=capital,
    )


@pytest.fixture
def unadjusted_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        confirm_module,
        "_strategy_with_latest_complete_data_adjustment",
        lambda strategy: strategy,
    )


@pytest.fixture
def in_place_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_IN_PLACE_CARD_EDITS_ENABLED", "true")


def _assert_offered_the_floor(patch: dict[str, Any]) -> None:
    constraint = patch["optional_parameter_status"]["unsupported_constraints"][0]
    assert constraint["category"] == "unsupported_starting_capital"
    assert constraint["minimum"] == 10.0
    assert constraint["simplification_options"][0] == {
        "label": "Use $10",
        "replacement_values": {"capital_amount": 10.0},
    }


# ── One owner ────────────────────────────────────────────────────────────────


def test_the_floor_is_ten_and_the_capability_contract_reads_it() -> None:
    assert MIN_STARTING_CAPITAL == 10.0
    contract = build_default_capability_contract()
    allowed = contract.get_allowed_range("initial_capital")
    assert allowed is not None
    assert allowed.minimum == MIN_STARTING_CAPITAL
    # Unchanged: the amount used when none is stated, and the ceiling.
    assert contract.optional_defaults["initial_capital"] == 1000.0
    assert MAX_STARTING_CAPITAL == 100_000_000.0


@pytest.mark.parametrize("strategy_type", sorted(_ONE_BANKROLL_RULES))
def test_the_card_gate_admits_ten_and_refuses_less(strategy_type: str) -> None:
    _validate_launch_envelope(_launch_request(strategy_type, 10.0))
    with pytest.raises(ValueError, match="invalid_starting_capital"):
        _validate_launch_envelope(_launch_request(strategy_type, UNDER_THE_FLOOR))


def test_a_recurring_plan_keeps_its_own_money_rules() -> None:
    plan = build_dca_capital_plan(
        starting_capital=0.0, contribution=5.0, period="monthly"
    )
    assert (plan.starting_capital, plan.contribution) == (0.0, 5.0)
    with pytest.raises(
        DcaCapitalError, match="dca_requires_starting_capital_or_contribution"
    ):
        build_dca_capital_plan(starting_capital=0.0, contribution=0.0, period="monthly")


# ── The run ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("strategy_type", sorted(_ONE_BANKROLL_RULES))
def test_a_ten_dollar_run_executes_and_nine_ninety_nine_is_refused(
    strategy_type: str,
) -> None:
    launch = run_launch_backtest(_launch_request(strategy_type, 10.0))
    assert launch.envelope.execution_status == "succeeded", launch.envelope.failure_reason
    performance = launch.envelope.metrics["aggregate"]["performance"]
    rows = _rows(launch.result_card)
    assert rows["cash_value"].startswith("$10.00 -> $")
    assert rows["total_return_pct"] == f"{performance['total_return_pct']:+.1f}%"

    refused = run_launch_backtest(_launch_request(strategy_type, UNDER_THE_FLOOR))
    assert refused.envelope.execution_status == "blocked_invalid_input"
    assert refused.envelope.failure_reason == "invalid_starting_capital"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_card_decides_and_stores_the_precision_once(language: str) -> None:
    small = run_launch_backtest(_launch_request("buy_and_hold", 10.0), language=language)
    performance = small.envelope.metrics["aggregate"]["performance"]
    ending = 10.0 + performance["profit"]
    assert small.result_card["currency_fraction_digits"] == 2
    assert _rows(small.result_card)["cash_value"] == (
        f"$10.00 -> {format_result_money(ending, fraction_digits=2)}"
    )
    assert re.fullmatch(
        r"\$10\.00 -> \$\d+\.\d{2}", _rows(small.result_card)["cash_value"]
    )

    large = run_launch_backtest(
        _launch_request("buy_and_hold", 10_000.0), language=language
    )
    assert large.result_card["currency_fraction_digits"] == 0
    assert re.fullmatch(r"\$10,000 -> \$[\d,]+", _rows(large.result_card)["cash_value"])

    # A card stored before the decision existed reads whole dollars.
    assert stored_currency_fraction_digits({}) == 0


def test_every_backend_reader_rounds_half_up() -> None:
    for value, digits, text in ((10.125, 2, "$10.13"), (12_048.5, 0, "$12,049")):
        assert format_result_money(value, fraction_digits=digits) == text
        shown = readout_display_value(
            {"value": value, "unit": "currency", "currency": "USD"},
            language="en",
            currency_fraction_digits=digits,
        )
        assert shown is not None
        assert shown["text"] == text


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_readout_reads_the_stored_precision_without_a_series(language: str) -> None:
    money = {"value": 12.05, "unit": "currency", "currency": "USD"}
    expected = "$" + format_decimal(
        Decimal("12.05"), format="#,##0.00", locale=language.replace("-", "_")
    )
    sheet = with_currency_fraction_digits(
        {
            "symbols": ["AAPL"],
            "benchmark_symbol": "SPY",
            "facts": {
                "portfolio.ending_equity": dict(money),
                "portfolio.peak_equity": dict(money),
            },
            "series": {},
        },
        2,
    )

    prompt_facts = readout_prompt_facts(sheet, language=language)
    assert prompt_facts["facts"]["portfolio.ending_equity"]["display"] == expected
    headline = headline_request_lines(headline_readout_facts(sheet), language=language)
    assert f"Ending portfolio value: {expected}" in headline


def test_conversation_sheets_carry_the_card_precision() -> None:
    launch = run_launch_backtest(_launch_request("buy_and_hold", 10.0))
    run = build_runtime_backtest_run(
        user_id="precision-owner",
        conversation_id="precision-conversation",
        result_card=launch.result_card,
        envelope=launch.envelope.model_dump(mode="python"),
        default_benchmark_func=lambda _asset_class, _symbols: "SPY",
        run_id=SOURCE_RUN_ID,
    )
    assert run is not None
    assert stored_currency_fraction_digits(run.conversation_result_card) == 2
    sheet = _run_sheet(
        {
            "result_card": run.conversation_result_card,
            "metrics": run.metrics,
            "config_snapshot": run.config_snapshot,
            "symbols": run.symbols,
            "benchmark_symbol": run.benchmark_symbol,
        }
    )
    assert stored_currency_fraction_digits(sheet) == 2


# ── Chat ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", LANGUAGES)
def test_chat_under_the_floor_is_offered_the_floor(
    unadjusted_dates: None, language: str
) -> None:
    contract = build_default_capability_contract()
    state = RunState.new(
        current_user_message="Buy and hold NFLX with $9.99 in 2024.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = _draft(UNDER_THE_FLOOR)

    confirmation = confirm_stage(state=state, contract=contract, language=language)

    assert confirmation.outcome == "needs_clarification"
    assert "confirmation_payload" not in confirmation.patch
    _assert_offered_the_floor(confirmation.patch)

    state.requested_field = confirmation.patch["requested_field"]
    state.missing_required_fields = confirmation.patch["missing_required_fields"]
    state.optional_parameter_status = confirmation.patch["optional_parameter_status"]
    clarification = clarify_stage(
        state=state,
        contract=contract,
        clarification_generator=lambda request: None,
        language=language,
    )
    typed = clarification.patch["clarification"]
    assert typed["reason_code"] == "unsupported_starting_capital"
    assert typed["payload"]["minimum"] == 10.0
    assert typed["options"][0]["replacement_values"] == {"capital_amount": 10.0}


def test_an_amount_over_the_ceiling_is_offered_the_ceiling(
    unadjusted_dates: None,
) -> None:
    state = RunState.new(
        current_user_message="Buy and hold NFLX", recent_thread_history=[]
    )
    state.candidate_strategy_draft = _draft(MAX_STARTING_CAPITAL + 1)

    confirmation = confirm_stage(
        state=state, contract=build_default_capability_contract()
    )

    constraint = confirmation.patch["optional_parameter_status"][
        "unsupported_constraints"
    ][0]
    assert constraint["simplification_options"][0] == {
        "label": "Use $100,000,000",
        "replacement_values": {"capital_amount": MAX_STARTING_CAPITAL},
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_chat_ten_dollars_mints_a_card_at_ten(
    unadjusted_dates: None, language: str
) -> None:
    state = RunState.new(
        current_user_message="Buy and hold NFLX with $10 in 2024.",
        recent_thread_history=[],
    )
    state.candidate_strategy_draft = _draft(10.0)

    result = confirm_stage(
        state=state, contract=build_default_capability_contract(), language=language
    )

    assert result.outcome == "await_approval"
    payload = result.stage_patch["confirmation_payload"]
    assert payload["launch_payload"]["capital_amount"] == 10.0
    card = runtime_confirmation_card(
        {"stage_outcome": "await_approval", "confirmation_payload": payload},
        confirmation_id=CONFIRMATION_ID,
        conversation_id="c1",
        language=language,
    )
    assert card is not None
    assert _rows(card)["starting_capital"] == "$10"


# ── A card edit turn ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_card_edit_turn_holds_the_floor(unadjusted_dates: None, language: str) -> None:
    for amount in (10.0, UNDER_THE_FLOOR):
        resolved = apply_edit_operations(
            [EditOperation(op="set", target="capital", number=amount)],
            current_asset_universe=["NFLX"],
        )
        assert not resolved.unsupported
        summary = _draft(10_000.0)
        field_provenance: dict[str, str] = {}
        apply_resolved_artifact_edit_to_strategy_summary(
            resolved,
            candidate=summary,
            field_provenance=field_provenance,
        )
        summary.extra_parameters["field_provenance"] = field_provenance
        state = RunState.new(
            current_user_message=f"change the capital to ${amount}",
            recent_thread_history=[],
        )
        state = state.model_copy(update={"candidate_strategy_draft": summary})

        result = confirm_stage(
            state=state, contract=build_default_capability_contract(), language=language
        )

        if amount == 10.0:
            assert result.outcome == "await_approval"
            launch = result.stage_patch["confirmation_payload"]["launch_payload"]
            assert launch["capital_amount"] == 10.0
        else:
            assert result.outcome == "needs_clarification"
            _assert_offered_the_floor(result.patch)


# ── In place and retest ──────────────────────────────────────────────────────


def _client() -> TestClient:
    client = TestClient(app)
    assert client.post("/api/v1/dev/reset").status_code == 200
    return client


def _conversation_id(client: TestClient, language: str) -> str:
    response = client.post("/api/v1/conversations", json={"language": language})
    return str(response.json()["conversation"]["id"])


def _user_id(client: TestClient) -> str:
    return str(client.get("/api/v1/me").json()["user"]["id"])


def _card_payload(capital: float) -> dict[str, Any]:
    window = {"start": "2023-01-02", "end": "2023-06-30"}
    strategy = {
        "strategy_type": "buy_and_hold",
        "asset_universe": ["NFLX"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": window,
        "sizing_mode": "capital_amount",
        "capital_amount": capital,
    }
    launch = {
        "strategy_type": "buy_and_hold",
        "symbol": "NFLX",
        "symbols": ["NFLX"],
        "asset_class": "equity",
        "timeframe": "1D",
        "date_range": window,
        "sizing_mode": "capital_amount",
        "capital_amount": capital,
        "parameters": {},
        "risk_rules": [],
        "benchmark_symbol": "SPY",
        "language": "en",
    }
    return {
        "confirmation_id": CONFIRMATION_ID,
        "artifact_id": CONFIRMATION_ID,
        "strategy": strategy,
        "optional_parameters": {},
        "launch_payload": launch,
        "validation": {"status": "ready_to_run", "executable": True},
    }


def _plant_card(
    client: TestClient, conversation_id: str, payload: dict[str, Any]
) -> None:
    card = runtime_confirmation_card(
        {"stage_outcome": "await_approval", "confirmation_payload": payload},
        confirmation_id=CONFIRMATION_ID,
        conversation_id=conversation_id,
        language="en",
    )
    assert card is not None
    create_message(
        user_id=_user_id(client),
        conversation_id=conversation_id,
        role="assistant",
        content=str(card.get("summary") or ""),
        metadata={
            "conversation_mode": "confirm",
            "confirmation_card": card,
            "confirmation_payload": payload,
        },
        settle_usage=None,
    )


def _direct_edit(
    client: TestClient, conversation_id: str, confirmation_id: str, body: dict[str, Any]
):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/confirmations/"
        f"{confirmation_id}/direct-edit",
        json=body,
    )


def _assert_in_place_edits_hold_the_floor(
    client: TestClient, conversation_id: str, confirmation_id: str
) -> None:
    refused = _direct_edit(
        client, conversation_id, confirmation_id, {"capital": UNDER_THE_FLOOR}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "invalid_starting_capital"

    accepted = _direct_edit(client, conversation_id, confirmation_id, {"capital": 10})
    assert accepted.status_code == 200, accepted.text
    metadata = accepted.json()["message"]["metadata"]
    assert metadata["confirmation_payload"]["launch_payload"]["capital_amount"] == 10
    card = metadata["confirmation_card"]
    assert _rows(card)["starting_capital"] == "$10"
    assert card["capabilities"]["edit_constraints"]["capital"] == {
        "min": MIN_STARTING_CAPITAL,
        "max": MAX_STARTING_CAPITAL,
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_an_in_place_capital_edit_holds_the_floor(
    in_place_edits: None, language: str
) -> None:
    client = _client()
    conversation_id = _conversation_id(client, language)
    _plant_card(client, conversation_id, _card_payload(10_000.0))

    _assert_in_place_edits_hold_the_floor(client, conversation_id, CONFIRMATION_ID)


def _stream_payloads(stream: str, event_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for part in stream.split("\n\n"):
        data_line = next(
            (line for line in part.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line is None:
            continue
        raw = data_line.removeprefix("data: ").strip()
        if raw == "[DONE]":
            continue
        event = json.loads(raw)
        if event.get("type") == event_type:
            payloads.append(event.get("payload", event))
    return payloads


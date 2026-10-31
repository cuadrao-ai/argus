"""Today is the New York date on every reader (#586).

A relative period, a default end date and the date the model reads derive from
one clock. Read from a UTC host after 20:00 ET, "today" was already the next
day. None of the instants below falls on the host's date, so a reader still on
the host clock fails here.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from argus.agent_runtime.artifact_edit_planner import _artifact_assumption_edit_messages
from argus.agent_runtime.capabilities.contract import build_default_capability_contract
from argus.agent_runtime.interpreter.executable_grounding import (
    _draft_uses_launch_default_window,
)
from argus.agent_runtime.interpreter.focused_extraction import (
    _focused_strategy_extraction_messages,
)
from argus.agent_runtime.interpreter.run_field_audits import (
    _date_endpoint_is_runtime_current,
    _stated_run_field_fidelity_messages,
)
from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter
from argus.agent_runtime.llm_interpreter_types import (
    LLMInterpretationResponse,
    LLMStrategyDraft,
)
from argus.agent_runtime.stages.interpret_types import InterpretationRequest
from argus.agent_runtime.state.models import UserState
from argus.agent_runtime.strategy_contract import (
    resolve_date_range,
    resolve_executable_date_range,
)
from argus.api.chat.confirmation import (
    _confirmation_date_range_payload,
    _edit_constraints,
)
from argus.domain.backtesting.date_window import validate_backtest_date_window
from argus.domain.clock import new_york_now, new_york_today
from argus.domain.engine import normalize_backtest_config
from argus.domain.research.source_selection import question_date
from argus.nlp.natural_time import resolve_date_range_intent, resolve_date_range_text

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src/argus"
OWNER = SOURCE_ROOT / "domain/clock.py"

INSTANTS = pytest.mark.parametrize(
    ("asked_at", "new_york_date"),
    [
        # 20:17 EDT on 2026-09-09.
        (datetime(2026, 9, 10, 0, 17, tzinfo=timezone.utc), date(2026, 9, 9)),
        # 20:17 EST on 2025-12-31, the evening a UTC host has already turned the year.
        (datetime(2026, 1, 1, 1, 17, tzinfo=timezone.utc), date(2025, 12, 31)),
        # Noon EDT.
        (datetime(2026, 3, 16, 16, 0, tzinfo=timezone.utc), date(2026, 3, 16)),
    ],
    ids=["daylight-evening", "standard-evening", "midday"],
)


@INSTANTS
def test_today_and_the_question_date_are_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    assert new_york_today() == new_york_date
    assert question_date() == new_york_date
    assert new_york_now() == asked_at


@INSTANTS
def test_today_ends_on_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    resolved = resolve_date_range({"start": "2025-06-02", "end": "today"})

    assert resolved.end == new_york_date


@INSTANTS
def test_this_week_ends_on_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    resolved = resolve_date_range_intent(
        {"kind": "rolling_window", "count": 1, "unit": "week", "confidence": 0.9}
    )

    assert resolved is not None
    assert resolved.payload == {
        "start": (new_york_date - timedelta(days=7)).isoformat(),
        "end": new_york_date.isoformat(),
    }


@INSTANTS
def test_the_last_30_days_end_on_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    resolved = resolve_date_range_text("the last 30 days")

    assert resolved is not None
    assert resolved.payload == {
        "start": (new_york_date - timedelta(days=30)).isoformat(),
        "end": new_york_date.isoformat(),
    }


@INSTANTS
def test_year_to_date_is_the_new_york_year(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    resolved = resolve_date_range("year_to_date")

    assert (resolved.start, resolved.end) == (
        date(new_york_date.year, 1, 1),
        new_york_date,
    )


@INSTANTS
def test_since_january_ends_on_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    resolved = resolve_date_range_intent(
        {"kind": "since", "year": new_york_date.year, "confidence": 0.9}
    )

    assert resolved is not None
    assert resolved.payload == {
        "start": date(new_york_date.year, 1, 1).isoformat(),
        "end": new_york_date.isoformat(),
    }


@INSTANTS
def test_the_default_window_ends_on_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)

    assert resolve_executable_date_range(None).end == new_york_date


@INSTANTS
def test_every_prompt_tells_the_model_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)
    today = new_york_date.isoformat()
    request = InterpretationRequest(
        current_user_message="Buy and hold AAPL from 2025-06-02 to today.",
        recent_thread_history=[],
        latest_task_snapshot=None,
        user=UserState(user_id="u-586"),
    )
    response = LLMInterpretationResponse(
        intent="strategy_drafting",
        task_relation="new_task",
        requires_clarification=False,
        user_goal_summary="Buy and hold AAPL.",
        candidate_strategy_draft=LLMStrategyDraft(
            strategy_type="buy_and_hold",
            asset_universe=["AAPL"],
            date_range={"start": "2025-06-02", "end": "today"},
        ),
    )

    system_prompt = OpenRouterStructuredInterpreter(
        contract=build_default_capability_contract()
    )._system_prompt()
    focused = _focused_strategy_extraction_messages(request)[0].content
    fidelity = _stated_run_field_fidelity_messages(response=response, request=request)
    planner = _artifact_assumption_edit_messages(
        current_user_message="End it today.",
        prior_strategy=None,
        active_confirmation=None,
    )

    assert f"The current runtime date is {today};" in system_prompt
    assert f"'today' or {today}, not a stale model date" in focused
    assert f"runtime date {today} only when" in fidelity[0]["content"]
    assert f"Today is {today}." in planner[0]["content"]


@INSTANTS
def test_the_date_the_model_was_told_reads_back_as_today(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)
    today = new_york_date.isoformat()

    assert _date_endpoint_is_runtime_current(today)
    assert _draft_uses_launch_default_window(
        LLMStrategyDraft(date_range={"start": "2016-01-01", "end": today})
    )


@INSTANTS
def test_an_end_after_the_new_york_date_is_in_the_future(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)
    start = new_york_date - timedelta(days=30)

    validate_backtest_date_window(start=start, end=new_york_date)
    with pytest.raises(ValueError, match="future_end_date"):
        validate_backtest_date_window(start=start, end=new_york_date + timedelta(days=1))


@INSTANTS
def test_the_card_and_the_engine_default_read_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    freeze_new_york_clock(asked_at)
    today = new_york_date.isoformat()

    card_period = _confirmation_date_range_payload(
        {"start": "2025-06-02", "end": "today"}, display="June 2, 2025 to today"
    )
    constraints = _edit_constraints({"asset_class": "equity"})
    config = normalize_backtest_config(
        {"template": "rsi_mean_reversion", "asset_class": "equity", "symbols": ["AAPL"]}
    )

    assert card_period is not None and card_period["end"] == today
    assert constraints["date_window"]["max_end"] == today
    assert config["end_date"] == (new_york_date - timedelta(days=1)).isoformat()


@INSTANTS
def test_market_data_windows_that_end_today_end_on_the_new_york_date(
    monkeypatch, freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    """A row's coverage probe, an off-coverage latest close and the
    tradable-history probe fetch through the day the user is on."""
    import asyncio

    import pandas as pd
    from argus.agent_runtime import research_grounded, research_rows
    from argus.domain import market_data
    from argus.domain.market_data import provider, tradability

    freeze_new_york_clock(asked_at)
    ends: list[date] = []

    def fetch(symbol, asset_class, start, end, timeframe):
        ends.append(end)
        return pd.Series([1.0, 2.0], index=pd.to_datetime([start, end]))

    monkeypatch.setattr(provider, "fetch_price_series", fetch)
    monkeypatch.setattr(
        market_data,
        "tradable_history",
        lambda symbol, asset_class: market_data.TradableHistory("tradable"),
    )

    research_rows._earliest_available("NVDA", "equity")
    asyncio.run(research_grounded._latest_close("NVDA", "equity"))
    tradability._probe("NVDA", "equity")

    assert ends == [new_york_date] * 3


@INSTANTS
def test_a_row_names_a_full_window_only_back_from_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    """"Over the last 3 years" is counted back from the day the test runs to."""
    from argus.agent_runtime import research_rows

    freeze_new_york_clock(asked_at)
    requested_start = new_york_date - timedelta(
        days=365 * research_rows.TEST_WINDOW_YEARS
    )

    def listed(days_after_requested_start: int) -> research_rows.RowWindow:
        listing = requested_start + timedelta(days=days_after_requested_start)
        return research_rows.row_window(
            [{"symbol": "NVDA", "asset_class": "equity"}],
            probe=lambda _symbol, _asset_class: listing,
        )

    slack = research_rows._COVERAGE_SLACK_DAYS
    assert listed(slack).is_full
    assert not listed(slack + 1).is_full


@INSTANTS
def test_a_movers_snapshot_is_dated_on_the_new_york_date(
    freeze_new_york_clock, asked_at: datetime, new_york_date: date
) -> None:
    from argus.context.providers import (
        build_alpaca_market_movers_packet,
        build_alpaca_most_actives_packet,
    )

    freeze_new_york_clock(asked_at)

    movers = build_alpaca_market_movers_packet(
        market_type="stocks", movers={"gainers": [], "losers": []}
    )
    actives = build_alpaca_most_actives_packet(by="volume", most_actives=[])

    assert movers.coverage_end == actives.coverage_end == new_york_date


def _clock_offense(node: ast.AST, path: Path) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    method, receiver = node.func.attr, node.func.value
    arguments = [*node.args, *node.keywords]
    if isinstance(receiver, ast.Name):
        if receiver.id in {"date", "datetime"} and method == "today":
            return True
        if receiver.id == "datetime" and method == "now" and not arguments:
            return True
        return (
            method == "now"
            and path != OWNER
            and any(
                isinstance(argument, ast.Name) and argument.id == "EASTERN"
                for argument in node.args
            )
        )
    if method == "date" and not arguments and isinstance(receiver, ast.Call):
        clock = receiver.func
        reads_now = (
            isinstance(clock, ast.Attribute) and clock.attr in {"now", "utcnow"}
        ) or (isinstance(clock, ast.Name) and clock.id == "utcnow")
        return reads_now and path != OWNER
    return False


def test_no_reader_dates_today_outside_the_one_clock() -> None:
    """A date derived from the current instant comes from the owner.
    `date.today()` and a zoneless `now()` read the host's calendar,
    `now(tz).date()` and `utcnow().date()` read another zone's, and
    `now(EASTERN)` outside the owner is a second clock."""
    offenders = [
        f"{path.relative_to(SOURCE_ROOT)}:{node.lineno}"
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if _clock_offense(node, path)
    ]

    assert offenders == []

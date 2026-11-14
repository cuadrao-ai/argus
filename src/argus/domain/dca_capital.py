"""The one owner of what money means in a recurring-contribution run.

A DCA run has exactly two money roles and they are peers, never each other's
default: ``starting_capital`` is the seed invested on day one, and
``contribution`` is the amount invested every period. Every layer that shows,
edits, validates, or executes a DCA plan reads a ``DcaCapitalPlan`` built here,
so no layer can decide for itself that one role may stand in for the other.

The engine config carries the plan under ``dca_capital`` and carries no
top-level ``starting_capital``, ``recurring_contribution``, or
``starting_principal`` for a DCA template, so a reader that reaches for the
wrong role raises instead of silently reading the other one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Any

from argus.domain.cadences import SUPPORTED_DCA_CADENCE_VALUES

MAX_STARTING_CAPITAL = 100_000_000.0

DCA_CAPITAL_SCHEMA_VERSION = "dca_capital_v1"

# The names each money role travels under between the interpreter's drafts,
# the audits that re-type them and the semantic reader that decides what the
# plan may do. A seed role is money put to work on day one; a ceiling role
# bounds the whole plan. One tuple each, so a writer and a reader can never
# disagree on which is which.
DCA_SEED_ROLES: tuple[str, ...] = (
    "initial_capital",
    "starting_capital",
    "starting_principal",
    "initial_lump_sum",
    "initial_lump",
    "lump_sum",
)
DCA_CEILING_ROLES: tuple[str, ...] = (
    "total_capital",
    "total_budget",
    "max_budget",
    "investment_budget",
    "cap",
    "contribution_cap",
    "capital_cap",
    "investment_cap",
)

DCA_CAPITAL_CONFIG_KEY = "dca_capital"

# Legacy engine configs stored the recurring contribution in the shared
# ``starting_capital`` slot and always wrote a zero ``starting_principal``.
LEGACY_DCA_CAPITAL_KEYS = ("starting_capital", "recurring_contribution")

CONTRIBUTION_PERIOD_VALUES: tuple[str, ...] = SUPPORTED_DCA_CADENCE_VALUES

# Whole-period lengths, in the unit each period is counted in. A period fits a
# window when one whole period ends on or before the window's last day.
_PERIOD_DAYS: dict[str, int] = {"daily": 1, "weekly": 7, "biweekly": 14}
_PERIOD_MONTHS: dict[str, int] = {"monthly": 1, "quarterly": 3}


class DcaCapitalError(ValueError):
    """A DCA plan the engine cannot run, named by its rule."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DcaCapitalPlan:
    """Both money roles plus the period they are spent on, declared together."""

    starting_capital: float
    contribution: float
    period: str

    @property
    def seeds_on_day_one(self) -> bool:
        return self.starting_capital > 0.0

    def total_invested(self, contribution_count: int) -> float:
        """Every dollar the plan puts to work over ``contribution_count`` buys."""
        return self.starting_capital + self.contribution * max(contribution_count, 0)

    def per_symbol(self, symbol_count: int) -> "DcaCapitalPlan":
        """Split both roles the same way, so equal weight cannot skew one role."""
        divisor = float(max(symbol_count, 1))
        return DcaCapitalPlan(
            starting_capital=self.starting_capital / divisor,
            contribution=self.contribution / divisor,
            period=self.period,
        )

    def money_payload(self) -> dict[str, Any]:
        """Only the money. The period stays in ``parameters.dca_cadence``."""
        return {
            "schema_version": DCA_CAPITAL_SCHEMA_VERSION,
            "starting_capital": self.starting_capital,
            "contribution": self.contribution,
        }


def build_dca_capital_plan(
    *,
    starting_capital: float | None,
    contribution: float | None,
    period: str | None,
) -> DcaCapitalPlan:
    """Build the plan or refuse by name. Absent starting capital means zero."""
    seed = _money_role(starting_capital, default=0.0, code="invalid_starting_capital")
    amount = _money_role(
        contribution,
        default=0.0,
        code="invalid_recurring_contribution",
    )
    if seed <= 0.0 and amount <= 0.0:
        raise DcaCapitalError("dca_requires_starting_capital_or_contribution")
    if amount <= 0.0:
        raise DcaCapitalError("dca_contribution_zero_is_buy_and_hold")
    resolved_period = supported_contribution_period(period)
    if resolved_period is None:
        raise DcaCapitalError("unsupported_dca_cadence")
    return DcaCapitalPlan(
        starting_capital=seed,
        contribution=amount,
        period=resolved_period,
    )


def _money_role(value: Any, *, default: float, code: str) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DcaCapitalError(code)
    amount = float(value)
    if not isfinite(amount) or amount < 0.0 or amount > MAX_STARTING_CAPITAL:
        raise DcaCapitalError(code)
    return amount


def supported_contribution_period(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in CONTRIBUTION_PERIOD_VALUES else None


def contribution_period_fits_window(
    period: str,
    *,
    start: date,
    end: date,
) -> bool:
    """One whole period must end on or before the window's last day."""
    resolved = supported_contribution_period(period)
    if resolved is None or end < start:
        return False
    if resolved in _PERIOD_DAYS:
        return start + timedelta(days=_PERIOD_DAYS[resolved] - 1) <= end
    return _add_months(start, _PERIOD_MONTHS[resolved]) - timedelta(days=1) <= end


def contribution_periods_for_window(
    *,
    start: date,
    end: date,
) -> tuple[str, ...]:
    """The periods a window can actually hold, in canonical order."""
    return tuple(
        period
        for period in CONTRIBUTION_PERIOD_VALUES
        if contribution_period_fits_window(period, start=start, end=end)
    )


def validate_contribution_period_fits_window(
    period: str,
    *,
    start: date,
    end: date,
) -> None:
    if not contribution_period_fits_window(period, start=start, end=end):
        raise DcaCapitalError("contribution_period_exceeds_window")


# Coverage's own reason for moving a window, as the only input to which window
# a contribution period has to fit. Only alignment is safe to measure the ask
# against, so it is the value named here rather than its complement.
CALENDAR_ALIGNMENT_REASON = "calendar_alignment"


def contribution_period_window(
    *,
    requested: tuple[date, date] | None,
    effective: tuple[date, date],
    adjustment_reason: Any = None,
) -> tuple[date, date]:
    """The window a contribution period must fit, given why coverage moved it.

    One owner, because the card advertises the periods it will accept and the
    request model refuses the ones it will not: if they picked this window
    separately, a card could offer a period the engine then rejects.

    Nudging a boundary to the nearest session leaves the user's month a month,
    so the ask is what counts. Truncating a year to three weeks because the
    asset is newly listed does not, so there the served window counts.
    """
    if requested is None or requested == effective:
        return effective
    # The ask counts only when coverage says the move was calendar alignment.
    # Everything else measures the served window: a truncation genuinely cannot
    # hold the period, a record written before the reason existed cannot say
    # which move it was, and a reason added later is unknown here. Defaulting
    # the other way would run a year-long plan against three weeks of data.
    if str(adjustment_reason or "") == CALENDAR_ALIGNMENT_REASON:
        return requested
    return effective


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def dca_capital_config_fields(plan: DcaCapitalPlan) -> dict[str, Any]:
    """The only DCA money keys an engine config may carry."""
    return {DCA_CAPITAL_CONFIG_KEY: plan.money_payload()}


def dca_contribution_period_from_config(config: dict[str, Any]) -> str:
    """The period, read from the one config slot that holds it."""
    parameters = config.get("parameters")
    raw = parameters.get("dca_cadence") if isinstance(parameters, dict) else None
    period = supported_contribution_period(raw)
    if period is None:
        raise DcaCapitalError("unsupported_dca_cadence")
    return period


def dca_capital_plan_from_config(config: dict[str, Any]) -> DcaCapitalPlan:
    """Read the declared plan from an engine config, or migrate a legacy one."""
    declared = config.get(DCA_CAPITAL_CONFIG_KEY)
    if isinstance(declared, dict):
        return build_dca_capital_plan(
            starting_capital=declared.get("starting_capital"),
            contribution=declared.get("contribution"),
            period=dca_contribution_period_from_config(config),
        )
    return _legacy_dca_capital_plan(config)


def _legacy_dca_capital_plan(config: dict[str, Any]) -> DcaCapitalPlan:
    """Configs written before the plan existed spent every dollar per period.

    Their ``starting_capital`` was the contribution and their seed was always
    zero, so the migration is one fixed reading, not a choice between fields.
    """
    contribution: Any = None
    for key in LEGACY_DCA_CAPITAL_KEYS:
        if key in config:
            contribution = config[key]
            break
    return build_dca_capital_plan(
        starting_capital=0.0,
        contribution=contribution,
        period=dca_contribution_period_from_config(config),
    )

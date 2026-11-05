from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any, cast

from argus.api.artifact_presentation import without_private_prose
from argus.api.schemas import (
    DecisionActionAvailability,
    DecisionState,
    RunDossier,
    RunDossierTested,
    SearchDecisionAction,
    SearchDossierDecision,
    SearchDossierMetric,
    SearchDossierOutcome,
    SearchRetestAction,
    SearchRetestRepair,
)
from argus.domain.clock import new_york_today
from argus.domain.display_figure import display_figure
from argus.domain.evidence import result_metrics_summary
from argus.domain.result_readout_facts import with_result_readout_facts
from argus.domain.retest_setup import (
    has_finalized_evidence_identity,
    retest_setup_from_run,
)

_DECISION_STATES: tuple[DecisionState, ...] = (
    "promising",
    "watching",
    "rejected",
    "revisit_later",
)
_MAX_METRICS = 4
_MAX_LABEL_LENGTH = 160
_RUN_FRESH_STRATEGIES = {
    "buy_and_hold",
    "dca_accumulation",
    "indicator_threshold",
    "signal_strategy",
}
_RUN_FRESH_CADENCES = {
    "daily",
    "weekly",
    "biweekly",
    "monthly",
    "quarterly",
}
_RUN_FRESH_PARAMETER_KEYS = (
    "indicator",
    "indicator_period",
    "entry_threshold",
    "exit_threshold",
    "fast_period",
    "slow_period",
    "moving_average_type",
)


def project_run_dossier(
    *,
    run: Mapping[str, Any],
    artifact: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    result_message_id: str | None,
    decision_action_availability: DecisionActionAvailability | None,
) -> RunDossier:
    """Project one run and its artifact into the bounded public dossier shape."""
    run_id = text(run.get("id"))
    artifact_id = text(artifact.get("id"))
    if run_id is None or text(artifact.get("source_run_id")) != run_id:
        raise ValueError("Run dossier requires one matching evidence-backed run.")
    if artifact_id is None:
        raise ValueError("Run dossier evidence artifact requires an id.")

    run_label = run_label_for(run)
    metric_rows: list[SearchDossierMetric] = []
    metrics = result_metrics_summary(run.get("metrics"))
    if isinstance(metrics, dict):
        for name, value in metrics.items():
            if len(metric_rows) >= _MAX_METRICS:
                break
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                if name.endswith("_pct") and not isinstance(value, str):
                    # The grid prints these beside the Quick Take; one rounding.
                    value = display_figure(value)
                metric_rows.append(SearchDossierMetric(name=name, value=value))

    current_decision = (
        decision
        if decision is not None
        and text(decision.get("evidence_artifact_id")) == artifact_id
        else None
    )
    decision_state = (
        current_decision.get("decision_state") if current_decision is not None else None
    )
    decision_projection = (
        SearchDossierDecision(
            state=cast(DecisionState, decision_state),
            note=_bounded_note(current_decision.get("note"), 2000),
            run_label=run_label,
        )
        if decision_state in _DECISION_STATES
        else None
    )

    actions = []
    # The run-fresh transport remains the already-shipped typed action until the
    # separate typed-retest lane replaces it.
    retest_action = project_retest_action(run=run)
    if retest_action is not None:
        actions.append(retest_action)
    if decision_action_availability is not None:
        actions.append(
            SearchDecisionAction(
                availability=decision_action_availability,
                evidence_artifact_id=artifact_id,
                decision_state=(
                    cast(DecisionState, decision_state)
                    if decision_state in _DECISION_STATES
                    else None
                ),
                note=(
                    _bounded_note(current_decision.get("note"), 2000)
                    if current_decision is not None
                    else None
                ),
                run_label=run_label,
            )
        )

    readout_bank = with_result_readout_facts(
        without_private_prose(
            {
                key: run.get(key)
                for key in (
                    "symbols",
                    "metrics",
                    "config_snapshot",
                    "benchmark_symbol",
                    "conversation_result_card",
                )
            }
        )
    )
    config = mapping(readout_bank.get("config_snapshot"))
    resolved_parameters = mapping(config.get("resolved_parameters"))
    start_date, end_date = run_date_span(run)
    return RunDossier(
        run_id=run_id,
        run_label=run_label,
        completed_at=row_activity(run),
        result_message_id=text(result_message_id),
        tested=RunDossierTested(
            symbols=run_symbols(run),
            strategy_family=_bounded_text(strategy_family_for(run), 80),
            cadence=_bounded_text(
                resolved_parameters.get("cadence") or config.get("cadence"),
                24,
            ),
            timeframe=_bounded_text(
                resolved_parameters.get("timeframe") or config.get("timeframe"),
                24,
            ),
            start_date=start_date,
            end_date=end_date,
        ),
        outcome=SearchDossierOutcome(
            run_label=run_label,
            completed_at=row_activity(run),
            benchmark_symbol=_bounded_text(
                run.get("benchmark_symbol"),
                24,
            ),
            result_fact_bank=readout_bank,
            metrics=metric_rows,
        ),
        decision=decision_projection,
        actions=actions,
    )


def newest_evidence_backed_completed_runs(
    *,
    runs: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """Return newest-first completed runs with one current evidence artifact."""
    latest_artifact_by_run: dict[str, Mapping[str, Any]] = {}
    for artifact in evidence:
        run_id = text(artifact.get("source_run_id"))
        artifact_id = text(artifact.get("id"))
        if run_id is None or artifact_id is None:
            continue
        current = latest_artifact_by_run.get(run_id)
        if current is None or (
            row_activity(artifact),
            artifact_id,
        ) > (
            row_activity(current),
            text(current.get("id")) or "",
        ):
            latest_artifact_by_run[run_id] = artifact

    eligible = [
        (run, latest_artifact_by_run[run_id])
        for run in runs
        if run.get("status", "completed") == "completed"
        and (run_id := text(run.get("id"))) is not None
        and run_id in latest_artifact_by_run
    ]
    return sorted(
        eligible,
        key=lambda pair: (row_activity(pair[0]), text(pair[0].get("id")) or ""),
        reverse=True,
    )


def current_decision_for(
    artifact: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    artifact_id = text(artifact.get("id"))
    return max(
        (
            decision
            for decision in decisions
            if text(decision.get("evidence_artifact_id")) == artifact_id
        ),
        key=lambda row: (row_activity(row), text(row.get("id")) or ""),
        default=None,
    )


def result_message_id_for(
    run: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
) -> str | None:
    run_id = text(run.get("id"))
    candidates = [
        message
        for message in messages
        if message.get("role") == "assistant"
        and (
            text(message_metadata(message).get("result_run_id")) == run_id
            or text(message_metadata(message).get("latest_run_id")) == run_id
        )
        and text(message.get("id")) is not None
    ]
    latest = max(
        candidates,
        key=lambda row: (
            isinstance(message_metadata(row).get("result_card"), Mapping)
            and bool(message_metadata(row).get("result_card")),
            row_activity(row),
            text(row.get("id")) or "",
        ),
        default=None,
    )
    return text(latest.get("id")) if latest is not None else None


def project_retest_action(
    *,
    run: Mapping[str, Any],
    today: date | None = None,
) -> SearchRetestAction | None:
    """Offer a retest only when the backend can faithfully reconstruct the run.

    Eligibility and admission share `retest_confirmation_payload`, so an
    offered action is always one the confirmation path can materialize -
    including under the execution-realism kill switch, which idealizes costs a
    costed source run recorded.
    """
    # Imported lazily: `domain` does not otherwise depend on `agent_runtime`,
    # and eligibility must not fork from the materializer it mirrors.
    from argus.agent_runtime.retest_confirmation import (
        retest_confirmation_payload,
    )
    from argus.domain.retest_setup import (
        repaired_retest_setup,
        retest_dossier_availability,
    )

    if not has_finalized_evidence_identity(run.get("conversation_result_card")):
        # Admission rejects an unfinalized run/evidence tuple, so offering it
        # here would advertise a button that can only fail.
        return None
    setup = retest_setup_from_run(run, today=today or new_york_today())
    if setup is None:
        return None
    availability = retest_dossier_availability(setup)
    eligible_setup = repaired_retest_setup(setup, availability)
    if retest_confirmation_payload(eligible_setup) is None:
        return None
    return SearchRetestAction(
        source_run_id=setup.source_run_id,
        run_label=run_label_for(run),
        state=availability.state,
        reason_code=availability.reason_code,
        repair=(
            SearchRetestRepair(
                kind=availability.repair.kind,
                start_date=availability.repair.start_date,
                end_date=availability.repair.end_date,
            )
            if availability.repair is not None
            else None
        ),
    )


def run_label_for(run: Mapping[str, Any]) -> str:
    card = run.get("conversation_result_card")
    if isinstance(card, Mapping):
        label = _bounded_text(card.get("title"), _MAX_LABEL_LENGTH)
        if label:
            return label
    symbols = ", ".join(run_symbols(run))
    return _bounded_text(f"{symbols} Backtest", _MAX_LABEL_LENGTH) or "Backtest run"


def strategy_family_for(run: Mapping[str, Any]) -> str | None:
    card = run.get("conversation_result_card")
    return text(mapping(run.get("config_snapshot")).get("template")) or (
        text(card.get("strategy_label")) if isinstance(card, Mapping) else None
    )


def run_symbols(run: Mapping[str, Any]) -> list[str]:
    symbols = text_list(run.get("symbols"))
    if symbols:
        return symbols
    card = run.get("conversation_result_card")
    return text_list(card.get("symbols")) if isinstance(card, Mapping) else []


def run_date_span(run: Mapping[str, Any]) -> tuple[date | None, date | None]:
    config = mapping(run.get("config_snapshot"))
    config_date_range = mapping(config.get("date_range"))
    card = run.get("conversation_result_card")
    card_date_range = mapping(card.get("date_range")) if isinstance(card, Mapping) else {}
    return (
        date_value(
            config.get("start_date")
            or config_date_range.get("start")
            or card_date_range.get("start")
        ),
        date_value(
            config.get("end_date")
            or config_date_range.get("end")
            or card_date_range.get("end")
        ),
    )


def row_activity(row: Mapping[str, Any]) -> datetime:
    for key in ("completed_at", "updated_at", "created_at"):
        value = row.get(key)
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is not None:
                return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        bounded for item in value[:5] if (bounded := _bounded_text(item, 40)) is not None
    ]


def date_value(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def message_metadata(message: Mapping[str, Any]) -> Mapping[str, Any]:
    return mapping(message.get("metadata"))


def _bounded_text(value: object, maximum: int) -> str | None:
    value_text = text(value)
    return value_text[:maximum] if value_text is not None else None


def _bounded_note(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:maximum]


def _mapping_or_none(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _consistent_mapping(*values: object) -> tuple[bool, dict[str, Any] | None]:
    present = [value for value in values if value is not None]
    if not present:
        return True, None
    if any(not isinstance(value, Mapping) for value in present):
        return False, None
    mappings = [dict(cast(Mapping[str, Any], value)) for value in present]
    if any(value != mappings[0] for value in mappings[1:]):
        return False, None
    return True, mappings[0]


def _consistent_number(
    *values: object,
    allow_zero: bool = False,
) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    parsed = [
        _nonnegative_number(value) if allow_zero else _positive_number(value)
        for value in present
    ]
    if any(value is None for value in parsed):
        return None
    numbers = cast(list[float], parsed)
    if any(value != numbers[0] for value in numbers[1:]):
        return None
    return numbers[0]


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 else None


def _format_number(value: float | None) -> str:
    if value is None:
        return "0"
    return f"{value:g}"


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

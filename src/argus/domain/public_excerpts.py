"""Build and audit the frozen payload behind a public evidence receipt.

The pipeline is ``EvidenceArtifact -> PublicExcerptSnapshot -> PublicExcerptView``.
Only this module turns private records into a public payload, and it fails closed:
if the audit in :func:`audit_public_excerpt_payload` finds anything on the
never-expose list the receipt is never created.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import date
from typing import Any, get_args

from argus.api.public_excerpt_schemas import (
    PUBLIC_EXCERPT_OWNER_NOTE_MAX_LENGTH,
    MetricKey,
    PublicExcerptAssumption,
    PublicExcerptDateRange,
    PublicExcerptListItem,
    PublicExcerptMetric,
    PublicExcerptPayload,
    PublicExcerptSnapshot,
    PublicExcerptStrategyFact,
    PublicExcerptView,
    PublicExcerptVisual,
    PublicExcerptVisualPoint,
)
from argus.api.schemas import EvidenceArtifact

# The projection borrows the engine's own substitution rather than restating it. When
# an exit rule is absent the compiler mirrors the entry by flipping its direction, and
# a second opinion about what "mirrored" means is how a receipt ends up describing an
# exit that never ran.
from argus.domain.crossover_mirror import (
    mirrored_moving_average_crossover_rule as engine_mirrored_exit_rule,
)
from argus.domain.result_figures import shown_benchmark_gap
from argus.domain.result_readout_facts import (
    engine_config_from_snapshot as _engine_config,
)

PUBLIC_EXCERPT_ID_BYTES = 24
PUBLIC_EXCERPT_PATH_PREFIX = "/r/"
MAX_VISUAL_POINTS = 500
# A recurring run with modeled costs states the most: three plan facts, the
# fractional-share model, two structural facts, two cost facts, and the benchmark.
MAX_ASSUMPTIONS = 9
MAX_METRICS = 8
MAX_SYMBOLS = 5
MAX_TEXT_LENGTH = 240

CROSSOVER_WINDOW_KEYS = ("fast_indicator", "fast_period", "slow_indicator", "slow_period")

# Every field _moving_average_crossover_condition reads out of a rule, which is the
# whole of what the engine consumes. Completeness is judged over this set and not over
# a chosen part of it: judging by the window fields alone is exactly how the
# independently configured exit direction went unnoticed once the windows were fixed.
CROSSOVER_RULE_FIELDS = ("type", *CROSSOVER_WINDOW_KEYS, "direction")

# Owner-facing. A receipt exists to be a truthful frozen record, so a strategy this
# module cannot describe completely is refused rather than published partially.
_UNDESCRIBABLE_STRATEGY = (
    "Argus cannot describe this strategy on a shared page yet, so this result "
    "cannot be shared."
)

# Same rule, applied to what the run assumed. Understating a cost the run modeled is
# a lie about the numbers beside it, so an assumption that will not project refuses
# rather than falling back to the sentence the run happened to freeze.
_UNDESCRIBABLE_ASSUMPTIONS = (
    "Argus cannot describe what this run assumed on a shared page, so this result "
    "cannot be shared."
)

# Same rule again, for the result numbers.
_UNDESCRIBABLE_METRICS = (
    "Argus cannot describe this result's numbers on a shared page, so this result "
    "cannot be shared."
)

# The one card row whose value is a sentence rather than a number. It is skipped by
# name, and the comparison it renders is carried typed from the run's own metrics
# instead, so this is a redirection rather than a loss.
PROSE_METRIC_KEYS = frozenset({"benchmark_delta"})

BENCHMARK_METRIC_KEYS = frozenset({"benchmark_return_pct", "delta_vs_benchmark_pct"})

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# §3 of the sharing spec, from decision memo §15.7. Absolute.
NEVER_EXPOSE_KEY_MARKERS = (
    "conversation_id",
    "conversation_ids",
    "message_id",
    "run_id",
    "job_id",
    "artifact_id",
    "idea_id",
    "version_id",
    "strategy_id",
    "decision_id",
    "user_id",
    "owner_id",
    "visitor",
    "route_receipt",
    "receipts",
    "provider",
    "model",
    "retry",
    "transcript",
    "broker",
    "account",
    "memory",
    "token",
    "latency",
    "cost_usd",
)

NEVER_EXPOSE_VALUE_MARKERS = (
    "openrouter",
    "alpaca",
    "perplexity",
    "supabase",
    "langgraph",
    "route_receipt",
    "system_prompt",
    "bearer ",
    "sk-",
)

_WHITESPACE_RE = re.compile(r"\s+")
# Two never-expose markers carry a separator, and fields on the way into the payload
# rewrite separators: a strategy fact turns underscores into spaces. Folding both the
# value and the marker to one separator means the marker is matched on what the field
# means rather than on how it happened to be punctuated.
_SEPARATOR_RE = re.compile(r"[ _]+")
_CONTROL_CHARS = {"Cc", "Cf", "Cs", "Co", "Cn"}


class PublicExcerptSanitizationError(ValueError):
    """The payload could not be proven safe to publish, so nothing is published."""


class PublicExcerptOwnerNoteError(ValueError):
    """The owner note is not publishable as written."""


class PublicExcerptSourceError(ValueError):
    """The selected source cannot back a receipt, with owner-readable typed context."""

    def __init__(
        self, message: str, *, reason: str = "unsupported_turn", field: str | None = None
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.field = field


class PublicExcerptUnreadableError(RuntimeError):
    """A stored receipt cannot be read by this build.

    Separate from every other failure on this surface because it is temporary and
    about Argus rather than about the receipt: the row is intact, the reader is
    behind it. The viewer is told to try again, never that their link is dead.
    """


def new_public_excerpt_id() -> str:
    """An unguessable url token. 24 bytes of urlsafe entropy, no owner signal."""
    return secrets.token_urlsafe(PUBLIC_EXCERPT_ID_BYTES)


def public_excerpt_path(public_id: str) -> str:
    return f"{PUBLIC_EXCERPT_PATH_PREFIX}{public_id}"


def payload_digest(payload: PublicExcerptPayload) -> str:
    """Stable digest of the frozen payload. Any drift changes this string."""
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_owner_note(note: object) -> str | None:
    """Normalize the bounded owner note before the owner sees the exact preview."""
    if note is None:
        return None
    if not isinstance(note, str):
        raise PublicExcerptOwnerNoteError("The note must be text.")
    # Control characters become spaces rather than vanishing, so removing a
    # newline cannot silently join two words into one.
    cleaned = "".join(
        " " if unicodedata.category(character) in _CONTROL_CHARS else character
        for character in note
    )
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return None
    if len(cleaned) > PUBLIC_EXCERPT_OWNER_NOTE_MAX_LENGTH:
        raise PublicExcerptOwnerNoteError("The note is too long to publish.")
    return cleaned


def build_public_excerpt_payload(
    *,
    artifact: EvidenceArtifact,
    run_chart: dict[str, Any] | None,
    run_config_snapshot: dict[str, Any] | None = None,
    owner_note: str | None,
    content_language: str,
) -> PublicExcerptPayload:
    """Assemble the closed payload from frozen records, then audit it."""
    if artifact.artifact_type != "backtest":
        raise PublicExcerptSourceError("Only completed backtest results are shareable.")
    source = artifact.payload if isinstance(artifact.payload, dict) else {}
    result_card = _mapping(source.get("result_card"))
    provenance = _mapping(source.get("provenance"))
    date_range = _date_range(result_card.get("date_range"))
    if date_range is None:
        raise PublicExcerptSourceError("The result has no tested date range.")
    benchmark_symbol = _text(provenance.get("benchmark_symbol"))
    payload = PublicExcerptPayload(
        idea_title=_text(artifact.title) or _text(result_card.get("title")) or "Backtest",
        asset_class=_asset_class(
            provenance.get("asset_class") or result_card.get("asset_class")
        ),
        symbols=_symbols(provenance.get("symbols") or result_card.get("symbols")),
        strategy_facts=_strategy_facts(run_config_snapshot),
        assumptions=_assumptions(
            run_config_snapshot,
            benchmark_symbol=benchmark_symbol,
        ),
        date_range=date_range,
        metrics=_metrics(
            result_card.get("rows"),
            performance=_aggregate_performance(source),
            benchmark_symbol=benchmark_symbol,
        ),
        benchmark_symbol=benchmark_symbol,
        visual=_visual(run_chart),
        owner_note=owner_note,
        content_language="es-419" if content_language == "es-419" else "en",
    )
    audit_public_excerpt_payload(
        payload,
        private_ids=_private_ids(artifact),
        skip_value_markers_for=("owner_note",),
    )
    return payload


def audit_public_excerpt_payload(
    payload: PublicExcerptPayload,
    *,
    private_ids: tuple[str, ...] = (),
    skip_value_markers_for: tuple[str, ...] = (),
) -> None:
    """Adversarial gate over the serialized payload.

    Checks the shape (no key outside the closed set), the keys (nothing named
    after a private record) and the values (no identifier, no provider or model
    metadata, no known private id).
    """
    serialized = payload.model_dump(mode="json")
    expected_keys = set(PublicExcerptPayload.model_fields)
    if set(serialized) != expected_keys:
        unexpected = sorted(set(serialized) - expected_keys)
        missing = sorted(expected_keys - set(serialized))
        raise PublicExcerptSanitizationError(
            f"Receipt payload shape drifted. Unexpected: {unexpected}. "
            f"Missing: {missing}."
        )
    audit_public_excerpt_document(
        serialized,
        private_ids=private_ids,
        skip_value_markers_for=skip_value_markers_for,
    )


def audit_public_excerpt_document(
    document: dict[str, Any],
    *,
    private_ids: tuple[str, ...] = (),
    skip_value_markers_for: tuple[str, ...] = (),
    check_value_markers: bool = True,
) -> None:
    """Audit an arbitrary would-be public document, keys and values alike.

    Separate from the typed gate so the never-expose rules can be attacked with
    shapes the schema would refuse to build, which is how a leak would actually
    arrive: through a field someone added later.
    """
    lowered_private_ids = tuple(
        value.lower() for value in private_ids if isinstance(value, str) and value
    )
    _audit_node(
        document,
        path=(),
        private_ids=lowered_private_ids,
        skip_value_markers_for=skip_value_markers_for,
        check_value_markers=check_value_markers,
    )


def _public_turn_symbols(turn: Any) -> list[str]:
    """The asset identities a turn publishes; a calculation publishes none."""
    if turn.kind == "research_answer":
        return list(turn.anchor_symbols)
    if turn.kind == "backtest":
        return list(turn.fact_bank.symbols)
    return []


def snapshot_list_item(snapshot: PublicExcerptSnapshot) -> PublicExcerptListItem:
    """Owner-facing row. Carries no source id, only what the owner needs to act."""
    from argus.domain.public_excerpt_kinds import document_kind

    payload = snapshot.payload
    if payload.schema_version == 1:
        title, symbols, dates = payload.idea_title, payload.symbols, payload.date_range
    else:
        title = snapshot.title
        symbols = list(
            dict.fromkeys(
                symbol for turn in payload.turns for symbol in _public_turn_symbols(turn)
            )
        )
        dates = None
        if len(payload.turns) == 1 and payload.turns[0].kind == "backtest":
            config = payload.turns[0].fact_bank.config_snapshot
            if config.date_range:
                dates = PublicExcerptDateRange(
                    start=config.date_range.start, end=config.date_range.end
                )
            elif config.start_date and config.end_date:
                dates = PublicExcerptDateRange(
                    start=config.start_date, end=config.end_date
                )
    return PublicExcerptListItem(
        id=snapshot.id,
        public_id=snapshot.public_id,
        path=public_excerpt_path(snapshot.public_id),
        title=title,
        symbols=symbols,
        date_range=dates,
        kind=document_kind(payload),
        created_at=snapshot.created_at,
        revoked_at=snapshot.revoked_at,
        revocation_reason=snapshot.revocation_reason,
    )


def snapshot_public_view(snapshot: PublicExcerptSnapshot) -> PublicExcerptView:
    """Projection for an unauthenticated viewer. Revoked receipts keep nothing."""
    if snapshot.revoked_at is not None:
        return PublicExcerptView(public_id=snapshot.public_id, status="revoked")
    from argus.domain.public_excerpt_kinds import document_kind

    return PublicExcerptView(
        public_id=snapshot.public_id,
        status="available",
        kind=document_kind(snapshot.payload),
        created_at=snapshot.created_at,
        payload=snapshot.payload,
    )


def revoked_public_view(public_id: str) -> PublicExcerptView:
    """The tombstone. Unknown and revoked ids are indistinguishable to a viewer."""
    return PublicExcerptView(public_id=public_id, status="revoked")


def _audit_node(
    node: Any,
    *,
    path: tuple[str, ...],
    private_ids: tuple[str, ...],
    skip_value_markers_for: tuple[str, ...],
    check_value_markers: bool,
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _audit_key(str(key), path=path)
            _audit_node(
                value,
                path=(*path, str(key)),
                private_ids=private_ids,
                skip_value_markers_for=skip_value_markers_for,
                check_value_markers=check_value_markers,
            )
        return
    if isinstance(node, list):
        for value in node:
            _audit_node(
                value,
                path=path,
                private_ids=private_ids,
                skip_value_markers_for=skip_value_markers_for,
                check_value_markers=check_value_markers,
            )
        return
    if isinstance(node, str):
        _audit_value(
            node,
            path=path,
            private_ids=private_ids,
            skip_value_markers_for=skip_value_markers_for,
            check_value_markers=check_value_markers,
        )


def _audit_key(key: str, *, path: tuple[str, ...]) -> None:
    lowered = key.lower()
    for marker in NEVER_EXPOSE_KEY_MARKERS:
        if marker in lowered:
            location = ".".join((*path, key)) or key
            raise PublicExcerptSanitizationError(
                f"Receipt payload field '{location}' names never-expose data."
            )


def _audit_value(
    value: str,
    *,
    path: tuple[str, ...],
    private_ids: tuple[str, ...],
    skip_value_markers_for: tuple[str, ...],
    check_value_markers: bool,
) -> None:
    location = ".".join(path) or "payload"
    lowered = value.lower()
    for private_id in private_ids:
        if private_id and private_id in lowered:
            raise PublicExcerptSanitizationError(
                f"Receipt payload field '{location}' carries a private id."
            )
    if not check_value_markers or (path and path[-1] in skip_value_markers_for):
        return
    folded = _SEPARATOR_RE.sub("_", lowered)
    for marker in NEVER_EXPOSE_VALUE_MARKERS:
        if marker in lowered or _SEPARATOR_RE.sub("_", marker) in folded:
            raise PublicExcerptSanitizationError(
                f"Receipt payload field '{location}' carries provider metadata."
            )


def _private_ids(artifact: EvidenceArtifact) -> tuple[str, ...]:
    source = artifact.payload if isinstance(artifact.payload, dict) else {}
    nested = _mapping(source.get("source"))
    candidates = (
        artifact.id,
        artifact.idea_id,
        artifact.idea_version_id,
        artifact.source_conversation_id,
        artifact.source_run_id,
        nested.get("run_id"),
        nested.get("conversation_id"),
        nested.get("strategy_id"),
    )
    return tuple(value for value in candidates if isinstance(value, str) and value)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _WHITESPACE_RE.sub(" ", value).strip()
    if not normalized:
        return None
    return normalized[:MAX_TEXT_LENGTH]


def _text_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for entry in value:
        normalized = _text(entry)
        if normalized is not None:
            items.append(normalized)
        if len(items) >= limit:
            break
    return items


def _symbols(value: object) -> list[str]:
    return [symbol.upper() for symbol in _text_list(value, limit=MAX_SYMBOLS)]


def _asset_class(value: object) -> str | None:
    return value if value in {"equity", "crypto", "currency_pair"} else None


def _date_range(value: object) -> PublicExcerptDateRange | None:
    """The tested window as two calendar dates, or nothing.

    The run also freezes a rendered ``display`` string, and it is deliberately not
    read: it is written in the author's language, which says nothing about who opens
    the link. Two ISO dates are the same fact in a form the page can speak.
    """
    mapping = _mapping(value)
    start = _iso_date(mapping.get("start"))
    end = _iso_date(mapping.get("end"))
    if start is None or end is None:
        return None
    return PublicExcerptDateRange(start=start, end=end)


def _iso_date(value: object) -> str | None:
    """A real calendar date in ISO form, or nothing. The viewer's page parses this."""
    text = _text(value)
    if text is None or _ISO_DATE_RE.match(text) is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _metrics(
    rows: object,
    *,
    performance: dict[str, Any],
    benchmark_symbol: str | None,
) -> list[PublicExcerptMetric]:
    """The result numbers, under keys the page labels in the viewer's language.

    The row's own label is not read. It is written in the author's language, and a
    frozen "Peor caída" is unreadable to half the people a link reaches.

    A key this projection does not know is refused, not dropped. Dropping is how the
    benchmark comparison disappeared from every real receipt while the page went on
    naming a benchmark: a silent skip turns a generator that grew a row into a
    receipt that quietly says less than the run did.
    """
    known = set(get_args(MetricKey))
    metrics: list[PublicExcerptMetric] = []
    for entry in rows if isinstance(rows, list) else []:
        row = _mapping(entry)
        key = _text(row.get("key"))
        if key in PROSE_METRIC_KEYS:
            continue
        display = _text(row.get("value"))
        if key not in known or display is None:
            raise PublicExcerptSourceError(_UNDESCRIBABLE_METRICS)
        metrics.append(PublicExcerptMetric(key=key, value=display))
    metrics.extend(_benchmark_metrics(performance))
    if benchmark_symbol is not None and not any(
        metric.key in BENCHMARK_METRIC_KEYS for metric in metrics
    ):
        # The payload would name a benchmark and then carry no number for it, which
        # is the defect this projection exists to prevent rather than to commit.
        raise PublicExcerptSourceError(_UNDESCRIBABLE_METRICS)
    if len(metrics) > MAX_METRICS:
        raise PublicExcerptSourceError(_UNDESCRIBABLE_METRICS)
    return metrics


def _benchmark_metrics(performance: dict[str, Any]) -> list[PublicExcerptMetric]:
    """The comparison, read from the run's own metrics rather than from the card.

    The card renders this one as a sentence, in English in both languages (see the
    issue filed against ``benchmark_comparison_from_delta``), so the numbers behind
    it are taken from where the engine put them. Both are frozen: the benchmark's
    return so the page can show what it did, and the gap ``shown_benchmark_gap``
    states, the difference of the two returns as shown, so the frozen comparison
    matches the figures beside it.
    """
    metrics: list[PublicExcerptMetric] = []
    benchmark_return = _amount(performance.get("benchmark_return_pct"))
    if benchmark_return is not None:
        metrics.append(
            PublicExcerptMetric(
                key="benchmark_return_pct",
                value=f"{benchmark_return:+.1f}%",
            )
        )
    delta = shown_benchmark_gap(
        _amount(performance.get("total_return_pct")),
        benchmark_return,
        _amount(performance.get("delta_vs_benchmark_pct")),
    )
    if delta is not None:
        # Bare, because its unit is percentage points and that unit is a word.
        metrics.append(
            PublicExcerptMetric(key="delta_vs_benchmark_pct", value=_number(delta))
        )
    return metrics


def _aggregate_performance(artifact_payload: dict[str, Any]) -> dict[str, Any]:
    """Where the engine's own numbers live on the artifact."""
    aggregate = _mapping(_mapping(artifact_payload.get("metrics")).get("aggregate"))
    return _mapping(aggregate.get("performance"))


def _assumptions(
    config_snapshot: object,
    *,
    benchmark_symbol: str | None,
) -> list[PublicExcerptAssumption]:
    """Freeze what the run assumed, as keys and scalars rather than as prose.

    The run writes these as prose into its result card, correctly translated into the
    language the author was working in. That is the wrong shape for a public link:
    the author's language is not the viewer's, and no generator can know who will
    open it. So the same facts are read from the frozen run config here, and the
    lines are composed at view time, in the register the surface reads in.

    Long only and equal weight are stated unconditionally because they are true of
    every Argus run by construction, not because the card happened to mention them.
    """
    engine = _engine_config(config_snapshot)
    assumptions: list[PublicExcerptAssumption] = []
    if _is_recurring_contribution_run(config_snapshot, engine):
        assumptions.extend(_contribution_assumptions(engine))
    assumptions.append(PublicExcerptAssumption(key="long_only"))
    assumptions.append(PublicExcerptAssumption(key="equal_weight"))

    costs = _modeled_cost_bps(engine)
    if costs is None:
        assumptions.append(PublicExcerptAssumption(key="no_costs"))
    else:
        fee_bps, slippage_bps = costs
        assumptions.append(
            PublicExcerptAssumption(key="modeled_fee_bps", value=_number(fee_bps))
        )
        assumptions.append(
            PublicExcerptAssumption(
                key="modeled_slippage_bps", value=_number(slippage_bps)
            )
        )
    if benchmark_symbol is not None:
        # The engine charges the benchmark the same modeled costs it charges the
        # strategy, so which of the two keys applies is decided here, once, from the
        # run rather than re-derived by every surface that renders it.
        assumptions.append(
            PublicExcerptAssumption(
                key="benchmark" if costs is None else "benchmark_same_modeled_costs",
                value=benchmark_symbol,
            )
        )
    if len(assumptions) > MAX_ASSUMPTIONS:
        raise PublicExcerptSourceError(_UNDESCRIBABLE_ASSUMPTIONS)
    return assumptions


def _is_recurring_contribution_run(
    config_snapshot: object, engine: dict[str, Any]
) -> bool:
    snapshot = _mapping(config_snapshot)
    resolved_strategy = _mapping(snapshot.get("resolved_strategy"))
    identity = {
        (_text(snapshot.get("template")) or "").lower(),
        (_text(resolved_strategy.get("strategy_type")) or "").lower(),
        (_text(engine.get("template")) or "").lower(),
    }
    return "dca_accumulation" in identity


def _contribution_assumptions(
    engine: dict[str, Any],
) -> list[PublicExcerptAssumption]:
    """The contribution facts, read through the plan the run actually executed.

    The receipt's key vocabulary is frozen, so ``starting_principal`` keeps its
    public name while the plan owns what that number is. A plan that cannot be
    read at all is refused: its contribution is the number every other number on
    the page was produced from.
    """
    from argus.domain.dca_capital import (
        DcaCapitalError,
        dca_capital_plan_from_config,
    )

    try:
        plan = dca_capital_plan_from_config(engine)
    except DcaCapitalError as exc:
        raise PublicExcerptSourceError(_UNDESCRIBABLE_ASSUMPTIONS) from exc
    facts = [
        PublicExcerptAssumption(
            key="recurring_contribution", value=_number(plan.contribution)
        ),
        PublicExcerptAssumption(key="contribution_cadence", value=plan.period),
        PublicExcerptAssumption(
            key="starting_principal", value=_number(plan.starting_capital)
        ),
        PublicExcerptAssumption(key="fractional_shares"),
    ]
    return facts


def _cadence(engine: dict[str, Any]) -> str | None:
    """The contribution cadence as its frozen token, never as a localized word."""
    candidates = (
        _mapping(engine.get("parameters")).get("dca_cadence"),
        engine.get("dca_cadence"),
        engine.get("cadence"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower()
    return None


def _modeled_cost_bps(engine: dict[str, Any]) -> tuple[float, float] | None:
    """The execution costs the run modeled, or nothing when it modeled none.

    Read from the frozen config rather than through
    ``_execution_realism_settings``, which consults the live feature flag: a flag
    flipped after the run would otherwise decide what the receipt says the run
    assumed. The config carries the field only when the flag was on at run time,
    which is the frozen truth this page is supposed to hold.

    A run that states costs it cannot express is refused rather than reported as
    costless, because understating them misdescribes every number beside it.
    """
    realism = _mapping(engine.get("_execution_realism"))
    if not bool(realism.get("enabled")):
        return None
    fee_bps = _amount(realism.get("fee_bps"))
    slippage_bps = _amount(realism.get("slippage_bps"))
    if fee_bps is None or slippage_bps is None or fee_bps < 0.0 or slippage_bps < 0.0:
        raise PublicExcerptSourceError(_UNDESCRIBABLE_ASSUMPTIONS)
    if fee_bps <= 0.0 and slippage_bps <= 0.0:
        return None
    return fee_bps, slippage_bps


def _amount(value: object) -> float | None:
    """A finite number, whatever numeric shape the snapshot froze it in."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _number(value: float) -> str:
    """A bare number with no separators, so the viewer's locale supplies its own."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _strategy_facts(config_snapshot: object) -> list[PublicExcerptStrategyFact]:
    """Freeze the parameters that define what was executed.

    The strategy label is a category name. For every shape except buy and hold it
    does not identify what produced the numbers: two RSI runs with different periods
    and thresholds, or two crossovers with different windows, would otherwise render
    as the same strategy with different results, which is the opposite of evidence.

    Dispatched on shape, not assembled from whichever fields happen to be present.
    Each shape below declares the complete set of parameters that decide its trades,
    and a shape whose set is not fully present projects nothing at all. Partial
    parameters are worse than none here: a viewer cannot tell that a receipt naming
    one window of a crossover is missing the other, so it would read as a truthful
    record of a strategy that never ran.
    """
    snapshot = _mapping(config_snapshot)
    resolved_strategy = _mapping(snapshot.get("resolved_strategy"))
    resolved_parameters = _mapping(snapshot.get("resolved_parameters"))
    # Two config_snapshot shapes reach here. The agent path nests the strategy under
    # resolved_strategy/resolved_parameters; the direct engine path stores the engine
    # config itself, whose parameters live under `parameters`. Reading only the first
    # left every run made through the second with no parameters at all.
    engine_parameters = _mapping(snapshot.get("parameters"))
    entry_rule = _mapping(resolved_strategy.get("entry_rule"))
    exit_rule = _mapping(resolved_strategy.get("exit_rule"))
    parameters = {**engine_parameters, **resolved_parameters}

    label, required, optional = _strategy_shape(
        snapshot=snapshot,
        resolved_strategy=resolved_strategy,
        entry_rule=entry_rule,
        exit_rule=exit_rule,
        parameters=parameters,
    )

    facts: list[PublicExcerptStrategyFact] = [
        PublicExcerptStrategyFact(key="strategy_type", value=label)
    ]
    for key in required:
        value = _strategy_fact_value(
            _strategy_source_value(
                key,
                parameters=parameters,
                resolved_strategy=resolved_strategy,
                entry_rule=entry_rule,
                exit_rule=exit_rule,
            )
        )
        if value is None:
            raise PublicExcerptSourceError(_UNDESCRIBABLE_STRATEGY)
        facts.append(PublicExcerptStrategyFact(key=key, value=value))
    for key in optional:
        value = _strategy_fact_value(
            _strategy_source_value(
                key,
                parameters=parameters,
                resolved_strategy=resolved_strategy,
                entry_rule=entry_rule,
                exit_rule=exit_rule,
            )
        )
        if value is not None:
            facts.append(PublicExcerptStrategyFact(key=key, value=value))
    return facts


def _strategy_shape(
    *,
    snapshot: dict[str, Any],
    resolved_strategy: dict[str, Any],
    entry_rule: dict[str, Any],
    exit_rule: dict[str, Any],
    parameters: dict[str, Any],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Resolve the executed shape: its truthful name, then the set that defines it.

    Keyed on the typed rule before the execution type, because the rule is what the
    engine compiles and the execution type does not name a shape on its own:
    ``signal_strategy`` covers both a moving average crossover and an arbitrary rule
    spec, and naming a crossover "signal strategy" would be true of the runtime and
    useless to a reader.

    Direction is deliberately not among any shape's facts. Argus executes long only
    (see ``_build_long_only_execution_ledger``), so a frozen "bearish" names which way
    two averages crossed and not a position taken; published beside a sell rule it
    reads as shorting a stock. The rendered sentence carries the crossing direction
    already.

    Raises rather than returning nothing for a shape it cannot describe. A caller that
    had to interpret an empty result published a page describing a strategy this
    module had declined to describe.
    """
    template = (_text(snapshot.get("template")) or "").lower()
    strategy_type = (_text(resolved_strategy.get("strategy_type")) or "").lower()
    rule_type = (_text(entry_rule.get("type")) or "").lower()
    identity = {template, strategy_type}

    if rule_type == "moving_average_crossover":
        return (
            "moving average crossover",
            _crossover_required_keys(entry_rule=entry_rule, exit_rule=exit_rule),
            (),
        )
    if rule_type == "macd_crossover":
        return (
            "macd crossover",
            ("fast_period", "slow_period", "signal_period"),
            (),
        )
    if "dca_accumulation" in identity:
        return ("dca accumulation", ("cadence",), ())
    if "buy_and_hold" in identity:
        return ("buy and hold", (), ())
    if "buy_the_dip" in identity:
        # fixed_parameters in the capability registry: the trigger is hardcoded in
        # the engine, so there is nothing frozen to disclose, and nothing to borrow
        # from the indicator shape it shares an execution type with either.
        return ("buy the dip", (), ())
    if identity & {"indicator_threshold", "rsi_mean_reversion"}:
        name = (
            "rsi threshold" if template == "rsi_mean_reversion" else "indicator threshold"
        )
        return (
            name,
            ("indicator", "indicator_period", "entry_threshold", "exit_threshold"),
            (),
        )
    # A generic rule spec is a condition tree, and an unrecognised shape is unknown by
    # definition. Neither can be flattened into key and value pairs without inventing
    # something, so neither is shareable.
    raise PublicExcerptSourceError(_UNDESCRIBABLE_STRATEGY)


def _crossover_required_keys(
    *,
    entry_rule: dict[str, Any],
    exit_rule: dict[str, Any],
) -> tuple[str, ...]:
    """The crossover facts a receipt owes, entry side plus exit side when they differ.

    The rule compiler builds entry and exit independently and never requires them to
    match, so reading the windows from the entry rule alone can state an exit that did
    not run. When the exit rule is absent the engine substitutes the mirror of the
    entry, which is the exit the rendered "crossed back" sentence describes.

    Anything that is not that mirror has to be stated or refused, judged over the
    engine's whole field set. A difference the payload has a fact for is projected; a
    difference it has none for, such as an exit configured in the same direction as the
    entry, refuses rather than publishing the mirror's sentence over it.
    """
    if not exit_rule:
        return CROSSOVER_WINDOW_KEYS
    if (_text(exit_rule.get("type")) or "").lower() != "moving_average_crossover":
        # A crossover entry paired with some other kind of exit is a shape this module
        # has no faithful projection for.
        raise PublicExcerptSourceError(_UNDESCRIBABLE_STRATEGY)
    mirror = engine_mirrored_exit_rule(entry_rule) or {}
    differing = {
        field
        for field in CROSSOVER_RULE_FIELDS
        if _rule_field_token(exit_rule.get(field)) != _rule_field_token(mirror.get(field))
    }
    if not differing:
        return CROSSOVER_WINDOW_KEYS
    unprojectable = differing.difference(CROSSOVER_WINDOW_KEYS)
    if unprojectable:
        raise PublicExcerptSourceError(_UNDESCRIBABLE_STRATEGY)
    return (*CROSSOVER_WINDOW_KEYS, *(f"exit_{key}" for key in CROSSOVER_WINDOW_KEYS))


def _rule_field_token(value: object) -> str | None:
    """Compare rule fields the way the compiler reads them, case and type folded.

    ``20`` and ``"20"`` are the same window to the engine, and ``"Bullish"`` is the
    same direction, so a comparison that called them different would refuse runs it
    can describe perfectly well.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return _strategy_fact_value(value)
    return str(value).strip().lower() or None


def _strategy_source_value(
    key: str,
    *,
    parameters: dict[str, Any],
    resolved_strategy: dict[str, Any],
    entry_rule: dict[str, Any],
    exit_rule: dict[str, Any],
) -> object:
    """Where each fact is frozen from, most specific source first."""
    candidates: tuple[object, ...]
    if key == "cadence":
        candidates = (
            parameters.get("dca_cadence"),
            resolved_strategy.get("cadence"),
            parameters.get("cadence"),
        )
    elif key == "indicator":
        candidates = (
            parameters.get("indicator"),
            entry_rule.get("indicator"),
            exit_rule.get("indicator"),
        )
    elif key == "indicator_period":
        candidates = (
            parameters.get("indicator_period"),
            entry_rule.get("period"),
            entry_rule.get("indicator_period"),
            exit_rule.get("period"),
        )
    elif key == "entry_threshold":
        candidates = (
            parameters.get("entry_threshold"),
            parameters.get("indicator_entry_threshold"),
            entry_rule.get("threshold"),
        )
    elif key == "exit_threshold":
        candidates = (
            parameters.get("exit_threshold"),
            parameters.get("indicator_exit_threshold"),
            exit_rule.get("threshold"),
        )
    elif key.startswith("exit_") and key[len("exit_") :] in CROSSOVER_WINDOW_KEYS:
        # Only the exit rule may speak for the exit side.
        candidates = (exit_rule.get(key[len("exit_") :]),)
    else:
        # fast_indicator, fast_period, slow_indicator, slow_period, signal_period:
        # the typed rule is the only place these are frozen.
        candidates = (entry_rule.get(key), parameters.get(key))
    for candidate in candidates:
        if candidate not in (None, ""):
            return candidate
    return None


def _strategy_fact_value(value: object) -> str | None:
    """Plain scalars only. A nested structure is not a fact a viewer can read."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Whole numbers read as periods and thresholds, not as decimals.
        return _number(value)
    if isinstance(value, str):
        normalized = _text(value)
        if normalized is None:
            return None
        return normalized[:48].replace("_", " ")
    return None


def _visual(chart: object) -> PublicExcerptVisual | None:
    mapping = _mapping(chart)
    if mapping.get("kind") != "portfolio_equity":
        return None
    series = _visual_series(mapping.get("series"))
    if len(series) < 2:
        return None
    base_value = mapping.get("base_value")
    return PublicExcerptVisual(
        kind="portfolio_equity",
        currency=_text(mapping.get("currency")),
        base_value=float(base_value) if isinstance(base_value, int | float) else None,
        series=series,
    )


def _visual_series(value: object) -> list[PublicExcerptVisualPoint]:
    if not isinstance(value, list):
        return []
    points: list[PublicExcerptVisualPoint] = []
    for entry in value:
        row = _mapping(entry)
        time = _text(row.get("time"))
        observed = row.get("value")
        if time is None or not isinstance(observed, int | float):
            continue
        points.append(PublicExcerptVisualPoint(time=time, value=float(observed)))
    return _downsample(points)


def _downsample(
    points: list[PublicExcerptVisualPoint],
) -> list[PublicExcerptVisualPoint]:
    """Keep the payload small on a phone without moving the endpoints."""
    if len(points) <= MAX_VISUAL_POINTS:
        return points
    stride = len(points) / (MAX_VISUAL_POINTS - 1)
    sampled = [points[int(index * stride)] for index in range(MAX_VISUAL_POINTS - 1)]
    sampled.append(points[-1])
    return sampled

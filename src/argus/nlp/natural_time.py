from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, cast

from dateparser.date import DateDataParser
from dateparser.languages.loader import default_loader
from dateparser.search import search_dates

from argus.domain.clock import new_york_today

DatePeriod = Literal["day", "week", "month", "year"]
DateIntentUnit = Literal["day", "week", "month", "quarter", "year"]


@dataclass(frozen=True)
class NaturalDateRange:
    label: str
    start: date
    end: date
    evidence_spans: tuple[str, ...] = ()

    @property
    def payload(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass(frozen=True)
class DateRangeIntentResolution:
    label: str
    payload: dict[str, str]
    evidence_spans: tuple[str, ...] = ()


def date_range_evidence_has_explicit_endpoints(
    evidence_spans: tuple[str, ...],
) -> bool:
    """Return true when natural-time evidence came from two user-visible endpoints."""

    spans = tuple(str(span or "").strip() for span in evidence_spans if str(span or "").strip())
    if len(spans) < 2:
        return False
    return not any(_is_generated_time_span_endpoint(span) for span in spans)


@dataclass(frozen=True)
class _ParsedDate:
    value: date
    period: DatePeriod
    span: str


def resolve_date_range_text(
    text: str,
    *,
    today: date | None = None,
    languages: tuple[str, ...] | None = None,
    require_parts: tuple[str, ...] = (),
) -> NaturalDateRange | None:
    """Resolve bounded natural-language date/window text into canonical dates.

    Dateparser is intentionally wrapped here rather than called directly from runtime
    contracts: Argus can bound inputs, normalize endpoint semantics, and reject weak
    single-date false positives in one place.
    """

    raw = str(text or "").strip()
    if not raw:
        return None
    if text_has_fractional_duration(raw):
        return None
    current_date = today or new_york_today()
    matches = _search_date_spans(raw, today=current_date, languages=languages)
    if not matches:
        return None

    time_span = _range_from_returned_time_span(matches, today=current_date)
    if time_span is not None:
        return time_span

    parsed = [
        parsed
        for span, _ in matches
        if (parsed := _parse_date_span(span, today=current_date, languages=languages, require_parts=require_parts))
        is not None
    ]
    if len(parsed) < 2:
        return None

    if any(item.period == "year" for item in parsed) and any(
        item.period == "month"
        or (item.period == "day" and any(char.isdigit() for char in item.span))
        for item in parsed
    ):
        # A year alongside finer dates may qualify their year rather than name
        # an endpoint. Search can also drop one of those dates. Do not let this
        # partial reading overwrite the structured interpreter's full range.
        return None

    first = parsed[0]
    last = parsed[-1]
    if (
        first.period in {"day", "month"}
        and last.period in {"day", "month"}
        and not _span_has_explicit_year(first.span)
        and _span_has_explicit_year(last.span)
    ):
        try:
            shared_year_first = first.value.replace(year=last.value.year)
        except ValueError:
            return None
        if shared_year_first <= last.value:
            first = _ParsedDate(
                value=shared_year_first,
                period=first.period,
                span=first.span,
            )

    start = _endpoint_date(first, endpoint="start", today=current_date)
    end = _endpoint_date(last, endpoint="end", today=current_date)
    if end < start:
        return None
    label = _relative_window_label(start=start, end=end, today=current_date) or (
        f"{start} to {end}"
    )
    return NaturalDateRange(
        label=label,
        start=start,
        end=end,
        evidence_spans=(first.span, last.span),
    )


def resolve_rolling_window_intent_text(
    text: str,
    *,
    today: date | None = None,
    languages: tuple[str, ...] | None = None,
    confidence: float = 0.65,
) -> dict[str, Any] | None:
    """Recover a canonical rolling-window intent from bounded date evidence.

    This is intentionally a repair path for short LLM-provided evidence spans, not
    a chat-message parser. The language-specific work stays inside dateparser;
    Argus only converts a resolved relative range into language-neutral intent.
    """

    raw = str(text or "").strip()
    if not raw:
        return None
    current_date = today or new_york_today()
    idiom_window = _trailing_window_fields_from_idiom(raw)
    if idiom_window is not None:
        return {
            "kind": "rolling_window",
            **idiom_window,
            "anchor": "today",
            "confidence": confidence,
            "evidence": raw,
        }
    resolved = resolve_date_range_text(
        raw,
        today=current_date,
        languages=languages,
    )
    window = (
        _rolling_window_fields_from_range(
            start=resolved.start,
            end=resolved.end,
            today=current_date,
        )
        if resolved is not None
        else _rolling_window_fields_from_single_date_evidence(
            raw,
            today=current_date,
            languages=languages,
        )
    )
    if window is None:
        return None
    return {
        "kind": "rolling_window",
        **window,
        "anchor": "today",
        "confidence": confidence,
        "evidence": raw,
    }


def resolve_calendar_year_intent_text(
    text: str,
    *,
    today: date | None = None,
    languages: tuple[str, ...] | None = None,
    confidence: float = 0.8,
) -> dict[str, Any] | None:
    """Recover a canonical calendar-year intent from bounded date-answer text.

    This helper is for typed pending-date contracts, not general chat routing.
    It uses dateparser to identify a single explicit year, then returns the same
    machine intent shape produced by the structured interpreter.
    """

    raw = str(text or "").strip()
    if not raw:
        return None
    current_date = today or new_york_today()
    years: list[int] = []
    for span, _ in _search_date_spans(
        raw,
        today=current_date,
        languages=languages,
        return_time_span=False,
    ):
        parsed = _parse_date_span(span, today=current_date, languages=languages)
        if parsed is None or parsed.period != "year":
            continue
        if not _span_has_explicit_year(parsed.span):
            continue
        if parsed.value.year > current_date.year:
            continue
        years.append(parsed.value.year)
    unique_years = list(dict.fromkeys(years))
    if len(unique_years) != 1:
        return None
    return {
        "kind": "calendar_year",
        "year": unique_years[0],
        "confidence": confidence,
        "evidence": raw,
    }


def resolve_date_range_intent(
    intent: Mapping[str, Any] | object | None,
    *,
    today: date | None = None,
) -> DateRangeIntentResolution | None:
    """Resolve canonical interpreter time intent into an Argus date-range patch.

    This is intentionally not a natural-language parser. The LLM owns phrases such
    as "los últimos 12 meses" or "year to date" and returns language-neutral
    fields; this function only performs deterministic date math and validation.
    """

    payload = _intent_payload(intent)
    if not payload:
        return None
    current_date = today or new_york_today()
    current_year = payload.get("year_reference") == "current_year"
    if not _intent_confidence_is_usable(payload):
        return None

    kind = str(payload.get("kind") or "").strip()
    evidence = _intent_evidence_spans(payload)

    if kind == "future_window":
        # A forward-looking horizon is original intent, never a resolvable
        # historical test window (issue #241 executable boundary).
        return None

    year = current_date.year if current_year else _positive_int(payload.get("year"))
    start = _intent_date(
        payload.get("start"), today=current_date, current_year=current_year
    )
    end = _intent_date(payload.get("end"), today=current_date, current_year=current_year)
    if current_year and any(
        payload.get(key) and value is None
        for key, value in (("start", start), ("end", end))
    ):
        return None

    if kind == "rolling_window":
        count = _positive_number(payload.get("count"))
        unit = _intent_unit(payload.get("unit"))
        if count is None or unit is None:
            return None
        end = end or current_date
        start = _subtract_period(end, count=count, unit=unit)
        if end < start:
            return None
        return DateRangeIntentResolution(
            label=_relative_label(count=count, unit=unit),
            payload={"start": start.isoformat(), "end": end.isoformat()},
            evidence_spans=evidence,
        )

    if kind == "year_to_date":
        year = year or current_date.year
        if year > current_date.year:
            return None
        if end is None:
            end = current_date if year == current_date.year else date(year, 12, 31)
        if end < date(year, 1, 1):
            return None
        return DateRangeIntentResolution(
            label="year to date" if year == current_date.year else f"{year} so far",
            payload={"start": date(year, 1, 1).isoformat(), "end": end.isoformat()},
            evidence_spans=evidence,
        )

    if kind == "calendar_year":
        if year is None or year > current_date.year:
            return None
        end = current_date if year == current_date.year else date(year, 12, 31)
        return DateRangeIntentResolution(
            label=str(year),
            payload={"start": date(year, 1, 1).isoformat(), "end": end.isoformat()},
            evidence_spans=evidence,
        )

    if kind == "since":
        if start is None and year is not None:
            start = date(year, 1, 1)
        if start is None or start > current_date:
            return None
        end = end or current_date
        if end < start:
            return None
        return DateRangeIntentResolution(
            label=f"since {start.isoformat()}",
            payload={"start": start.isoformat(), "end": end.isoformat()},
            evidence_spans=evidence,
        )

    if kind in {"explicit_range", "endpoint_patch"}:
        patch: dict[str, str] = {}
        offset_date = _intent_day_offset_date(payload, today=current_date)
        endpoint = str(payload.get("endpoint") or "").strip()
        if start is not None:
            patch["start"] = start.isoformat()
        if end is not None:
            patch["end"] = end.isoformat()
        if kind == "endpoint_patch" and endpoint in {"start", "end"}:
            endpoint_value = (start if endpoint == "start" else end) or offset_date
            if endpoint_value is None:
                return None
            patch = {endpoint: endpoint_value.isoformat()}
        if not patch or (
            patch.get("start") and patch.get("end") and patch["end"] < patch["start"]
        ):
            return None
        label = (
            f"{patch['start']} to {patch['end']}"
            if set(patch) == {"start", "end"}
            else "date endpoint"
        )
        return DateRangeIntentResolution(
            label=label,
            payload=patch,
            evidence_spans=evidence,
        )
    return None


def _is_leap_day_clamp_pair(start: date, end: date) -> bool:
    """True when a Feb-29 anchor clamped to Feb-28 marks the same month/year day.

    A trailing 1-year window ending on Feb 29 subtracts to Feb 28 of the prior
    (non-leap) year, so the endpoints share a month-aligned anchor even though
    their day-of-month differs.
    """

    return {(start.month, start.day), (end.month, end.day)} == {(2, 28), (2, 29)}


def _rolling_window_fields_from_range(
    *,
    start: date,
    end: date,
    today: date,
) -> dict[str, Any] | None:
    if end < start or end != today:
        return None
    month_delta = (end.year - start.year) * 12 + (end.month - start.month)
    if month_delta > 0 and (start.day == end.day or _is_leap_day_clamp_pair(start, end)):
        return {"count": month_delta, "unit": "month"}
    day_delta = end.toordinal() - start.toordinal()
    if day_delta <= 0:
        return None
    if day_delta % 365 == 0:
        return {"count": day_delta // 365, "unit": "year"}
    if day_delta % 7 == 0:
        return {"count": day_delta // 7, "unit": "week"}
    return {"count": day_delta, "unit": "day"}


_WINDOW_UNIT_TOKENS: dict[str, DateIntentUnit] = {
    "day": "day", "days": "day", "dia": "day", "día": "day",
    "dias": "day", "días": "day",
    "week": "week", "weeks": "week", "semana": "week", "semanas": "week",
    "month": "month", "months": "month", "mes": "month", "meses": "month",
    "year": "year", "years": "year", "ano": "year", "año": "year",
    "anos": "year", "años": "year",
}
_WINDOW_QUALIFIER_TOKENS = frozenset(
    {
        "last", "past", "trailing",
        "ultimo", "último", "ultima", "última",
        "ultimos", "últimos", "ultimas", "últimas",
        "pasado", "pasada", "pasados", "pasadas",
    }
)
_WINDOW_FILLER_TOKENS = frozenset(
    {"del", "de", "desde", "el", "la", "los", "las", "the", "from", "este", "esta"}
)
# Trailing anchors: the phrase explicitly runs up to today.
_WINDOW_ANCHOR_PHRASES = (
    ("para", "aca"), ("para", "acá"),
    ("hasta", "hoy"), ("hasta", "ahora"), ("hasta", "la", "fecha"),
    ("a", "la", "fecha"), ("al", "dia", "de", "hoy"), ("al", "día", "de", "hoy"),
    ("to", "now"), ("to", "date"), ("to", "today"),
    ("until", "now"), ("until", "today"), ("till", "now"), ("till", "today"),
    ("so", "far"),
)
_WINDOW_COUNT_WORDS = {"un": 1, "una": 1, "one": 1, "a": 1}


def _trailing_window_fields_from_idiom(text: str) -> dict[str, Any] | None:
    """Recognize "del último año para acá" / "last year to now" shaped spans.

    dateparser resolves these idioms to a single calendar date, which downstream
    turned into a zero-day window; the shape is deterministic, so read it as a
    trailing window anchored on today.
    """
    tokens = [
        token
        for token in _split_preserving_decimal_commas(text.casefold())
        if token
    ]
    tokens = [token.strip(".,!?") for token in tokens if token.strip(".,!?")]
    if not tokens:
        return None
    anchored = False
    for phrase in _WINDOW_ANCHOR_PHRASES:
        size = len(phrase)
        if len(tokens) > size and tuple(tokens[-size:]) == phrase:
            tokens = tokens[:-size]
            anchored = True
            break
    while tokens and tokens[0] in _WINDOW_FILLER_TOKENS:
        tokens = tokens[1:]
    qualified = False
    if tokens and tokens[0] in _WINDOW_QUALIFIER_TOKENS:
        qualified = True
        tokens = tokens[1:]
    count: float = 1
    decimal_count = _decimal_count_token(tokens[0]) if tokens else None
    if tokens and (decimal_count is not None or tokens[0] in _WINDOW_COUNT_WORDS):
        count = (
            decimal_count
            if decimal_count is not None
            else _WINDOW_COUNT_WORDS[tokens[0]]
        )
        tokens = tokens[1:]
    if not tokens or count <= 0:
        return None
    unit = _WINDOW_UNIT_TOKENS.get(tokens[0])
    if unit is None or unit == "quarter":
        return None
    trailing = tokens[1:]
    if trailing and not (
        len(trailing) <= 1 and trailing[0] in _WINDOW_QUALIFIER_TOKENS
    ):
        return None
    if trailing:
        qualified = True
    # A bare count+unit ("6 meses") is only a window when the phrase anchors
    # or qualifies it; otherwise leave it to the general parser.
    if not qualified and not anchored:
        return None
    # Whole counts stay integers so existing intent payloads are unchanged.
    if float(count) == int(count):
        count = int(count)
    return {"count": count, "unit": unit}


def _split_preserving_decimal_commas(text: str) -> list[str]:
    """Split on whitespace and commas, keeping a comma between digits.

    es-419 writes fractional quantities with a decimal comma ("8,5 meses");
    list commas ("enero, febrero") still separate tokens.
    """
    output: list[str] = []
    for index, char in enumerate(text):
        if char == "," and not (
            index > 0
            and index + 1 < len(text)
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            output.append(" ")
        else:
            output.append(char)
    return "".join(output).split()


def _decimal_count_token(token: str) -> float | None:
    """Read a bare or decimal numeric token: "8", "8.5", or "8,5"."""
    cleaned = str(token or "").strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return float(cleaned)
    for separator in (".", ","):
        head, sep, tail = cleaned.partition(separator)
        if sep and head.isdigit() and tail.isdigit():
            return float(f"{head}.{tail}")
    return None


def text_has_fractional_duration(
    text: str,
) -> bool:
    """A decimal quantity immediately before a duration-unit token.

    dateparser reads only the digits after the separator ("8.5 months ago"
    becomes "5 months ago"), so any dateparser-backed read of such text is
    untrustworthy and must refuse rather than guess (#332). This bounds the
    existing deterministic fallback parser; it is not a language gate in
    front of LLM interpretation.
    """
    tokens = [
        token.strip(".,!?")
        for token in _split_preserving_decimal_commas(str(text or "").casefold())
    ]
    tokens = [token for token in tokens if token]
    for token, next_token in zip(tokens, tokens[1:], strict=False):
        if next_token not in _WINDOW_UNIT_TOKENS:
            continue
        value = _decimal_count_token(token)
        if value is None or token.isdigit():
            continue
        return True
    return False


def _rolling_window_fields_from_single_date_evidence(
    text: str,
    *,
    today: date,
    languages: tuple[str, ...] | None,
) -> dict[str, Any] | None:
    parsed = _single_searched_date_span(text, today=today, languages=languages)
    if parsed is not None and parsed.period != "day" and parsed.value < today:
        if _span_has_explicit_year(parsed.span):
            return None
        window = _rolling_window_fields_from_range(
            start=parsed.value,
            end=today,
            today=today,
        )
        if (
            parsed.period == "year"
            and window is not None
            and window.get("unit") == "month"
            and int(window.get("count") or 0) % 12 == 0
        ):
            return {"count": int(window["count"]) // 12, "unit": "year"}
        return window
    return None


def resolve_date_range_endpoint_patch(
    base_intent: Mapping[str, Any] | object | None,
    endpoint_patch: Mapping[str, Any] | object | None,
    *,
    today: date | None = None,
) -> DateRangeIntentResolution | None:
    """Resolve an endpoint edit against a prior canonical date-range intent."""

    base = _intent_payload(base_intent)
    patch = _intent_payload(endpoint_patch)
    if not base or not patch:
        return None
    if str(base.get("kind") or "").strip() != "rolling_window":
        return None
    if str(patch.get("kind") or "").strip() != "endpoint_patch":
        return None
    if not _intent_confidence_is_usable(base) or not _intent_confidence_is_usable(patch):
        return None

    count = _positive_number(base.get("count"))
    unit = _intent_unit(base.get("unit"))
    endpoint = str(patch.get("endpoint") or "").strip()
    if count is None or unit is None or endpoint not in {"start", "end"}:
        return None

    current_date = today or new_york_today()
    start = _intent_date(patch.get("start"), today=current_date)
    end = _intent_date(patch.get("end"), today=current_date)
    offset_date = _intent_day_offset_date(patch, today=current_date)
    endpoint_value = (start if endpoint == "start" else end) or offset_date
    if endpoint_value is None:
        return None

    if endpoint == "start":
        start_date = endpoint_value
        end_date = _add_period(endpoint_value, count=count, unit=unit)
    else:
        end_date = endpoint_value
        start_date = _subtract_period(endpoint_value, count=count, unit=unit)
    if end_date < start_date:
        return None

    evidence = tuple(
        dict.fromkeys([*_intent_evidence_spans(base), *_intent_evidence_spans(patch)])
    )
    return DateRangeIntentResolution(
        label=_relative_label(count=count, unit=unit),
        payload={"start": start_date.isoformat(), "end": end_date.isoformat()},
        evidence_spans=evidence,
    )


def _intent_payload(intent: Mapping[str, Any] | object | None) -> dict[str, Any]:
    if intent is None:
        return {}
    if isinstance(intent, Mapping):
        return dict(intent)
    model_dump = getattr(intent, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _intent_confidence_is_usable(payload: Mapping[str, Any]) -> bool:
    confidence = payload.get("confidence")
    if confidence in (None, ""):
        return True
    try:
        return float(confidence) >= 0.5
    except (TypeError, ValueError):
        return False


def _intent_evidence_spans(payload: Mapping[str, Any]) -> tuple[str, ...]:
    evidence = str(payload.get("evidence") or "").strip()
    return (evidence,) if evidence else ()


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _positive_number(value: Any) -> float | None:
    """A strictly positive finite quantity; fractional durations are valid.

    The LLM interprets "the last 8.5 months" into count=8.5; deterministic
    code only validates and computes from it (#332).
    """
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0 or parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _intent_unit(value: Any) -> DateIntentUnit | None:
    normalized = str(value or "").strip()
    if normalized in {"day", "week", "month", "quarter", "year"}:
        return cast(DateIntentUnit, normalized)
    return None


def _intent_date(
    value: Any, *, today: date, current_year: bool = False
) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        value = value.isoformat()
    text = str(value or "").strip()
    if not text:
        return None
    if text in {"today", "current_date"}:
        return today
    try:
        if current_year and text.startswith("--"):
            # The model supplies month/day and the typed year reference only.
            # Even a stale ISO year cannot override the runtime clock.
            return date.fromisoformat(f"{today.year}-{text[2:]}")
        parsed = date.fromisoformat(text)
        return parsed.replace(year=today.year) if current_year else parsed
    except ValueError:
        return None


def _intent_day_offset_date(payload: Mapping[str, Any], *, today: date) -> date | None:
    offset = payload.get("day_offset")
    if offset in (None, ""):
        return None
    anchor = str(payload.get("anchor") or "today").strip()
    if anchor not in {"today", "current_date"}:
        return None
    try:
        days = int(offset)
    except (TypeError, ValueError):
        return None
    return today + timedelta(days=days)


def parse_date_text(
    text: str,
    *,
    today: date | None = None,
    endpoint: Literal["start", "end"] = "start",
    languages: tuple[str, ...] | None = None,
    prefer_dates_from: Literal["past", "future"] | None = None,
    require_parts: tuple[str, ...] = (),
) -> date | None:
    current_date = today or new_york_today()
    if text_has_fractional_duration(str(text or "")):
        return None
    parsed = _parse_date_span(
        str(text or ""),
        today=current_date,
        languages=languages,
        prefer_dates_from=prefer_dates_from,
        require_parts=require_parts,
    )
    if parsed is None:
        parsed = _single_searched_date_span(
            str(text or ""),
            today=current_date,
            languages=languages,
            prefer_dates_from=prefer_dates_from,
            require_parts=require_parts,
        )
    if parsed is None:
        return None
    return _endpoint_date(parsed, endpoint=endpoint, today=current_date)


def date_range_intent_matches_evidence(
    intent: Mapping[str, Any] | object | None,
    *,
    current_message: str,
    language: str | None = None,
) -> bool:
    """Validate a typed date against its current-turn quote, without reading intent
    from unrelated message text. The date resolver owns both canonical values.
    """
    evidence = str(_intent_payload(intent).get("evidence") or "").strip()
    if not evidence or evidence not in current_message:
        return False
    today = new_york_today()
    proposed = resolve_date_range_intent(intent, today=today)
    if proposed is None:
        return False
    languages = dateparser_languages_for_user_language(language)
    quoted = resolve_date_range_text(evidence, today=today, languages=languages, require_parts=("month", "year"))
    if quoted is not None:
        supported = quoted.payload
    else:
        supported = {}
        for endpoint in ("start", "end"):
            value = parse_date_text(
                evidence, today=today, endpoint=endpoint, languages=languages, require_parts=("month", "year"),
            )
            if value is not None:
                supported[endpoint] = value.isoformat()
    return all(supported.get(key) == value for key, value in proposed.payload.items())


def dateparser_languages_for_user_language(language: str | None) -> tuple[str, ...]:
    primary = str(language or "en").strip().replace("_", "-").split("-", 1)[0]
    primary = primary.casefold()
    if not primary or not primary.isalpha():
        return ("en",)
    if primary == "en":
        return ("en",)
    return (primary, "en")


def _rounded_days(value: float) -> int:
    """Half-up day rounding: deterministic, direction-free, test-stable."""
    return int(value + 0.5)


def _split_months(months: float) -> tuple[int, float]:
    whole = int(months)
    fraction = months - whole
    if fraction < 1e-9:
        return whole, 0.0
    return whole, fraction


def _add_fractional_months(value: date, months: float) -> date:
    whole_months, fraction = _split_months(months)
    anchor = shift_months(value, whole_months)
    if fraction == 0.0:
        return anchor
    # Forward, the fraction traverses the month the anchor sits in.
    days_in_month = calendar.monthrange(anchor.year, anchor.month)[1]
    return anchor + timedelta(days=_rounded_days(fraction * days_in_month))


def shift_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def contains_named_date_evidence(
    text: str,
    *,
    today: date | None = None,
    languages: tuple[str, ...] | None = None,
) -> bool:
    """Return whether dateparser found month/day-like natural date evidence.

    Runtime contracts use this as a guardrail to avoid broadening text such as
    "January 2024" into the entire calendar year without carrying dateparser's
    language data directly in the runtime layer.
    """

    current_date = today or new_york_today()
    for span, _ in _search_date_spans(
        str(text or ""),
        today=current_date,
        languages=languages,
        return_time_span=False,
    ):
        parsed = _parse_date_span(span, today=current_date, languages=languages)
        if parsed is None:
            continue
        if not any(char.isdigit() for char in parsed.span) and parsed.period != "month":
            continue
        if parsed.period in {"day", "month", "week"} and any(
            char.isalpha() for char in parsed.span
        ):
            return True
    return False


def _search_date_spans(
    text: str,
    *,
    today: date,
    languages: tuple[str, ...] | None,
    return_time_span: bool = True,
    prefer_dates_from: Literal["past", "future"] | None = None,
) -> list[tuple[str, datetime]]:
    settings = {
        "RELATIVE_BASE": _relative_base(today),
        "RETURN_AS_TIMEZONE_AWARE": False,
        "PREFER_DAY_OF_MONTH": "first",
        "PREFER_MONTH_OF_YEAR": "first",
    }
    if prefer_dates_from is not None:
        settings["PREFER_DATES_FROM"] = prefer_dates_from
    if return_time_span:
        settings["RETURN_TIME_SPAN"] = True
    results = search_dates(
        _normalize_compact_range_separators(text),
        languages=list(languages) if languages else None,
        settings=settings,
    )
    return list(results or [])


def _parse_date_span(
    span: str,
    *,
    today: date,
    languages: tuple[str, ...] | None,
    prefer_dates_from: Literal["past", "future"] | None = None,
    require_parts: tuple[str, ...] = (),
) -> _ParsedDate | None:
    settings = {
        "RELATIVE_BASE": _relative_base(today),
        "RETURN_AS_TIMEZONE_AWARE": False,
        "PREFER_DAY_OF_MONTH": "first",
        "PREFER_MONTH_OF_YEAR": "first",
        "REQUIRE_PARTS": list(require_parts),
    }
    if prefer_dates_from is not None:
        settings["PREFER_DATES_FROM"] = prefer_dates_from
    parser = DateDataParser(
        languages=list(languages) if languages else None,
        settings=settings,
    )
    data = parser.get_date_data(_strip_time_span_suffix(span))
    if data.date_obj is None:
        return None
    period = str(data.period or "day")
    if require_parts and period == "month":
        # Numeric amounts plus a year can parse as a month. Coarse calendar
        # evidence needs a month name recognized by the library's locale data.
        locale = default_loader.get_locale(data.locale)
        translated = locale.translate(span, settings=parser._settings)
        month_tokens = "".join(char if char.isalpha() else " " for char in translated).split()
        if calendar.month_name[data.date_obj.month].casefold() not in month_tokens:
            return None
    if period not in {"day", "week", "month", "year"}:
        period = "day"
    return _ParsedDate(
        value=data.date_obj.date(),
        period=cast(DatePeriod, period),
        span=_strip_time_span_suffix(span),
    )


def _single_searched_date_span(
    text: str,
    *,
    today: date,
    languages: tuple[str, ...] | None,
    prefer_dates_from: Literal["past", "future"] | None = None,
    require_parts: tuple[str, ...] = (),
) -> _ParsedDate | None:
    if text_has_fractional_duration(text):
        return None
    matches = _search_date_spans(
        text,
        today=today,
        languages=languages,
        return_time_span=False,
        prefer_dates_from=prefer_dates_from,
    )
    if len(matches) != 1:
        return None
    span, value = matches[0]
    parsed = _parse_date_span(
        span,
        today=today,
        languages=languages,
        prefer_dates_from=prefer_dates_from,
        require_parts=require_parts,
    )
    if parsed is not None:
        return parsed
    if require_parts:
        return None
    return _ParsedDate(
        value=value.date(),
        period="day",
        span=span,
    )


def _endpoint_date(
    parsed: _ParsedDate,
    *,
    endpoint: Literal["start", "end"],
    today: date,
) -> date:
    if parsed.period == "day":
        return parsed.value
    if parsed.period == "week":
        start = parsed.value
        end = min(date.fromordinal(start.toordinal() + 6), today)
        return start if endpoint == "start" else end
    if parsed.period == "month":
        if endpoint == "start":
            return parsed.value.replace(day=1)
        day = calendar.monthrange(parsed.value.year, parsed.value.month)[1]
        return parsed.value.replace(day=day)
    if endpoint == "start":
        return date(parsed.value.year, 1, 1)
    return date(parsed.value.year, 12, 31)


def _range_from_returned_time_span(
    matches: list[tuple[str, datetime]],
    *,
    today: date,
) -> NaturalDateRange | None:
    start: tuple[str, date] | None = None
    end: tuple[str, date] | None = None
    for span, value in matches:
        normalized = span.casefold()
        if normalized.endswith("(start)"):
            start = (span, value.date())
        elif normalized.endswith("(end)"):
            end = (span, value.date())
    if start is None or end is None or end[1] < start[1]:
        return None
    label = _relative_window_label(start=start[1], end=end[1], today=today) or (
        f"{start[1]} to {end[1]}"
    )
    return NaturalDateRange(
        label=label,
        start=start[1],
        end=end[1],
        evidence_spans=(start[0], end[0]),
    )


def _relative_window_label(*, start: date, end: date, today: date) -> str | None:
    if end < start or end != today:
        return None
    month_delta = (end.year - start.year) * 12 + (end.month - start.month)
    if month_delta > 0 and start.day == end.day:
        unit = "month" if month_delta == 1 else "months"
        return f"past {month_delta} {unit}"
    day_delta = end.toordinal() - start.toordinal()
    if day_delta > 0:
        if day_delta % 365 == 0:
            years = day_delta // 365
            unit = "year" if years == 1 else "years"
            return f"past {years} {unit}"
        if day_delta % 7 == 0:
            weeks = day_delta // 7
            unit = "week" if weeks == 1 else "weeks"
            return f"past {weeks} {unit}"
    return None


def _relative_base(value: date) -> datetime:
    return datetime.combine(value, time(hour=12))


def _normalize_compact_range_separators(value: str) -> str:
    text = str(value or "")
    output: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char not in {"-", "–", "—"}:
            output.append(char)
            index += 1
            continue
        prev_index = _previous_non_space_index(text, index - 1)
        next_index = _next_non_space_index(text, index + 1)
        if (
            prev_index is not None
            and next_index is not None
            and text[prev_index].isdigit()
            and text[next_index].isalpha()
        ):
            while output and output[-1].isspace():
                output.pop()
            output.append(" to ")
            index = next_index
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _strip_time_span_suffix(value: str) -> str:
    stripped = str(value or "").strip()
    lowered = stripped.casefold()
    for suffix in ("(start)", "(end)"):
        if lowered.endswith(suffix):
            return stripped[: -len(suffix)].rstrip()
    return stripped


def _is_generated_time_span_endpoint(value: str) -> bool:
    lowered = str(value or "").strip().casefold()
    return lowered.endswith("(start)") or lowered.endswith("(end)")


def _span_has_explicit_year(value: str) -> bool:
    text = str(value or "")
    for index in range(max(len(text) - 3, 0)):
        candidate = text[index : index + 4]
        if not candidate.isdigit():
            continue
        previous_ok = index == 0 or not text[index - 1].isdigit()
        next_index = index + 4
        next_ok = next_index >= len(text) or not text[next_index].isdigit()
        if previous_ok and next_ok:
            return True
    return False


def _previous_non_space_index(value: str, index: int) -> int | None:
    while index >= 0:
        if not value[index].isspace():
            return index
        index -= 1
    return None


def _next_non_space_index(value: str, index: int) -> int | None:
    while index < len(value):
        if not value[index].isspace():
            return index
        index += 1
    return None


def _relative_label(*, count: float, unit: str) -> str:
    unit_name = {
        "d": "day",
        "w": "week",
        "m": "month",
        "mo": "month",
        "q": "quarter",
        "y": "year",
    }.get(unit, unit.removesuffix("s"))
    if count == 1:
        return f"past {unit_name}"
    display = str(int(count)) if float(count) == int(count) else f"{count:g}"
    return f"past {display} {unit_name}s"


def _subtract_period(today: date, *, count: float, unit: str) -> date:
    if unit in {"d", "day", "days"}:
        return today - timedelta(days=_rounded_days(count))
    if unit in {"w", "week", "weeks"}:
        return today - timedelta(days=_rounded_days(count * 7))
    if unit in {"m", "mo", "month", "months"}:
        months = count
    elif unit in {"q", "quarter", "quarters"}:
        months = count * 3
    else:
        months = count * 12
    whole_months, fraction = _split_months(months)
    anchor = shift_months(today, -whole_months)
    if fraction == 0.0:
        return anchor
    # The fractional remainder crosses backward into the previous month, so
    # its calendar length converts the fraction to days: half a month before
    # December 1 lands mid-November.
    crossed = anchor - timedelta(days=1)
    days_in_crossed = calendar.monthrange(crossed.year, crossed.month)[1]
    return anchor - timedelta(days=_rounded_days(fraction * days_in_crossed))


def _add_period(value: date, *, count: float, unit: str) -> date:
    if unit in {"d", "day", "days"}:
        return value + timedelta(days=_rounded_days(count))
    if unit in {"w", "week", "weeks"}:
        return value + timedelta(days=_rounded_days(count * 7))
    if unit in {"m", "mo", "month", "months"}:
        months = count
    elif unit in {"q", "quarter", "quarters"}:
        months = count * 3
    else:
        return _add_fractional_months(value, count * 12)
    return _add_fractional_months(value, months)

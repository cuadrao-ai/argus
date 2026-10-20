from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import mimetypes
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.llm.openrouter_retention import openrouter_provider_policy
from argus.llm.openrouter_tasks import OPENROUTER_PROFILES

from tests.interpreter_prompt_surface import (
    DOCUMENT_EXTRACTION_OWNERS,
    model_facing_surface,
)

REPO = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO / "docs" / "reports" / "evidence"
DEFAULT_MANIFEST = (
    EVIDENCE_ROOT
    / "cuadrao-receipt-payment-truth-1212"
    / "pending-measurement-manifest.json"
)
CONTEXT_TOKENS = 1_048_576
OUTPUT_TOKENS = 12_000
TIMEOUT_SECONDS = 90
MAX_CALLS = 3
SPEND_CAP = Decimal("5.00")
HOSTED_ENVS = frozenset({"production", "staging", "preview"})
ORDER_FIXTURE = "order-confirmation-estimated-tax"
INPUT_CACHE_KEYS = ("input_cache_read", "input_cache_write")
BLANK_RECEIPT_FIELDS = (
    "merchant",
    "occurred_on",
    "currency",
    "subtotal",
    "tax",
    "estimated_tax",
    "service",
    "tip",
    "total",
    "rnc",
    "ncf",
    "ecf",
    "itbis",
)
RECEIPT_ITEMS = (("Arroz", Decimal("150.00")), ("Leche", Decimal("100.50")))


class MeasurementError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TokenRates:
    input_usd_per_token: Decimal
    output_usd_per_token: Decimal


@dataclass(frozen=True)
class CallReservation:
    context_tokens: int
    output_tokens: int
    rates: TokenRates

    @property
    def usd(self) -> Decimal:
        return (
            Decimal(self.context_tokens) * self.rates.input_usd_per_token
            + Decimal(self.output_tokens) * self.rates.output_usd_per_token
        )


@dataclass
class SpendLedger:
    cap_usd: Decimal
    max_calls: int
    reservation: CallReservation
    spent_usd: Decimal = Decimal("0")
    attempted: list[str] = field(default_factory=list)

    def authorize(self, fixture_id: str) -> None:
        if fixture_id in self.attempted:
            raise MeasurementError("already_attempted")
        if len(self.attempted) >= self.max_calls:
            raise MeasurementError("call_limit")
        if self.spent_usd + self.reservation.usd > self.cap_usd:
            raise MeasurementError("spend_cap")
        self.attempted.append(fixture_id)

    def record(self, cost: Decimal) -> None:
        self.spent_usd += cost


@dataclass(frozen=True)
class Fixture:
    id: str
    path: Path
    sha256: str
    entry: dict


def _rate(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise MeasurementError("invalid_price") from None
    if not amount.is_finite() or amount < 0:
        raise MeasurementError("invalid_price")
    return amount


def _optional_rate(pricing: dict, name: str) -> Decimal:
    if name not in pricing:
        return Decimal(0)
    return _rate(pricing[name])


def token_rates(pricing: dict) -> TokenRates:
    if "prompt" not in pricing or "completion" not in pricing:
        raise MeasurementError("invalid_price")
    cache = Decimal(0)
    for name in INPUT_CACHE_KEYS:
        if name in pricing:
            cache = max(cache, _rate(pricing[name]))
    return TokenRates(
        input_usd_per_token=max(
            _rate(pricing["prompt"]),
            _optional_rate(pricing, "image"),
            cache,
        ),
        output_usd_per_token=max(
            _rate(pricing["completion"]),
            _optional_rate(pricing, "internal_reasoning"),
        ),
    )


def reservation_from_endpoints(endpoints: list[dict]) -> CallReservation:
    found: list[CallReservation] = []
    for endpoint in endpoints:
        pricing = endpoint.get("pricing")
        if not isinstance(pricing, dict):
            continue
        try:
            rates = token_rates(pricing)
        except MeasurementError:
            continue
        found.append(CallReservation(CONTEXT_TOKENS, OUTPUT_TOKENS, rates))
    if not found:
        raise MeasurementError("no_price")
    return max(found, key=lambda item: item.usd)


def _money(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise MeasurementError("invalid_cost")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise MeasurementError("invalid_cost") from None
    if not amount.is_finite() or amount < 0:
        raise MeasurementError("invalid_cost")
    return amount


def usage_cost(metadata: dict) -> Decimal:
    receipts = metadata.get("route_receipts")
    if not isinstance(receipts, list) or len(receipts) != 1:
        raise MeasurementError("unknown_cost_or_multiple_attempts")
    receipt = receipts[0]
    if not isinstance(receipt, dict):
        raise MeasurementError("invalid_cost")
    cost = _money(receipt.get("usage_cost_usd"))
    usage = metadata.get("usage")
    if isinstance(usage, dict) and "cost" in usage:
        direct = _money(usage.get("cost"))
        if direct != cost:
            raise MeasurementError("cost_disagrees")
        return direct
    return cost


def _text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _same_money(actual: object, expected: object) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    try:
        return Decimal(str(actual)) == Decimal(str(expected))
    except InvalidOperation:
        return False


def _purchases(rows: tuple) -> list:
    return [row for row in rows if getattr(row, "evidence", None) == "transaction"]


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return _text(value)
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _mark(passed: bool, expected: object, actual: object) -> bool | dict:
    """A passing check stays true. A failed check keeps the expected value
    beside the model's actual value."""

    if passed:
        return True
    return {"expected": _plain(expected), "actual": _plain(actual)}


def _merchant_first(checks: dict) -> dict:
    merchant = checks.get("merchant")
    if merchant is None or merchant is True:
        return checks
    ordered = {"merchant": merchant}
    ordered.update((key, value) for key, value in checks.items() if key != "merchant")
    return ordered


def _check_ok(value: object) -> bool:
    return value is True


def receipt_dop_checks(batch: ExtractionBatch) -> dict[str, bool | dict]:
    receipt = batch.receipt
    purchases = _purchases(batch.candidates)
    items = (
        ()
        if receipt is None
        else tuple(
            (item.description, _decimal_or_none(item.total)) for item in receipt.items
        )
    )
    merchant = None if receipt is None else receipt.merchant
    occurred = None if receipt is None else _iso(receipt.occurred_on)
    fiscal_names = ("rnc", "ncf", "ecf", "itbis")
    component_names = ("subtotal", "tax", "service", "tip")
    fiscal = (
        None
        if receipt is None
        else {name: getattr(receipt, name) for name in fiscal_names}
    )
    components = (
        None
        if receipt is None
        else {name: getattr(receipt, name) for name in component_names}
    )
    units = (
        []
        if receipt is None
        else [
            {"quantity": item.quantity, "unit_price": item.unit_price}
            for item in receipt.items
        ]
    )
    amount = purchases[0].amount if len(purchases) == 1 else None
    return _merchant_first(
        {
            "readable": _mark(batch.readable is True, True, batch.readable),
            "complete": _mark(batch.complete is True, True, batch.complete),
            "one_purchase_candidate": _mark(len(purchases) == 1, 1, len(purchases)),
            "merchant": _mark(
                receipt is not None and merchant == "Colmado Nube de Papel",
                "Colmado Nube de Papel",
                merchant,
            ),
            "date": _mark(
                receipt is not None and occurred == "2026-09-10",
                "2026-09-10",
                occurred,
            ),
            "currency": _mark(
                receipt is not None and receipt.currency == "DOP",
                "DOP",
                None if receipt is None else receipt.currency,
            ),
            "total": _mark(
                receipt is not None and _same_money(receipt.total, "250.50"),
                "250.50",
                None if receipt is None else receipt.total,
            ),
            "missing_fiscal_unknown": _mark(
                receipt is not None and all(value is None for value in fiscal.values()),
                {name: None for name in fiscal_names},
                fiscal,
            ),
            "unprinted_components_unknown": _mark(
                receipt is not None
                and all(value is None for value in components.values()),
                {name: None for name in component_names},
                components,
            ),
            "printed_items_exact": _mark(
                items == RECEIPT_ITEMS,
                [("Arroz", "150.00"), ("Leche", "100.50")],
                [(description, amount) for description, amount in items],
            ),
            "unprinted_item_units_unknown": _mark(
                receipt is not None
                and bool(receipt.items)
                and all(
                    item.quantity is None and item.unit_price is None
                    for item in receipt.items
                ),
                "null quantity and unit price on every printed item",
                units,
            ),
            "purchase_amount_exact": _mark(
                len(purchases) == 1 and _same_money(amount, "250.50"),
                "250.50",
                amount,
            ),
        }
    )


def unreadable_checks(batch: ExtractionBatch) -> dict[str, bool | dict]:
    receipt = batch.receipt
    observations = batch.observations
    invented = {}
    if receipt is not None:
        invented = {
            name: getattr(receipt, name)
            for name in BLANK_RECEIPT_FIELDS
            if getattr(receipt, name) is not None
        }
        if receipt.items:
            invented["items"] = len(receipt.items)
    blank = receipt is None or not invented
    observation_values = [
        {
            "amount": row.amount,
            "merchant": row.merchant,
            "currency": row.currency,
            "occurred_on": _iso(row.occurred_on),
        }
        for row in observations
        if row.amount is not None
        or row.merchant is not None
        or row.currency is not None
        or row.occurred_on is not None
    ]
    return {
        "marked_unreadable": _mark(batch.readable is False, False, batch.readable),
        "zero_candidates": _mark(len(batch.candidates) == 0, 0, len(batch.candidates)),
        "no_invented_receipt_values": _mark(blank, {}, invented),
        "no_invented_items": _mark(
            receipt is None or len(receipt.items) == 0,
            0,
            0 if receipt is None else len(receipt.items),
        ),
        "no_invented_observations": _mark(
            len(observations) == 0, 0, len(observations)
        ),
        "no_invented_observation_values": _mark(
            not observation_values, [], observation_values
        ),
    }


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _iso(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _order_actual(batch: ExtractionBatch, money_writes: int) -> dict:
    receipt = batch.receipt
    codes = [issue.code for issue in batch.issues]
    return {
        "readable": batch.readable is True,
        "complete": batch.complete is True,
        "payment_status": None if receipt is None else receipt.payment_status,
        "purchase_candidates": len(_purchases(batch.candidates)),
        "purchase_observations": len(_purchases(batch.observations)),
        "paid_purchase_date": None if receipt is None else _iso(receipt.occurred_on),
        "receipt_tax": None if receipt is None else receipt.tax,
        "estimated_tax": None if receipt is None else receipt.estimated_tax,
        "receipt_total": None if receipt is None else receipt.total,
        "issue": codes,
        "money_writes": money_writes,
    }


def _order_matches(actual: dict, expected: dict) -> dict[str, bool | dict]:
    checks: dict[str, bool | dict] = {}
    for key, wanted in expected.items():
        got = actual[key]
        if key in {"estimated_tax", "receipt_total", "receipt_tax"}:
            checks[key] = _mark(_same_money(got, wanted), wanted, got)
        elif key == "issue":
            codes = got if isinstance(got, list) else []
            checks[key] = _mark(
                wanted in codes
                and set(codes) <= {wanted, "no_financial_observations"},
                wanted,
                codes,
            )
        else:
            checks[key] = _mark(got == wanted, wanted, got)
    return checks


def score_checks(
    fixture: Fixture, batch: ExtractionBatch, money_writes: int
) -> dict[str, bool | dict]:
    if fixture.id == "receipt-dop":
        return receipt_dop_checks(batch)
    if fixture.id == "unreadable":
        return unreadable_checks(batch)
    if fixture.id == ORDER_FIXTURE:
        expected = fixture.entry.get("expected")
        if not isinstance(expected, dict):
            raise MeasurementError("missing_expected")
        return _order_matches(_order_actual(batch, money_writes), expected)
    return {"recognized": _mark(False, True, False)}


def _check_count(fixture: Fixture) -> int:
    if fixture.id == ORDER_FIXTURE and isinstance(fixture.entry.get("expected"), dict):
        return len(fixture.entry["expected"])
    if fixture.id == "receipt-dop":
        return len(receipt_dop_checks(ExtractionBatch(candidates=())))
    if fixture.id == "unreadable":
        return len(unreadable_checks(ExtractionBatch(candidates=())))
    return 1


def require_api_key() -> None:
    if os.getenv("APP_ENV", "").strip().lower() in HOSTED_ENVS:
        raise MeasurementError("hosted_environment")
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        raise MeasurementError("missing_api_key")


def _require_declared_checks(fixture_id: str, entry: dict) -> None:
    if fixture_id == "receipt-dop" and "expected_checks" in entry:
        names = set(receipt_dop_checks(ExtractionBatch(candidates=())))
        if set(entry["expected_checks"]) != names:
            raise MeasurementError("check_manifest_drift")
    if fixture_id == "unreadable" and "expected_checks" in entry:
        names = set(unreadable_checks(ExtractionBatch(candidates=())))
        if set(entry["expected_checks"]) != names:
            raise MeasurementError("check_manifest_drift")
    if fixture_id == ORDER_FIXTURE:
        expected = entry.get("expected")
        if not isinstance(expected, dict):
            raise MeasurementError("missing_expected")
        sample = _order_actual(ExtractionBatch(candidates=()), 0)
        if not set(expected) <= set(sample):
            raise MeasurementError("check_manifest_drift")


def load_fixtures(manifest_path: Path, root: Path) -> tuple[dict, tuple[Fixture, ...]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = manifest.get("model")
    if not isinstance(model, str) or not model or ":" in model:
        raise MeasurementError("model_variant")
    if manifest.get("retries") not in (0, None):
        raise MeasurementError("retries_forbidden")
    fixtures: list[Fixture] = []
    seen: set[str] = set()
    for entry in manifest["fixtures"]:
        fixture_id = entry["id"]
        if fixture_id in seen:
            raise MeasurementError("duplicate_fixture")
        seen.add(fixture_id)
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise MeasurementError("fixture_path_outside_repository")
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise MeasurementError("fixture_checksum_mismatch") from None
        if digest != entry["sha256"]:
            raise MeasurementError("fixture_checksum_mismatch")
        _require_declared_checks(fixture_id, entry)
        fixtures.append(Fixture(fixture_id, path, digest, entry))
    if not fixtures:
        raise MeasurementError("missing_fixtures")
    return manifest, tuple(fixtures)


def _resolve_output(path: Path, evidence_root: Path) -> Path:
    resolved = path.resolve()
    root = evidence_root.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise MeasurementError("output_outside_evidence")
    return resolved


def _claim(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write("{}\n")
    except FileExistsError:
        raise MeasurementError("output_exists") from None


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()


def _surface() -> dict:
    observed = model_facing_surface(REPO)
    try:
        return {name: observed[name] for name in sorted(DOCUMENT_EXTRACTION_OWNERS)}
    except KeyError:
        raise MeasurementError("surface_missing") from None


def _profile() -> dict:
    profile = OPENROUTER_PROFILES["document_extraction"]
    raw_timeout = os.getenv(
        "ARGUS_OPENROUTER_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS", ""
    ).strip()
    timeout = profile.timeout_seconds
    if raw_timeout:
        try:
            timeout = int(raw_timeout)
        except ValueError:
            raise MeasurementError("profile_drift") from None
    if (
        profile.max_retries != 0
        or profile.max_tokens != OUTPUT_TOKENS
        or timeout != TIMEOUT_SECONDS
        or timeout <= 0
    ):
        raise MeasurementError("profile_drift")
    return {
        "max_tokens": profile.max_tokens,
        "timeout_seconds": timeout,
        "max_retries": profile.max_retries,
    }


def _regression(baseline: dict, cases: list[dict], baseline_path: str) -> dict:
    recorded = {
        case["fixture"]: case.get("checks", {})
        for case in baseline.get("cases", [])
        if isinstance(case, dict)
    }
    regressed: list[str] = []
    held: dict[str, bool] = {}
    unavailable: list[str] = []
    for case in cases:
        previous = recorded.get(case["fixture"])
        if not isinstance(previous, dict):
            continue
        if case["status"] == "unavailable":
            unavailable.append(case["fixture"])
            continue
        drifted = sorted(
            key
            for key, value in previous.items()
            if value is True and case["checks"].get(key) is not True
        )
        held[case["fixture"]] = not drifted
        regressed.extend(f"{case['fixture']}.{key}" for key in drifted)
    return {
        "baseline_scorecard": baseline_path,
        "held": held,
        "regressed": regressed,
        "unavailable": unavailable,
    }


def _case(
    fixture: Fixture,
    status: str,
    checks: dict,
    cost: Decimal | None,
    provider_error: dict | None = None,
) -> dict:
    case = {
        "fixture": fixture.id,
        "fixture_sha256": fixture.sha256,
        "status": status,
        "checks": checks,
        "usage": None if cost is None else {"cost": _text(cost)},
        "actual_cost_usd": None if cost is None else _text(cost),
    }
    if provider_error is not None:
        case["provider_error"] = provider_error
    return case


def _provider_error(exc: BaseException) -> dict | None:
    response = _http_response(exc)
    if response is None:
        return None
    status = getattr(response, "status_code", None)
    message, code = _provider_error_fields(response)
    return {
        "http_status": status if isinstance(status, int) else None,
        "message": message,
        "code": code,
    }


def _http_response(exc: BaseException):
    pending = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if (
            current is None
            or id(current) in seen
            or not isinstance(current, BaseException)
        ):
            continue
        seen.add(id(current))
        response = getattr(current, "response", None)
        if isinstance(getattr(response, "status_code", None), int) and callable(
            getattr(response, "json", None)
        ):
            return response
        pending.append(current.__cause__)
        pending.append(current.__context__)
    return None


def _provider_error_fields(response) -> tuple[str | None, str | int | None]:
    try:
        payload = response.json()
    except Exception:
        return None, None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None, None
    return _provider_message(error.get("message")), _provider_code(error.get("code"))


def _provider_message(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _redact_api_key(value)


def _provider_code(value: object) -> str | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _redact_api_key(value)
    return None


def _redact_api_key(value: str) -> str:
    secret = os.environ.get("OPENROUTER_API_KEY")
    if secret:
        return value.replace(secret, "")
    return value


def _scorecard(
    manifest: dict,
    fixtures: tuple[Fixture, ...],
    cases: list[dict],
    spent: Decimal,
    stop: str | None,
    baseline: dict,
    baseline_path: str,
    profile: dict,
) -> dict:
    comparison = _regression(baseline, cases, baseline_path)
    check_passed = sum(
        sum(_check_ok(value) for value in case["checks"].values()) for case in cases
    )
    check_failed = sum(
        sum(not _check_ok(value) for value in case["checks"].values())
        for case in cases
    )
    check_unavailable = sum(
        _check_count(fixture)
        for fixture, case in zip(fixtures, cases, strict=False)
        if case["status"] == "unavailable"
    )
    complete = stop is None and len(cases) == len(fixtures)
    passed = (
        complete
        and all(case["status"] == "passed" for case in cases)
        and not comparison["regressed"]
        and not comparison["unavailable"]
    )
    provider_error = next(
        (
            case["provider_error"]
            for case in cases
            if isinstance(case.get("provider_error"), dict)
        ),
        None,
    )
    scorecard = {
        "scope": "document_extraction",
        "status": "passed" if passed else "failed",
    }
    if provider_error is not None:
        scorecard["provider_error"] = provider_error
    scorecard.update(
        {
            "candidate_sha": _git_head(),
            "surface": _surface(),
            "totals": {
                "passed": sum(case["status"] == "passed" for case in cases),
                "failed": sum(case["status"] == "failed" for case in cases),
                "unavailable": sum(case["status"] == "unavailable" for case in cases),
            },
            "checks": {
                "passed": check_passed,
                "failed": check_failed,
                "unavailable": check_unavailable,
            },
            "model": manifest["model"],
            "profile": profile,
            "privacy": openrouter_provider_policy(),
            "known_actual_cost_usd": _text(spent),
            "money_writes": 0,
            "stop_reason": stop,
            "comparison": comparison,
            "cases": cases,
        }
    )
    return scorecard


async def _invoke(fn: Callable, *args):
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


def _load_extractor():
    from argus.domain.ingestion.documents.config import DocumentExtractionSettings
    from argus.domain.ingestion.documents.extractor import DocumentExtractor

    return DocumentExtractor, DocumentExtractionSettings


async def _default_extract(fixture: Fixture, model: str) -> ExtractionBatch:
    os.environ["CUADRAO_VISION_MODEL"] = model
    os.environ["ARGUS_VISION_MODEL"] = model
    extractor_cls, settings_cls = _load_extractor()
    extractor = extractor_cls(settings_cls(enabled=True))
    media_type = mimetypes.guess_type(fixture.path.name)[0] or "application/octet-stream"
    return await extractor.extract(
        fixture.path.read_bytes(),
        fixture.path.name,
        media_type,
        "document-measurement",
        datetime.now(timezone.utc),
    )


async def _default_endpoints(model: str) -> list[dict]:
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"https://openrouter.ai/api/v1/models/{quote(model, safe='/')}/endpoints"
        )
        response.raise_for_status()
        return response.json()["data"]["endpoints"]


async def run_measurement(
    *,
    manifest_path: Path,
    output: Path,
    fixture_root: Path,
    extract: Callable[..., Awaitable[ExtractionBatch] | ExtractionBatch] | None = None,
    fetch_endpoints: Callable[..., Awaitable[list[dict]] | list[dict]] | None = None,
) -> dict:
    manifest, fixtures = load_fixtures(manifest_path, fixture_root)
    require_api_key()
    if output.exists():
        raise MeasurementError("output_exists")
    baseline_rel = manifest.get("baseline_scorecard")
    if not isinstance(baseline_rel, str) or not baseline_rel:
        raise MeasurementError("baseline_missing")
    baseline_path = fixture_root / baseline_rel
    if not baseline_path.is_file():
        raise MeasurementError("baseline_missing")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    profile = _profile()
    if extract is None:
        _load_extractor()
    endpoints = await _invoke(fetch_endpoints or _default_endpoints, manifest["model"])
    reservation = reservation_from_endpoints(endpoints)
    ledger = SpendLedger(SPEND_CAP, MAX_CALLS, reservation)
    extract_fn = extract or _default_extract
    cases: list[dict] = []
    stop = None
    claimed = False
    for fixture in fixtures:
        try:
            ledger.authorize(fixture.id)
        except MeasurementError as error:
            if error.code in {"spend_cap", "call_limit", "already_attempted"}:
                stop = error.code
                break
            raise
        if not claimed:
            _claim(output)
            claimed = True
        try:
            batch = await _invoke(extract_fn, fixture, manifest["model"])
            cost = usage_cost(batch.metadata)
        except MeasurementError as error:
            cases.append(_case(fixture, "unavailable", {}, None))
            stop = error.code
            break
        except Exception as exc:
            cases.append(_case(fixture, "unavailable", {}, None, _provider_error(exc)))
            stop = "provider_failed"
            break
        ledger.record(cost)
        checks = score_checks(fixture, batch, 0)
        status = (
            "passed"
            if all(_check_ok(value) for value in checks.values())
            else "failed"
        )
        cases.append(_case(fixture, status, checks, cost))
        if cost > reservation.usd or ledger.spent_usd > ledger.cap_usd:
            stop = "request_price_bound_exceeded"
            break
    if not claimed:
        raise MeasurementError(stop or "spend_cap")
    scorecard = _scorecard(
        manifest,
        fixtures,
        cases,
        ledger.spent_usd,
        stop,
        baseline,
        baseline_rel,
        profile,
    )
    output.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    return scorecard


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run three document extractions under a five dollar cap."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE_ROOT)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    fixture_root: Path | None = None,
    extract: Callable | None = None,
    fetch_endpoints: Callable | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        output = _resolve_output(args.output, args.evidence_root)
        scorecard = asyncio.run(
            run_measurement(
                manifest_path=args.manifest,
                output=output,
                fixture_root=fixture_root or REPO,
                extract=extract,
                fetch_endpoints=fetch_endpoints,
            )
        )
    except MeasurementError as error:
        print(error.code, file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": scorecard["status"],
                "totals": scorecard["totals"],
                "checks": scorecard["checks"],
                "known_actual_cost_usd": scorecard["known_actual_cost_usd"],
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0 if scorecard["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Literal, TypeVar, cast

import httpx
from langchain_openrouter import ChatOpenRouter
from loguru import logger
from pydantic import BaseModel

from argus.agent_runtime import turn_execution
from argus.env import load_project_dotenv
from argus.llm import openrouter_model_env as model_policy
from argus.llm.openrouter_key_policy import resolve_openrouter_api_key
from argus.llm.openrouter_tasks import (
    OPENROUTER_PROFILES,
    OPENROUTER_TASK_MODEL_TIERS,
    OpenRouterModelTier,
    OpenRouterProfile,
    OpenRouterReasoningEffort,
    OpenRouterTask,
)
from argus.llm.openrouter_usage import (
    merge_openrouter_token_usage,
    normalize_openrouter_token_usage,
    normalize_openrouter_usage_cost,
    openrouter_token_usage_from_payload,
    openrouter_usage_cost_from_payload,
)
from argus.llm.tool_call_receipts import current_tool_call_receipt_scope
from argus.llm.tool_call_receipts import (
    tool_call_receipt_scope as tool_call_receipt_scope,
)
from argus.log_sink import exception_origin

load_project_dotenv()

_OpenRouterRetryAttempt = tuple[OpenRouterTask, float, str, Literal["json_schema", "chat_model"], str | None, list[str] | None]

_REQUEST_GUARD: ContextVar[Callable[[OpenRouterTask, dict[str, object]], dict[str, object]] | None] = ContextVar("openrouter_request_guard", default=None)


@contextmanager
def openrouter_request_guard(guard: Callable[[OpenRouterTask, dict[str, object]], dict[str, object]]) -> Iterator[None]:
    token = _REQUEST_GUARD.set(guard)
    try:
        yield
    finally:
        _REQUEST_GUARD.reset(token)


def _guard_request(task: OpenRouterTask, payload: dict[str, object]) -> dict[str, object]:
    guard = _REQUEST_GUARD.get()
    return guard(task, payload) if guard else payload

SchemaModelT = TypeVar("SchemaModelT", bound=BaseModel)


@dataclass(frozen=True)
class OpenRouterRouteReceipt:
    task: OpenRouterTask
    tier: OpenRouterModelTier
    model: str
    fallback_model: str
    mode: Literal["json_schema", "chat_model"]
    schema_name: str | None
    latency_ms: int
    outcome: Literal["succeeded", "failed", "skipped"]
    failure_mode: str | None = None
    fallback_used: bool = False
    token_usage: dict[str, int] | None = None
    usage_cost_usd: float | None = None
    context_packet_ids: list[str] = field(default_factory=list)
    repair_effect: dict[str, object] = field(default_factory=dict)
    created_at: str = ""

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "task": self.task,
            "tier": self.tier,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "mode": self.mode,
            "schema_name": self.schema_name,
            "latency_ms": self.latency_ms,
            "outcome": self.outcome,
            "failure_mode": self.failure_mode,
            "fallback_used": self.fallback_used,
            "token_usage": self.token_usage,
            "usage_cost_usd": self.usage_cost_usd,
            "context_packet_ids": list(self.context_packet_ids),
            "created_at": self.created_at,
        }
        if self.repair_effect:
            result["repair_effect"] = dict(self.repair_effect)
        return result


_ROUTE_RECEIPTS: list[OpenRouterRouteReceipt] = []
_ROUTE_RECEIPTS_LOCK = Lock()
_ROUTE_RECEIPT_CAPTURE: ContextVar[list[OpenRouterRouteReceipt] | None] = ContextVar(
    "openrouter_route_receipt_capture",
    default=None,
)


_TIER_PRIMARY_ENV = model_policy.TIER_PRIMARY_ENV
_TIER_FALLBACK_ENV = model_policy.TIER_FALLBACK_ENV

_VALID_REASONING_EFFORTS = frozenset(("xhigh", "high", "medium", "low", "minimal", "none"))
_REASONING_EFFORT_ENV_BY_TASK: dict[OpenRouterTask, str] = {
    "interpretation": "ARGUS_STRUCTURED_REASONING_EFFORT",
    "capability_conflict": "ARGUS_CAPABILITY_REASONING_EFFORT",
}
_PROMPT_CACHE_STRUCTURED_ARTIFACT_TASKS = frozenset(("interpretation", "interpretation_repair", "field_fidelity", "capability_conflict"))


def openrouter_model_tier_for_task(task: OpenRouterTask | None) -> OpenRouterModelTier:
    if task is None:
        return "chat"
    return OPENROUTER_TASK_MODEL_TIERS[task]


def resolve_openrouter_model(
    model_name: str | None = None,
    fallback: bool = False,
    *,
    task: OpenRouterTask | None = None,
) -> str:
    """
    Resolves the model name to use for the task-specific model tier.
    """
    if model_name:
        return model_name

    tier = openrouter_model_tier_for_task(task)
    env_names = _TIER_FALLBACK_ENV[tier] if fallback else _TIER_PRIMARY_ENV[tier]
    return _first_configured_model(env_names)


def openrouter_model_candidates(
    model_name: str | None = None,
    *,
    task: OpenRouterTask = "interpretation",
) -> list[str]:
    if model_name:
        return [model_name]
    tier = openrouter_model_tier_for_task(task)
    return _unique_nonempty(
        [
            _env_model_value(name)
            for name in (*_TIER_PRIMARY_ENV[tier], *_TIER_FALLBACK_ENV[tier])
        ]
    )


def openrouter_structured_model_candidates(
    model_name: str | None = None,
    *,
    task: OpenRouterTask = "interpretation",
) -> list[str]:
    return openrouter_model_candidates(model_name, task=task)


def _env_model_value(name: str) -> str:
    return os.getenv(name, "").strip()


def _first_configured_model(env_names: tuple[str, ...]) -> str:
    for name in env_names:
        value = _env_model_value(name)
        if value:
            return value
    return ""


def _unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def build_openrouter_model(
    task: OpenRouterTask,
    *,
    model_name: str | None = None,
) -> ChatOpenRouter | None:
    """
    Builds a ChatOpenRouter instance for the given task.
    """
    api_key = resolve_openrouter_api_key()
    if not api_key:
        logger.warning("OpenRouter unavailable; missing API key", llm_task=task)
        return None

    profile = openrouter_profile_for_task(task)
    resolved_model = resolve_openrouter_model(model_name, task=task)
    if not resolved_model:
        logger.warning("OpenRouter unavailable; no model configured", llm_task=task)
        return None

    return ChatOpenRouter(
        model_name=resolved_model,
        **model_policy.model_sampling_parameters(resolved_model, profile.temperature),
        max_tokens=profile.max_tokens,
        timeout=profile.timeout_seconds,
        max_retries=profile.max_retries,
        openrouter_api_key=api_key,
    )


def openrouter_task_timeout_seconds(task: OpenRouterTask) -> float:
    return float(openrouter_profile_for_task(task).timeout_seconds)


def openrouter_profile_for_task(task: OpenRouterTask) -> OpenRouterProfile:
    profile = OPENROUTER_PROFILES[task]
    timeout_override = _task_timeout_override_seconds(task)
    reasoning_effort = _task_reasoning_effort_override(task)
    if timeout_override is None and reasoning_effort is None:
        return profile
    return replace(
        profile,
        timeout_seconds=timeout_override or profile.timeout_seconds,
        reasoning_effort=reasoning_effort or profile.reasoning_effort,
    )


def _task_timeout_override_seconds(task: OpenRouterTask) -> int | None:
    raw_value = os.getenv(f"ARGUS_OPENROUTER_{task.upper()}_TIMEOUT_SECONDS", "")
    if not raw_value.strip():
        return None
    try:
        timeout_seconds = int(raw_value)
    except ValueError:
        logger.warning(
            "Ignoring invalid OpenRouter task timeout override",
            llm_task=task,
            timeout_env_value=raw_value,
        )
        return None
    if timeout_seconds <= 0:
        logger.warning(
            "Ignoring non-positive OpenRouter task timeout override",
            llm_task=task,
            timeout_env_value=raw_value,
        )
        return None
    return timeout_seconds


def _task_reasoning_effort_override(task: OpenRouterTask) -> OpenRouterReasoningEffort | None:
    env_name = _REASONING_EFFORT_ENV_BY_TASK.get(task)
    raw_value = os.getenv(env_name, "") if env_name else ""
    normalized = raw_value.strip().lower()
    if not normalized:
        return None
    if normalized in _VALID_REASONING_EFFORTS:
        return cast(OpenRouterReasoningEffort, normalized)
    logger.warning("Ignoring invalid OpenRouter reasoning effort override", llm_task=task, reasoning_effort_env_value=raw_value)
    return None


def record_openrouter_route_receipt(
    *,
    task: OpenRouterTask,
    model_name: str | None,
    mode: Literal["json_schema", "chat_model"],
    schema_name: str | None,
    latency_ms: int,
    outcome: Literal["succeeded", "failed", "skipped"],
    failure_mode: str | None = None,
    token_usage: dict[str, int] | None = None,
    usage_cost_usd: float | None = None,
    context_packet_ids: list[str] | None = None,
) -> OpenRouterRouteReceipt:
    tier = openrouter_model_tier_for_task(task)
    fallback_model = resolve_openrouter_model(fallback=True, task=task)
    resolved_model = resolve_openrouter_model(model_name, task=task)
    receipt = OpenRouterRouteReceipt(
        task=task,
        tier=tier,
        model=resolved_model,
        fallback_model=fallback_model,
        mode=mode,
        schema_name=schema_name,
        latency_ms=max(0, int(latency_ms)),
        outcome=outcome,
        failure_mode=failure_mode,
        token_usage=normalize_openrouter_token_usage(token_usage),
        usage_cost_usd=normalize_openrouter_usage_cost(usage_cost_usd),
        context_packet_ids=_normalized_context_packet_ids(context_packet_ids),
        repair_effect=current_tool_call_receipt_scope(),
        fallback_used=bool(
            fallback_model
            and resolved_model == fallback_model
            and resolved_model != resolve_openrouter_model(task=task)
        ),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with _ROUTE_RECEIPTS_LOCK:
        _ROUTE_RECEIPTS.append(receipt)
    capture = _ROUTE_RECEIPT_CAPTURE.get()
    if capture is not None:
        capture.append(receipt)
    fields = receipt.as_dict()
    # Render displays the message, not Loguru extras. Both projections derive
    # from the receipt; never dump the logger's potentially sensitive context.
    logger.bind(
        llm_task=fields["task"],
        llm_tier=fields["tier"],
        **{key: value for key, value in fields.items() if key not in {"task", "tier"}},
    ).info("OpenRouter route receipt {}", json.dumps(fields, separators=(",", ":")))
    return receipt


def annotate_latest_openrouter_route_receipt(
    *,
    task: OpenRouterTask,
    schema_name: str,
    repair_effect: dict[str, object],
) -> bool:
    """Attach value-free repair evidence to this request's latest matching call."""

    capture = _ROUTE_RECEIPT_CAPTURE.get()
    if capture is None:
        return False
    scope = current_tool_call_receipt_scope()
    for receipt in reversed(capture):
        if receipt.task == task and receipt.schema_name == schema_name:
            if scope and receipt.repair_effect.get("tool_call_id") != scope["tool_call_id"]:
                continue
            identity = {
                key: receipt.repair_effect[key]
                for key in ("tool_call_id", "tool_name")
                if key in receipt.repair_effect
            }
            receipt.repair_effect.clear()
            receipt.repair_effect.update(repair_effect)
            receipt.repair_effect.update(identity)
            fields = {
                "task": receipt.task,
                "schema_name": receipt.schema_name,
                "receipt_created_at": receipt.created_at,
                "repair_effect": dict(receipt.repair_effect),
            }
            logger.bind(llm_task=receipt.task, llm_schema_name=receipt.schema_name).info(
                "OpenRouter repair effect {}", json.dumps(fields, separators=(",", ":"))
            )
            return True
    return False


def _reserve_openrouter_attempt(task: OpenRouterTask, timeout_seconds: float, model_name: str, mode: Literal["json_schema", "chat_model"], schema_name: str | None, context_packet_ids: list[str] | None) -> turn_execution.ProviderCallPermit | None:
    if (permit := turn_execution.reserve_provider_call(task, timeout_seconds)) is not None:
        return permit
    record_openrouter_route_receipt(task=task, model_name=model_name, mode=mode, schema_name=schema_name, latency_ms=0, outcome="skipped", failure_mode=turn_execution.turn_budget_block_reason(), context_packet_ids=context_packet_ids)
    return None


def get_openrouter_route_receipts() -> list[OpenRouterRouteReceipt]:
    with _ROUTE_RECEIPTS_LOCK:
        return list(_ROUTE_RECEIPTS)


def clear_openrouter_route_receipts() -> None:
    with _ROUTE_RECEIPTS_LOCK:
        _ROUTE_RECEIPTS.clear()


def begin_openrouter_route_receipt_capture() -> Token[list[OpenRouterRouteReceipt] | None]:
    return _ROUTE_RECEIPT_CAPTURE.set([])


def end_openrouter_route_receipt_capture(
    token: Token[list[OpenRouterRouteReceipt] | None],
) -> list[OpenRouterRouteReceipt]:
    receipts = list(_ROUTE_RECEIPT_CAPTURE.get() or [])
    _ROUTE_RECEIPT_CAPTURE.reset(token)
    return receipts


def summarize_openrouter_route_receipts(
    receipts: Iterable[OpenRouterRouteReceipt] | None = None,
) -> dict[str, object]:
    """
    Builds a small internal latency/failure waterfall from existing receipts.

    This is diagnostic only. It must not bypass semantic arbitration,
    capability validation, context replayability, or fallback observability.
    """

    active_receipts = list(receipts) if receipts is not None else get_openrouter_route_receipts()
    route_waterfall: list[dict[str, object]] = []
    for receipt in active_receipts:
        row: dict[str, object] = {
            "task": receipt.task,
            "tier": receipt.tier,
            "model": receipt.model,
            "fallback_model": receipt.fallback_model,
            "latency_ms": receipt.latency_ms,
            "outcome": receipt.outcome,
            "failure_mode": receipt.failure_mode,
            "fallback_used": receipt.fallback_used,
            "context_packet_ids": list(receipt.context_packet_ids),
        }
        if receipt.repair_effect:
            row["repair_effect"] = dict(receipt.repair_effect)
        route_waterfall.append(row)
    slowest = max(active_receipts, key=lambda receipt: receipt.latency_ms, default=None)
    return {
        "receipt_count": len(active_receipts),
        "total_latency_ms": sum(receipt.latency_ms for receipt in active_receipts),
        "failure_count": sum(1 for receipt in active_receipts if receipt.outcome == "failed"),
        "fallback_count": sum(1 for receipt in active_receipts if receipt.fallback_used),
        "slowest_task": slowest.task if slowest is not None else None,
        "slowest_latency_ms": slowest.latency_ms if slowest is not None else 0,
        "context_packet_ids": _unique_context_packet_ids(active_receipts),
        "token_usage": _merged_receipt_token_usage(active_receipts),
        "route_waterfall": route_waterfall,
    }


async def invoke_openrouter_json_schema(
    *,
    task: OpenRouterTask,
    messages: Sequence[Mapping[str, object]],
    schema_model: type[SchemaModelT],
    schema_name: str,
    model_name: str | None = None,
    context_packet_ids: list[str] | None = None,
) -> SchemaModelT | None:
    started_at = time.perf_counter()
    api_key = resolve_openrouter_api_key()
    if not api_key:
        logger.warning("OpenRouter unavailable; missing API key", llm_task=task)
        record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=_elapsed_ms(started_at),
            outcome="skipped",
            failure_mode="missing_api_key",
            context_packet_ids=context_packet_ids,
        )
        return None

    candidate_models = openrouter_structured_model_candidates(model_name, task=task)
    if not candidate_models:
        logger.warning("OpenRouter unavailable; no model configured", llm_task=task)
        record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=_elapsed_ms(started_at),
            outcome="skipped",
            failure_mode="missing_model",
            context_packet_ids=context_packet_ids,
        )
        return None

    profile = openrouter_profile_for_task(task)
    last_exc: Exception | None = None
    for index, candidate_model in enumerate(candidate_models):
        attempt_started_at = time.perf_counter()
        if (permit := _reserve_openrouter_attempt(task, profile.timeout_seconds, candidate_model, "json_schema", schema_name, context_packet_ids)) is None:
            return None
        payload = _json_schema_payload(
            model=candidate_model,
            messages=messages,
            schema_model=schema_model,
            schema_name=schema_name,
            profile=profile,
        )
        data: dict[str, object] = {}
        try:
            async with httpx.AsyncClient(timeout=permit.timeout_seconds) as client:
                if (response := await asyncio.wait_for(
                    _post_openrouter_json_schema(
                        client=client,
                        api_key=api_key,
                        payload=payload,
                        retry_attempt=(task, profile.timeout_seconds, candidate_model, "json_schema", schema_name, context_packet_ids),
                    ),
                    timeout=permit.timeout_seconds,
                )) is None:
                    return None
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Invalid OpenRouter response")
            data = body
            _raise_openrouter_payload_error(data)
            if task == "document_extraction":
                choices = data.get("choices")
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict) or choices[0].get("finish_reason") != "stop":
                    raise ValueError("Incomplete document response")
            content = _openrouter_message_content(data)
            if not content:
                raise ValueError(
                    "OpenRouter JSON schema response did not include content"
                )
            result = schema_model.model_validate_json(
                _json_content_without_code_fences(content)
            )
        except Exception as exc:
            last_exc = exc
            record_openrouter_route_receipt(
                task=task,
                model_name=candidate_model,
                mode="json_schema",
                schema_name=schema_name,
                latency_ms=_elapsed_ms(attempt_started_at),
                outcome="failed",
                failure_mode=type(exc).__name__,
                token_usage=openrouter_token_usage_from_payload(data),
                usage_cost_usd=openrouter_usage_cost_from_payload(data),
                context_packet_ids=context_packet_ids,
            )
            if index + 1 < len(candidate_models):
                log_openrouter_failure(
                    task=task,
                    model_name=candidate_model,
                    exc=exc,
                    message="JSON schema completion failed; trying next configured model",
                )
                continue
            raise
        record_openrouter_route_receipt(
            task=task,
            model_name=candidate_model,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=_elapsed_ms(attempt_started_at),
            outcome="succeeded",
            token_usage=openrouter_token_usage_from_payload(data),
            usage_cost_usd=openrouter_usage_cost_from_payload(data),
            context_packet_ids=context_packet_ids,
        )
        return result
    if last_exc is not None:
        raise last_exc
    return None


async def invoke_openrouter_chat_completion(
    *,
    task: OpenRouterTask,
    messages: Sequence[Mapping[str, object]],
    model_name: str | None = None,
    context_packet_ids: list[str] | None = None,
) -> str | None:
    started_at = time.perf_counter()
    api_key = resolve_openrouter_api_key()
    if not api_key:
        logger.warning("OpenRouter unavailable; missing API key", llm_task=task)
        record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="chat_model",
            schema_name=None,
            latency_ms=_elapsed_ms(started_at),
            outcome="skipped",
            failure_mode="missing_api_key",
            context_packet_ids=context_packet_ids,
        )
        return None

    candidate_models = openrouter_model_candidates(model_name, task=task)
    if not candidate_models:
        logger.warning("OpenRouter unavailable; no model configured", llm_task=task)
        record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="chat_model",
            schema_name=None,
            latency_ms=_elapsed_ms(started_at),
            outcome="skipped",
            failure_mode="missing_model",
            context_packet_ids=context_packet_ids,
        )
        return None

    profile = openrouter_profile_for_task(task)
    last_exc: Exception | None = None
    for index, candidate_model in enumerate(candidate_models):
        attempt_started_at = time.perf_counter()
        if (permit := _reserve_openrouter_attempt(task, profile.timeout_seconds, candidate_model, "chat_model", None, context_packet_ids)) is None:
            return None
        payload: dict[str, object] = {
            "model": candidate_model,
            "messages": messages,
            **model_policy.model_sampling_parameters(candidate_model, profile.temperature),
            "max_tokens": profile.max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=permit.timeout_seconds) as client:
                response = await asyncio.wait_for(
                    _post_openrouter_json_schema(
                        client=client,
                        api_key=api_key,
                        payload=payload,
                        retry_attempt=(task, profile.timeout_seconds, candidate_model, "chat_model", None, context_packet_ids),
                    ),
                    timeout=permit.timeout_seconds,
                )
                if response is None:
                    return None
                data = response.json()
                _raise_openrouter_payload_error(data)
        except Exception as exc:
            last_exc = exc
            record_openrouter_route_receipt(
                task=task,
                model_name=candidate_model,
                mode="chat_model",
                schema_name=None,
                latency_ms=_elapsed_ms(attempt_started_at),
                outcome="failed",
                failure_mode=type(exc).__name__,
                context_packet_ids=context_packet_ids,
            )
            if index + 1 < len(candidate_models):
                log_openrouter_failure(
                    task=task,
                    model_name=candidate_model,
                    exc=exc,
                    message="Chat completion failed; trying next configured model",
                )
                continue
            raise

        content = _openrouter_message_content(data).strip()
        token_usage = openrouter_token_usage_from_payload(data)
        usage_cost_usd = openrouter_usage_cost_from_payload(data)
        if not content:
            record_openrouter_route_receipt(
                task=task,
                model_name=candidate_model,
                mode="chat_model",
                schema_name=None,
                latency_ms=_elapsed_ms(attempt_started_at),
                outcome="failed",
                failure_mode="empty_response",
                token_usage=token_usage,
                usage_cost_usd=usage_cost_usd,
                context_packet_ids=context_packet_ids,
            )
            if index + 1 < len(candidate_models):
                continue
            return None
        record_openrouter_route_receipt(
            task=task,
            model_name=candidate_model,
            mode="chat_model",
            schema_name=None,
            latency_ms=_elapsed_ms(attempt_started_at),
            outcome="succeeded",
            token_usage=token_usage,
            usage_cost_usd=usage_cost_usd,
            context_packet_ids=context_packet_ids,
        )
        return content
    if last_exc is not None:
        raise last_exc
    return None


def invoke_openrouter_json_schema_sync(
    *,
    task: OpenRouterTask,
    messages: Sequence[Mapping[str, object]],
    schema_model: type[SchemaModelT],
    schema_name: str,
    model_name: str | None = None,
    context_packet_ids: list[str] | None = None,
) -> SchemaModelT | None:
    started_at = time.perf_counter()
    api_key = resolve_openrouter_api_key()
    if not api_key:
        logger.warning("OpenRouter unavailable; missing API key", llm_task=task)
        record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=_elapsed_ms(started_at),
            outcome="skipped",
            failure_mode="missing_api_key",
            context_packet_ids=context_packet_ids,
        )
        return None

    candidate_models = openrouter_structured_model_candidates(model_name, task=task)
    if not candidate_models:
        logger.warning("OpenRouter unavailable; no model configured", llm_task=task)
        record_openrouter_route_receipt(
            task=task,
            model_name=model_name,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=_elapsed_ms(started_at),
            outcome="skipped",
            failure_mode="missing_model",
            context_packet_ids=context_packet_ids,
        )
        return None

    profile = openrouter_profile_for_task(task)
    last_exc: Exception | None = None
    for index, candidate_model in enumerate(candidate_models):
        attempt_started_at = time.perf_counter()
        if (permit := _reserve_openrouter_attempt(task, profile.timeout_seconds, candidate_model, "json_schema", schema_name, context_packet_ids)) is None:
            return None
        payload = _json_schema_payload(
            model=candidate_model,
            messages=messages,
            schema_model=schema_model,
            schema_name=schema_name,
            profile=profile,
        )
        try:
            with httpx.Client(timeout=permit.timeout_seconds) as client:
                response = _post_openrouter_json_schema_sync(
                    client=client,
                    api_key=api_key,
                    payload=payload,
                    retry_attempt=(task, profile.timeout_seconds, candidate_model, "json_schema", schema_name, context_packet_ids),
                )
            if response is None:
                return None
            data = response.json()
            _raise_openrouter_payload_error(data)
            content = _openrouter_message_content(data)
            if not content:
                raise ValueError(
                    "OpenRouter JSON schema response did not include content"
                )
            result = schema_model.model_validate_json(
                _json_content_without_code_fences(content)
            )
        except Exception as exc:
            last_exc = exc
            record_openrouter_route_receipt(
                task=task,
                model_name=candidate_model,
                mode="json_schema",
                schema_name=schema_name,
                latency_ms=_elapsed_ms(attempt_started_at),
                outcome="failed",
                failure_mode=type(exc).__name__,
                context_packet_ids=context_packet_ids,
            )
            if index + 1 < len(candidate_models):
                log_openrouter_failure(
                    task=task,
                    model_name=candidate_model,
                    exc=exc,
                    message="JSON schema completion failed; trying next configured model",
                )
                continue
            raise
        record_openrouter_route_receipt(
            task=task,
            model_name=candidate_model,
            mode="json_schema",
            schema_name=schema_name,
            latency_ms=_elapsed_ms(attempt_started_at),
            outcome="succeeded",
            token_usage=openrouter_token_usage_from_payload(data),
            usage_cost_usd=openrouter_usage_cost_from_payload(data),
            context_packet_ids=context_packet_ids,
        )
        return result
    if last_exc is not None:
        raise last_exc
    return None


def _normalized_context_packet_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        packet_id = str(value or "").strip()
        if packet_id and packet_id not in normalized:
            normalized.append(packet_id)
    return normalized


def _unique_context_packet_ids(receipts: Iterable[OpenRouterRouteReceipt]) -> list[str]:
    normalized: list[str] = []
    for receipt in receipts:
        for packet_id in receipt.context_packet_ids:
            if packet_id and packet_id not in normalized:
                normalized.append(packet_id)
    return normalized


def _merged_receipt_token_usage(
    receipts: Iterable[OpenRouterRouteReceipt],
) -> dict[str, int] | None:
    merged: dict[str, int] | None = None
    for receipt in receipts:
        merged = merge_openrouter_token_usage(merged, receipt.token_usage)
    return merged


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _apply_reasoning_for_structured_artifact(
    payload: dict[str, object],
    profile: OpenRouterProfile,
) -> None:
    if profile.task == "document_extraction":
        payload["provider"] = {"require_parameters": True, "data_collection": "deny", "zdr": True, "allow_fallbacks": False}
        return
    payload["reasoning"] = {"effort": profile.reasoning_effort}


def _messages_with_stable_prefix_prompt_cache(
    messages: Sequence[Mapping[str, object]],
    *,
    model: str,
    task: OpenRouterTask,
) -> list[dict[str, object]]:
    payload_messages: list[dict[str, object]] = [dict(message) for message in messages]
    if task not in _PROMPT_CACHE_STRUCTURED_ARTIFACT_TASKS:
        return payload_messages

    cache_index = 0
    content = payload_messages[0].get("content") if payload_messages and payload_messages[0].get("role") == "system" else None
    has_later_system_context = any(message.get("role") in {"system", "developer"} for message in payload_messages[1:])
    if not isinstance(content, str) or not content or (model.startswith("google/gemini") and has_later_system_context):
        return payload_messages
    payload_messages[cache_index]["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    return payload_messages


_SCHEMA_IN_PROMPT_INSTRUCTION = (
    "Return a single JSON object that validates against this JSON Schema. "
    "Output only the JSON object, no prose, no code fences.\nJSON Schema:\n"
)


def _document_wire_schema(node: object, *, fields: bool = False) -> object:
    if isinstance(node, list):
        return [_document_wire_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    # Provider grammar limits do not weaken local Pydantic validation.
    unsupported = {"default", "minLength", "maxLength", "pattern", "format", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minItems", "maxItems", "uniqueItems", "minProperties", "maxProperties"}
    projected = {
        key: _document_wire_schema(item, fields=not fields and key in {"properties", "$defs"})
        for key, item in node.items() if fields or key not in unsupported
    }
    if not fields and "properties" in projected:
        projected["required"] = list(projected["properties"])
        projected["additionalProperties"] = False
    return projected


def _json_schema_payload(
    *,
    model: str,
    messages: Sequence[Mapping[str, object]],
    schema_model: type[SchemaModelT],
    schema_name: str,
    profile: OpenRouterProfile,
) -> dict[str, object]:
    openai_document = profile.task == "document_extraction" and model.startswith("openai/")
    sampling_parameters = (
        {} if openai_document or openrouter_model_tier_for_task(profile.task) == "readout"
        else model_policy.model_sampling_parameters(model, profile.temperature)
    )
    if model.startswith("anthropic/"):
        # Anthropic strict structured outputs reject core shapes of our
        # schemas (numeric bounds, any-typed values, open objects such as
        # extra_parameters), so every native json_schema call 400s. Embed the
        # schema in a system message instead; client-side pydantic validation
        # and the candidate retry loop own correctness either way.
        schema_message = {
            "role": "system",
            "content": (
                _SCHEMA_IN_PROMPT_INSTRUCTION
                + json.dumps(schema_model.model_json_schema())
            ),
        }
        payload: dict[str, object] = {
            "model": model,
            "messages": _messages_with_stable_prefix_prompt_cache([schema_message, *messages], model=model, task=profile.task),
            **sampling_parameters,
            "max_tokens": profile.max_tokens,
        }
        _apply_reasoning_for_structured_artifact(payload, profile)
        return payload
    payload = {
        "model": model,
        "messages": _messages_with_stable_prefix_prompt_cache(messages, model=model, task=profile.task),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": _document_wire_schema(schema_model.model_json_schema()) if openai_document else schema_model.model_json_schema(),
            },
        },
        "provider": {"require_parameters": True},
        **sampling_parameters,
        "max_completion_tokens" if openai_document else "max_tokens": profile.max_tokens,
    }
    _apply_reasoning_for_structured_artifact(payload, profile)
    return payload


def _json_content_without_code_fences(content: str) -> str:
    """Strip a markdown code fence around a JSON body, if present.

    Schema-in-prompt providers occasionally fence their JSON despite
    instructions — sometimes on one line ("```json {...}```") or with prose
    after the closing fence; strict structured outputs never fence, so this
    is a no-op for them.
    """

    text = content.strip()
    if not text.startswith("```"):
        fence_at = text.find("```")
        if text.startswith(("{", "[")) or fence_at == -1:
            return text
        # A JSON value that opens before the first ``` and parses past it owns
        # that ``` as string content; otherwise the fence is real and the
        # fenced body wins.
        brace_candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
        brace_at = min(brace_candidates) if brace_candidates else -1
        if brace_at != -1 and brace_at < fence_at:
            try:
                _, span = json.JSONDecoder().raw_decode(text[brace_at:])
            except ValueError:
                span = 0
            if brace_at + span > fence_at:
                return text[brace_at : brace_at + span]
        text = text[fence_at:]
    text = text[len("```") :]
    info_end = 0
    while info_end < len(text) and (
        text[info_end].isalnum() or text[info_end] in "_-"
    ):
        info_end += 1
    text = text[info_end:]
    closing = text.rfind("```")
    if closing != -1:
        text = text[:closing]
    return text.strip()


async def _post_openrouter_json_schema(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    payload: dict[str, object],
    retry_attempt: _OpenRouterRetryAttempt,
) -> httpx.Response | None:
    response = await client.post(
        "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key), json=_guard_request(retry_attempt[0], payload)
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400 or "reasoning" not in payload:
            raise
        if (permit := _reserve_openrouter_attempt(*retry_attempt)) is None:
            return None
        fallback_payload = {key: value for key, value in payload.items() if key != "reasoning"}
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key),
            json=_guard_request(retry_attempt[0], fallback_payload),
            timeout=permit.timeout_seconds,
        )
        response.raise_for_status()
    return response


def _post_openrouter_json_schema_sync(
    *,
    client: httpx.Client,
    api_key: str,
    payload: dict[str, object],
    retry_attempt: _OpenRouterRetryAttempt,
) -> httpx.Response | None:
    response = client.post(
        "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key), json=_guard_request(retry_attempt[0], payload)
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400 or "reasoning" not in payload:
            raise
        if (permit := _reserve_openrouter_attempt(*retry_attempt)) is None:
            return None
        fallback_payload = {key: value for key, value in payload.items() if key != "reasoning"}
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions", headers=_openrouter_headers(api_key),
            json=_guard_request(retry_attempt[0], fallback_payload),
            timeout=permit.timeout_seconds,
        )
        response.raise_for_status()
    return response

def _openrouter_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _raise_openrouter_payload_error(data: dict[str, object]) -> None:
    error = data.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "OpenRouter returned an error payload")
        code = error.get("code")
        raise ValueError(f"{message} code={code}")


def _openrouter_message_content(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    if isinstance(content, dict):
        return json.dumps(content)
    return ""


def log_openrouter_failure(
    *,
    task: OpenRouterTask,
    model_name: str | None,
    exc: Exception,
    message: str,
) -> None:
    profile = openrouter_profile_for_task(task)
    resolved_model = resolve_openrouter_model(model_name, task=task)
    error_type = type(exc).__name__
    # The default loguru sink renders only the message, so anything a reader
    # needs in production has to live in the formatted string, not in extra.
    # Exception text and validation locations can echo private request values.
    error_origin = exception_origin(exc)
    logger.warning(
        (
            f"{message} "
            f"task={task} model={resolved_model} "
            f"max_tokens={profile.max_tokens} error_type={error_type} "
            f"error_origin={error_origin or '<unknown>'}"
        ),
        llm_task=task,
        model=resolved_model,
        max_tokens=profile.max_tokens,
        error_type=error_type,
        error_origin=error_origin,
    )

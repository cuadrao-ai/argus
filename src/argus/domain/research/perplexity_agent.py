"""Perplexity Agent API client for finance_search research.

One HTTP boundary with an injectable transport so tests stay hermetic. Each
attempt's httpx timeouts are sized from what is left of the call's own
timeout. A failure after which the provider cannot have started paid work (a
429, a 5xx, a connection that failed before the request was sent) is asked
again at that boundary, a bounded number of times inside that timeout. After a
read timeout or a connection dropped mid-request the attempt is recorded as
unpriced, and a background submission is marked as possibly billing a run.
The parser is deterministic: it walks the typed ``output`` items the Agent API
documents, never user language. Provider identity is scrubbed at parse time
because route receipts and the cost ledger own provenance, not prose.

Every request carries the retrieval parameters the spec derived for it: the
model fallback chain, the strict typed-output schema, the response language,
and the web search options. The answer is read back in that typed shape with
every row the model wrote: a row's citation is the model's own, and a row
written without one is kept apart so the turn can say the figure has no
source.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger
from pydantic import ValidationError

from argus.domain.research.answer_contract import (
    TypedAnswer,
    typed_answer_response_format,
)
from argus.domain.research.billing import (
    UnpricedResearchSpend,
    UnpricedSpendRecorder,
    record_unpriced_spend,
    unpriced_spend,
)
from argus.domain.research.config import ResearchConfigSpec
from argus.domain.research.contracts import (
    MAX_ANSWER_CHARS,
    MAX_PACKET_ROWS,
    MAX_PACKET_SOURCES,
    MAX_PACKET_TICKERS,
    MAX_PEER_PAIRS,
    MAX_URL_CHARS,
    PROVIDER_HOSTS,
    BackgroundPoll,
    ResearchNamePair,
    ResearchPacket,
    ResearchPricingError,
    ResearchSource,
    ResearchUnavailableError,
    ResearchUsage,
    RetrievedRow,
)
from argus.domain.research.pricing import validated_research_cost_usd
from argus.log_sink import exception_origin

PERPLEXITY_AGENT_URL = "https://api.perplexity.ai/v1/agent"

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "incomplete"}


@dataclass(frozen=True)
class StructuredAgentLimits:
    """Optional provider request limits, explicit and caller-owned."""

    max_tool_calls: int | None = None
    parallel_tool_calls: bool | None = None
    web_search_max_tokens: int | None = None
    web_search_max_tokens_per_page: int | None = None
    web_search_max_results: int | None = None
    fetch_url_max_urls: int | None = None
    fetch_url_total_budget_tokens: int | None = None

    def __post_init__(self) -> None:
        for name, minimum, maximum in (
            ("max_tool_calls", 0, None),
            ("web_search_max_tokens", 1, None),
            ("web_search_max_tokens_per_page", 1, None),
            ("web_search_max_results", 1, 50),
            ("fetch_url_max_urls", 1, 10),
            ("fetch_url_total_budget_tokens", 1, 120000),
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < minimum
                or (maximum is not None and value > maximum)
            ):
                raise ValueError(f"invalid structured request limit: {name}")
        if self.parallel_tool_calls is not None and not isinstance(
            self.parallel_tool_calls, bool
        ):
            raise ValueError("parallel_tool_calls must be boolean")


@dataclass(frozen=True)
class StructuredAgentResult:
    """Complete caller-validated output beside the existing retrieval invoice."""

    draft: dict[str, Any]
    sources: tuple[ResearchSource, ...]
    usage: ResearchUsage
    tool_results: tuple[str, ...]
    provider_response_id: str | None


class PerplexityAgentClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key.strip()
        self._transport = transport
        # A retry's deadline and its wait read these, so a test can script time.
        self._clock = clock
        self._sleep = sleep
        self._reported_unpriced_ids: set[str] = set()

    def run_structured(
        self,
        prompt: str,
        spec: ResearchConfigSpec,
        *,
        schema_model: Any,
        schema_name: str,
        instructions: str,
        limits: StructuredAgentLimits | None = None,
    ) -> StructuredAgentResult:
        """Run the caller's closed contract without research prose processing."""
        from argus.domain.research.contracts import _strict_schema

        schema = schema_model.model_json_schema()
        definitions = schema.pop("$defs", {})
        payload = self._request_body(prompt, spec)
        if limits is not None:
            for key in ("max_tool_calls", "parallel_tool_calls"):
                if (value := getattr(limits, key)) is not None:
                    payload[key] = value
            tool_fields = {
                "web_search": ("max_tokens", "max_tokens_per_page", "max_results"),
                "fetch_url": ("max_urls", "total_budget_tokens"),
            }
            for tool in payload["tools"]:
                for key in tool_fields.get(tool["type"], ()):
                    if (value := getattr(limits, f"{tool['type']}_{key}")) is not None:
                        tool[key] = value
        payload["instructions"] = instructions
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": _strict_schema(schema, definitions),
            },
        }
        started = time.monotonic()
        response = self._post(payload, timeout_seconds=spec.timeout_seconds)
        usage = _usage_from_response(
            response,
            latency_ms=int((time.monotonic() - started) * 1000),
            on_unpriced=self._record_unpriced,
        )
        try:
            if (
                response.get("status") not in (None, "completed")
                or response.get("incomplete_details")
                or response.get("error")
            ):
                raise ValueError("incomplete structured response")
            output = response.get("output")
            if not isinstance(output, list):
                raise ValueError("missing output list")
            text_blocks: list[str] = []
            parsed = _ParsedToolResults()
            for item in output:
                if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                    raise ValueError("invalid output item")
                item_type = item["type"]
                reader = _TOOL_RESULT_READERS.get(item_type)
                if reader is not None:
                    parsed.tool_results.append(item_type)
                    reader(item, parsed)
                elif item_type == "message":
                    if item.get("status") not in (None, "completed"):
                        raise ValueError("incomplete output message")
                    content = item.get("content")
                    if not isinstance(content, list):
                        raise ValueError("invalid message content")
                    for chunk in content:
                        if (
                            not isinstance(chunk, dict)
                            or chunk.get("type") != "output_text"
                            or not isinstance(chunk.get("text"), str)
                        ):
                            raise ValueError("invalid structured text chunk")
                        text_blocks.append(chunk["text"])
                        for annotation in chunk.get("annotations") or []:
                            _append_public_source(parsed, annotation)
            draft = schema_model.model_validate_json(
                "".join(text_blocks), strict=True, extra="forbid"
            ).model_dump()
            if not isinstance(draft, dict):
                raise ValueError("structured draft is not an object")
            return StructuredAgentResult(
                draft=draft,
                sources=tuple(parsed.sources),
                usage=usage,
                tool_results=tuple(parsed.tool_results),
                provider_response_id=str(response.get("id") or "") or None,
            )
        except Exception:  # noqa: BLE001
            # The response was billed even if its whole draft cannot be read.
            # Neither partial prose nor schema errors containing it escape.
            raise ResearchUnavailableError(
                "malformed_response",
                "structured output did not match the caller contract",
                usage=usage,
            ) from None

    def run_research(self, prompt: str, spec: ResearchConfigSpec) -> ResearchPacket:
        payload = self._request_body(prompt, spec)
        started = time.monotonic()
        response = self._post(payload, timeout_seconds=spec.timeout_seconds)
        latency_ms = int((time.monotonic() - started) * 1000)
        packet = _packet_from_response(
            response, latency_ms=latency_ms, on_unpriced=self._record_unpriced
        )
        _observe_retrieval(packet, spec)
        return packet

    def submit_background(self, prompt: str, spec: ResearchConfigSpec) -> str:
        payload = self._request_body(prompt, spec)
        payload["background"] = True
        try:
            response = self._post(payload, timeout_seconds=spec.timeout_seconds)
        except ResearchUnavailableError as exc:
            if exc.transient and not exc.paid_work_ruled_out:
                # The provider may already be running, and billing, this run; a
                # Retry would start a second one, so the reader is not offered one.
                exc.run_may_be_billing = True
            raise
        background_id = str(response.get("id") or "").strip()
        if not background_id:
            raise ResearchUnavailableError("malformed_response", "missing id")
        return background_id

    def poll_background(
        self,
        background_id: str,
        *,
        timeout_seconds: float = 30.0,
        spec: ResearchConfigSpec | None = None,
    ) -> BackgroundPoll:
        started = time.monotonic()
        response = self._get(
            f"{PERPLEXITY_AGENT_URL}/{background_id}", timeout_seconds=timeout_seconds
        )
        status = str(response.get("status") or "").strip() or "in_progress"
        if status not in _TERMINAL_STATUSES:
            return BackgroundPoll(
                status="in_progress" if status != "queued" else "queued"
            )
        if status != "completed":
            error = response.get("error")
            detail = json.dumps(error)[:500] if error else None
            return BackgroundPoll(status=status, failure_detail=detail)  # type: ignore[arg-type]
        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            packet = _packet_from_response(
                response, latency_ms=latency_ms, on_unpriced=self._record_unpriced
            )
        except ResearchUnavailableError as exc:
            # The run is complete, so polling again cannot change its answer:
            # an answer that cannot be read is the job's terminal failure. It
            # was still billed, so the invoice leaves with the failure.
            return BackgroundPoll(
                status="failed",
                failure_detail=f"{exc.reason}: {exc.detail or ''}",
                failure_reason=exc.reason,
                usage=exc.usage,
            )
        if spec is not None:
            _observe_retrieval(packet, spec)
        return BackgroundPoll(status="completed", packet=packet)

    def _record_unpriced(self, spend: UnpricedResearchSpend) -> None:
        response_id = spend.provider_response_id
        if response_id and response_id in self._reported_unpriced_ids:
            return
        record_unpriced_spend(spend)
        if response_id:
            self._reported_unpriced_ids.add(response_id)

    def _request_body(self, prompt: str, spec: ResearchConfigSpec) -> dict[str, Any]:
        body: dict[str, Any] = {
            "models": list(spec.models),
            "input": prompt,
            "tools": [_tool_declaration(tool, spec) for tool in spec.tools],
            "max_steps": spec.max_steps,
            "max_output_tokens": spec.max_output_tokens,
        }
        if spec.reasoning_effort is not None:
            body["reasoning"] = {"effort": spec.reasoning_effort}
        if spec.language:
            body["language_preference"] = spec.language
        if spec.typed_output:
            body["instructions"] = spec.instructions
            body["response_format"] = typed_answer_response_format()
        return body

    def _post(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        """One request, asked again only when the provider cannot have started
        paid work on it.

        Each attempt's httpx timeouts are sized from what is left of the call's
        timeout, and a retry starts only while at least half of it is left."""
        deadline = self._clock() + timeout_seconds
        remaining = timeout_seconds
        attempt = 1
        while True:
            try:
                return self._send("POST", PERPLEXITY_AGENT_URL, payload, remaining)
            except ResearchUnavailableError as exc:
                delay = _retry_delay(
                    exc,
                    attempt=attempt,
                    remaining=deadline - self._clock(),
                    ceiling=timeout_seconds,
                )
                if delay is None:
                    raise
                # The deployed log sink drops structured extras, so what a count
                # of retries needs is in the message.
                logger.warning(
                    "Research provider retried"
                    f" reason={exc.reason} status={exc.status} attempt={attempt}"
                    f" delay_seconds={delay:g}"
                )
                self._sleep(delay)
                remaining = deadline - self._clock()
                attempt += 1

    def _get(self, url: str, *, timeout_seconds: float) -> dict[str, Any]:
        # Not retried here: the poller asks again until its own deadline.
        return self._send("GET", url, None, timeout_seconds)

    def _record_unanswered(
        self, failure: ResearchUnavailableError, *, latency_ms: int
    ) -> None:
        """An attempt the provider may have billed without answering: no invoice
        will arrive, and no response id came back to correlate one with."""
        self._record_unpriced(
            unpriced_spend(
                document={},
                usage=ResearchUsage(
                    invocations=None,
                    finance_search_invocations=None,
                    web_search_invocations=None,
                    fetch_url_invocations=None,
                    latency_ms=latency_ms,
                ),
                error=ResearchPricingError(
                    "unanswered_attempt",
                    f"{failure.reason}: {failure.detail or ''}"[:500],
                ),
            )
        )

    def _send(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ResearchUnavailableError("not_configured")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        started = self._clock()
        try:
            # httpx applies this timeout to each connect, read, write and pool
            # wait on its own.
            with httpx.Client(
                transport=self._transport, timeout=timeout_seconds
            ) as client:
                response = client.request(method, url, headers=headers, json=payload)
        except (httpx.HTTPError, OSError) as exc:
            # An OSError httpx did not map fails closed, as sent.
            timed_out = isinstance(exc, (httpx.TimeoutException, TimeoutError))
            failure = ResearchUnavailableError(
                "timeout" if timed_out else "transport",
                str(exc),
                sent=not isinstance(exc, _UNSENT_ERRORS),
            )
            if method == "POST" and failure.sent:
                self._record_unanswered(
                    failure, latency_ms=int((self._clock() - started) * 1000)
                )
            raise failure from exc
        if response.status_code >= 400:
            # The deployed log sink drops structured extras; the status rides
            # in the message.
            logger.warning(
                "Research provider returned an error status"
                f" status={response.status_code}"
            )
            raise ResearchUnavailableError(
                "not_configured" if response.status_code in (401, 403) else "http_error",
                f"http {response.status_code}",
                status=response.status_code,
                retry_after_seconds=_retry_after_seconds(
                    response.headers.get("retry-after")
                ),
            )
        try:
            document = response.json()
        except ValueError as exc:
            raise ResearchUnavailableError("malformed_response", str(exc)) from exc
        if not isinstance(document, dict):
            raise ResearchUnavailableError("malformed_response", "non-object body")
        return document


# A transient failure is asked at most this many times in all. Each wait
# doubles from the first backoff unless the provider names its own.
_MAX_ATTEMPTS = 3
_FIRST_BACKOFF_SECONDS = 1.0


def _retry_delay(
    failure: ResearchUnavailableError,
    *,
    attempt: int,
    remaining: float,
    ceiling: float,
) -> float | None:
    """How long to wait before asking again, or None when not to ask again.

    Only a failure after which the provider cannot have started paid work is
    asked again: a 429, a 5xx, or a connection that failed before the request
    was sent. After a read timeout or a connection dropped mid-request, the
    reader decides. A retry starts only while at least half the call's ceiling
    is left to answer in."""
    if not failure.paid_work_ruled_out or attempt >= _MAX_ATTEMPTS:
        return None
    delay = (
        failure.retry_after_seconds
        if failure.retry_after_seconds is not None
        else _FIRST_BACKOFF_SECONDS * 2 ** (attempt - 1)
    )
    return delay if remaining - delay >= ceiling / 2 else None


# The request provably never left Argus: no connection or proxy could be
# opened, or none freed up in the pool. Every other transport failure may have
# come after the provider started work.
_UNSENT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
)


def _retry_after_seconds(value: str | None) -> float | None:
    """The wait a response asks for, in either Retry-After form: whole seconds
    or an HTTP date. Anything else is no instruction, and the backoff applies."""
    text = (value or "").strip()
    if text.isascii() and text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        return None
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _packet_from_response(
    document: dict[str, Any],
    *,
    latency_ms: int,
    on_unpriced: UnpricedSpendRecorder = record_unpriced_spend,
) -> ResearchPacket:
    # The invoice is read before anything can reject the response, so every
    # rejection below carries what Argus was billed. A document that got this
    # far was served; only transport and a non-object body have no invoice.
    usage = _usage_from_response(document, latency_ms=latency_ms, on_unpriced=on_unpriced)
    try:
        return _packet_from_priced_response(document, usage=usage)
    except ResearchUnavailableError as exc:
        raise ResearchUnavailableError(exc.reason, exc.detail, usage=usage) from exc
    except Exception as exc:  # noqa: BLE001
        # However the document defeats the parser, it is a malformed response
        # Argus was billed for, not a crashed turn. Checking each nested shape
        # would only name the ones seen so far; the next one is already out
        # there. The catch is wide enough to cover an Argus-side regression in
        # the parser too. Exception chains can include raw provider values,
        # even with diagnostic locals disabled, so retain only the error class.
        origin = exception_origin(exc)
        logger.warning(
            "Research response could not be parsed error_type={} error_origin={}",
            type(exc).__name__,
            origin,
            error_type=type(exc).__name__,
            error_origin=origin,
        )
        raise ResearchUnavailableError(
            "malformed_response", "response shape not parseable", usage=usage
        ) from exc


def _packet_from_priced_response(
    document: dict[str, Any], *, usage: ResearchUsage
) -> ResearchPacket:
    output = document.get("output")
    if not isinstance(output, list):
        raise ResearchUnavailableError("malformed_response", "missing output list")
    text_blocks: list[str] = []
    parsed = _ParsedToolResults()
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if not isinstance(item_type, str):
            continue
        reader = _TOOL_RESULT_READERS.get(item_type)
        if reader is not None:
            # Reading a tool result is what records it as retrieval evidence;
            # the two facts share one owner and cannot drift.
            parsed.tool_results.append(item_type)
            reader(item, parsed)
        elif item_type == "message":
            for chunk in item.get("content") or []:
                if not isinstance(chunk, dict) or chunk.get("type") != "output_text":
                    continue
                text = chunk.get("text")
                if isinstance(text, str) and text.strip():
                    text_blocks.append(text)
                # Some models carry their citations as annotations on the
                # same chunk instead of as search_results items.
                for annotation in chunk.get("annotations") or []:
                    if isinstance(annotation, dict):
                        _append_public_source(parsed, annotation)
    typed = _typed_retrieval("\n\n".join(text_blocks))
    rows: list[RetrievedRow] = []
    unsourced: list[RetrievedRow] = []
    if typed is not None:
        rows, unsourced = _sourced_rows(typed.rows)
        answer = _sanitize_answer(typed.answer_markdown)
    else:
        answer = _sanitize_answer("\n\n".join(text_blocks))
    if not answer:
        raise ResearchUnavailableError("empty_answer")
    seen: set[str] = set()
    unique_pairs = []
    for pair in parsed.pairs:
        key = pair.symbol.upper()
        if key in seen:
            continue
        seen.add(key)
        unique_pairs.append(pair)
    return ResearchPacket(
        answer_markdown=answer[:MAX_ANSWER_CHARS],
        categories=tuple(parsed.categories[:12]),
        tickers=tuple(parsed.tickers[:MAX_PACKET_TICKERS]),
        sources=tuple(parsed.sources[:MAX_PACKET_SOURCES]),
        name_pairs=tuple(unique_pairs[:MAX_PEER_PAIRS]),
        rows=tuple(rows),
        typed_answer=typed is not None,
        unsourced_rows=tuple(unsourced),
        calculations=(
            tuple(item.model_dump(mode="json") for item in typed.calculations)
            if typed is not None
            else ()
        ),
        source_urls=_public_urls(typed.source_urls) if typed is not None else (),
        follow_up_questions=(
            tuple(typed.follow_up_questions) if typed is not None else ()
        ),
        declined=bool(typed.declined) if typed is not None else False,
        tool_results=tuple(parsed.tool_results),
        usage=usage,
        background_id=str(document.get("id") or "") or None,
    )


@dataclass
class _ParsedToolResults:
    """Everything the tool result items of one response contribute."""

    categories: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)
    pairs: list[ResearchNamePair] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)


def _typed_retrieval(text: str) -> TypedAnswer | None:
    """The answer in its requested typed shape, or None when it is prose.

    Machine format only: a JSON object, optionally inside a code fence. A
    document that is not one is prose and is delivered as such. A document
    that is JSON-shaped but not the schema, an invalid row or an answer the
    output budget truncated, is a broken contract, never prose: its figures
    cannot be verified and its text must never reach a reader, so it fails
    closed as a malformed response."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        if body.startswith(("{", "[")):
            raise ResearchUnavailableError(
                "malformed_response", "typed answer is not valid JSON"
            ) from exc
        return None
    if not isinstance(parsed, dict):
        # Any JSON value that is not the answer object: an array, a string,
        # a number. The model answered in JSON and not in the schema.
        raise ResearchUnavailableError(
            "malformed_response", "typed answer is not the answer object"
        )
    try:
        return TypedAnswer.model_validate(parsed)
    except ValidationError as exc:
        raise ResearchUnavailableError(
            "malformed_response",
            f"typed answer did not match the schema: {type(exc).__name__}",
        ) from exc


def _sourced_rows(
    rows: list[RetrievedRow],
) -> tuple[list[RetrievedRow], list[RetrievedRow]]:
    """Rows that carry a citation, and rows the model wrote without one.

    A citation is kept as the model wrote it: the page it names is the
    figure's source, whether or not this response retrieved that page. A
    row read from the provider's own finance data keeps its evidence in the
    tool result and loses the provider URL, the way every provider-host
    citation does. A row with no citation at all is kept apart so the turn
    can say, under the answer, that the figure has no source."""
    if len(rows) > MAX_PACKET_ROWS:
        # More figures than the packet carries: an answer whose evidence would
        # be cut cannot be published whole, so it is not the contract.
        raise ResearchUnavailableError(
            "malformed_response", f"typed answer carries more than {MAX_PACKET_ROWS} rows"
        )
    sourced: list[RetrievedRow] = []
    unsourced: list[RetrievedRow] = []
    for row in rows:
        url = str(row.source_url or "").strip()
        if not url:
            unsourced.append(row.model_copy(update={"source_url": None}))
            continue
        if _is_provider_host(urlparse(url).netloc.lower()):
            row = row.model_copy(update={"source_url": None})
        sourced.append(row)
    return sourced, unsourced


def _observe_retrieval(packet: ResearchPacket, spec: ResearchConfigSpec) -> None:
    """Record the compensations, so a decaying provider read is visible.

    The deployed log sink drops structured extras, so every fact is in the
    message itself."""
    served = packet.usage.model
    if served and served != spec.models[0]:
        logger.warning(
            "Research served by a fallback model"
            f" shape={spec.shape} primary={spec.models[0]} served={served}"
        )
    if spec.typed_output and not packet.typed_answer:
        logger.warning(
            "Research answer arrived as prose under a typed request"
            f" shape={spec.shape} model={served or 'unknown'}"
        )
    if packet.unsourced_rows:
        logger.warning(
            "Research rows written without a citation"
            f" shape={spec.shape} unsourced={len(packet.unsourced_rows)}"
            f" cited={len(packet.rows)}"
        )


def _tool_declaration(tool: str, spec: ResearchConfigSpec) -> dict[str, Any]:
    """One tool entry in the request. Only web search takes options: context
    size, the recency and domain filters, and the reader's location."""
    declaration: dict[str, Any] = {"type": tool}
    if tool != "web_search":
        return declaration
    if spec.search_context_size is not None:
        declaration["search_context_size"] = spec.search_context_size
    filters: dict[str, Any] = {}
    if spec.recency is not None:
        filters["search_recency_filter"] = spec.recency
    if spec.source_domains:
        filters["search_domain_filter"] = list(spec.source_domains)
    if filters:
        declaration["filters"] = filters
    if spec.location is not None:
        declaration["user_location"] = spec.location.model_dump(exclude_none=True)
    return declaration


def _read_finance_results(item: dict[str, Any], parsed: _ParsedToolResults) -> None:
    for value in item.get("categories") or []:
        if isinstance(value, str) and value not in parsed.categories:
            parsed.categories.append(value)
    for value in item.get("tickers") or []:
        if isinstance(value, str) and value not in parsed.tickers:
            parsed.tickers.append(value)
    for result in item.get("results") or []:
        if not isinstance(result, dict):
            continue
        category = result.get("category")
        if isinstance(category, str) and category not in parsed.categories:
            parsed.categories.append(category)
        for url in result.get("sources") or []:
            _append_public_source(parsed, {"url": url})
        if category == "tickers_lookup":
            parsed.pairs.extend(_pairs_from_lookup(str(result.get("content") or "")))
        elif category == "etf_holdings":
            parsed.pairs.extend(_pairs_from_holdings(str(result.get("content") or "")))


def _read_search_results(item: dict[str, Any], parsed: _ParsedToolResults) -> None:
    # Web search citations live in their own output items: title, url, and
    # the publisher's own date. This is the channel the sector and
    # comparison shapes fill.
    for result in item.get("results") or []:
        if isinstance(result, dict):
            _append_public_source(parsed, result)


def _read_fetch_url_results(item: dict[str, Any], parsed: _ParsedToolResults) -> None:
    # A page the model opened is a page it read: title, url and an excerpt,
    # no publisher date. It is a typed source the way a search hit is.
    for content in item.get("contents") or []:
        if isinstance(content, dict):
            _append_public_source(parsed, content)


# The one owner of which output items are tool results. Recorded responses
# carry exactly one finance_results item per finance_search call, one
# search_results item per web search and one fetch_url_results item per
# fetched page batch; a response that ran no tool carries none. A kind read
# here is retrieval evidence whether or not the invoice arrived.
_TOOL_RESULT_READERS: dict[str, Callable[[dict[str, Any], _ParsedToolResults], None]] = {
    "finance_results": _read_finance_results,
    "search_results": _read_search_results,
    "fetch_url_results": _read_fetch_url_results,
}


def _usage_from_response(
    document: dict[str, Any],
    *,
    latency_ms: int,
    on_unpriced: UnpricedSpendRecorder = record_unpriced_spend,
) -> ResearchUsage:
    raw_model = document.get("model")
    model = raw_model.strip() if isinstance(raw_model, str) else ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    # Unknown until the invoice establishes each count; a lost or malformed
    # invoice leaves them None, never zero.
    finance_search_invocations: int | None = None
    web_search_invocations: int | None = None
    fetch_url_invocations: int | None = None
    pricing_error: ResearchPricingError | None = None
    try:
        usage = document.get("usage")
        if not isinstance(usage, dict):
            raise ResearchPricingError("invalid_usage", "missing usage")
        details = usage.get("tool_calls_details")
        if details is None:
            details = {}
        if not isinstance(details, dict):
            raise ResearchPricingError(
                "invalid_usage", "invalid usage.tool_calls_details"
            )
        finance_search_invocations = _tool_invocation_count(details, "finance_search")
        web_search_invocations = _tool_invocation_count(
            details, "web_search", "search_web"
        )
        fetch_url_invocations = _tool_invocation_count(details, "fetch_url")
        if not model:
            raise ResearchPricingError("invalid_usage", "missing model")
        input_tokens = _required_nonnegative_int(
            usage, "input_tokens", path="usage.input_tokens"
        )
        output_tokens = _required_nonnegative_int(
            usage, "output_tokens", path="usage.output_tokens"
        )
        input_details = usage.get("input_tokens_details")
        if not isinstance(input_details, dict):
            raise ResearchPricingError(
                "invalid_usage", "invalid usage.input_tokens_details"
            )
        cache_creation_input_tokens = _required_nonnegative_int(
            input_details,
            "cache_creation_input_tokens",
            path="usage.input_tokens_details.cache_creation_input_tokens",
        )
        cache_read_input_tokens = _required_nonnegative_int(
            input_details,
            "cache_read_input_tokens",
            path="usage.input_tokens_details.cache_read_input_tokens",
        )
        cached_tokens = input_details.get("cached_tokens")
        if cached_tokens is not None and (
            isinstance(cached_tokens, bool)
            or not isinstance(cached_tokens, int)
            or cached_tokens != cache_read_input_tokens
        ):
            raise ResearchPricingError(
                "invalid_usage",
                "invalid usage.input_tokens_details.cached_tokens",
            )
        cost = usage.get("cost")
        if not isinstance(cost, dict) or cost.get("currency") != "USD":
            raise ResearchPricingError("invalid_pricing", "invalid usage.cost currency")
        provider_tool_costs_usd = _tool_cost_details(cost)
        cost_usd = validated_research_cost_usd(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            finance_search_invocations=finance_search_invocations,
            web_search_invocations=web_search_invocations,
            fetch_url_invocations=fetch_url_invocations,
            provider_input_cost_usd=_required_nonnegative_decimal(
                cost, "input_cost", path="usage.cost.input_cost"
            ),
            provider_output_cost_usd=_required_nonnegative_decimal(
                cost, "output_cost", path="usage.cost.output_cost"
            ),
            # A cache bucket nothing was billed in arrives absent or null, the
            # way the documented example shows; the component check still
            # holds a zero against the bucket's token count.
            provider_cache_creation_cost_usd=_optional_nonnegative_decimal(
                cost, "cache_creation_cost", path="usage.cost.cache_creation_cost"
            ),
            provider_cache_read_cost_usd=_optional_nonnegative_decimal(
                cost, "cache_read_cost", path="usage.cost.cache_read_cost"
            ),
            provider_tool_calls_cost_usd=_optional_nonnegative_decimal(
                cost, "tool_calls_cost", path="usage.cost.tool_calls_cost"
            ),
            provider_tool_costs_usd=provider_tool_costs_usd,
            provider_total_cost_usd=_required_nonnegative_decimal(
                cost, "total_cost", path="usage.cost.total_cost"
            ),
        )
    except ResearchPricingError as exc:
        cost_usd = None
        pricing_error = exc
    parsed_usage = ResearchUsage(
        invocations=finance_search_invocations,
        finance_search_invocations=finance_search_invocations,
        web_search_invocations=web_search_invocations,
        fetch_url_invocations=fetch_url_invocations,
        model=model,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )

    if pricing_error is not None:
        on_unpriced(
            unpriced_spend(document=document, usage=parsed_usage, error=pricing_error)
        )
    return parsed_usage


def _tool_invocation_count(details: dict[str, Any], *provider_keys: str) -> int:
    counts: list[int] = []
    for key in provider_keys:
        if key not in details:
            continue
        entry = details[key]
        if not isinstance(entry, dict):
            raise ResearchPricingError(
                "invalid_usage", f"invalid usage.tool_calls_details.{key}"
            )
        counts.append(
            _required_nonnegative_int(
                entry,
                "invocation",
                path=f"usage.tool_calls_details.{key}.invocation",
            )
        )
    if not counts:
        return 0
    if any(count != counts[0] for count in counts[1:]):
        joined = ", ".join(provider_keys)
        raise ResearchPricingError("invalid_usage", f"conflicting tool counts: {joined}")
    return counts[0]


def _required_nonnegative_int(values: dict[str, Any], key: str, *, path: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResearchPricingError("invalid_usage", f"invalid {path}")
    return value


def _required_nonnegative_decimal(
    values: dict[str, Any], key: str, *, path: str
) -> Decimal:
    if key not in values:
        raise ResearchPricingError("invalid_pricing", f"invalid {path}")
    return _nonnegative_decimal(values[key], path=path)


def _optional_nonnegative_decimal(
    values: dict[str, Any], key: str, *, path: str
) -> Decimal:
    if values.get(key) is None:
        return Decimal(0)
    return _nonnegative_decimal(values[key], path=path)


def _nonnegative_decimal(value: Any, *, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchPricingError("invalid_pricing", f"invalid {path}")
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < 0:
        raise ResearchPricingError("invalid_pricing", f"invalid {path}")
    return parsed


def _tool_cost_details(cost: dict[str, Any]) -> dict[str, Decimal]:
    details = cost.get("tool_calls_cost_details")
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise ResearchPricingError(
            "invalid_pricing", "invalid usage.cost.tool_calls_cost_details"
        )
    normalized: dict[str, Decimal] = {}
    aliases = {
        "finance_search": "finance_search",
        "web_search": "web_search",
        "search_web": "web_search",
        "fetch_url": "fetch_url",
    }
    for provider_key, value in details.items():
        tool = aliases.get(provider_key)
        if tool is None:
            raise ResearchPricingError(
                "invalid_pricing",
                "unknown tool in usage.cost.tool_calls_cost_details",
            )
        parsed = _nonnegative_decimal(
            value, path=f"usage.cost.tool_calls_cost_details.{provider_key}"
        )
        previous = normalized.get(tool)
        if previous is not None and previous != parsed:
            raise ResearchPricingError(
                "invalid_pricing", f"conflicting tool costs: {tool}"
            )
        normalized[tool] = parsed
    return normalized


# Ticker-shaped cell: 1-5 uppercase letters, optionally a class suffix. Cells
# are read only from markdown table rows, which are machine-generated
# structure, never prose, and every symbol still passes the resolver before
# anything becomes tappable.
_TICKER_CELL = re.compile(r"^[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?$")
_TICKER_HEADERS = frozenset({"TICKER", "SYMBOL", "ETF"})


def symbols_from_answer_tables(markdown: str) -> list[str]:
    """Symbols named in the answer's own tables, in the order shown.

    A market survey often reports its assets only in tables, with no typed
    ticker list attached. Reading those cells is the same deterministic
    markdown walk the lookup and holdings parsers already do.
    """
    symbols: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        for cell in stripped.strip("|").split("|"):
            candidate = cell.strip().strip("*` ").upper()
            if not candidate or candidate in _TICKER_HEADERS:
                continue
            if _TICKER_CELL.fullmatch(candidate) and candidate not in symbols:
                symbols.append(candidate)
    return symbols


def _is_provider_host(host: str) -> bool:
    return any(host == p or host.endswith(f".{p}") for p in PROVIDER_HOSTS)


def _public_urls(urls: list[str]) -> tuple[str, ...]:
    """The pages an answer names, held to the rule every public source meets."""
    kept = [
        url
        for url in urls
        if url.startswith("https://")
        and len(url) <= MAX_URL_CHARS
        and not _is_provider_host(urlparse(url).netloc.lower())
    ]
    return tuple(dict.fromkeys(kept))


def _append_public_source(parsed: _ParsedToolResults, entry: Any) -> None:
    """One citation, bounded and scrubbed.

    Accepts either channel's shape: a search result, an annotation, or a
    bare finance URL. Provider-identity hosts never survive into the public
    sources, so Argus never cites the tool that answered it.
    """
    if not isinstance(entry, dict):
        return
    raw_url = entry.get("url") or entry.get("link") or entry.get("uri")
    if not isinstance(raw_url, str):
        return
    candidate = raw_url.strip()
    if not candidate.startswith("https://") or len(candidate) > MAX_URL_CHARS:
        return
    sources = parsed.sources
    if _is_provider_host(urlparse(candidate).netloc.lower()):
        return
    if any(source.url == candidate for source in sources):
        return
    title = entry.get("title") or entry.get("name") or ""
    published = entry.get("date") or entry.get("last_updated") or None
    sources.append(
        ResearchSource(
            url=candidate,
            title=str(title)[:200].strip(),
            source_date=str(published)[:10] if published else None,
        )
    )


def _pairs_from_holdings(content: str) -> list[ResearchNamePair]:
    """Parse the provider's ``etf_holdings`` markdown table.

    Machine-generated fixed format: a header row naming ``symbol`` and
    ``name`` columns, then one holding per row, top weights first. Row order
    is preserved so the heaviest constituents become the offerable pairs;
    the resolver still gates every one before anything is tappable, which is
    what grounds exposure vehicles whose tickers collide.
    """
    pairs: list[ResearchNamePair] = []
    symbol_index: int | None = None
    name_index: int | None = None
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        lowered = [cell.lower() for cell in cells]
        if symbol_index is None:
            if "symbol" in lowered and "name" in lowered:
                symbol_index = lowered.index("symbol")
                name_index = lowered.index("name")
            continue
        if name_index is None or len(cells) <= max(symbol_index, name_index):
            continue
        ticker = cells[symbol_index].strip("*").upper()
        if not ticker or set(ticker) <= {"-", " ", ":"}:
            continue
        if not re.fullmatch(r"[A-Z0-9.\-/]{1,12}", ticker):
            continue
        display = cells[name_index] or ticker
        pairs.append(ResearchNamePair(symbol=ticker, name=display.title()))
    return pairs


def _pairs_from_lookup(content: str) -> list[ResearchNamePair]:
    """Parse the provider's ``tickers_lookup`` markdown table.

    This walks a machine-generated fixed format (query | ticker | name rows),
    never user language. Unparseable rows are dropped, not guessed.
    """
    pairs: list[ResearchNamePair] = []
    for line in content.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        query, ticker, name = cells[0], cells[1], cells[2]
        if not ticker or ticker.upper() in ("TICKER", "NOT_FOUND"):
            continue
        if set(ticker) <= {"-", " ", ":"}:
            continue
        if not re.fullmatch(r"[A-Z0-9.\-/]{1,12}", ticker.strip("*").upper()):
            continue
        display = name or query
        if not display:
            continue
        pairs.append(
            ResearchNamePair(name=display[:120], symbol=ticker.strip("*").upper())
        )
    return pairs


_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")


def strip_mechanism_narration(text: str) -> str:
    """Drop any sentence that names a provider tool.

    The Voice Boundary forbids raw internal names in assistant prose, and
    spec section 2 forbids handing the user a capability list; an answer
    explaining that "the requested finance_search tool was not available"
    breaks both at once. Tool names come from the configurations themselves,
    so a newly configured tool is covered without editing this function.
    Whole sentences go, because a sentence about a mechanism has nothing
    left to say once the mechanism is removed. Degradation is still told to
    the reader, from the typed signal on the packet.
    """
    if not _PROVIDER_VOCABULARY.search(text):
        return text
    kept: list[str] = []
    for block in text.split("\n"):
        sentences = re.split(r"(?<=[.!?])\s+", block)
        surviving = [
            sentence
            for sentence in sentences
            if not _PROVIDER_VOCABULARY.search(sentence)
        ]
        if sentences and not surviving:
            continue
        kept.append(" ".join(surviving).strip())
    return "\n".join(kept).strip()


def _provider_vocabulary_pattern() -> re.Pattern[str]:
    """Provider vocabulary, derived from the tools this rail declares.

    The declared names are the seed; their families are the reach. The leak
    that prompted this guard named ``finance_quotes`` and
    ``finance_company_profile``, which are the same provider vocabulary as
    the declared ``finance_search`` without being declared themselves.
    Matching the family prefix covers those, and covers whatever the
    provider names next, without a hand-maintained list. Snake_case
    identifiers do not occur in ordinary finance prose, so the reach is
    wide without being greedy.
    """
    from argus.domain.research.config import declared_tool_names

    tools = sorted(declared_tool_names())
    prefixes = sorted({tool.split("_", 1)[0] for tool in tools if "_" in tool})
    alternatives = [re.escape(tool) for tool in tools]
    alternatives += [rf"{re.escape(prefix)}_[a-z][a-z0-9_]*" for prefix in prefixes]
    if not alternatives:
        return re.compile(r"(?!x)x")
    return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b")


_PROVIDER_VOCABULARY = _provider_vocabulary_pattern()


def _sanitize_answer(text: str) -> str:
    """Presentation-only cleanup: provider-host links become plain text and
    typographic dashes normalize to house style (digit ranges keep a hyphen)."""

    def _replace_link(match: re.Match[str]) -> str:
        if _is_provider_host(urlparse(match.group(2)).netloc.lower()):
            return match.group(1)
        return match.group(0)

    cleaned = _LINK_PATTERN.sub(_replace_link, text)
    cleaned = re.sub(r"https?://(?:[a-z0-9-]+\.)*perplexity\.ai\S*", "", cleaned)
    # A lone dash table cell is an empty-value marker, not punctuation.
    cleaned = re.sub(r"\|\s*[—–]\s*(?=\|)", "| - ", cleaned)
    cleaned = re.sub(r"(?<=\d)\s*[—–]\s*(?=\d)", "-", cleaned)
    cleaned = re.sub(r"\s*[—–]\s*", ", ", cleaned)
    return strip_mechanism_narration(cleaned).strip()

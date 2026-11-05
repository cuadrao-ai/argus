from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from argus.llm.openrouter import openrouter_profile_for_task, openrouter_request_guard


def rate(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("invalid_price") from None
    if not result.is_finite() or result < 0:
        raise ValueError("invalid_price")
    return result


@dataclass(frozen=True)
class PriceEnvelope:
    model: str
    provider: str
    context_tokens: int
    output_tokens: int
    prompt: Decimal
    completion: Decimal
    cache_read: Decimal = Decimal(0)
    cache_write: Decimal = Decimal(0)
    output_parameter: str = "max_tokens"

    @property
    def maximum_cost(self) -> Decimal:
        # Cache rates are full input prices, not surcharges on the prompt rate.
        input_rate = max(self.prompt, self.cache_read, self.cache_write)
        return self.context_tokens * input_rate + self.output_tokens * self.completion

    def evidence(self) -> dict:
        return dict(
            model=self.model,
            provider=self.provider,
            context_tokens=self.context_tokens,
            output_tokens=self.output_tokens,
            output_parameter=self.output_parameter,
            prompt_usd_per_token=str(self.prompt),
            completion_usd_per_token=str(self.completion),
            cache_read_usd_per_token=str(self.cache_read),
            cache_write_usd_per_token=str(self.cache_write),
            reserved_input_usd_per_token=str(
                max(self.prompt, self.cache_read, self.cache_write)
            ),
            maximum_request_usd=str(self.maximum_cost),
        )


def price_envelope(model: str, endpoints: list[dict]) -> PriceEnvelope:
    if ":" in model:
        raise ValueError("no_bounded_endpoint")
    profile = openrouter_profile_for_task("document_extraction")
    envelopes = []
    for endpoint in endpoints:
        try:
            prices = endpoint["pricing"]
            rates = {
                "prompt": rate(prices["prompt"]),
                "completion": rate(prices["completion"]),
                "input_cache_read": Decimal(0),
                "input_cache_write": Decimal(0),
            }
            overrides = prices.get("overrides", [])
            if not isinstance(overrides, list):
                raise ValueError("invalid_price_tiers")
            for tier in overrides:
                if not isinstance(tier, dict):
                    raise ValueError("invalid_price_tier")
                threshold = tier.get("min_prompt_tokens")
                if (
                    not isinstance(threshold, int)
                    or isinstance(threshold, bool)
                    or threshold < 0
                ):
                    raise ValueError("invalid_price_threshold")
            for index, tier in enumerate([prices, *overrides]):
                for name, value in tier.items():
                    if name in rates:
                        rates[name] = max(rates[name], rate(value))
                    elif name == "web_search":
                        # The dispatch guard excludes every search activation path.
                        rate(value)
                    elif (
                        name == "discount"
                        or (index == 0 and name == "overrides")
                        or (index > 0 and name == "min_prompt_tokens")
                    ):
                        continue
                    elif rate(value) != 0:
                        raise ValueError("unbounded_additional_price")
            prompt, completion = rates["prompt"], rates["completion"]
            context = endpoint["context_length"]
            if not isinstance(context, int) or isinstance(context, bool) or context <= 0:
                raise ValueError("missing_context_limit")
            supported = endpoint["supported_parameters"]
            if "structured_outputs" not in supported:
                continue
            output_parameter = next(
                (
                    name
                    for name in ("max_tokens", "max_completion_tokens")
                    if name in supported
                ),
                None,
            )
            if output_parameter is None:
                continue
            output = endpoint.get("max_completion_tokens")
            if output is not None and output < profile.max_tokens:
                continue
            provider = endpoint["tag"]
            if not isinstance(provider, str) or not provider:
                continue
            envelopes.append(
                PriceEnvelope(
                    model,
                    provider,
                    context,
                    profile.max_tokens,
                    prompt,
                    completion,
                    rates["input_cache_read"],
                    rates["input_cache_write"],
                    output_parameter,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not envelopes:
        raise ValueError("no_bounded_endpoint")
    return min(envelopes, key=lambda item: item.maximum_cost)


@dataclass
class BenchmarkBudget:
    envelope: PriceEnvelope
    cap: Decimal
    max_attempts: int
    reserved: Decimal = field(default=Decimal(0), init=False)
    attempted: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if not self.cap.is_finite() or self.cap <= 0 or self.max_attempts <= 0:
            raise ValueError("invalid_spend_cap")
        if self.envelope.maximum_cost * self.max_attempts > self.cap:
            raise ValueError("run_exceeds_cap")

    def evidence(self) -> dict:
        return self.envelope.evidence() | dict(
            approved_cap_usd=str(self.cap),
            maximum_run_usd=str(self.envelope.maximum_cost * self.max_attempts),
            reserved_usd=str(self.reserved),
            attempts=len(self.attempted),
            attempted_fixtures=sorted(self.attempted),
        )

    @contextmanager
    def attempt(self, fixture_id: str, save: Callable[[], None]) -> Iterator[None]:
        def authorize(task: str, payload: dict) -> dict:
            if fixture_id in self.attempted:
                raise ValueError("already_attempted")
            if (
                len(self.attempted) >= self.max_attempts
                or self.reserved + self.envelope.maximum_cost > self.cap
            ):
                raise ValueError("spend_cap_reached")
            provider = payload.get("provider", {})
            privacy = dict(
                require_parameters=True,
                data_collection="deny",
                zdr=True,
                allow_fallbacks=False,
            )
            if (
                task != "document_extraction"
                or payload.get("model") != self.envelope.model
                or payload.get(self.envelope.output_parameter)
                != self.envelope.output_tokens
                or {"max_tokens", "max_completion_tokens"}.intersection(payload)
                != {self.envelope.output_parameter}
                or not isinstance(provider, dict)
                or any(provider.get(k) != v for k, v in privacy.items())
                or any(
                    k in payload
                    for k in (
                        "tools",
                        "plugins",
                        "models",
                        "route",
                        "reasoning",
                        "web_search_options",
                        "preset",
                        "presets",
                    )
                )
            ):
                raise ValueError("unexpected_benchmark_request")
            guarded = payload | {
                "provider": provider
                | dict(
                    only=[self.envelope.provider],
                    max_price=dict(
                        prompt=float(self.envelope.prompt * 1_000_000),
                        completion=float(self.envelope.completion * 1_000_000),
                        request=0,
                        image=0,
                    ),
                )
            }
            self.attempted.add(fixture_id)
            self.reserved += self.envelope.maximum_cost
            save()
            return guarded

        with openrouter_request_guard(authorize):
            yield

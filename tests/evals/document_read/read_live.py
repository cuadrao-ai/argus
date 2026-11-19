"""The process that makes the live reads. ``run_live`` starts it; do not run it by hand.

It reads with the environment it was started with and changes none of it. It
refuses to make a read unless that read would use the selected key and model.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
from pathlib import Path

from argus.domain.ingestion.documents import extractor as reader
from loguru import logger
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from tests.evals.document_read.dataset import DEFAULT_OUT, build_set, write_set
from tests.evals.document_read.scoring import (
    build_scorecard,
    known_cost_usd,
    prepare_set,
    read_set,
    summary_table,
)

#: The names a local read looks at first, for the key and for the model.
KEY_SETTING = "CUADRAO_OPENROUTER_API_KEY_DEV"
MODEL_SETTING = "CUADRAO_VISION_MODEL"


class Provider(BaseSettings):
    """The key and document model ``run_live`` selected for this process."""

    model_config = SettingsConfigDict(env_file=None, hide_input_in_errors=True)

    key: SecretStr = Field(validation_alias=KEY_SETTING, min_length=1)
    model: str = Field(validation_alias=MODEL_SETTING, min_length=1)


def selected_provider() -> Provider:
    """The selected key and model, once a read is shown to use both. Or stop."""

    try:
        provider = Provider()
    except ValidationError:
        raise SystemExit("no key or model was selected: start through run_live") from None
    key = provider.key.get_secret_value()
    try:
        used = reader.resolve_openrouter_api_key("registered")
    except RuntimeError as error:
        raise SystemExit(f"the key policy refused this shell: {error}") from None
    if not hmac.compare_digest(used.encode(), key.encode()):
        raise SystemExit("a read would not use the selected key")
    if reader.resolve_openrouter_model(task="document_extraction") != provider.model:
        raise SystemExit("a read would not use the selected model")
    return provider


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--cap-usd", type=float, required=True)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    provider = selected_provider()
    samples = build_set()
    write_set(samples, DEFAULT_OUT)
    args.out.mkdir(parents=True, exist_ok=True)
    results = asyncio.run(
        read_set(
            samples,
            prepare_set(samples),
            stop=lambda done: known_cost_usd(done) >= args.cap_usd,
            only=frozenset(args.only),
        )
    )
    scorecard = build_scorecard(
        samples,
        results,
        tier="live",
        candidate_sha=args.candidate_sha,
        model=provider.model,
    )
    (args.out / "scorecard.json").write_text(
        json.dumps(scorecard, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("\n{}", summary_table(scorecard))
    logger.info("{}", json.dumps({**scorecard["totals"], **scorecard["provider_usage"]}))


if __name__ == "__main__":
    main()

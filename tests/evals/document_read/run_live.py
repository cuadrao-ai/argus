"""Operator entry for the live receipt-read measurement. Not collected by pytest.

    python -m tests.evals.document_read.run_live \
        --out docs/reports/evidence/<name> \
        --env-file <untracked env> --key-name <variable holding the key>

Every read is a real provider call and costs money. Run it only at a gate in
``tests/evals/README.md`` with the spend approved. The key is read from the
named variable of the env file into this process only and is never printed.
The runner stops once the known cost reaches ``--cap-usd``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from argus.domain.ingestion.documents import extractor as reader

from tests.evals.document_read.dataset import DEFAULT_OUT, build_set, write_set
from tests.evals.document_read.scoring import (
    build_scorecard,
    known_cost_usd,
    prepare_set,
    read_set,
    summary_table,
)

MODEL_SETTING = "CUADRAO_VISION_MODEL"


def load_settings(env_file: Path, key_name: str, model: str | None) -> str:
    """Put the key and the document model into this process. Returns the model."""

    from dotenv import dotenv_values

    values = dotenv_values(env_file)
    key = (values.get(key_name) or "").strip()
    if not key:
        raise SystemExit(f"{key_name} is not set in the env file")
    os.environ["OPENROUTER_API_KEY"] = key
    os.environ.pop("APP_ENV", None)
    chosen = (model or values.get(MODEL_SETTING) or "").strip()
    if chosen:
        os.environ[MODEL_SETTING] = chosen
    resolved = reader.resolve_openrouter_model(task="document_extraction")
    if not resolved:
        raise SystemExit(f"pass --model or set {MODEL_SETTING} in the env file")
    return resolved


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    model = load_settings(args.env_file, args.key_name, args.model)
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
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root)
    scorecard = build_scorecard(
        samples,
        results,
        tier="live",
        candidate_sha=head.decode().strip(),
        model=model,
    )
    (args.out / "scorecard.json").write_text(
        json.dumps(scorecard, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return scorecard


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--key-name", default="OPENROUTER_API_KEY")
    parser.add_argument("--model")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--cap-usd", type=float, default=2.0)
    scorecard = run(parser.parse_args())
    print(summary_table(scorecard))
    print(json.dumps({**scorecard["totals"], **scorecard["provider_usage"]}))


if __name__ == "__main__":
    main()

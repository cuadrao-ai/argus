"""Operator entry for the live receipt-read measurement. Not collected by pytest.

    python -m tests.evals.document_read.run_live \
        --out docs/reports/evidence/<name> \
        --env-file <untracked env> --key-name <variable holding the key>

Every read is a real provider call and costs money. Run it only at a gate in
``tests/evals/README.md`` with the spend approved. The key is read from the
named variable of the env file and is never logged. The reads run in a second
process. That process starts with the selected key and document model and with
every other model credential and document model blank, so nothing the shell or
the project ``.env`` holds can reach a read. This process changes nothing in its
own environment. The run stops once the known cost reaches ``--cap-usd``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from argus.llm.openrouter_key_policy import MODEL_CREDENTIAL_ENV_NAMES
from argus.llm.openrouter_model_env import TIER_FALLBACK_ENV, TIER_PRIMARY_ENV
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from tests.evals.document_read.read_live import KEY_SETTING, MODEL_SETTING

ROOT = Path(__file__).resolve().parents[3]
#: Every name that can change the account or the model a read uses.
_PROVIDER_SETTINGS = frozenset(
    {
        "APP_ENV",
        *MODEL_CREDENTIAL_ENV_NAMES,
        *TIER_PRIMARY_ENV["vision"],
        *TIER_FALLBACK_ENV["vision"],
    }
)


class Selected(BaseModel):
    """The one key and document model the operator chose for this run."""

    model_config = ConfigDict(frozen=True)

    key: SecretStr
    model: str


class _HostedMarks(BaseSettings):
    """What marks a hosted service. Passed on so the key policy can refuse one."""

    model_config = SettingsConfigDict(env_file=None)

    render: str = ""
    render_service_id: str = ""


def load_settings(env_file: Path, key_name: str, model: str | None) -> Selected:
    """Take the key and document model from the env file and ``--model`` only."""

    values = dotenv_values(env_file)
    key = (values.get(key_name) or "").strip()
    if not key:
        raise SystemExit(f"{key_name} is not set in the env file")
    chosen = (model or values.get(MODEL_SETTING) or "").strip()
    if not chosen:
        raise SystemExit(f"pass --model or set {MODEL_SETTING} in the env file")
    return Selected(key=SecretStr(key), model=chosen)


def child_environment(selected: Selected) -> dict[str, str]:
    """The whole environment of the reading process. Nothing else is inherited."""

    marks = _HostedMarks()
    return {
        # Blank, not absent: a load of the project .env fills only absent names.
        **dict.fromkeys(_PROVIDER_SETTINGS, ""),
        "RENDER": marks.render,
        "RENDER_SERVICE_ID": marks.render_service_id,
        "PYTHONPATH": os.pathsep.join(path for path in sys.path if path),
        KEY_SETTING: selected.key.get_secret_value(),
        MODEL_SETTING: selected.model,
    }


def run(args: argparse.Namespace) -> int:
    """Start the reading process and return its exit code."""

    selected = load_settings(args.env_file, args.key_name, args.model)
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True)
    command = (
        sys.executable,
        "-m",
        "tests.evals.document_read.read_live",
        *("--out", str(args.out.resolve())),
        *("--candidate-sha", head.strip()),
        *("--cap-usd", str(args.cap_usd)),
        *("--only", *args.only),
    )
    reads = subprocess.run(
        command, cwd=ROOT, env=child_environment(selected), check=False
    )
    return reads.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--key-name", default="OPENROUTER_API_KEY")
    parser.add_argument("--model")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--cap-usd", type=float, default=2.0)
    raise SystemExit(run(parser.parse_args()))


if __name__ == "__main__":
    main()

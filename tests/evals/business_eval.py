"""Inputs used to verify the archived Business measurement."""

from __future__ import annotations

import hashlib
from pathlib import Path

CASE_DIR = Path(__file__).with_name("business_cases")
JUDGE_MODEL = "x-ai/grok-4.3"
APPROVED_JUDGE_MODELS = (
    JUDGE_MODEL,
    "anthropic/claude-haiku-5.5",
    "anthropic/claude-sonnet-5.5",
    "openai/gpt-6-luna-pro",
)
RUNTIME_CANDIDATES = (
    "anthropic/claude-haiku-5.5",
    "openai/gpt-6-luna-pro",
    "deepseek/deepseek-v4.1-flash",
)


def fixture_digest(directory: Path = CASE_DIR) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.yaml")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()

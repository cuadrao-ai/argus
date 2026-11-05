"""Canonical identity hashing and Idempotency-Key validation for every write."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import date, datetime
from typing import Any, Literal


class CanonicalJSONError(ValueError):
    """A value cannot participate in canonical identity serialization."""


def _canonical_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise CanonicalJSONError("non-finite numbers are not canonical")
    if isinstance(value, uuid.UUID):
        return str(value).lower()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Canonical serializer: sorted keys, compact, unescaped UTF-8, real nulls."""

    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


KeyState = Literal["ok", "missing", "invalid"]


def validate_idempotency_key(raw: str | None) -> tuple[KeyState, str | None]:
    """1-128 visible ASCII (0x21-0x7e); no trimming or other normalization."""

    if raw is None:
        return "missing", None
    if raw == "" or raw.strip() == "":
        return "missing", None
    if any(character.isspace() for character in raw):
        return "invalid", None
    if not (1 <= len(raw) <= 128):
        return "invalid", None
    if any(not (0x21 <= ord(character) <= 0x7E) for character in raw):
        return "invalid", None
    return "ok", raw

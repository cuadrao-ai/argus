"""Serialize the exact assistant prose a judge scored, for failure attribution.

Retention is additive: nothing here may reach a verdict, a failed check, or a
status. Redaction and truncation shape the serialized copy only, never the
string handed to the judge.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from argus.domain.credential_shapes import (
    BEARER_PATTERN,
    CREDENTIAL_KEY_PATTERN,
    JWT_PATTERN,
    PREFIXED_KEY_PATTERN,
    PRIVATE_KEY_BANNER_PATTERN,
    UPPERCASE_KEY_PATTERN,
    URL_USERINFO_PATTERN,
    environment_secret_values,
)

# The response-style contract asks for one or two short paragraphs, so this
# budget keeps conforming prose whole and clips only degenerate output.
PROSE_TEXT_RETENTION_LIMIT = 4000
# Judges react to closing capability claims as often as to opening tone, so the
# tail survives truncation instead of only the first N characters.
PROSE_TEXT_RETENTION_TAIL = 1500
PROSE_TEXT_ELISION_TEMPLATE = "\n[... {count} characters elided ...]\n"

_CREDENTIAL_KEY = CREDENTIAL_KEY_PATTERN
_CREDENTIAL_ASSIGNMENT = rf"[\"']?{_CREDENTIAL_KEY}[\"']?\s*[:=]\s*"
# An auth value is a scheme followed by its credentials, so the space after the
# scheme name does not end the value.
_AUTH_SCHEME = r"(?:bearer|basic|digest|negotiate|token|apikey)"
# Retained prose is provider and runtime error output, so a dumped request or
# response header is the realistic leak vector. A header value owns its own
# internal separators, so it ends at the line, not at the first space or `;`.
_CREDENTIAL_HEADER = (
    r"(?:set-)?cookie|proxy-authorization|x-api-key|x-auth-token|x-csrf-token"
    r"|x-amz-security-token|x-goog-api-key"
)
# A quoted value ends at its closing quote, and a backslash escape is not that
# quote.
_DOUBLE_QUOTED = r'"(?:[^"\\\n]|\\.){4,}"'
_SINGLE_QUOTED = r"'(?:[^'\\\n]|\\.){4,}'"
_MARKER_PREFIX = "[redacted:"

# Every rule must consume a secret to its real end. A value's boundary comes
# from its own grammar, the opener, its escape convention, and its internal
# separators, never from a generic delimiter set: cutting early publishes the
# tail, and the shortened head can also fall under a length guard so the rule
# stops firing and publishes the whole value.
#
# Ordered: narrower structural rules run before the generic address rule, and
# quoted assignments run before unquoted ones.
_REDACTION_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        PRIVATE_KEY_BANNER_PATTERN,
        "[redacted:private_key]",
    ),
    (
        "jwt",
        JWT_PATTERN,
        "[redacted:jwt]",
    ),
    (
        "bearer_token",
        BEARER_PATTERN,
        r"\1 [redacted:bearer_token]",
    ),
    (
        "api_key",
        PREFIXED_KEY_PATTERN,
        "[redacted:api_key]",
    ),
    (
        "api_key",
        UPPERCASE_KEY_PATTERN,
        "[redacted:api_key]",
    ),
    (
        "url_userinfo",
        URL_USERINFO_PATTERN,
        "[redacted:url_userinfo]@",
    ),
    (
        # A quoted header value still ends at its closing quote.
        "credential_header",
        re.compile(
            rf"(?i)([\"']?(?:{_CREDENTIAL_HEADER})[\"']?\s*[:=]\s*)"
            rf"(?:{_DOUBLE_QUOTED}|{_SINGLE_QUOTED})"
        ),
        r"\1[redacted:credential_header]",
    ),
    (
        # Unquoted, a header value owns every separator it contains, so only
        # the line ends it.
        "credential_header",
        re.compile(
            rf"(?im)([\"']?(?:{_CREDENTIAL_HEADER})[\"']?\s*[:=]\s*)[^\n\"']{{4,}}"
        ),
        r"\1[redacted:credential_header]",
    ),
    (
        # A quoted value runs to its closing quote, whatever it contains.
        "credential_assignment",
        re.compile(rf"(?i)({_CREDENTIAL_ASSIGNMENT}){_DOUBLE_QUOTED}"),
        r'\1"[redacted:credential_assignment]"',
    ),
    (
        "credential_assignment",
        re.compile(rf"(?i)({_CREDENTIAL_ASSIGNMENT}){_SINGLE_QUOTED}"),
        r"\1'[redacted:credential_assignment]'",
    ),
    (
        # An unterminated quote, as in a clipped log line, has no closing
        # delimiter to trust, so the line end is the only safe boundary.
        "credential_assignment",
        re.compile(rf"(?im)({_CREDENTIAL_ASSIGNMENT})[\"'](?:[^\"'\\\n]|\\.){{4,}}$"),
        r"\1[redacted:credential_assignment]",
    ),
    (
        "credential_assignment",
        re.compile(
            rf"(?i)({_CREDENTIAL_ASSIGNMENT})((?:{_AUTH_SCHEME}\s+)?)"
            rf"[^\s,;&)}}\]\"']{{6,}}"
        ),
        r"\1\2[redacted:credential_assignment]",
    ),
    (
        # RFC 5322 atext, so an address like o'brien@ or weird!name@ does not
        # leave its opening characters behind as a partial identifier.
        "email",
        re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[\w-]+\.[\w.-]*\w"),
        "[redacted:email]",
    ),
)


def judged_prose_evidence(assistant_text: str) -> dict[str, Any]:
    """Return the retention record for the exact text supplied to the judge.

    ``text`` equals the judged string verbatim whenever ``truncated`` is false
    and ``redactions`` is empty; ``sha256`` and ``character_count`` always
    describe the judged string itself so two runs stay comparable.
    """
    redacted, redactions = redact_sensitive_text(assistant_text)
    retained, omitted = truncate_retained_text(redacted)
    return {
        "text": retained,
        "sha256": hashlib.sha256(assistant_text.encode("utf-8")).hexdigest(),
        "character_count": len(assistant_text),
        "truncated": omitted > 0,
        "omitted_character_count": omitted,
        "redactions": redactions,
    }


def redact_sensitive_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Strip credential-shaped and user-identifying spans from committed text."""
    counts: dict[str, int] = {}
    redacted = text
    for secret in environment_secret_values():
        occurrences = redacted.count(secret)
        if occurrences:
            redacted = redacted.replace(secret, "[redacted:environment_secret]")
            counts["environment_secret"] = (
                counts.get("environment_secret", 0) + occurrences
            )
    for kind, pattern, replacement in _REDACTION_RULES:
        redacted, applied = _apply_rule(redacted, pattern, replacement)
        if applied:
            counts[kind] = counts.get(kind, 0) + applied
    return redacted, [{"kind": kind, "count": counts[kind]} for kind in sorted(counts)]


def _apply_rule(
    text: str,
    pattern: re.Pattern[str],
    replacement: str,
) -> tuple[str, int]:
    applied = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal applied
        # An earlier rule already removed this span; redacting it again would
        # report one secret as two.
        if _MARKER_PREFIX in match.group(0):
            return match.group(0)
        applied += 1
        return match.expand(replacement)

    return pattern.sub(replace, text), applied


def truncate_retained_text(text: str) -> tuple[str, int]:
    """Clip to the retention budget, keeping the head and the tail."""
    if len(text) <= PROSE_TEXT_RETENTION_LIMIT:
        return text, 0
    head_length = PROSE_TEXT_RETENTION_LIMIT - PROSE_TEXT_RETENTION_TAIL
    omitted = len(text) - PROSE_TEXT_RETENTION_LIMIT
    return (
        text[:head_length]
        + PROSE_TEXT_ELISION_TEMPLATE.format(count=omitted)
        + text[-PROSE_TEXT_RETENTION_TAIL:],
        omitted,
    )



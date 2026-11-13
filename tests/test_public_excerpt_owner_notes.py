"""Owner-chosen prose is no longer refused by credential-shape heuristics.

Credential safety checks remain independent of sharing decisions.
"""

from __future__ import annotations

import re

import pytest
from argus.domain.public_excerpts import (
    audit_public_excerpt_document,
    normalize_owner_note,
)

# Owner notes use the same exact-preview boundary as question and answer prose.


# Real credential shapes. Each is a distinct grammar: an issuer prefix, a segment
# count, a scheme keyword, a PEM banner, userinfo in a URL. None is caught by length
# alone, which is the point.
#
# Assembled from a prefix and a body at import time so no live-looking key literal
# sits in this file. A pushed literal trips secret scanning, and the correct answer
# to that is a fixture that cannot be mistaken for a credential, not an allowlist
# entry that teaches the scanner to ignore one.
def _shaped(prefix: str, body: str, template: str = "{}") -> str:
    return template.format(f"{prefix}{body}")


CREDENTIAL_NOTES: tuple[tuple[str, str], ...] = (
    (
        "aws access key id",
        _shaped("AKIA", "IOSFODNN7EXAMPLE", "keys {} for the data pull"),
    ),
    (
        "aws secret access key",
        _shaped("wJalrXUtnFEMI", "K7MDENGbPxRfiCYEXAMPLEKEY", "secret {} used here"),
    ),
    ("github classic token", _shaped("ghp", "_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")),
    ("github fine grained token", _shaped("github", "_pat_11ABCDE0000_ABCDEFGHIJ")),
    ("stripe live secret", _shaped("sk", "_live_EXAMPLENOTAREALKEY")),
    ("stripe publishable", _shaped("pk", "_live_EXAMPLENOTAREALKEY")),
    ("slack bot token", _shaped("xoxb", "-0000000000-EXAMPLENOTAREAL")),
    ("gitlab token", _shaped("glpat", "-EXAMPLENOTAREALTOKEN")),
    (
        "jwt",
        _shaped(
            "eyJhbGciOiJIUzI1NiJ9.",
            "eyJzdWIiOiJFWEFNUExFIn0.EXAMPLEnotAREALsignature00",
        ),
    ),
    ("bearer header", _shaped("Bearer ", "EXAMPLEnotAREALtoken00", "Authorization: {}")),
    ("private key banner", "-----BEGIN RSA PRIVATE KEY-----"),
    ("url userinfo", _shaped("admin:", "notarealpassword", "from https://{}@host/x")),
    ("keyed opaque value", _shaped("api_key = ", "a1b2c3d4e5f6g7")),
    # The key is the signal, so none of these depend on the value's size or its
    # character class. Each of the three evaded a length or charset guard.
    ("short keyed password", _shaped("password=", "hunter2")),
    ("punctuated keyed password", _shaped("password=", "P@ssw0rd")),
    ("one character keyed secret", _shaped("PASSWORD = ", "x")),
    ("short keyed api key", _shaped("api_key: ", "abc")),
    ("keyed token", _shaped("token: ", "a")),
    ("keyed client secret", _shaped("client_secret = ", "shh")),
    ("keyed access key", _shaped("access_key: ", "q")),
)

# Notes a real owner might write. Several deliberately name a credential without
# carrying one, because redaction that eats ordinary notes defeats the feature.
ORDINARY_NOTES: tuple[str, ...] = (
    "The secret: consistency beat every clever entry rule I tried.",
    "Tested my token strategy on the dip and it held up better than expected.",
    "Ran this for my brother in law who kept asking whether timing works.",
    "Password protected my spreadsheet after this, the numbers surprised me.",
    "Shared because the drawdown in March 2020 is the part people forget.",
    "My key takeaway is that the benchmark won on a risk adjusted basis.",
    "Access to good data mattered more than the rules themselves.",
    "AAPL and SPY only, monthly buys of 500 dollars, no leverage anywhere.",
    "Authorization from nobody needed, this is just my own money and my own idea.",
    "Probé esto en español y el resultado fue peor que comprar y mantener.",
    # Naming a credential is not carrying one. Redaction that eats ordinary notes
    # defeats the feature, so these are as load-bearing as the cases above.
    "the password reset flow is what finally convinced me to try this",
    "my api key expired last week so the data stops in March",
    "token economics were the whole reason I looked at this one",
    "I wrote my password down somewhere safe and moved on",
    "the secret: patience. Nothing clever, just not selling.",
)


@pytest.mark.parametrize(("name", "note"), CREDENTIAL_NOTES, ids=lambda value: value)
def test_owner_preview_accepts_credential_shaped_prose(name: str, note: str) -> None:
    assert normalize_owner_note(note) == note


@pytest.mark.parametrize("note", ORDINARY_NOTES, ids=lambda value: value[:36])
def test_an_ordinary_note_is_not_over_redacted(note: str) -> None:
    """Naming a credential in a sentence does not make the sentence one."""
    assert normalize_owner_note(note) == note


def test_credential_shapes_do_not_override_the_owner_preview() -> None:
    audit_public_excerpt_document({"idea_title": "AKIAIOSFODNN7EXAMPLE run"})


def test_every_recognized_credential_key_is_caught_when_assigned() -> None:
    """The guard for the credential class, at the altitude the class lives at.

    Two hand-written alternations had to agree and did not, so `csrf_token=x` reached a
    public page while `password=x` did not. Both grammars are now generated from one
    list, and this walks that list: every name, in each separator spelling, with a one
    character value, must be refused. The value is never the reason.
    """
    from argus.domain.credential_shapes import (
        CREDENTIAL_KEY_NAMES,
        credential_shape_in,
    )

    missed: list[str] = []
    for name in CREDENTIAL_KEY_NAMES:
        for separator in ("_", "-", "", " "):
            key = separator.join(name.split())
            for assignment in (f"{key}=x", f"{key}: x", f"{key.upper()} = 1"):
                if credential_shape_in(assignment) is None:
                    missed.append(assignment)
    assert not missed, f"assigned credential keys not caught: {missed}"


def test_the_two_credential_grammars_cannot_disagree() -> None:
    """One list, both grammars. A second list is how the class stayed open."""
    from argus.domain import credential_shapes

    for name in credential_shapes.CREDENTIAL_KEY_NAMES:
        spelling = "_".join(name.split())
        # Present in the shared pattern the eval lane consumes...
        assert re.search(
            credential_shapes.CREDENTIAL_KEY_PATTERN, spelling, re.IGNORECASE
        ), f"{spelling} missing from the shared key pattern"
        # ...and in the assignment rule the receipt path consumes.
        assert credential_shapes.keyed_credential_in(f"{spelling}=x"), spelling

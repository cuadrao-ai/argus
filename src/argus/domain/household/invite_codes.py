"""Invite codes, links and settings shared by household and beta invites.

A code is 12 Crockford base32 characters (60 bits), shown as XXXX-XXXX-XXXX.
Only a keyed digest is stored, in ``argus_private.invite_code_digests``, never
on a client-readable table: HMAC-SHA-256 under a server secret that lives in
the environment and never in the database. The digest names its version and
the key that made it (``v2.<key id>.<hex>``), so a secret can be rotated: the
previous secret still finds its codes, and a code found under it is re-hashed
to the current secret on use. There is no unkeyed fallback; without a secret
codes cannot be made or looked up (fail closed).

The link token is 256 random bits and stays a plain SHA-256 digest: a digest of
that much entropy cannot be reversed, so a key would add nothing. It stays in
the URL fragment, so it never reaches a web server log.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
import secrets
from collections import Counter
from dataclasses import dataclass, field

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.household.errors import InviteCodesUnavailable

CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 12
CODE_GROUP = 4
UNIVERSAL_LINK_BASE = "https://cuadrao.ai/invite#"
LEGACY_HOUSEHOLD_LINK_BASE = "argus-household://invite#"
BETA_INVITE_QUOTA = 10
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1", "U": "V"})

# Read by InviteCodeSecretSettings (env_prefix + field name).
CODE_SECRET_ENV = "CUADRAO_INVITE_CODE_SECRET"
CODE_SECRET_PREVIOUS_ENV = "CUADRAO_INVITE_CODE_SECRET_PREVIOUS"
MIN_SECRET_LENGTH = 32
# A placeholder like "a" * 32 or "changeme" repeated is refused. This is a
# floor against obvious mistakes, not a strength proof: generate the secret
# with `openssl rand -base64 48`. A random 32-character hex value can fail
# this estimate when its character frequencies are skewed.
MIN_SECRET_DISTINCT = 10
MIN_SECRET_BITS = 96
DIGEST_VERSION = "v2"
DIGEST_PATTERN = re.compile(r"^v2\.[0-9a-f]{8}\.[0-9a-f]{64}$")
# Flags that turn on a surface which makes or looks up codes.
CODE_FLAGS = (
    "CUADRAO_HOUSEHOLDS_ENABLED",
    "CUADRAO_BETA_INVITES_ENABLED",
    "CUADRAO_BETA_INVITE_GATE_ENABLED",
)


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw: str) -> str | None:
    """Uppercase, drop separators, fold look-alike letters. None if invalid."""
    value = "".join(ch for ch in raw.upper() if ch not in " -_\t").translate(_CONFUSABLE)
    if len(value) != CODE_LENGTH or any(ch not in CODE_ALPHABET for ch in value):
        return None
    return value


def format_code(code: str) -> str:
    return "-".join(code[i : i + CODE_GROUP] for i in range(0, len(code), CODE_GROUP))


class InviteCodeSecretSettings(BaseSettings):
    """``CUADRAO_INVITE_CODE_SECRET`` and ``CUADRAO_INVITE_CODE_SECRET_PREVIOUS``.

    Read fresh on each call (like the surface flags), never from a file, and
    kept as ``SecretStr`` so a repr or log line cannot show a value. Length
    and presence are checked by ``CodeHasher.from_secrets``, which fails closed.
    """

    model_config = SettingsConfigDict(env_prefix="CUADRAO_INVITE_CODE_", extra="ignore")
    secret: SecretStr | None = None
    secret_previous: SecretStr | None = None


def _reveal(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


@dataclass(frozen=True)
class CodeKey:
    """One server secret. ``key_id`` names it in stored digests, not the secret."""

    key_id: str
    secret: bytes = field(repr=False)

    @classmethod
    def from_secret(cls, raw: str) -> CodeKey:
        value = raw.strip()
        if len(value) < MIN_SECRET_LENGTH:
            raise InviteCodesUnavailable(
                f"The invite code secret must be at least {MIN_SECRET_LENGTH} characters."
            )
        if _estimated_bits(value) < MIN_SECRET_BITS or (
            len(set(value)) < MIN_SECRET_DISTINCT
        ):
            raise InviteCodesUnavailable(
                "The invite code secret looks like a placeholder; generate one"
                " with `openssl rand -base64 48`."
            )
        secret = value.encode("utf-8")
        key_id = hmac.new(secret, b"argus-invite-code-key-id", hashlib.sha256)
        return cls(key_id=key_id.hexdigest()[:8], secret=secret)

    def digest(self, code: str) -> str:
        mac = hmac.new(
            self.secret,
            f"argus-invite-code:{DIGEST_VERSION}:{code}".encode(),
            hashlib.sha256,
        )
        return f"{DIGEST_VERSION}.{self.key_id}.{mac.hexdigest()}"


def _estimated_bits(value: str) -> float:
    """Length times the per-character Shannon entropy of the value itself."""
    counts = Counter(value)
    total = len(value)
    per_char = -sum(n / total * math.log2(n / total) for n in counts.values())
    return per_char * total


@dataclass(frozen=True)
class CodeHasher:
    """The current secret makes digests; the previous one only finds old codes."""

    current: CodeKey
    previous: CodeKey | None = None

    @classmethod
    def from_secrets(cls, current: str | None, previous: str | None = None) -> CodeHasher:
        if not current or not current.strip():
            raise InviteCodesUnavailable()
        key = CodeKey.from_secret(current)
        old = CodeKey.from_secret(previous) if previous and previous.strip() else None
        if old is not None and old.key_id == key.key_id:
            old = None
        return cls(current=key, previous=old)

    @classmethod
    def from_env(cls) -> CodeHasher:
        settings = InviteCodeSecretSettings()
        return cls.from_secrets(
            _reveal(settings.secret), _reveal(settings.secret_previous)
        )

    def digest(self, code: str) -> str:
        return self.current.digest(code)

    def candidates(self, code: str) -> list[str]:
        """Digests to look a typed code up by: current secret first."""
        keys = [self.current] + ([self.previous] if self.previous else [])
        return [key.digest(code) for key in keys]


def code_surface_on() -> bool:
    return any(_flag(name) for name in CODE_FLAGS)


def code_secret_problem() -> str | None:
    """Why codes cannot work right now, or None. Read by readiness and startup."""
    try:
        CodeHasher.from_env()
    except InviteCodesUnavailable as error:
        return error.detail
    return None


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def _text(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@dataclass(frozen=True)
class InviteSettings:
    universal_link_enabled: bool = False
    gate_enabled: bool = False
    waitlist_url: str | None = None
    testflight_url: str | None = None
    founder_user_id: str | None = None
    quota: int = BETA_INVITE_QUOTA

    @classmethod
    def from_env(cls) -> InviteSettings:
        return cls(
            universal_link_enabled=_flag("CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED"),
            gate_enabled=_flag("CUADRAO_BETA_INVITE_GATE_ENABLED"),
            waitlist_url=_text("CUADRAO_WAITLIST_URL"),
            testflight_url=_text("CUADRAO_TESTFLIGHT_PUBLIC_URL"),
            founder_user_id=_text("CUADRAO_INVITE_FOUNDER_USER_ID"),
        )

    def is_founder(self, user_id: str | None) -> bool:
        """Only a verified, non-empty subject can be the founder; null never is."""
        if not self.founder_user_id or not user_id:
            return False
        return self.founder_user_id.strip().lower() == str(user_id).strip().lower()


def invite_link(token: str, *, household: bool, settings: InviteSettings) -> str | None:
    """The share link. Off keeps today's household scheme; beta has no link yet."""
    if settings.universal_link_enabled:
        return UNIVERSAL_LINK_BASE + token
    return LEGACY_HOUSEHOLD_LINK_BASE + token if household else None


def unique_code(connection, hasher: CodeHasher) -> tuple[str, str]:  # noqa: ANN001
    """A code no live digest already names, under the current or previous secret."""
    for _ in range(8):
        code = new_code()
        taken = connection.execute(
            "select 1 from argus_private.invite_code_digests where digest=any(%s)",
            (hasher.candidates(code),),
        ).fetchone()
        if taken is None:
            return code, hasher.digest(code)
    raise RuntimeError("Could not allocate a unique invite code.")


def store_code(
    connection,  # noqa: ANN001
    digest: str,
    *,
    household_invitation_id: str | None = None,
    beta_invitation_id: str | None = None,
) -> None:
    connection.execute(
        "insert into argus_private.invite_code_digests"
        "(digest,household_invitation_id,beta_invitation_id) values(%s,%s,%s)",
        (digest, household_invitation_id, beta_invitation_id),
    )


def find_code(connection, code: str | None, hasher: CodeHasher) -> str | None:  # noqa: ANN001
    """The invitation id a typed code names, household or beta, or None.

    A code found under the previous secret is re-hashed to the current one, so
    long-lived group-link codes move to the new secret as they are used.
    """
    normalized = normalize_code(code or "")
    if normalized is None:
        return None
    candidates = hasher.candidates(normalized)
    row = connection.execute(
        "select digest,coalesce(household_invitation_id,beta_invitation_id)"
        " from argus_private.invite_code_digests where digest=any(%s)"
        " order by digest=%s desc limit 1",
        (candidates, candidates[0]),
    ).fetchone()
    if row is None:
        return None
    if row[0] != candidates[0]:
        connection.execute(
            "update argus_private.invite_code_digests set digest=%s,rehashed_at=now()"
            " where digest=%s",
            (candidates[0], row[0]),
        )
    return str(row[1])

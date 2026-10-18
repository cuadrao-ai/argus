"""Fail closed unless both coordinates name the Cuadrao staging project.

There is no override. A missing, unknown, or mismatched target is a refusal.
Error text never includes the URL: a database URL can carry a password.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict

STAGING_REF = "skedzwocnmrhfigiwyzi"
STAGING_HOST = f"{STAGING_REF}.supabase.co"
SEED_SPACE_NAME = "QA Seed"
_QA_OWNER = re.compile(r"^qa-seed(?:\+[^@]+)?@[^@\s]+$")


class StagingRefused(RuntimeError):
    """The process is not allowed to write."""


def refuse_unless_staging(environ: Mapping[str, str]) -> str:
    """Return the staging ref, or raise when the target is not that project."""

    url_ref = _supabase_ref(environ)
    database_ref = _database_ref(environ)
    if url_ref != STAGING_REF or database_ref != STAGING_REF:
        raise StagingRefused("refusing to write: target is not the staging project")
    service_key = (environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not service_key:
        raise StagingRefused("refusing to write: staging service role is not configured")
    return STAGING_REF


def refuse_unless_plaid_sandbox(environ: Mapping[str, str]) -> None:
    """Sandbox only. Checked from the environment before any product import."""

    environment = (environ.get("PLAID_ENV") or "").strip().lower() or "sandbox"
    if environment != "sandbox":
        raise StagingRefused("refusing to write: Plaid is not sandbox")
    injected = (environ.get("PLAID_CREDENTIALS_INJECTED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    has_keys = bool((environ.get("PLAID_CLIENT_ID") or "").strip()) and bool(
        (environ.get("PLAID_SECRET") or "").strip()
    )
    if not has_keys and not injected:
        raise StagingRefused(
            "refusing to write: Plaid sandbox credentials are not configured"
        )
    secret = (
        environ.get("CUADRAO_INGESTION_SECRET_KEY")
        or environ.get("ARGUS_INGESTION_SECRET_KEY")
        or ""
    ).strip()
    if not secret:
        raise StagingRefused("refusing to write: ingestion secret is not configured")


def _supabase_ref(environ: Mapping[str, str]) -> str:
    raw = (
        environ.get("SUPABASE_URL") or environ.get("SUPABASE_PROJECT_URL") or ""
    ).strip()
    if not raw:
        raise StagingRefused("refusing to write: Supabase URL is not configured")
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or host != STAGING_HOST:
        raise StagingRefused("refusing to write: Supabase URL is not the staging project")
    return STAGING_REF


def require_qa_owner(email: str) -> str:
    """The only account the seed may write. ``qa-seed@`` or ``qa-seed+...@``."""

    cleaned = email.strip().lower()
    if _QA_OWNER.fullmatch(cleaned) is None:
        raise StagingRefused("refusing to write: the account is not a QA seed account")
    return cleaned


def require_seed_space(name: str | None) -> None:
    """An owner with no Business, or the Business this seed created."""

    if name is not None and name != SEED_SPACE_NAME:
        raise StagingRefused("refusing to write: the account already owns a Business")


def _database_ref(environ: Mapping[str, str]) -> str:
    raw = (environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raise StagingRefused("refusing to write: database URL is not configured")
    try:
        info = conninfo_to_dict(raw)
    except Exception:
        raise StagingRefused(
            "refusing to write: database URL is not the staging project"
        ) from None
    # libpq connects to hostaddr even when host names staging, and a query
    # `host` replaces the URI host. A comma is more than one host.
    if info.get("hostaddr"):
        raise StagingRefused("refusing to write: database URL is not the staging project")
    host = str(info.get("host") or "").strip().lower()
    if not host or "," in host:
        raise StagingRefused("refusing to write: database URL is not the staging project")
    if host.endswith(".pooler.supabase.com"):
        username = str(info.get("user") or "")
        prefix = "postgres."
        if not username.startswith(prefix) or username[len(prefix) :] != STAGING_REF:
            raise StagingRefused(
                "refusing to write: database URL is not the staging project"
            )
        return STAGING_REF
    if host.removeprefix("db.") != STAGING_HOST:
        raise StagingRefused("refusing to write: database URL is not the staging project")
    return STAGING_REF

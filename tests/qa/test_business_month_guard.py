"""The seed refuses every target except the staging project, with no override."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

QA = Path(__file__).resolve().parents[2] / "scripts" / "qa"
sys.path.insert(0, str(QA))
guard = importlib.import_module("business_month_guard")

STAGING = "skedzwocnmrhfigiwyzi"
PROD = "lgdhvepyrzbnscqssgqq"
PASSWORD = "super-secret-db-password"


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "SUPABASE_URL": f"https://{STAGING}.supabase.co",
        "DATABASE_URL": (
            f"postgresql://postgres.{STAGING}:{PASSWORD}"
            f"@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        ),
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
    }
    base.update(overrides)
    return base


def test_staging_pooler_and_direct_hosts_are_accepted() -> None:
    assert guard.refuse_unless_staging(_env()) == STAGING
    direct = _env(
        DATABASE_URL=f"postgresql://postgres:{PASSWORD}@db.{STAGING}.supabase.co:5432/postgres"
    )
    assert guard.refuse_unless_staging(direct) == STAGING


@pytest.mark.parametrize(
    "overrides",
    [
        {"SUPABASE_URL": f"https://{PROD}.supabase.co"},
        {"SUPABASE_URL": "https://otherprojectref.supabase.co"},
        {"SUPABASE_URL": ""},
        {"DATABASE_URL": ""},
        {"SUPABASE_SERVICE_ROLE_KEY": ""},
        {
            "DATABASE_URL": (
                f"postgresql://postgres:{PASSWORD}@db.{PROD}.supabase.co:5432/postgres"
            )
        },
        {
            "DATABASE_URL": (
                f"postgresql://postgres.{PROD}:{PASSWORD}"
                "@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            )
        },
        {"DATABASE_URL": "not a url"},
        {"SUPABASE_URL": f"http://{STAGING}.supabase.co"},
    ],
)
def test_anything_other_than_staging_is_refused(overrides: dict[str, str]) -> None:
    with pytest.raises(guard.StagingRefused) as caught:
        guard.refuse_unless_staging(_env(**overrides))
    message = str(caught.value)
    assert PASSWORD not in message
    assert "postgresql" not in message
    assert PROD not in message


def test_a_query_host_or_hostaddr_is_refused() -> None:
    cases = [
        (
            f"postgresql://postgres:{PASSWORD}@db.{STAGING}.supabase.co/postgres"
            f"?host=db.{PROD}.supabase.co"
        ),
        (
            f"postgresql://postgres:{PASSWORD}@db.{STAGING}.supabase.co/postgres"
            "?hostaddr=127.0.0.1"
        ),
        (
            f"host=db.{STAGING}.supabase.co,db.{PROD}.supabase.co user=postgres "
            f"password={PASSWORD} dbname=postgres"
        ),
    ]
    for database_url in cases:
        with pytest.raises(guard.StagingRefused) as caught:
            guard.refuse_unless_staging(_env(DATABASE_URL=database_url))
        message = str(caught.value)
        assert PASSWORD not in message
        assert "postgresql" not in message
        assert PROD not in message
        assert "127.0.0.1" not in message
        assert STAGING not in message


def test_keyword_form_uses_the_effective_staging_host() -> None:
    accepted = _env(
        DATABASE_URL=(
            f"host=db.{STAGING}.supabase.co user=postgres password={PASSWORD} "
            "dbname=postgres"
        )
    )
    assert guard.refuse_unless_staging(accepted) == STAGING


def test_only_a_qa_seed_account_with_no_other_business_may_write() -> None:
    assert guard.require_qa_owner("QA-Seed+October@Example.com") == (
        "qa-seed+october@example.com"
    )
    assert guard.require_qa_owner("qa-seed@example.com") == "qa-seed@example.com"
    guard.require_seed_space(None)
    guard.require_seed_space(guard.SEED_SPACE_NAME)
    for email in ("owner@example.com", "qa+october@example.com", "qa-seed"):
        with pytest.raises(guard.StagingRefused) as caught:
            guard.require_qa_owner(email)
        assert "QA seed account" in str(caught.value)
    with pytest.raises(guard.StagingRefused) as caught:
        guard.require_seed_space("Mi negocio")
    assert "already owns a Business" in str(caught.value)


def test_there_is_no_override_parameter() -> None:
    assert "override" not in inspect.signature(guard.refuse_unless_staging).parameters


def test_plaid_must_be_sandbox_with_credentials() -> None:
    guard.refuse_unless_plaid_sandbox(
        {
            "PLAID_ENV": "sandbox",
            "PLAID_CLIENT_ID": "client",
            "PLAID_SECRET": "secret",
            "CUADRAO_INGESTION_SECRET_KEY": "key",
        }
    )
    with pytest.raises(guard.StagingRefused):
        guard.refuse_unless_plaid_sandbox(
            {
                "PLAID_ENV": "production",
                "PLAID_CLIENT_ID": "client",
                "PLAID_SECRET": "secret",
                "CUADRAO_INGESTION_SECRET_KEY": "key",
            }
        )
    with pytest.raises(guard.StagingRefused):
        guard.refuse_unless_plaid_sandbox({"PLAID_ENV": "sandbox"})

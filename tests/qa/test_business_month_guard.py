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

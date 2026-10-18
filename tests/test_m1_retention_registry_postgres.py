"""Exercise the private retention registry on the disposable migrated database."""

import os
from pathlib import Path

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL is not configured")


def test_m1_retention_registry_contract():
    psycopg = pytest.importorskip("psycopg")
    sql = Path(__file__).with_name("sql").joinpath("m1_retention_registry.sql")
    with psycopg.connect(DSN, autocommit=True) as connection:
        connection.execute(sql.read_text())

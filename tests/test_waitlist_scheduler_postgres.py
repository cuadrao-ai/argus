"""Verify scheduler credentials without committing a queued HTTP request."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import psycopg
import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def db():
    assert urlparse(DSN).hostname in {"localhost", "127.0.0.1", "::1"}
    with psycopg.connect(DSN) as connection, connection.transaction(force_rollback=True):
        connection.execute(
            "select vault.create_secret(%s, %s)",
            ("https://skedzwocnmrhfigiwyzi.supabase.co", "cuadrao_waitlist_project_url"),
        )
        yield connection


def test_scheduler_queues_only_the_dedicated_secret_header(db):
    db.execute(
        "select vault.create_secret(%s, %s)",
        ("local-scheduler-fixture", "cuadrao_waitlist_scheduler_key"),
    )
    request_id = db.execute("select cuadrao_scheduler.remind_waitlist()").fetchone()[0]
    assert db.execute(
        "select url, headers, timeout_milliseconds from net.http_request_queue where id=%s",
        (request_id,),
    ).fetchone() == (
        "https://skedzwocnmrhfigiwyzi.supabase.co/functions/v1/waitlist-reminders",
        {
            "Content-Type": "application/json",
            "X-Cuadrao-Waitlist-Scheduler-Key": "local-scheduler-fixture",
        },
        120000,
    )


def test_scheduler_does_not_fall_back_to_the_old_service_role_secret(db):
    db.execute(
        "select vault.create_secret(%s, %s)",
        ("local-old-service-fixture", "cuadrao_waitlist_service_role_key"),
    )
    with pytest.raises(psycopg.errors.RaiseException, match="credential is missing"):
        with db.transaction():
            db.execute("select cuadrao_scheduler.remind_waitlist()")


@pytest.mark.parametrize("role", ["anon", "authenticated", "service_role"])
def test_scheduler_rpc_remains_unavailable_to_client_roles(db, role):
    assert db.execute(
        "select has_schema_privilege(%s, 'cuadrao_scheduler', 'USAGE'), "
        "has_function_privilege(%s, 'cuadrao_scheduler.remind_waitlist()', 'EXECUTE')",
        (role, role),
    ).fetchone() == (False, False)

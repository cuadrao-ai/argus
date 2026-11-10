"""Recovery proofs for state the welcome-email code did not create.

Rows approved before the enforcement migration, claims left unconsumed by an
outage, and delivery rows without a matching allowlist state must all be
operable through service-role surfaces alone.
"""

from __future__ import annotations

import os

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")

from test_access_request_postgres import (  # noqa: E402
    _claim_token,
    _claim_welcome,
    _cleanup_access_rows,
    _complete_welcome,
    _insert_allowlist_row,
    _random_email,
)


def test_pre_migration_user_revoke_and_reenable_survive_without_delivery() -> None:
    # A row approved before the welcome-email feature existed: role user,
    # zero delivery rows. Revoke and restore must both work.
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="user")

                cursor.execute("set role service_role")
                cursor.execute(
                    "update public.private_alpha_allowlist set disabled_at = now() "
                    "where email = %s",
                    (email,),
                )
                cursor.execute(
                    "update public.private_alpha_allowlist set disabled_at = null "
                    "where email = %s",
                    (email,),
                )
                cursor.execute("reset role")

                cursor.execute(
                    "select role, disabled_at from public.private_alpha_allowlist "
                    "where email = %s",
                    (email,),
                )
                assert cursor.fetchone() == ("user", None)
    finally:
        _cleanup_access_rows(email)


def test_emergency_rollback_succeeds_while_a_claim_is_open() -> None:
    # The documented allowlist-only kill switch must work during precisely
    # the incident that leaves claims open.
    claimed = _random_email()
    plain = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=claimed, role="requested")
                _insert_allowlist_row(cursor, email=plain, role="requested")
                _claim_token(cursor, email=claimed)

                cursor.execute("set role service_role")
                cursor.execute(
                    """
                    update public.private_alpha_allowlist
                    set disabled_at = coalesce(disabled_at, now()),
                        updated_at = now()
                    where role = 'requested' and disabled_at is null
                      and email in (%s, %s)
                    """,
                    (claimed, plain),
                )
                cursor.execute("reset role")

                cursor.execute(
                    """
                    select count(*) from public.private_alpha_allowlist
                    where email in (%s, %s) and disabled_at is null
                    """,
                    (claimed, plain),
                )
                assert cursor.fetchone() == (0,)
    finally:
        _cleanup_access_rows(claimed)
        _cleanup_access_rows(plain)


def test_expired_claim_release_restores_approvability() -> None:
    # A claim left unconsumed by an outage: blocked at 24 hours, releasable
    # through the service-role RPC, then claimable again with a fresh token.
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")
                stale_token = _claim_token(cursor, email=email)

                cursor.execute(
                    """
                    update public.private_alpha_access_welcome_claims
                    set claimed_at = now() - interval '3 days'
                    where recipient_email = %s
                    """,
                    (email,),
                )
                blocked = _claim_welcome(cursor, email=email)
                assert blocked is not None
                assert blocked[-1] is False

                cursor.execute("set role service_role")
                cursor.execute(
                    "select public.release_expired_private_alpha_access_welcome_claims()"
                )
                released = cursor.fetchone()
                cursor.execute("reset role")
                assert released is not None and released[0] >= 1

                fresh_token = _claim_token(cursor, email=email)
                assert fresh_token != stale_token
    finally:
        _cleanup_access_rows(email)


def test_regrant_after_offboarding_sends_again_and_replaces_delivery() -> None:
    # A delivery row without a matching allowlist state: the person was
    # offboarded and re-requests in another language. The new grant must be
    # claimable, and completion must replace the stale delivery record.
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")
                first_token = _claim_token(cursor, email=email)
                assert _complete_welcome(
                    cursor,
                    email=email,
                    claim_token=first_token,
                ) == (True,)

                cursor.execute("set role service_role")
                cursor.execute(
                    "delete from public.private_alpha_allowlist where email = %s",
                    (email,),
                )
                cursor.execute("reset role")
                _insert_allowlist_row(
                    cursor, email=email, role="requested", language="es-419"
                )

                # The recorded-delivery replay must refuse a fresh grant even
                # though a delivery row exists: a requested row means a send
                # is owed, so promotion without email is not reachable.
                assert _complete_welcome(
                    cursor,
                    email=email,
                    language="es-419",
                    subject="Bienvenido a Argus",
                    claim_token=None,
                ) == (False,)

                second_token = _claim_token(
                    cursor,
                    email=email,
                    language="es-419",
                    subject="Bienvenido a Argus",
                )
                assert second_token != first_token
                assert _complete_welcome(
                    cursor,
                    email=email,
                    language="es-419",
                    subject="Bienvenido a Argus",
                    provider_receipt="resend-email-id-regrant",
                    claim_token=second_token,
                ) == (True,)

                cursor.execute(
                    """
                    select language, subject, provider_receipt
                    from public.private_alpha_access_welcome_deliveries
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (
                    "es-419",
                    "Bienvenido a Argus",
                    "resend-email-id-regrant",
                )
                cursor.execute(
                    "select role from public.private_alpha_allowlist " "where email = %s",
                    (email,),
                )
                assert cursor.fetchone() == ("user",)
    finally:
        _cleanup_access_rows(email)

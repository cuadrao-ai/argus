"""Real-Postgres proof for service-owned private-alpha access requests."""

from __future__ import annotations

import os
import ssl
from concurrent.futures import ThreadPoolExecutor
from email import message_from_string
from threading import Barrier

import pytest
from faker import Faker

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
LOCAL_URL = os.getenv("ARGUS_LOCAL_SUPABASE_URL", "").strip()
LOCAL_SERVICE_KEY = os.getenv("ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")
fake = Faker()

WELCOME_CONTENT_VERSION = "private-alpha-access-welcome/v1"
WELCOME_SUBJECT = "Welcome to Argus"
WELCOME_RECEIPT = "resend-email-id-461"
UNKNOWN_CLAIM_TOKEN = "00000000-0000-4000-8000-000000000000"


def _random_email() -> str:
    return fake.unique.email(domain="example.com").lower()


def _cleanup_access_rows(email: str) -> None:
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                delete from public.private_alpha_access_welcome_claims
                where recipient_email = %s
                """,
                (email,),
            )
            cursor.execute(
                """
                delete from public.private_alpha_access_welcome_deliveries
                where recipient_email = %s
                """,
                (email,),
            )
            cursor.execute(
                "delete from public.private_alpha_allowlist where email = %s",
                (email,),
            )


def _insert_allowlist_row(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    email: str,
    role: str,
    language: str = "en",
    disabled: bool = False,
) -> None:
    cursor.execute(
        """
        insert into public.private_alpha_allowlist (
          email,
          role,
          language,
          disabled_at
        )
        values (%s, %s, %s, case when %s then now() else null end)
        """,
        (email, role, language, disabled),
    )


def _complete_welcome(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    email: str,
    language: str = "en",
    content_version: str = WELCOME_CONTENT_VERSION,
    subject: str = WELCOME_SUBJECT,
    provider_receipt: str = WELCOME_RECEIPT,
    claim_token: str | None = UNKNOWN_CLAIM_TOKEN,
) -> tuple[bool]:
    cursor.execute("set role service_role")
    try:
        cursor.execute(
            """
            select public.complete_private_alpha_access_welcome(
              %s, %s, %s, %s, %s, %s
            )
            """,
            (
                email,
                language,
                content_version,
                subject,
                provider_receipt,
                claim_token,
            ),
        )
        result = cursor.fetchone()
        assert result is not None
        return result
    finally:
        cursor.execute("reset role")


def _claim_welcome(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    email: str,
    language: str = "en",
    content_version: str = WELCOME_CONTENT_VERSION,
    subject: str = WELCOME_SUBJECT,
) -> tuple[object, ...] | None:
    cursor.execute("set role service_role")
    try:
        cursor.execute(
            """
            select recipient_email, language, content_version, subject,
                   claim_token::text, claimed_at, send_allowed
            from public.claim_private_alpha_access_welcome(%s, %s, %s, %s)
            """,
            (email, language, content_version, subject),
        )
        return cursor.fetchone()
    finally:
        cursor.execute("reset role")


def _claim_token(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    email: str,
    language: str = "en",
    subject: str = WELCOME_SUBJECT,
) -> str:
    claim = _claim_welcome(
        cursor,
        email=email,
        language=language,
        subject=subject,
    )
    assert claim is not None
    assert claim[-1] is True
    token = claim[4]
    assert isinstance(token, str)
    return token


def test_access_request_constraints_and_rls_are_service_role_only() -> None:
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select relrowsecurity
                from pg_class
                where oid = 'public.private_alpha_allowlist'::regclass
                """
            )
            assert cursor.fetchone() == (True,)

            cursor.execute(
                """
                select
                  has_table_privilege(
                    'service_role',
                    'public.private_alpha_allowlist',
                    'select,insert,update,delete'
                  ),
                  (
                    select count(*)
                    from pg_policies
                    where schemaname = 'public'
                      and tablename = 'private_alpha_allowlist'
                  )
                """
            )
            assert cursor.fetchone() == (True, 0)

            cursor.execute(
                """
                select pg_get_constraintdef(oid)
                from pg_constraint
                where conrelid = 'public.private_alpha_allowlist'::regclass
                  and conname in (
                    'private_alpha_allowlist_role_check',
                    'private_alpha_allowlist_language_check'
                  )
                order by conname
                """
            )
            constraints = " ".join(row[0] for row in cursor.fetchall())

    assert "'requested'::text" in constraints
    assert "'es-419'::text" in constraints


def test_direct_requested_user_activation_without_delivery_is_rejected() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.private_alpha_allowlist (email, role, language)
                    values (%s, 'requested', 'en')
                    """,
                    (email,),
                )

                cursor.execute("set role service_role")
                with pytest.raises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        """
                        update public.private_alpha_allowlist
                        set role = 'user'
                        where email = %s
                        """,
                        (email,),
                    )
                cursor.execute("reset role")

                cursor.execute(
                    """
                    select role,
                           (
                             select count(*)
                             from public.private_alpha_access_welcome_deliveries
                             where recipient_email = %s
                           )
                    from public.private_alpha_allowlist
                    where email = %s
                    """,
                    (email, email),
                )
                assert cursor.fetchone() == ("requested", 0)
    finally:
        _cleanup_access_rows(email)


def test_pending_claim_reuses_token_inside_window_and_blocks_after_expiry() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")

                first = _claim_welcome(cursor, email=email)
                second = _claim_welcome(cursor, email=email)
                assert first is not None
                assert second is not None
                assert first[4] == second[4]
                assert first[-1] is second[-1] is True

                cursor.execute(
                    """
                    update public.private_alpha_access_welcome_claims
                    set claimed_at = now() - interval '24 hours'
                    where recipient_email = %s
                    """,
                    (email,),
                )

                expired = _claim_welcome(cursor, email=email)
                assert expired is not None
                assert expired[4] == first[4]
                assert expired[-1] is False
    finally:
        _cleanup_access_rows(email)


def test_open_claim_never_blocks_operator_lifecycle_and_fails_closed() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")
                claim_token = _claim_token(cursor, email=email)

                cursor.execute("set role service_role")
                cursor.execute(
                    "update public.private_alpha_allowlist set disabled_at = now() "
                    "where email = %s",
                    (email,),
                )
                cursor.execute("reset role")

                # The edited row invalidates the open claim at completion time
                # instead of the claim freezing the row.
                assert _complete_welcome(
                    cursor,
                    email=email,
                    claim_token=claim_token,
                ) == (False,)

                cursor.execute("set role service_role")
                cursor.execute(
                    "delete from public.private_alpha_allowlist where email = %s",
                    (email,),
                )
                cursor.execute("reset role")
                cursor.execute(
                    "select count(*) from public.private_alpha_allowlist "
                    "where email = %s",
                    (email,),
                )
                assert cursor.fetchone() == (0,)
    finally:
        _cleanup_access_rows(email)


@pytest.mark.parametrize(
    (
        "role",
        "stored_language",
        "disabled",
        "request_language",
        "expected_allowlist_row",
    ),
    [
        pytest.param(None, "en", False, "en", None, id="missing"),
        pytest.param(
            "requested",
            "en",
            True,
            "en",
            ("requested", "en", True),
            id="disabled",
        ),
        pytest.param("admin", "en", False, "en", ("admin", "en", False), id="admin"),
        pytest.param(
            "developer",
            "en",
            False,
            "en",
            ("developer", "en", False),
            id="developer",
        ),
        pytest.param(
            "requested",
            "es-419",
            False,
            "en",
            ("requested", "es-419", False),
            id="language-mismatch",
        ),
        pytest.param(
            "user",
            "en",
            False,
            "en",
            ("user", "en", False),
            id="active-user-without-delivery",
        ),
    ],
)
def test_completion_rejects_ineligible_allowlist_state_without_delivery(
    role: str | None,
    stored_language: str,
    disabled: bool,
    request_language: str,
    expected_allowlist_row: tuple[str, str, bool] | None,
) -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                if role is not None:
                    _insert_allowlist_row(
                        cursor,
                        email=email,
                        role=role,
                        language=stored_language,
                        disabled=disabled,
                    )

                assert _complete_welcome(
                    cursor,
                    email=email,
                    language=request_language,
                ) == (False,)

                cursor.execute(
                    """
                    select role, language, disabled_at is not null
                    from public.private_alpha_allowlist
                    where email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == expected_allowlist_row
                cursor.execute(
                    """
                    select count(*)
                    from public.private_alpha_access_welcome_deliveries
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (0,)
    finally:
        _cleanup_access_rows(email)


@pytest.mark.parametrize(
    (
        "stored_language",
        "stored_content_version",
        "stored_subject",
        "request_language",
        "request_content_version",
        "request_subject",
    ),
    [
        pytest.param(
            "es-419",
            WELCOME_CONTENT_VERSION,
            WELCOME_SUBJECT,
            "en",
            WELCOME_CONTENT_VERSION,
            WELCOME_SUBJECT,
            id="language",
        ),
        pytest.param(
            "en",
            WELCOME_CONTENT_VERSION,
            WELCOME_SUBJECT,
            "en",
            "private-alpha-access-welcome/v2",
            WELCOME_SUBJECT,
            id="content-version",
        ),
        pytest.param(
            "en",
            WELCOME_CONTENT_VERSION,
            "Existing welcome subject",
            "en",
            WELCOME_CONTENT_VERSION,
            WELCOME_SUBJECT,
            id="subject",
        ),
    ],
)
def test_completion_rejects_conflicting_delivery_without_promotion(
    stored_language: str,
    stored_content_version: str,
    stored_subject: str,
    request_language: str,
    request_content_version: str,
    request_subject: str,
) -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")
                cursor.execute(
                    """
                    insert into public.private_alpha_access_welcome_deliveries (
                      recipient_email,
                      language,
                      content_version,
                      subject,
                      provider_receipt
                    )
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        email,
                        stored_language,
                        stored_content_version,
                        stored_subject,
                        WELCOME_RECEIPT,
                    ),
                )

                assert _complete_welcome(
                    cursor,
                    email=email,
                    language=request_language,
                    content_version=request_content_version,
                    subject=request_subject,
                ) == (False,)

                cursor.execute(
                    """
                    select role, language, disabled_at
                    from public.private_alpha_allowlist
                    where email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == ("requested", "en", None)
                cursor.execute(
                    """
                    select language, content_version, subject, provider_receipt
                    from public.private_alpha_access_welcome_deliveries
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchall() == [
                    (
                        stored_language,
                        stored_content_version,
                        stored_subject,
                        "resend-email-id-461",
                    )
                ]
    finally:
        _cleanup_access_rows(email)


def test_completion_constraint_failure_rolls_back_new_delivery_and_promotion() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")
                claim_token = _claim_token(cursor, email=email)

                with pytest.raises(psycopg.errors.CheckViolation):
                    _complete_welcome(
                        cursor,
                        email=email,
                        provider_receipt="",
                        claim_token=claim_token,
                    )

                cursor.execute(
                    """
                    select role, language, disabled_at
                    from public.private_alpha_allowlist
                    where email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == ("requested", "en", None)
                cursor.execute(
                    """
                    select count(*)
                    from public.private_alpha_access_welcome_deliveries
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (0,)
                cursor.execute(
                    """
                    select count(*)
                    from public.private_alpha_access_welcome_claims
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (1,)
    finally:
        _cleanup_access_rows(email)


def test_completion_records_delivery_and_promotes_atomically() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.private_alpha_allowlist (email, role, language)
                    values (%s, 'requested', 'en')
                    """,
                    (email,),
                )

                claim_token = _claim_token(cursor, email=email)
                assert _complete_welcome(
                    cursor,
                    email=email,
                    claim_token=claim_token,
                ) == (True,)

                cursor.execute(
                    """
                    select role, language, disabled_at
                    from public.private_alpha_allowlist
                    where email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == ("user", "en", None)

                cursor.execute(
                    """
                    select recipient_email, language, content_version, subject,
                           provider_receipt, sent_at is not null, created_at is not null
                    from public.private_alpha_access_welcome_deliveries
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (
                    email,
                    "en",
                    "private-alpha-access-welcome/v1",
                    "Welcome to Argus",
                    "resend-email-id-461",
                    True,
                    True,
                )
                cursor.execute(
                    """
                    select count(*)
                    from public.private_alpha_access_welcome_claims
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (0,)
    finally:
        _cleanup_access_rows(email)


def test_completion_replay_returns_true_with_one_delivery_row() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.private_alpha_allowlist (email, role, language)
                    values (%s, 'requested', 'en')
                    """,
                    (email,),
                )
                claim_token = _claim_token(cursor, email=email)
                results = [
                    _complete_welcome(
                        cursor,
                        email=email,
                        claim_token=claim_token,
                    ),
                    _complete_welcome(
                        cursor,
                        email=email,
                        claim_token=None,
                    ),
                ]

                assert results == [(True,), (True,)]
                cursor.execute(
                    """
                    select a.role, count(d.recipient_email)
                    from public.private_alpha_allowlist as a
                    left join public.private_alpha_access_welcome_deliveries as d
                      on d.recipient_email = a.email
                    where a.email = %s
                    group by a.role
                    """,
                    (email,),
                )
                assert cursor.fetchone() == ("user", 1)
    finally:
        _cleanup_access_rows(email)


def test_anon_cannot_insert_requested_row() -> None:
    email = _random_email()
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set role anon")
            try:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        insert into public.private_alpha_allowlist
                          (email, role, language)
                        values (%s, 'requested', 'en')
                        """,
                        (email,),
                    )
            finally:
                cursor.execute("reset role")


def test_concurrent_service_requests_create_exactly_one_requested_row() -> None:
    email = _random_email()
    worker_count = 4
    barrier = Barrier(worker_count)

    def request_access() -> tuple[str, str] | None:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set role service_role")
                barrier.wait(timeout=10)
                cursor.execute(
                    """
                    insert into public.private_alpha_allowlist (email, role, language)
                    values (%s, 'requested', 'en')
                    on conflict (email) do nothing
                    returning role, language
                    """,
                    (email,),
                )
                return cursor.fetchone()

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(lambda _: request_access(), range(worker_count)))

        assert results.count(("requested", "en")) == 1
        assert results.count(None) == worker_count - 1
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select role, language, disabled_at
                    from public.private_alpha_allowlist
                    where email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchall() == [("requested", "en", None)]
    finally:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.private_alpha_allowlist where email = %s",
                    (email,),
                )


def test_concurrent_claims_reuse_one_durable_send_identity() -> None:
    email = _random_email()
    worker_count = 4
    barrier = Barrier(worker_count)

    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _insert_allowlist_row(cursor, email=email, role="requested")

    def claim_access_welcome() -> tuple[object, ...] | None:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set role service_role")
                barrier.wait(timeout=10)
                cursor.execute(
                    """
                    select claim_token::text, send_allowed
                    from public.claim_private_alpha_access_welcome(
                      %s, 'en', %s, %s
                    )
                    """,
                    (email, WELCOME_CONTENT_VERSION, WELCOME_SUBJECT),
                )
                return cursor.fetchone()

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(lambda _: claim_access_welcome(), range(worker_count))
            )

        assert all(result is not None and result[1] is True for result in results)
        assert len({result[0] for result in results if result is not None}) == 1
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select count(*)
                    from public.private_alpha_access_welcome_claims
                    where recipient_email = %s
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (1,)
    finally:
        _cleanup_access_rows(email)


def test_concurrent_completion_has_one_delivery_and_one_active_row() -> None:
    email = _random_email()
    worker_count = 4
    barrier = Barrier(worker_count)

    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.private_alpha_allowlist (email, role, language)
                values (%s, 'requested', 'es-419')
                """,
                (email,),
            )
            claim_token = _claim_token(
                cursor,
                email=email,
                language="es-419",
                subject="Bienvenido a Argus",
            )

    def complete_access_welcome() -> tuple[bool]:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set role service_role")
                barrier.wait(timeout=10)
                cursor.execute(
                    """
                    select public.complete_private_alpha_access_welcome(
                      %s, 'es-419', %s, 'Bienvenido a Argus', %s, %s
                    )
                    """,
                    (
                        email,
                        WELCOME_CONTENT_VERSION,
                        WELCOME_RECEIPT,
                        claim_token,
                    ),
                )
                return cursor.fetchone()

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(lambda _: complete_access_welcome(), range(worker_count))
            )

        assert results == [(True,)] * worker_count
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select a.role, a.language, a.disabled_at,
                           count(d.recipient_email)
                    from public.private_alpha_allowlist as a
                    left join public.private_alpha_access_welcome_deliveries as d
                      on d.recipient_email = a.email
                    where a.email = %s
                    group by a.role, a.language, a.disabled_at
                    """,
                    (email,),
                )
                assert cursor.fetchall() == [("user", "es-419", None, 1)]
    finally:
        _cleanup_access_rows(email)


def test_browser_roles_cannot_reach_claim_or_delivery_state_machine() -> None:
    email = _random_email()
    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(cursor, email=email, role="requested")
                claim_token = _claim_token(cursor, email=email)
                assert _complete_welcome(
                    cursor,
                    email=email,
                    claim_token=claim_token,
                ) == (True,)

                cursor.execute(
                    """
                    select
                      (
                        select relrowsecurity
                        from pg_class
                        where oid =
                          'public.private_alpha_access_welcome_claims'::regclass
                      ),
                      has_table_privilege(
                        'service_role',
                        'public.private_alpha_access_welcome_claims',
                        'select,insert,update,delete'
                      ),
                      has_function_privilege(
                        'service_role',
                        'public.claim_private_alpha_access_welcome(text,text,text,text)',
                        'execute'
                      ),
                      has_function_privilege(
                        'service_role',
                        'public.complete_private_alpha_access_welcome(text,text,text,text,text,uuid)',
                        'execute'
                      ),
                      has_table_privilege(
                        'service_role',
                        'public.private_alpha_access_welcome_deliveries',
                        'select'
                      ),
                      has_table_privilege(
                        'service_role',
                        'public.private_alpha_access_welcome_deliveries',
                        'insert,update,delete'
                      ),
                      to_regprocedure(
                        'public.complete_private_alpha_access_welcome(text,text,text,text,text)'
                      ) is null,
                      (
                        select count(*)
                        from pg_policies
                        where schemaname = 'public'
                          and tablename in (
                            'private_alpha_access_welcome_claims',
                            'private_alpha_access_welcome_deliveries'
                          )
                      )
                    """
                )
                assert cursor.fetchone() == (
                    True,
                    False,
                    True,
                    True,
                    True,
                    False,
                    True,
                    0,
                )

                for role in ("anon", "authenticated"):
                    cursor.execute(f"set role {role}")
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        cursor.execute(
                            """
                            select claim_token
                            from public.private_alpha_access_welcome_claims
                            where recipient_email = %s
                            """,
                            (email,),
                        )
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        cursor.execute(
                            """
                            select *
                            from public.claim_private_alpha_access_welcome(
                              %s, 'en', %s, %s
                            )
                            """,
                            (
                                email,
                                WELCOME_CONTENT_VERSION,
                                WELCOME_SUBJECT,
                            ),
                        )
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        cursor.execute(
                            """
                            select public.complete_private_alpha_access_welcome(
                              %s, 'en', %s, %s, %s, null
                            )
                            """,
                            (
                                email,
                                WELCOME_CONTENT_VERSION,
                                WELCOME_SUBJECT,
                                WELCOME_RECEIPT,
                            ),
                        )
                    cursor.execute("reset role")

                cursor.execute("set role service_role")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        insert into public.private_alpha_access_welcome_deliveries (
                          recipient_email,
                          language,
                          content_version,
                          subject,
                          provider_receipt
                        )
                        values (%s, 'en', %s, %s, %s)
                        """,
                        (
                            _random_email(),
                            WELCOME_CONTENT_VERSION,
                            WELCOME_SUBJECT,
                            WELCOME_RECEIPT,
                        ),
                    )
                cursor.execute("reset role")
    finally:
        _cleanup_access_rows(email)


@pytest.mark.skipif(
    not (LOCAL_URL and LOCAL_SERVICE_KEY),
    reason="disposable local Supabase gateway is not configured",
)
def test_protected_approval_replay_uses_real_gateway_and_sends_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state
    from argus.api.main import app
    from argus.domain.supabase_gateway import SupabaseGateway
    from fastapi.testclient import TestClient

    from supabase import create_client

    class _RecordingSMTP:
        def __init__(
            self,
            host: str,
            port: int,
            *,
            timeout: float,
            context: ssl.SSLContext,
        ) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.context = context
            self.accepted_messages: list[str] = []

        def __enter__(self) -> "_RecordingSMTP":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            assert username == "resend"
            assert password

        def mail(self, sender: str) -> tuple[int, bytes]:
            assert sender == "no-responder@mail.cuadrao.ai"
            return 250, b"sender accepted"

        def rcpt(self, recipient: str) -> tuple[int, bytes]:
            assert recipient == email
            return 250, b"recipient accepted"

        def data(self, message: str) -> tuple[int, bytes]:
            self.accepted_messages.append(message)
            return 250, b"Queued. isolated-gateway-proof"

    email = _random_email()
    ops_token = fake.uuid4()
    smtp_instances: list[_RecordingSMTP] = []

    def _smtp(
        host: str,
        port: int,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> _RecordingSMTP:
        instance = _RecordingSMTP(
            host,
            port,
            timeout=timeout,
            context=context,
        )
        smtp_instances.append(instance)
        return instance

    try:
        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                _insert_allowlist_row(
                    cursor,
                    email=email,
                    role="requested",
                    language="es-419",
                )

        real_gateway = SupabaseGateway(client=create_client(LOCAL_URL, LOCAL_SERVICE_KEY))
        monkeypatch.setattr(api_state, "supabase_gateway", real_gateway)
        monkeypatch.setenv("ARGUS_OPS_TOKEN", ops_token)
        monkeypatch.setenv("ARGUS_APP_ORIGIN", "https://argus.example")
        monkeypatch.setenv(
            "ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD",
            fake.password(),
        )
        monkeypatch.setattr(
            "argus.domain.resend_email.smtplib.SMTP_SSL",
            _smtp,
        )

        client = TestClient(app)
        headers = {"Authorization": f"Bearer {ops_token}"}
        first = client.post(
            "/internal/access-requests/approve",
            json={"email": email},
            headers=headers,
        )
        second = client.post(
            "/internal/access-requests/approve",
            json={"email": email},
            headers=headers,
        )

        assert first.status_code == second.status_code == 200
        assert first.json() == second.json() == {"approved": True}
        accepted_messages = [
            message
            for instance in smtp_instances
            for message in instance.accepted_messages
        ]
        assert len(accepted_messages) == 1
        accepted_message = message_from_string(accepted_messages[0])
        assert accepted_message.get_content_type() == "multipart/alternative"
        assert accepted_message["To"] == email

        with psycopg.connect(DSN, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select a.role, count(d.recipient_email), min(d.language),
                           min(d.content_version), min(d.subject)
                    from public.private_alpha_allowlist as a
                    left join public.private_alpha_access_welcome_deliveries as d
                      on d.recipient_email = a.email
                    where a.email = %s
                    group by a.role
                    """,
                    (email,),
                )
                assert cursor.fetchone() == (
                    "user",
                    1,
                    "es-419",
                    WELCOME_CONTENT_VERSION,
                    "Bienvenido a Argus",
                )
    finally:
        _cleanup_access_rows(email)

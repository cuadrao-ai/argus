"""Postgres proof for the public RNC registry swap and lookup."""

from __future__ import annotations

import os
import threading
import time
from datetime import date

import pytest
from faker import Faker

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")

fake = Faker()
Faker.seed(18190000)

REGISTRY = "public.dgii_rnc"
LOAD = "public.dgii_rnc_load"
FILE_DATE = date(2026, 10, 18)
DENIED_ROLES = ("anon", "authenticated")
STATUS_ROWS = (
    ("101234567", "ACTIVO", "verificado"),
    ("101234568", "SUSPENDIDO", "no_activo"),
    ("101234569", "DADO DE BAJA", "no_activo"),
    ("101234570", "CESE TEMPORAL", "no_activo"),
    ("101234571", "ANULADO", "no_activo"),
    ("101234572", "RECHAZADO", "no_activo"),
    ("101234573", " activo ", "verificado"),
)


def _name() -> str:
    return fake.company()


def _empty(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("reset role")
        cursor.execute(f"truncate table {REGISTRY}, {LOAD}")


@pytest.fixture()
def connection():
    with psycopg.connect(DSN, autocommit=True) as conn:
        _empty(conn)
        yield conn
        _empty(conn)


def _insert(
    connection,
    table: str,
    rnc: str,
    name: str,
    trade_name: str | None,
    status: str,
    file_date: date,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into {table} (rnc, name, trade_name, status, file_date) "
            "values (%s, %s, %s, %s, %s)",
            (rnc, name, trade_name, status, file_date),
        )


def _contents(connection, table: str) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select rnc, name, trade_name, status, file_date "
            f"from {table} order by rnc, name"
        )
        return cursor.fetchall()


def test_check_accepts_nine_and_eleven_digit_ids_and_rejects_bad_values(connection):
    accepted = ("101234567", "00123456789")
    rejected_ids = ("1234567890", "12345678A", "1-01-23456-7")
    rejected_names = ("", "   ")
    rejected_trade_names = ("", "   ")
    for table in (REGISTRY, LOAD):
        _insert(connection, table, accepted[0], _name(), _name(), "ACTIVO", FILE_DATE)
        _insert(connection, table, accepted[1], _name(), None, "ACTIVO", FILE_DATE)
        with connection.cursor() as cursor:
            for rnc in rejected_ids:
                with pytest.raises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        f"insert into {table} (rnc, name, status, file_date) "
                        "values (%s, %s, 'ACTIVO', %s)",
                        (rnc, _name(), FILE_DATE),
                    )
            for name in rejected_names:
                with pytest.raises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        f"insert into {table} (rnc, name, trade_name, status, file_date) "
                        "values ('309876543', %s, null, 'ACTIVO', %s)",
                        (name, FILE_DATE),
                    )
            for trade_name in rejected_trade_names:
                with pytest.raises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        f"insert into {table} (rnc, name, trade_name, status, file_date) "
                        "values ('409876543', %s, %s, 'ACTIVO', %s)",
                        (_name(), trade_name, FILE_DATE),
                    )
        stored = {row[0]: row[2] for row in _contents(connection, table)}
        assert set(stored) == set(accepted)
        assert stored[accepted[0]]
        assert stored[accepted[1]] is None


def test_swap_with_too_few_rows_leaves_the_registry_intact(connection):
    original_name = _name()
    staged_name = _name()
    _insert(
        connection,
        REGISTRY,
        "101234567",
        original_name,
        None,
        "ACTIVO",
        date(2026, 1, 1),
    )
    _insert(
        connection, LOAD, "00123456789", staged_name, _name(), "SUSPENDIDO", FILE_DATE
    )
    before_registry = _contents(connection, REGISTRY)
    before_load = _contents(connection, LOAD)

    with connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RaiseException) as caught:
            cursor.execute("select public.dgii_rnc_swap(%s)", (2,))
    assert caught.value.diag.message_primary == (
        "dgii_rnc_load has 1 rows, fewer than the minimum 2"
    )
    assert _contents(connection, REGISTRY) == before_registry
    assert _contents(connection, LOAD) == before_load

    with connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RaiseException) as caught:
            cursor.execute("select public.dgii_rnc_swap(%s)", (0,))
    assert caught.value.diag.message_primary == "min_rows must be at least 1"
    assert _contents(connection, REGISTRY) == before_registry
    assert _contents(connection, LOAD) == before_load


def test_swap_with_duplicate_rnc_values_leaves_the_registry_intact(connection):
    original_name = _name()
    _insert(
        connection,
        REGISTRY,
        "101234567",
        original_name,
        None,
        "ACTIVO",
        date(2026, 1, 1),
    )
    _insert(connection, LOAD, "00123456789", _name(), _name(), "ACTIVO", FILE_DATE)
    _insert(connection, LOAD, "00123456789", _name(), None, "RECHAZADO", FILE_DATE)
    before_registry = _contents(connection, REGISTRY)
    before_load = _contents(connection, LOAD)

    with connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RaiseException) as caught:
            cursor.execute("select public.dgii_rnc_swap(%s)", (1,))
    assert caught.value.diag.message_primary == "dgii_rnc_load duplicate rnc count 1"
    assert _contents(connection, REGISTRY) == before_registry
    assert _contents(connection, LOAD) == before_load


def test_swap_replaces_the_registry_and_empties_the_load_table(connection):
    _insert(
        connection, REGISTRY, "101234567", _name(), _name(), "ANULADO", date(2026, 1, 1)
    )
    replacement = (
        ("00123456789", _name(), _name(), "ACTIVO", FILE_DATE),
        ("101234568", _name(), None, "SUSPENDIDO", FILE_DATE),
    )
    for row in replacement:
        _insert(connection, LOAD, *row)

    with connection.cursor() as cursor:
        cursor.execute("set role service_role")
        cursor.execute("select public.dgii_rnc_swap(%s)", (2,))
        assert cursor.fetchone() == (2,)
        cursor.execute("reset role")

    assert _contents(connection, REGISTRY) == list(replacement)
    assert _contents(connection, LOAD) == []

    for row in replacement:
        _insert(connection, LOAD, *row)
    with connection.cursor() as cursor:
        cursor.execute("select public.dgii_rnc_swap(%s)", (2,))
        assert cursor.fetchone() == (2,)
    assert _contents(connection, REGISTRY) == list(replacement)
    assert _contents(connection, LOAD) == []


def test_lookup_normalizes_digits_and_maps_status(connection):
    names = {rnc: _name() for rnc, _status, _verification in STATUS_ROWS}
    trade_names = {
        rnc: None if index % 2 else _name()
        for index, (rnc, _status, _verification) in enumerate(STATUS_ROWS)
    }
    for rnc, status, _verification in STATUS_ROWS:
        _insert(
            connection,
            REGISTRY,
            rnc,
            names[rnc],
            trade_names[rnc],
            status,
            FILE_DATE,
        )

    with connection.cursor() as cursor:
        cursor.execute("select * from public.dgii_rnc_lookup(%s)", ("1-01-23456-7",))
        assert cursor.fetchone() == (
            "101234567",
            names["101234567"],
            trade_names["101234567"],
            "ACTIVO",
            FILE_DATE,
            "verificado",
        )
        for rnc, status, verification in STATUS_ROWS:
            cursor.execute("select * from public.dgii_rnc_lookup(%s)", (rnc,))
            assert cursor.fetchone() == (
                rnc,
                names[rnc],
                trade_names[rnc],
                status,
                FILE_DATE,
                verification,
            )


def test_lookup_of_an_unknown_or_empty_rnc_returns_no_row(connection):
    _insert(connection, REGISTRY, "101234567", _name(), None, "ACTIVO", FILE_DATE)
    with connection.cursor() as cursor:
        for value in ("999999999", None, "", "---"):
            cursor.execute("select * from public.dgii_rnc_lookup(%s)", (value,))
            assert cursor.fetchall() == []


def test_anon_and_authenticated_cannot_select_or_execute(connection):
    _insert(connection, REGISTRY, "101234567", _name(), None, "ACTIVO", FILE_DATE)
    _insert(connection, LOAD, "00123456789", _name(), None, "ACTIVO", FILE_DATE)
    statements = (
        f"select * from {REGISTRY}",
        f"select * from {LOAD}",
        "select * from public.dgii_rnc_lookup('101234567')",
        "select public.dgii_rnc_swap(1)",
    )
    for role in DENIED_ROLES:
        with connection.cursor() as cursor:
            cursor.execute(f"set role {role}")
            try:
                for statement in statements:
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        cursor.execute(statement)
            finally:
                cursor.execute("reset role")


def test_service_role_can_select_and_execute(connection):
    staged_name = _name()
    staged_trade_name = _name()
    with connection.cursor() as cursor:
        cursor.execute("set role service_role")
        try:
            cursor.execute(
                f"insert into {LOAD} (rnc, name, trade_name, status, file_date) "
                "values (%s, %s, %s, %s, %s)",
                ("101234567", staged_name, staged_trade_name, "ACTIVO", FILE_DATE),
            )
            cursor.execute(f"select rnc, name, trade_name, status, file_date from {LOAD}")
            assert cursor.fetchall() == [
                ("101234567", staged_name, staged_trade_name, "ACTIVO", FILE_DATE)
            ]
            cursor.execute("select public.dgii_rnc_swap(%s)", (1,))
            assert cursor.fetchone() == (1,)
            cursor.execute(
                f"select rnc, name, trade_name, status, file_date from {REGISTRY}"
            )
            assert cursor.fetchall() == [
                ("101234567", staged_name, staged_trade_name, "ACTIVO", FILE_DATE)
            ]
            cursor.execute(f"select rnc from {LOAD}")
            assert cursor.fetchall() == []
            cursor.execute("select * from public.dgii_rnc_lookup(%s)", ("1-01-23456-7",))
            assert cursor.fetchone() == (
                "101234567",
                staged_name,
                staged_trade_name,
                "ACTIVO",
                FILE_DATE,
                "verificado",
            )
        finally:
            cursor.execute("reset role")


def _await_lock(application_name: str) -> None:
    deadline = time.monotonic() + 5
    with psycopg.connect(DSN, autocommit=True) as watcher:
        while time.monotonic() < deadline:
            with watcher.cursor() as cursor:
                cursor.execute(
                    """
                    select exists (
                        select 1
                        from pg_stat_activity
                        where application_name = %s
                          and wait_event_type = 'Lock'
                    )
                    """,
                    (application_name,),
                )
                if cursor.fetchone()[0]:
                    return
            time.sleep(0.02)
    raise AssertionError(f"{application_name} did not wait on a lock")


def _run_query(
    application_name: str, sql: str, args: tuple, outcome: dict, key: str
) -> None:
    try:
        with psycopg.connect(
            DSN, autocommit=True, application_name=application_name
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("set statement_timeout = '15s'")
                cursor.execute(sql, args)
                outcome[key] = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001 - the caller asserts the thread error
        outcome["errors"].append(exc)


def test_swap_blocks_a_concurrent_load_delete_and_publishes_the_loaded_rows(connection):
    loaded = (
        ("00123456789", _name(), _name(), "ACTIVO", FILE_DATE),
        ("101234568", _name(), None, "SUSPENDIDO", FILE_DATE),
    )
    _insert(connection, REGISTRY, "101234567", _name(), None, "ANULADO", date(2026, 1, 1))
    for row in loaded:
        _insert(connection, LOAD, *row)
    outcome = {"errors": []}
    holder = psycopg.connect(DSN, autocommit=False)
    worker = threading.Thread(
        target=_run_query,
        args=(
            "dgii_swap",
            "select public.dgii_rnc_swap(%s)",
            (len(loaded),),
            outcome,
            "swap",
        ),
    )
    try:
        with holder.cursor() as cursor:
            cursor.execute(f"lock table {REGISTRY} in access exclusive mode")
        worker.start()
        _await_lock("dgii_swap")
        with psycopg.connect(DSN, autocommit=True) as deleter:
            with deleter.cursor() as cursor:
                cursor.execute("set lock_timeout = '750ms'")
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    cursor.execute(f"delete from {LOAD}")
        holder.commit()
    finally:
        holder.rollback()
        holder.close()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert outcome["errors"] == []
    assert outcome["swap"] == [(len(loaded),)]
    assert _contents(connection, REGISTRY) == list(loaded)
    assert _contents(connection, LOAD) == []


def test_swap_rejects_null_and_zero_minimum_and_leaves_the_registry_intact(connection):
    _insert(connection, REGISTRY, "101234567", _name(), None, "ACTIVO", date(2026, 1, 1))
    before_registry = _contents(connection, REGISTRY)
    for minimum in (None, 0):
        with connection.cursor() as cursor:
            with pytest.raises(psycopg.errors.RaiseException) as caught:
                cursor.execute("select public.dgii_rnc_swap(%s)", (minimum,))
        assert caught.value.diag.message_primary == "min_rows must be at least 1"
        assert _contents(connection, REGISTRY) == before_registry
        assert _contents(connection, LOAD) == []


def test_lookup_waiting_on_a_swap_returns_the_published_row(connection):
    published = ("101234567", _name(), _name(), "ACTIVO", FILE_DATE)
    _insert(connection, REGISTRY, *published)
    _insert(connection, LOAD, *published)
    outcome = {"errors": []}
    holder = psycopg.connect(DSN, autocommit=False)
    swap_thread = threading.Thread(
        target=_run_query,
        args=("dgii_swap", "select public.dgii_rnc_swap(%s)", (1,), outcome, "swap"),
    )
    lookup_thread = threading.Thread(
        target=_run_query,
        args=(
            "dgii_lookup",
            "select * from public.dgii_rnc_lookup(%s)",
            ("1-01-23456-7",),
            outcome,
            "lookup",
        ),
    )
    try:
        with holder.cursor() as cursor:
            cursor.execute(f"lock table {REGISTRY} in access exclusive mode")
        swap_thread.start()
        _await_lock("dgii_swap")
        lookup_thread.start()
        _await_lock("dgii_lookup")
        holder.commit()
    finally:
        holder.rollback()
        holder.close()
        swap_thread.join(timeout=10)
        lookup_thread.join(timeout=10)

    assert not swap_thread.is_alive()
    assert not lookup_thread.is_alive()
    assert outcome["errors"] == []
    assert outcome["swap"] == [(1,)]
    assert outcome["lookup"] == [
        (
            published[0],
            published[1],
            published[2],
            published[3],
            published[4],
            "verificado",
        )
    ]

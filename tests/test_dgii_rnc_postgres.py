"""Postgres proof for the public RNC registry swap and lookup."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import replace
from datetime import date

import pytest
from faker import Faker

from scripts.ops.dgii_rnc_import import LOAD as IMPORT_CONFIG
from scripts.ops.dgii_rnc_import import (
    RncImportError,
    _apply_load,
    _copy_header,
    _psql_copy,
    main,
    parse_zip,
    validate,
)
from tests.dgii_rnc_zip import csv_file, csv_record, registry_zip, txt_record, txt_zip

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
START_DATE = date(2019, 3, 7)
COLUMNS = "rnc, name, trade_name, status, file_date, activity, start_date, regime"
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
    activity: str | None = None,
    start_date: date | None = None,
    regime: str | None = None,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into {table} ({COLUMNS}) values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (rnc, name, trade_name, status, file_date, activity, start_date, regime),
        )


def _contents(connection, table: str) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(f"select {COLUMNS} from {table} order by rnc, name")
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


@pytest.mark.parametrize("column", ["activity", "regime"])
def test_check_rejects_a_blank_activity_or_regime(connection, column):
    for table in (REGISTRY, LOAD):
        with connection.cursor() as cursor:
            for value in ("", "   "):
                with pytest.raises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        f"insert into {table} (rnc, name, status, file_date, {column}) "
                        "values ('101234567', %s, 'ACTIVO', %s, %s)",
                        (_name(), FILE_DATE, value),
                    )


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
        ("00123456789", _name(), _name(), "ACTIVO", FILE_DATE, fake.bs(), START_DATE, "RST"),
        ("101234568", _name(), None, "SUSPENDIDO", FILE_DATE, None, None, None),
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
            None,
            None,
            None,
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
                None,
                None,
                None,
            )


def test_lookup_returns_activity_start_date_and_regime(connection):
    activity = fake.bs()
    _insert(
        connection,
        REGISTRY,
        "101234567",
        _name(),
        None,
        "SUSPENDIDO",
        FILE_DATE,
        activity,
        START_DATE,
        "RST",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "select status, verification, activity, start_date, regime "
            "from public.dgii_rnc_lookup(%s)",
            ("101234567",),
        )
        assert cursor.fetchone() == (
            "SUSPENDIDO",
            "no_activo",
            activity,
            START_DATE,
            "RST",
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
                None,
                None,
                None,
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
        ("00123456789", _name(), _name(), "ACTIVO", FILE_DATE, fake.bs(), START_DATE, "RST"),
        ("101234568", _name(), None, "SUSPENDIDO", FILE_DATE, None, None, None),
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
    published = (
        "101234567",
        _name(),
        _name(),
        "ACTIVO",
        FILE_DATE,
        fake.bs(),
        START_DATE,
        "NORMAL",
    )
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
    assert outcome["lookup"] == [(*published[:5], "verificado", *published[5:])]


def test_the_importer_loads_a_zip_through_copy_and_swap(connection):
    active, suspended, short = "901234567", "90123456789", "90123456"
    active_name = _name()
    suspended_name = _name()
    trade_name = _name()
    activity = fake.bs()
    payload = registry_zip(
        csv_file(
            csv_record(
                active,
                active_name,
                activity=activity,
                started="07/03/2019",
                regime="NORMAL",
            ),
            csv_record(
                suspended, suspended_name, "SUSPENDIDO", started="31/02/2020", regime="RST"
            ),
            csv_record(short, _name()),
        ),
    )
    names = txt_zip(txt_record(active, trade_name), txt_record(short, _name()))
    config = replace(IMPORT_CONFIG, min_rows=2, size_limit_bytes=1 << 40)
    result = parse_zip(payload, config, trade_name_zip=names, keep_rows=False)
    try:
        validate(result, config)
        _apply_load(DSN, result, config)
    finally:
        os.unlink(result.spill_path)

    assert _contents(connection, LOAD) == []
    assert _contents(connection, REGISTRY) == [
        (active, active_name, trade_name, "ACTIVO", FILE_DATE, activity, START_DATE, "NORMAL"),
        (suspended, suspended_name, None, "SUSPENDIDO", FILE_DATE, None, None, "RST"),
    ]
    with connection.cursor() as cursor:
        cursor.execute("select verification from public.dgii_rnc_lookup(%s)", (suspended,))
        assert cursor.fetchone() == ("no_activo",)
        cursor.execute("select verification from public.dgii_rnc_lookup(%s)", (active,))
        assert cursor.fetchone() == ("verificado",)


TABLE_FACTS = (
    "select relowner::regrole::text, relrowsecurity, relforcerowsecurity, relreplident,"
    " reloptions from pg_class where oid = %(table)s::regclass",
    "select item.grantee::regrole::text, item.grantor::regrole::text, item.privilege_type"
    " from pg_class, aclexplode(relacl) as item where oid = %(table)s::regclass"
    " order by 1, 2, 3",
    "select conname, contype, pg_get_constraintdef(oid) from pg_constraint"
    " where conrelid = %(table)s::regclass order by 1",
    "select indexrelid::regclass::text, pg_get_indexdef(indexrelid) from pg_index"
    " where indrelid = %(table)s::regclass order by 1",
    "select attnum, attname, atttypid::regtype::text, attnotnull, atthasdef from pg_attribute"
    " where attrelid = %(table)s::regclass and attnum > 0 and not attisdropped order by 1",
    "select polname from pg_policy where polrelid = %(table)s::regclass order by 1",
    "select tgname from pg_trigger"
    " where tgrelid = %(table)s::regclass and not tgisinternal order by 1",
)
FUNCTION_FACTS = (
    "select proname, proowner::regrole::text, prosecdef, provolatile, proconfig, proacl::text[]"
    " from pg_proc where oid in ('public.dgii_rnc_swap(int)'::regprocedure,"
    " 'public.dgii_rnc_lookup(text)'::regprocedure) order by 1"
)
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
SERVICE_ROLE_PRIVILEGES = {
    REGISTRY: {"SELECT"},
    LOAD: {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"},
}


def _catalog(connection) -> list[list[tuple]]:
    with connection.cursor() as cursor:
        facts = []
        for table in (REGISTRY, LOAD):
            for statement in TABLE_FACTS:
                cursor.execute(statement, {"table": table})
                facts.append(cursor.fetchall())
        cursor.execute(FUNCTION_FACTS)
        facts.append(cursor.fetchall())
        return facts


def _fill_both(connection) -> None:
    _insert(connection, REGISTRY, "101234567", _name(), _name(), "ACTIVO", date(2026, 1, 1))
    _insert(connection, LOAD, "101234568", _name(), None, "ACTIVO", FILE_DATE)


def _swap(connection, min_rows: int = 1) -> None:
    with connection.cursor() as cursor:
        cursor.execute("select public.dgii_rnc_swap(%s)", (min_rows,))


def _privileges(connection, role: str, table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select privilege from unnest(%s::text[]) as privilege"
            " where has_table_privilege(%s, %s, privilege)",
            (list(TABLE_PRIVILEGES), role, table),
        )
        return {row[0] for row in cursor.fetchall()}


def test_the_swap_leaves_the_catalog_as_it_found_it(connection):
    before = _catalog(connection)
    for _ in range(2):
        _fill_both(connection)
        _swap(connection)
        assert _catalog(connection) == before
        with connection.cursor() as cursor:
            cursor.execute(f"truncate table {REGISTRY}")


def test_each_table_keeps_its_own_privileges_and_row_security_after_a_swap(connection):
    _fill_both(connection)
    _swap(connection)
    for table, granted in SERVICE_ROLE_PRIVILEGES.items():
        assert _privileges(connection, "service_role", table) == granted
        for role in DENIED_ROLES:
            assert _privileges(connection, role, table) == set()
        with connection.cursor() as cursor:
            cursor.execute(
                "select relrowsecurity, relforcerowsecurity,"
                " (select count(*) from pg_policy where polrelid = pg_class.oid)"
                " from pg_class where oid = %s::regclass",
                (table,),
            )
            assert cursor.fetchone() == (True, False, 0)
    with connection.cursor() as cursor:
        cursor.execute("set role service_role")
        try:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(f"delete from {REGISTRY}")
            cursor.execute(f"delete from {LOAD}")
        finally:
            cursor.execute("reset role")


def test_the_swap_publishes_the_load_table_itself_and_frees_the_old_one(connection):
    _fill_both(connection)
    with connection.cursor() as cursor:
        cursor.execute("select pg_relation_filenode(%s)", (LOAD,))
        load_file = cursor.fetchone()[0]
    _swap(connection)
    with connection.cursor() as cursor:
        cursor.execute("select pg_relation_filenode(%s)", (REGISTRY,))
        assert cursor.fetchone()[0] == load_file
        cursor.execute("select pg_relation_size(%s)", (LOAD,))
        assert cursor.fetchone()[0] == 0


def test_a_failure_after_the_renames_keeps_the_previous_rows_and_catalog(connection):
    _fill_both(connection)
    registry = _contents(connection, REGISTRY)
    loaded = _contents(connection, LOAD)
    with connection.cursor() as cursor:
        cursor.execute(
            "create function public.dgii_rnc_test_refuse() returns trigger language plpgsql"
            " as $$ begin raise exception 'refused by the test'; end; $$"
        )
        cursor.execute(
            f"create trigger refuse_truncate before truncate on {REGISTRY}"
            " for each statement execute function public.dgii_rnc_test_refuse()"
        )
    try:
        before = _catalog(connection)
        with pytest.raises(psycopg.errors.RaiseException) as caught:
            _swap(connection)
        assert caught.value.diag.message_primary == "refused by the test"
        assert _catalog(connection) == before
        assert _contents(connection, REGISTRY) == registry
        assert _contents(connection, LOAD) == loaded
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"drop trigger refuse_truncate on {REGISTRY}")
            cursor.execute("drop function public.dgii_rnc_test_refuse()")


def _load_cli(tmp_path, monkeypatch, csv_payload: bytes, txt_payload: bytes | None) -> int:
    monkeypatch.setattr(
        "scripts.ops.dgii_rnc_import.LOAD",
        replace(IMPORT_CONFIG, min_rows=1, size_limit_bytes=1 << 40),
    )
    monkeypatch.setenv("SUPABASE_STAGING_DB_URL", DSN)
    csv_path = tmp_path / "rnc-csv.zip"
    txt_path = tmp_path / "rnc-txt.zip"
    csv_path.write_bytes(csv_payload)
    if txt_payload is not None:
        txt_path.write_bytes(txt_payload)
    return main(["load", str(csv_path), str(txt_path)])


@pytest.mark.parametrize(
    "txt_payload",
    [None, b"not a zip", txt_zip("sin separadores"), txt_zip()],
    ids=["missing", "not_a_zip", "no_pipes", "no_records"],
)
def test_a_failed_txt_keeps_the_trade_names_that_exist(
    connection, tmp_path, monkeypatch, capsys, txt_payload
):
    kept_rnc, new_rnc, gone_rnc = "901234567", "901234568", "901234569"
    kept_name = _name()
    _insert(connection, REGISTRY, kept_rnc, _name(), kept_name, "ACTIVO", date(2026, 1, 1))
    _insert(connection, REGISTRY, gone_rnc, _name(), _name(), "ACTIVO", date(2026, 1, 1))
    payload = registry_zip(csv_file(csv_record(kept_rnc, _name()), csv_record(new_rnc, _name())))

    assert _load_cli(tmp_path, monkeypatch, payload, txt_payload) == 0

    stored = {row[0]: row[2] for row in _contents(connection, REGISTRY)}
    assert stored == {kept_rnc: kept_name, new_rnc: None}
    output = capsys.readouterr().out
    assert ": previous names stay\n" in output
    assert "trade_name_filled=1\n" in output


def test_a_good_txt_replaces_the_trade_names(connection, tmp_path, monkeypatch, capsys):
    rnc = "901234567"
    fresh = _name()
    _insert(connection, REGISTRY, rnc, _name(), _name(), "ACTIVO", date(2026, 1, 1))
    payload = registry_zip(csv_file(csv_record(rnc, _name())))

    assert _load_cli(tmp_path, monkeypatch, payload, txt_zip(txt_record(rnc, fresh))) == 0

    assert _contents(connection, REGISTRY)[0][2] == fresh
    assert "trade_names=loaded\n" in capsys.readouterr().out


@pytest.mark.parametrize(
    "bad_row",
    [
        "901234567\t \t\\N\tACTIVO\t2026-10-18\t\\N\t\\N\t\\N\n",
        "901234567\t{name}\x00\t\\N\tACTIVO\t2026-10-18\t\\N\t\\N\t\\N\n",
        "901234567\t{name}\t\\N\tACTIVO\tnot a date\t\\N\t\\N\t\\N\n",
    ],
    ids=["check_violation", "nul_byte", "bad_value"],
)
def test_a_failed_copy_names_the_error_and_no_row(connection, tmp_path, bad_row):
    name = _name()
    spill = tmp_path / "copy.tsv"
    spill.write_bytes(bad_row.format(name=name).encode("utf-8"))

    with pytest.raises(RncImportError) as caught:
        _psql_copy(DSN, _copy_header(IMPORT_CONFIG), str(spill))

    message = str(caught.value)
    assert "ERROR:" in message
    assert "901234567" not in message
    assert name not in message
    assert "\n" not in message
    assert _contents(connection, LOAD) == []

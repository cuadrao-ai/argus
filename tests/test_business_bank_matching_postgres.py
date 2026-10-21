"""Business bank matching tables on real Postgres.

Proves the identity key, immutable raw lines, one confirmed suggestion per
line, one account per space, and grant-scoped reads. Skips without a
disposable database.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import account, space

psycopg = pytest.importorskip("psycopg")
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def db(users):  # noqa: ANN001
    with psycopg.connect(shared.DSN) as connection:
        with connection.transaction(force_rollback=True):
            yield connection


def _as(cursor, user_id: str) -> None:  # noqa: ANN001
    cursor.execute("set local role authenticated")
    cursor.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": user_id, "role": "authenticated", "is_anonymous": False}),),
    )


def _grant(db, space_id: str, person: str, capabilities: list[str]) -> None:  # noqa: ANN001
    db.execute(
        "insert into public.business_client_grants"
        " (space_id, grantee_id, issuer_id, capabilities)"
        " values (%s, %s, %s, %s)",
        (space_id, person, person, capabilities),
    )


def _binding(db, space_id: str, account_id: str) -> str:  # noqa: ANN001
    return str(
        db.execute(
            "insert into public.business_bank_accounts (space_id, account_id, currency)"
            " values (%s, %s, 'DOP') returning id",
            (space_id, account_id),
        ).fetchone()[0]
    )


def _import(db, space_id: str, binding: str, person: str) -> str:  # noqa: ANN001
    return str(
        db.execute(
            "insert into public.business_bank_imports ("
            " space_id, bank_account_id, reader_id, source_sha256, idempotency_key,"
            " inserted_count, unchanged_count, imported_by)"
            " values (%s, %s, 'banco_popular', %s, 'k1', 1, 0, %s) returning id",
            (space_id, binding, "a" * 64, person),
        ).fetchone()[0]
    )


def _line(db, space_id: str, binding: str, import_id: str, digest: str) -> str:  # noqa: ANN001
    return str(
        db.execute(
            "insert into public.business_bank_lines ("
            " space_id, bank_account_id, first_import_id, occurred_on, description,"
            " normalized_description, amount, currency, raw_line, line_hash)"
            " values (%s, %s, %s, '2026-10-01', 'Synthetic', 'synthetic', -10, 'DOP',"
            " '{\"synthetic\": true}'::jsonb, %s) returning id",
            (space_id, binding, import_id, digest),
        ).fetchone()[0]
    )


def test_lines_are_immutable_and_identity_is_unique(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    space_id = space(db, owner)
    account_id = account(db, owner, space_id)
    binding = _binding(db, space_id, account_id)
    import_id = _import(db, space_id, binding, owner)
    _line(db, space_id, binding, import_id, "b" * 64)
    with (
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="immutable"),
        db.transaction(),
    ):
        db.execute("update public.business_bank_lines set description = 'changed'")
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _line(db, space_id, binding, import_id, "b" * 64)


def test_one_account_per_space(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    space_id = space(db, owner)
    first = account(db, owner, space_id)
    second = account(db, owner, space_id)
    _binding(db, space_id, first)
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _binding(db, space_id, second)


def _outcome(db, space_id: str, line_id: str, key: str, target: str | None = None) -> str:  # noqa: ANN001
    if target is None:
        sql = (
            "insert into public.business_bank_line_outcomes"
            " (space_id, line_id, kind, reason, create_key)"
            " values (%s, %s, 'no_receipt', 'cargo_banco', %s) returning id"
        )
        params: tuple = (space_id, line_id, key)
    else:
        sql = (
            "insert into public.business_bank_line_outcomes"
            " (space_id, line_id, kind, target_kind, target_id, prior_status,"
            " applied_status, applied_settled_on, applied_payment_method, create_key)"
            " values (%s, %s, 'match', 'receipt', %s, 'pendiente', 'pagado',"
            " '2026-10-01', 'transferencia', %s) returning id"
        )
        params = (space_id, line_id, target, key)
    return str(db.execute(sql, params).fetchone()[0])


def test_one_live_outcome_per_line_and_one_live_line_per_document(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    space_id = space(db, owner)
    binding = _binding(db, space_id, account(db, owner, space_id))
    import_id = _import(db, space_id, binding, owner)
    first = _line(db, space_id, binding, import_id, "d" * 64)
    second = _line(db, space_id, binding, import_id, "c" * 64)
    document = str(uuid4())

    live = _outcome(db, space_id, first, "k1", document)
    with (
        pytest.raises(psycopg.errors.UniqueViolation, match="live_line"),
        db.transaction(),
    ):
        _outcome(db, space_id, first, "k2")
    with (
        pytest.raises(psycopg.errors.UniqueViolation, match="live_document"),
        db.transaction(),
    ):
        _outcome(db, space_id, second, "k3", document)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "insert into public.business_bank_line_outcomes"
            " (space_id, line_id, kind, target_kind, target_id, reason, create_key)"
            " values (%s, %s, 'match', 'receipt', %s, 'personal', 'k4')",
            (space_id, second, document),
        )

    db.execute(
        "update public.business_bank_line_outcomes"
        " set ended_at = now(), end_key = 'undo' where id = %s",
        (live,),
    )
    _outcome(db, space_id, second, "k5", document)
    for change in (
        "set reason = 'personal'",
        "set ended_at = now(), end_key = 'again'",
        "set target_id = gen_random_uuid()",
    ):
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="immutable"),
            db.transaction(),
        ):
            db.execute(
                f"update public.business_bank_line_outcomes {change} where id = %s",
                (live,),
            )
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="immutable"),
        db.transaction(),
    ):
        db.execute(
            "delete from public.business_bank_line_outcomes where id = %s", (live,)
        )
    assert db.execute(
        "select count(*), count(*) filter (where ended_at is null)"
        " from public.business_bank_line_outcomes where target_id = %s",
        (document,),
    ).fetchone() == (2, 1)


BANK_TABLES = (
    "business_bank_accounts",
    "business_bank_imports",
    "business_bank_lines",
    "business_bank_suggestions",
    "business_bank_line_outcomes",
)


@pytest.mark.parametrize("table", BANK_TABLES)
def test_the_server_role_keeps_bank_rows_and_cannot_delete_or_truncate(db, table) -> None:  # noqa: ANN001
    granted = {
        privilege
        for privilege in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        )
        if db.execute(
            "select has_table_privilege('service_role', %s, %s)",
            (f"public.{table}", privilege),
        ).fetchone()[0]
    }
    assert granted == {"SELECT", "INSERT", "UPDATE"}
    for statement in (f"delete from public.{table}", f"truncate public.{table}"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute("set local role service_role")
            db.execute(statement)


def test_a_matched_settlement_changes_only_through_its_match(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    space_id = space(db, owner)
    binding = _binding(db, space_id, account(db, owner, space_id))
    line_id = _line(
        db, space_id, binding, _import(db, space_id, binding, owner), "a" * 64
    )
    activity = str(uuid4())
    db.execute(
        "insert into public.financial_activity_groups (id, user_id, kind, current_revision)"
        " values (%s, %s, 'expense', 1)",
        (activity, owner),
    )

    def settle(status: str, day: str | None, method: str | None) -> None:
        db.execute(
            "insert into public.business_document_settlements"
            " (space_id, owner_id, activity_id, document_kind, status, settled_on, payment_method)"
            " values (%s, %s, %s, 'receipt', %s, %s, %s)"
            " on conflict (space_id, activity_id) do update set status = excluded.status,"
            " settled_on = excluded.settled_on, payment_method = excluded.payment_method",
            (space_id, owner, activity, status, day, method),
        )

    settle("pendiente", None, None)
    live = _outcome(db, space_id, line_id, "k1", activity)
    with pytest.raises(psycopg.errors.CheckViolation, match="business_document_matched"):
        with db.transaction():
            settle("pagado", "2026-10-02", "efectivo")
    settle("pagado", "2026-10-01", "transferencia")
    with pytest.raises(psycopg.errors.CheckViolation, match="business_document_matched"):
        with db.transaction():
            settle("pendiente", None, None)
    db.execute(
        "update public.business_bank_line_outcomes set ended_at = now(), end_key = 'u'"
        " where id = %s",
        (live,),
    )
    settle("pendiente", None, None)


def test_deleting_the_person_keeps_the_outcome_history(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    person = users["other"]
    space_id = space(db, owner)
    binding = _binding(db, space_id, account(db, owner, space_id))
    line_id = _line(
        db, space_id, binding, _import(db, space_id, binding, owner), "b" * 64
    )
    outcome = str(
        db.execute(
            "insert into public.business_bank_line_outcomes"
            " (space_id, line_id, kind, reason, created_by, create_key)"
            " values (%s, %s, 'no_receipt', 'cargo_banco', %s, 'k1') returning id",
            (space_id, line_id, person),
        ).fetchone()[0]
    )
    db.execute(
        "update public.business_bank_line_outcomes"
        " set ended_at = now(), ended_by = %s, end_key = 'u' where id = %s",
        (person, outcome),
    )
    db.execute("delete from auth.users where id = %s", (person,))
    assert db.execute(
        "select created_by, ended_by, end_key, reason"
        " from public.business_bank_line_outcomes where id = %s",
        (outcome,),
    ).fetchone() == (None, None, "u", "cargo_banco")


def test_deleting_the_importer_keeps_the_upload(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    importer = users["other"]
    space_id = space(db, owner)
    account_id = account(db, owner, space_id)
    binding = _binding(db, space_id, account_id)
    import_id = _import(db, space_id, binding, importer)
    line_id = _line(db, space_id, binding, import_id, "f" * 64)

    db.execute("delete from auth.users where id = %s", (importer,))

    kept = db.execute(
        "select imported_by::text, inserted_count, idempotency_key"
        " from public.business_bank_imports where id = %s::uuid",
        (import_id,),
    ).fetchone()
    assert kept == (None, 1, "k1")
    assert db.execute(
        "select count(*) from auth.users where id = %s", (importer,)
    ).fetchone() == (0,)
    assert db.execute(
        "select count(*) from auth.users where id = %s", (owner,)
    ).fetchone() == (1,)
    assert db.execute(
        "select count(*) from public.spaces where id = %s::uuid", (space_id,)
    ).fetchone() == (1,)
    assert db.execute(
        "select count(*) from public.financial_accounts where id = %s::uuid",
        (account_id,),
    ).fetchone() == (1,)
    assert db.execute(
        "select count(*) from public.business_bank_accounts where id = %s::uuid",
        (binding,),
    ).fetchone() == (1,)
    assert db.execute(
        "select id::text, first_import_id::text, raw_line"
        " from public.business_bank_lines where id = %s::uuid",
        (line_id,),
    ).fetchone() == (line_id, import_id, {"synthetic": True})


def test_a_grant_can_read_and_authenticated_cannot_delete(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    other = users["other"]
    space_id = space(db, owner)
    account_id = account(db, owner, space_id)
    binding = _binding(db, space_id, account_id)
    import_id = _import(db, space_id, binding, owner)
    _line(db, space_id, binding, import_id, "e" * 64)
    policy = db.execute(
        "select qual from pg_policies where policyname = 'business_bank_lines_select'"
    ).fetchone()[0]
    assert "business_bank_has_capability" in policy
    definition = db.execute(
        "select pg_get_functiondef("
        "'argus_private.business_bank_has_capability(uuid, text)'::regprocedure)"
    ).fetchone()[0]
    assert "auth.uid()" in definition
    _grant(db, space_id, owner, ["read", "prepare"])
    with db.transaction(), db.cursor() as cursor:
        _as(cursor, owner)
        cursor.execute("select count(*) from public.business_bank_lines")
        assert cursor.fetchone()[0] == 1
    with db.transaction(), db.cursor() as cursor:
        _as(cursor, other)
        cursor.execute("select count(*) from public.business_bank_lines")
        assert cursor.fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
        with db.cursor() as cursor:
            _as(cursor, owner)
            cursor.execute("delete from public.business_bank_lines")

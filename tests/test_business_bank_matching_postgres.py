"""Business bank matching tables on real Postgres.

Proves the identity key, immutable raw lines, one confirmed suggestion per
line, one account per space, and grant-scoped reads. Skips without a
disposable database.
"""

from __future__ import annotations

import json

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


def test_one_confirmed_suggestion_is_rejected_on_insert(db, users) -> None:  # noqa: ANN001
    owner = users["owner"]
    space_id = space(db, owner)
    account_id = account(db, owner, space_id)
    binding = _binding(db, space_id, account_id)
    import_id = _import(db, space_id, binding, owner)
    line_id = _line(db, space_id, binding, import_id, "d" * 64)

    def confirm(target: str) -> None:
        db.execute(
            "insert into public.business_bank_suggestions ("
            " space_id, line_id, target_kind, target_id, status, amount_score,"
            " date_score, merchant_score, decided_at, decision_key)"
            " values (%s, %s, 'receipt', %s, 'confirmed', 1, 1, 0, now(), 'yes')",
            (space_id, line_id, target),
        )

    confirm("one")
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        confirm("two")


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

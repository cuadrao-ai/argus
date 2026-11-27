"""One normalized tax ID per open Business, including when installing the index."""

from pathlib import Path

import psycopg
import pytest
from faker import Faker
from psycopg import Connection

from tests import test_business_spaces_migration_postgres as spaces

db = spaces.db
users = spaces.users
pytestmark = spaces.pytestmark

INDEX = "spaces_open_business_rnc_uidx"
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase/migrations"
    / "20261127214124_open_business_rnc.sql"
)


def _set_tax_id(db: Connection, space_id: str, kind: str, digits: str) -> None:
    db.execute(
        "update public.spaces set business_tax_id_type=%s, business_rnc=%s where id=%s",
        (kind, digits, space_id),
    )


def test_duplicate_preflight_preserves_both_businesses_and_schema(
    db: Connection, users: dict[str, str], faker: Faker
) -> None:
    # Recreate the pre-migration state in a transaction the db fixture rolls back.
    db.execute(f"drop index if exists public.{INDEX}")
    db.execute(
        "revoke execute on function argus_private.business_rnc_digits(text) from service_role"
    )
    first = spaces.space(db, users["owner"])
    second = spaces.space(db, users["other"])
    digits = faker.numerify("1########")
    for business in (first, second):
        _set_tax_id(db, business, "rnc", digits)
    snapshot = "select * from public.spaces where id in (%s,%s) order by id"
    before = db.execute(snapshot, (first, second)).fetchall()
    with (
        pytest.raises(psycopg.errors.UniqueViolation, match="duplicate.*open Businesses"),
        db.transaction(),
    ):
        db.execute(MIGRATION.read_text())
    assert db.execute(snapshot, (first, second)).fetchall() == before
    assert db.execute("select to_regclass(%s)", (f"public.{INDEX}",)).fetchone() == (
        None,
    )
    assert not db.execute(
        "select has_function_privilege('service_role',"
        " 'argus_private.business_rnc_digits(text)', 'EXECUTE')"
    ).fetchone()[0]


@pytest.mark.parametrize(
    ("kind", "pattern"), [("rnc", "1########"), ("cedula", "00########1")]
)
def test_closed_business_releases_its_number_but_cannot_reopen_with_a_duplicate(
    db: Connection, users: dict[str, str], faker: Faker, kind: str, pattern: str
) -> None:
    first = spaces.owned_space(db, users["owner"])
    second = spaces.owned_space(db, users["other"])
    digits = faker.numerify(pattern)
    db.execute("set local role service_role")
    _set_tax_id(db, first, kind, digits)
    with pytest.raises(psycopg.errors.UniqueViolation, match=INDEX), db.transaction():
        _set_tax_id(db, second, kind, digits)
    db.execute("update public.spaces set closed_at=now() where id=%s", (first,))
    _set_tax_id(db, second, kind, digits)
    formatted = digits[:3] + "-" + digits[3:-1] + " " + digits[-1]
    assert db.execute(
        "select id::text from public.spaces where kind='business' and closed_at is null"
        " and business_rnc is not null and argus_private.business_rnc_digits(business_rnc)"
        " = argus_private.business_rnc_digits(%s)",
        (formatted,),
    ).fetchall() == [(second,)]
    with pytest.raises(psycopg.errors.UniqueViolation, match=INDEX), db.transaction():
        db.execute("update public.spaces set closed_at=null where id=%s", (first,))

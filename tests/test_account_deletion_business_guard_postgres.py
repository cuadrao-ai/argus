"""deletion_place_unit after 20261008140000 (Business spaces, M9).

Every unit of the Lane 6 world is placed twice, inside rolled-back
transactions: once with the previous function body read from
20261004090000, once with the current one. The results and rows match; a
unit holding a Business account raises ``business_account_in_copy``.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import psycopg
import pytest
from argus.domain.account_deletion.auth_admin import placeholder_email

from tests.household.financial_fixtures import DSN
from tests.household.financial_fixtures import lane as lane  # noqa: F401 - fixture
from tests.test_account_deletion_fk_census_postgres import (
    _invite_code_secret,  # noqa: F401 - autouse fixture (#794 invite codes)
)
from tests.test_account_deletion_postgres import (
    gotrue_admin_create,
    world,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase/migrations"

# Every table deletion_place_unit and deletion_rekey_binding write.
PLACED_TABLES = (
    "financial_accounts",
    "financial_activity_receipts",
    "financial_operation_receipts",
    "financial_observation_coverage",
    "financial_activity_groups",
    "financial_activity_revisions",
    "financial_records",
    "financial_record_revisions",
    "financial_activity_memberships",
    "financial_plan_links",
    "household_plan_archived_claims",
    "household_plan_archived_activities",
    "financial_goal_allocation_revisions",
    "financial_goal_allocations",
    "household_members",
    "household_plan_participants",
    "financial_plan_responsibilities",
    "household_plan_receipts",
    "household_plan_bindings",
    "financial_debt_plans",
)
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _place_unit_before_business_spaces() -> str:
    """The deletion_place_unit body 20261004090000 created, as a replacement."""
    text = (MIGRATIONS / "20261004090000_account_deletion.sql").read_text()
    start = text.index("create function argus_private.deletion_place_unit(")
    end = text.index("revoke all on function argus_private.deletion_place_unit")
    return "create or replace " + text[start + len("create ") : end]


def _placeholders_for_units(world) -> dict[tuple[str, str], str]:  # noqa: ANN001, F811
    with psycopg.connect(DSN) as c:
        units = c.execute(
            "select unit_kind, unit_id::text, scope_kind, scope_id::text"
            " from argus_private.deletion_placeholder_units(%s)",
            (world["a"],),
        ).fetchall()
    scopes = {(kind, scope): str(uuid.uuid4()) for _, _, kind, scope in units}
    for pid in scopes.values():
        with psycopg.connect(DSN) as c:
            c.execute(
                "insert into argus_private.account_placeholders (id) values (%s)", (pid,)
            )
        gotrue_admin_create(pid, placeholder_email(str(uuid.uuid4())))
        world["placeholders"].append(pid)
    return {(kind, unit): scopes[(sk, scope)] for kind, unit, sk, scope in units}


def _place_every_unit(world, units, *, body=None, business_account=None):  # noqa: ANN001, ANN202, F811
    """Run deletion_place_unit over A's units, the way the service orders them,
    in a transaction that is rolled back. Returns each unit's result and every
    row of the written tables that names A, B, C or a placeholder, with copied
    account ids replaced by their originals and fresh ids by a marker."""
    a = world["a"]
    people = [world["a"], world["b"], world["c"], *units.values()]
    with psycopg.connect(DSN) as c:
        try:
            if body:
                c.execute(body)
            if business_account:
                space = c.execute(
                    "insert into public.spaces (kind, name, created_by)"
                    " values ('business', 'Colmado', %s) returning id",
                    (a,),
                ).fetchone()[0]
                c.execute(
                    "update public.financial_accounts set owner_space_id = %s where id = %s",
                    (space, business_account),
                )
            known = set(UUID_TEXT.findall(json.dumps(_rows_naming(c, people))))
            c.execute(
                "select set_config('argus.locked_history_writer', 'deletion', true)"
            )
            results = {
                unit: c.execute(
                    "select argus_private.deletion_place_unit(%s, %s, %s, %s)",
                    (a, unit[0], unit[1], pid),
                ).fetchone()[0]
                for unit, pid in sorted(
                    units.items(), key=lambda i: (i[0][0] != "group", i[0])
                )
            }
            copies = {
                str(new): f"copy-of-{old}"
                for old, new in c.execute(
                    "select old_id, new_id from pg_temp.deletion_id_map"
                ).fetchall()
            }
            now = c.execute("select to_jsonb(now()) #>> '{}'").fetchone()[0]
            rows = []
            for row in _rows_naming(c, people):
                text = row.replace(now, "NOW")
                text = UUID_TEXT.sub(
                    lambda m: copies.get(m[0], m[0] if m[0] in known else "fresh"), text
                )
                rows.append(text)
            return results, sorted(rows), sorted(copies.values())
        finally:
            c.rollback()


def _rows_naming(c, people) -> list[str]:  # noqa: ANN001
    rows = []
    for table in PLACED_TABLES:
        rows += [
            f"{table} {r[0]}"
            for r in c.execute(
                f"select to_jsonb(t)::text from public.{table} t"
                " where to_jsonb(t)::text ~ %s",
                ("|".join(people),),
            ).fetchall()
        ]
    return rows


def test_place_unit_is_unchanged_for_personal_accounts(lane, world):  # noqa: F811
    units = _placeholders_for_units(world)
    before = _place_every_unit(world, units, body=_place_unit_before_business_spaces())
    after = _place_every_unit(world, units)
    results, rows, copies = after
    assert copies, "no unit copied an account; the comparison would be empty"
    assert any(results.values())
    assert any("copy-of-" in row for row in rows)
    assert after == before


def test_place_unit_refuses_to_copy_a_business_account(lane, world):  # noqa: F811
    units = _placeholders_for_units(world)
    _, _, copies = _place_every_unit(world, units)
    copied = [label.removeprefix("copy-of-") for label in copies]
    with pytest.raises(psycopg.errors.RaiseException, match="business_account_in_copy"):
        _place_every_unit(world, units, business_account=copied[0])
